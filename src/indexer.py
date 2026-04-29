"""Indexer: walk docs/, chunk, embed, persist to Chroma.

Usage:
    python -m src.indexer --rebuild              # full rebuild
    python -m src.indexer --query "RTOS mutex"   # smoke-test retrieval

Design choices:
- One chunk per ~500 tokens with 10% overlap. Estimated by 4 chars/token —
  good enough; we don't need exact token counts here, only consistent sizing.
- Splits paragraphs first (\\n\\n boundaries), then packs into chunks.
  Never splits mid-sentence within a paragraph.
- Embedding model: BAAI/bge-small-en-v1.5 (33M params, 384-dim, CPU-fast).
  Override via EMBED_MODEL env var.
- Chroma persists at ./chroma_db (override via CHROMA_DIR).
- Source metadata: filename + chunk_index + char_offset for citations.
"""
from __future__ import annotations

import argparse
import hashlib
import os
import sys
from pathlib import Path
from typing import Iterator

# Force UTF-8 on Windows console so rich can emit unicode glyphs without
# choking on cp1252. Must run before rich touches stdout.
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

import chromadb
from dotenv import load_dotenv
from rich import print as rprint
from rich.console import Console
from rich.progress import track
from sentence_transformers import SentenceTransformer

load_dotenv()

# Resolve paths relative to project root (parent of src/) so the script works
# regardless of the cwd it's invoked from.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DOCS_DIR = Path(os.getenv("DOCS_DIR") or PROJECT_ROOT / "docs")
CHROMA_DIR = os.getenv("CHROMA_DIR") or str(PROJECT_ROOT / "chroma_db")
EMBED_MODEL_NAME = os.getenv("EMBED_MODEL", "BAAI/bge-small-en-v1.5")
COLLECTION_NAME = "embedded_docs"

CHARS_PER_TOKEN = 4  # rough English heuristic
CHUNK_TOKENS = 500
OVERLAP_TOKENS = 50
CHUNK_CHARS = CHUNK_TOKENS * CHARS_PER_TOKEN
OVERLAP_CHARS = OVERLAP_TOKENS * CHARS_PER_TOKEN

# Module-level model cache. Loading SentenceTransformer per-call also
# re-validates with the HuggingFace hub (httpx); after a few calls the
# httpx client gets closed and subsequent loads fail with
# "Cannot send a request, as the client has been closed". Load once.
_MODEL_CACHE: SentenceTransformer | None = None


def _get_model() -> SentenceTransformer:
    global _MODEL_CACHE
    if _MODEL_CACHE is None:
        _MODEL_CACHE = SentenceTransformer(EMBED_MODEL_NAME)
    return _MODEL_CACHE


def iter_docs(root: Path) -> Iterator[tuple[Path, str]]:
    """Yield (path, text) for every supported file under root."""
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        suffix = path.suffix.lower()
        try:
            if suffix in {".md", ".txt"}:
                text = path.read_text(encoding="utf-8", errors="ignore")
                if text.strip():
                    yield path, text
            elif suffix == ".pdf":
                from pypdf import PdfReader

                reader = PdfReader(str(path))
                for page_num, page in enumerate(reader.pages, 1):
                    page_text = page.extract_text() or ""
                    if page_text.strip():
                        # PDFs yield one (path, text) per page so chunk metadata
                        # can pin a citation to a page number.
                        yield path, f"[PAGE {page_num}]\n{page_text}"
        except Exception as e:
            rprint(f"[yellow]skip {path}: {e}[/]")


def chunk_text(text: str) -> list[str]:
    """Pack paragraphs into chunks of ~CHUNK_CHARS with OVERLAP_CHARS overlap.

    Why paragraph-first: respects natural document structure, keeps related
    sentences together. Never splits mid-paragraph unless a single paragraph
    exceeds CHUNK_CHARS — in that case we fall back to character split.
    """
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    chunks: list[str] = []
    current: list[str] = []
    current_len = 0

    for para in paragraphs:
        # Single oversized paragraph: hard-split by chars
        if len(para) > CHUNK_CHARS:
            if current:
                chunks.append("\n\n".join(current))
                current, current_len = [], 0
            for i in range(0, len(para), CHUNK_CHARS - OVERLAP_CHARS):
                chunks.append(para[i : i + CHUNK_CHARS])
            continue

        if current_len + len(para) > CHUNK_CHARS and current:
            chunks.append("\n\n".join(current))
            tail = current[-1]
            if len(tail) <= OVERLAP_CHARS:
                current = [tail, para]
                current_len = len(tail) + len(para)
            else:
                current = [tail[-OVERLAP_CHARS:], para]
                current_len = OVERLAP_CHARS + len(para)
        else:
            current.append(para)
            current_len += len(para) + 2

    if current:
        chunks.append("\n\n".join(current))

    return chunks


