"""Eval runner: scores retrieval recall and answer keyword coverage.

Usage:
    python -m eval.runner                    # run all questions
    python -m eval.runner --no-llm           # retrieval-only (cheap, no API calls)
    python -m eval.runner --questions FILE   # custom YAML

Metrics:
    retrieval_recall@k:  fraction of questions where expected_src appears in top-k
    answer_keyword_hit:  fraction of expected_kw substrings present in answer
    tool_use_match:      fraction of expected tools that were actually called
    overall_score:       weighted mean (retrieval 0.4 / kw 0.4 / tools 0.2)

Design notes:
- We DON'T grade prose quality (would need an LLM judge — flaky + expensive).
- We DO grade factual coverage via keyword presence — strict but cheap.
- --no-llm mode skips the API entirely so you can iterate on chunking / embeddings
  without burning credits.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

import yaml
from rich.console import Console
from rich.table import Table

from src.retriever import retrieve

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_QUESTIONS = PROJECT_ROOT / "eval" / "questions.yaml"


@dataclass
class CaseResult:
    q: str
    retrieved_sources: list[str]
    retrieval_hit: bool | None  # None = no expected_src, skip metric
    answer: str | None
    keyword_hits: list[bool]
    expected_kw: list[str]
    tools_called: list[str]
    expected_tools: list[str]
    tool_hit: bool | None
    elapsed_s: float


def _retrieval_hit(retrieved: list[str], expected: list[str]) -> bool:
    """Pass if EVERY expected substring appears in any retrieved source."""
    return all(any(e in r for r in retrieved) for e in expected)


def _kw_hits(text: str, kws: list[str]) -> list[bool]:
    low = text.lower()
    return [kw.lower() in low for kw in kws]


def run_case(case: dict, k: int, use_llm: bool, llm=None, agent_run=None) -> CaseResult:
    t0 = time.monotonic()
    q = case["q"]
    expected_src = case.get("expected_src", []) or []
    expected_kw = case.get("expected_kw", []) or []
    expected_tools = case.get("tools", []) or []

    # Retrieval phase
    chunks = retrieve(q, k=k)
    retrieved_sources = [c["source"] for c in chunks]
    retrieval_hit = _retrieval_hit(retrieved_sources, expected_src) if expected_src else None

    answer: str | None = None
    keyword_hits: list[bool] = []
    tools_called: list[str] = []
    tool_hit: bool | None = None

    if use_llm and (expected_kw or expected_tools):
        from src.llm import EmbeddedDocsLLM
        from src.tools import TOOL_HANDLERS

        llm = llm or EmbeddedDocsLLM()
        history = []
        current_user_msg = q
        max_loops = 6
        text_parts: list[str] = []
        for _ in range(max_loops):
            resp = llm.ask(user_message=current_user_msg, retrieved_chunks=chunks, history=history)
            history.append({"role": "user", "content": current_user_msg})
            history.append({"role": "assistant", "content": resp.content})

            if resp.stop_reason == "tool_use":
                tool_results = []
                for block in resp.content:
                    if block.type != "tool_use":
                        continue
                    tools_called.append(block.name)
                    handler = TOOL_HANDLERS.get(block.name)
                    try:
                        result = handler(block.input) if handler else f"(unknown {block.name})"
                        is_err = handler is None
                    except Exception as e:
                        result = f"tool error: {e}"
                        is_err = True
                    tool_results.append(
                        {"type": "tool_result", "tool_use_id": block.id, "content": result, "is_error": is_err}
                    )
                current_user_msg = tool_results
                continue

            text_parts.extend(b.text for b in resp.content if b.type == "text")
            break

        answer = "\n".join(text_parts)
        keyword_hits = _kw_hits(answer, expected_kw)
        if expected_tools:
            tool_hit = all(t in tools_called for t in expected_tools)

    return CaseResult(
        q=q,
        retrieved_sources=retrieved_sources,
        retrieval_hit=retrieval_hit,
        answer=answer,
        keyword_hits=keyword_hits,
        expected_kw=expected_kw,
        tools_called=tools_called,
        expected_tools=expected_tools,
        tool_hit=tool_hit,
        elapsed_s=time.monotonic() - t0,
    )


def summarize(results: list[CaseResult], console: Console) -> dict:
    table = Table(title="Eval Results", show_lines=False)
    table.add_column("#", style="dim", width=3)
    table.add_column("Question", max_width=50)
    table.add_column("Retr", justify="center")
    table.add_column("KW", justify="center")
    table.add_column("Tools", justify="center")
    table.add_column("s", justify="right")

    for i, r in enumerate(results, 1):
        retr = "-" if r.retrieval_hit is None else ("[green]✓[/]" if r.retrieval_hit else "[red]✗[/]")
        if r.expected_kw:
            kw_pass = sum(r.keyword_hits)
            kw_str = f"{kw_pass}/{len(r.expected_kw)}"
            if kw_pass == len(r.expected_kw):
                kw_str = f"[green]{kw_str}[/]"
            elif kw_pass == 0:
                kw_str = f"[red]{kw_str}[/]"
            else:
                kw_str = f"[yellow]{kw_str}[/]"
        else:
            kw_str = "-"
        if r.expected_tools:
            tool_str = "[green]✓[/]" if r.tool_hit else "[red]✗[/]"
        else:
            tool_str = "-"
        table.add_row(str(i), r.q[:50], retr, kw_str, tool_str, f"{r.elapsed_s:.1f}")

    console.print(table)

    # Aggregate
    retr_cases = [r for r in results if r.retrieval_hit is not None]
    kw_total = sum(len(r.expected_kw) for r in results)
    kw_pass = sum(sum(r.keyword_hits) for r in results)
    tool_cases = [r for r in results if r.tool_hit is not None]

    metrics = {
        "n_questions": len(results),
        "retrieval_recall@k": (sum(1 for r in retr_cases if r.retrieval_hit) / len(retr_cases))
        if retr_cases else None,
        "answer_keyword_hit": (kw_pass / kw_total) if kw_total else None,
        "tool_use_match": (sum(1 for r in tool_cases if r.tool_hit) / len(tool_cases))
        if tool_cases else None,
        "total_elapsed_s": sum(r.elapsed_s for r in results),
    }

    # Weighted overall
    parts = []
    if metrics["retrieval_recall@k"] is not None:
        parts.append(("retrieval", metrics["retrieval_recall@k"], 0.4))
    if metrics["answer_keyword_hit"] is not None:
        parts.append(("keywords", metrics["answer_keyword_hit"], 0.4))
    if metrics["tool_use_match"] is not None:
        parts.append(("tools", metrics["tool_use_match"], 0.2))
    if parts:
        wsum = sum(w for _, _, w in parts)
        score = sum(v * w for _, v, w in parts) / wsum
        metrics["overall_score"] = score

    console.print()
    console.print("[bold]Metrics:[/]")
    for k, v in metrics.items():
        if isinstance(v, float):
            console.print(f"  {k}: [cyan]{v:.3f}[/]")
        else:
            console.print(f"  {k}: {v}")

    return metrics


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--questions", type=Path, default=DEFAULT_QUESTIONS)
    parser.add_argument("--no-llm", action="store_true", help="Retrieval-only, no API calls")
    parser.add_argument("--k", type=int, default=5)
    parser.add_argument("--out", type=Path, default=PROJECT_ROOT / "eval" / "last_run.json")
    args = parser.parse_args()

    cases = yaml.safe_load(args.questions.read_text(encoding="utf-8"))
    console = Console()

    use_llm = not args.no_llm
    if not use_llm:
        console.print("[yellow]--no-llm mode: skipping API calls (retrieval only)[/]")

    results: list[CaseResult] = []
    for i, case in enumerate(cases, 1):
        console.print(f"[dim][{i}/{len(cases)}] {case['q'][:70]}[/]")
        results.append(run_case(case, k=args.k, use_llm=use_llm))

    metrics = summarize(results, console)

    args.out.write_text(
        json.dumps(
            {
                "metrics": metrics,
                "cases": [
                    {
                        "q": r.q,
                        "retrieved_sources": r.retrieved_sources,
                        "retrieval_hit": r.retrieval_hit,
                        "expected_kw": r.expected_kw,
                        "keyword_hits": r.keyword_hits,
                        "tools_called": r.tools_called,
                        "expected_tools": r.expected_tools,
                        "tool_hit": r.tool_hit,
                        "elapsed_s": round(r.elapsed_s, 2),
                    }
                    for r in results
                ],
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    console.print(f"\n[dim]Wrote {args.out}[/]")


if __name__ == "__main__":
    main()
