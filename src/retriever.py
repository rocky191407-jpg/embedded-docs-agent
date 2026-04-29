"""Retriever: thin wrapper over indexer.query().

Why a separate module: the agent doesn't care about Chroma internals or the
embedding model — it just wants chunks with {source, page, text, score} keys.
This is also where re-ranking, hybrid search, or query rewriting would live
if we needed them later.
"""
from __future__ import annotations

from typing import Any

from src.indexer import query as _query


def retrieve(question: str, k: int = 5) -> list[dict[str, Any]]:
    """Return the top-k chunks for a question, formatted for the LLM.

    Returns a list of dicts compatible with what EmbeddedDocsLLM.ask() expects:
      [{"source": "...", "page": "?", "text": "...", "score": 0.8}, ...]

    `page` is "?" for markdown/text sources and an integer-string for PDFs
    where the indexer kept page boundaries in the [PAGE N] header.
    """
    raw = _query(question, k=k)
    out: list[dict[str, Any]] = []
    for r in raw:
        text = r["text"]
        page: str = "?"
        # Indexer prefixes PDF page chunks with "[PAGE N]\n"; lift it into metadata.
        if text.startswith("[PAGE "):
            try:
                page = text.split("]", 1)[0].removeprefix("[PAGE ").strip()
            except Exception:
                page = "?"
        out.append(
            {
                "source": r["source"],
                "page": page,
                "text": text,
                "score": r["score"],
                "chunk_index": r["chunk_index"],
            }
        )
    return out


__all__ = ["retrieve"]
