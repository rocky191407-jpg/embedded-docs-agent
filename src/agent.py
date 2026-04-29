"""Agent: glue retriever + LLM + tool handlers into an end-to-end loop.

Usage:
    python -m src.agent "How does my RTOS handle priority inversion?"
    python -m src.agent --interactive

Architecture:
    user query -> retrieve top-K chunks -> ask LLM with chunks
                                              |
                                              v
                                      stop_reason?
                                       |          \\
                                  end_turn       tool_use
                                       |              |
                                    print          dispatch
                                                  to handler
                                                      |
                                                  feed result
                                                  back, re-ask
"""
from __future__ import annotations

import argparse
import os
import sys
from typing import Any

# Force UTF-8 on Windows console
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

from anthropic.types import MessageParam
from rich import print as rprint
from rich.console import Console
from rich.markdown import Markdown
from rich.rule import Rule

from src.llm import EmbeddedDocsLLM
from src.retriever import retrieve
from src.tools import TOOL_HANDLERS

MAX_TOOL_LOOPS = 8


# ── Agent loop ───────────────────────────────────────────────────────────────

def run_turn(
    llm: EmbeddedDocsLLM,
    user_message: str,
    chunks: list[dict[str, Any]],
    history: list[MessageParam],
    console: Console,
) -> tuple[str, list[MessageParam]]:
    """Run one user turn: retrieve, ask, handle tool calls until end_turn.

    Returns (final_text, updated_history).
    """
    current_user_msg: str | list[dict] = user_message

    for loop_i in range(MAX_TOOL_LOOPS):
        resp = llm.ask(
            user_message=current_user_msg,
            retrieved_chunks=chunks,
            history=history,
        )
        u = resp.usage
        rprint(
            f"[dim]    [turn {loop_i+1}] stop={resp.stop_reason} "
            f"in={u.input_tokens} out={u.output_tokens} "
            f"cache_r={u.cache_read_input_tokens} cache_w={u.cache_creation_input_tokens}[/]"
        )

        # Append the user turn we just sent + the assistant response to history
        history.append({"role": "user", "content": current_user_msg})
        history.append({"role": "assistant", "content": resp.content})

        if resp.stop_reason == "end_turn":
            text_parts = [b.text for b in resp.content if b.type == "text"]
            return "\n".join(text_parts), history

        if resp.stop_reason == "tool_use":
            tool_results = []
            for block in resp.content:
                if block.type != "tool_use":
                    continue
                rprint(f"[yellow]    -> tool {block.name}({block.input})[/]")
                handler = TOOL_HANDLERS.get(block.name)
                if handler is None:
                    result = f"(unknown tool: {block.name})"
                    is_error = True
                else:
                    try:
                        result = handler(block.input)
                        is_error = False
                    except Exception as e:
                        result = f"tool error: {e}"
                        is_error = True
                tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": result,
                        "is_error": is_error,
                    }
                )
            # Next iteration sends tool results as the user turn
            current_user_msg = tool_results
            continue

        # Other stop reasons: pause_turn (server tools), refusal, max_tokens
        rprint(f"[red]    unexpected stop_reason: {resp.stop_reason}[/]")
        return f"(stopped: {resp.stop_reason})", history

    return "(max tool loops exceeded)", history


def ask(question: str, k: int = 5) -> str:
    """One-shot Q&A. Returns final answer text and prints to console."""
    console = Console()
    llm = EmbeddedDocsLLM()

    console.print(Rule(f"[bold cyan]Q:[/] {question}"))
    rprint(f"[dim]    retrieving k={k}...[/]")
    chunks = retrieve(question, k=k)
    for c in chunks:
        rprint(
            f"[dim]    chunk source={c['source']} idx={c['chunk_index']} score={c['score']:.3f}[/]"
        )

    final_text, _ = run_turn(llm, question, chunks, history=[], console=console)
    console.print(Rule("[bold green]Answer[/]"))
    console.print(Markdown(final_text))
    return final_text


def interactive() -> None:
    """Multi-turn REPL. Re-retrieves each turn; could be improved to keep chunks."""
    console = Console()
    llm = EmbeddedDocsLLM()
    history: list[MessageParam] = []

    rprint("[bold]Embedded Docs Agent[/] — type 'exit' or Ctrl+C to quit\n")
    while True:
        try:
            q = console.input("[bold cyan]you> [/]").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not q or q.lower() in {"exit", "quit"}:
            break
        chunks = retrieve(q, k=5)
        text, history = run_turn(llm, q, chunks, history, console)
        console.print(Markdown(text))
        console.print()


def main():
    parser = argparse.ArgumentParser(description="Embedded Docs Agent")
    parser.add_argument("question", nargs="?", help="One-shot question")
    parser.add_argument("--interactive", action="store_true", help="REPL mode")
    parser.add_argument("--k", type=int, default=5)
    args = parser.parse_args()

    if args.interactive:
        interactive()
    elif args.question:
        ask(args.question, k=args.k)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