def get_collection(rebuild: bool = False):
    client = chromadb.PersistentClient(path=CHROMA_DIR)
    if rebuild:
        try:
            client.delete_collection(COLLECTION_NAME)
        except Exception:
            pass
    return client.get_or_create_collection(
        name=COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"},
    )


def chunk_id(source: str, idx: int, text: str) -> str:
    h = hashlib.md5(text.encode("utf-8")).hexdigest()[:8]
    return f"{Path(source).stem}__{idx:04d}__{h}"


def build_index(rebuild: bool = False) -> int:
    if not DOCS_DIR.exists():
        rprint(f"[red]docs dir missing: {DOCS_DIR.resolve()}[/]")
        return 0

    rprint(f"[cyan]Loading embedding model: {EMBED_MODEL_NAME}[/] (first run downloads ~130MB)")
    model = _get_model()

    coll = get_collection(rebuild=rebuild)

    docs: list[str] = []
    metadatas: list[dict] = []
    ids: list[str] = []

    for path, text in iter_docs(DOCS_DIR):
        rel = path.relative_to(DOCS_DIR.parent)
        for i, chunk in enumerate(chunk_text(text)):
            docs.append(chunk)
            metadatas.append(
                {"source": str(rel), "chunk_index": i, "char_count": len(chunk)}
            )
            ids.append(chunk_id(str(rel), i, chunk))

    if not docs:
        rprint("[yellow]No content to index.[/]")
        return 0

    rprint(f"[cyan]Embedding {len(docs)} chunks...[/]")
    BATCH = 32
    embeddings: list[list[float]] = []
    for i in track(range(0, len(docs), BATCH), description="embedding"):
        batch = docs[i : i + BATCH]
        vecs = model.encode(batch, normalize_embeddings=True, show_progress_bar=False)
        embeddings.extend(vecs.tolist())

    coll.upsert(ids=ids, documents=docs, embeddings=embeddings, metadatas=metadatas)
    rprint(f"[green]Indexed {len(docs)} chunks -> {CHROMA_DIR}[/]")
    return len(docs)


def query(text: str, k: int = 5) -> list[dict]:
    coll = get_collection(rebuild=False)
    if coll.count() == 0:
        rprint("[red]Index is empty. Run with --rebuild first.[/]")
        return []

    model = _get_model()
    vec = model.encode([text], normalize_embeddings=True).tolist()
    res = coll.query(query_embeddings=vec, n_results=k)

    out: list[dict] = []
    for doc, meta, dist in zip(res["documents"][0], res["metadatas"][0], res["distances"][0]):
        out.append(
            {
                "source": meta["source"],
                "chunk_index": meta["chunk_index"],
                "score": 1 - dist,
                "text": doc,
            }
        )
    return out


def main():
    parser = argparse.ArgumentParser(description="Embedded docs indexer")
    g = parser.add_mutually_exclusive_group(required=True)
    g.add_argument("--rebuild", action="store_true", help="Wipe and re-index docs/")
    g.add_argument("--query", type=str, help="Smoke-test retrieval with a query")
    parser.add_argument("--k", type=int, default=5, help="Top-K for --query")
    args = parser.parse_args()

    if args.rebuild:
        n = build_index(rebuild=True)
        sys.exit(0 if n > 0 else 1)
    elif args.query:
        results = query(args.query, k=args.k)
        if not results:
            sys.exit(1)
        console = Console()
        for r in results:
            console.rule(f"[bold]{r['source']}[/] chunk={r['chunk_index']} score={r['score']:.3f}")
            print(r["text"][:600] + ("..." if len(r["text"]) > 600 else ""))
            print()


if __name__ == "__main__":
    main()
