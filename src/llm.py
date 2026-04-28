"""Claude API wrapper for the Embedded Docs Agent.

Pattern: prompt-cached RAG + tool use on Sonnet 4.6.

Render order is tools → system → messages, and cache is a prefix match — any
byte change anywhere in the prefix invalidates everything after it. So we
arrange the prompt with stability decreasing left-to-right:

  [ tools (frozen)              ]  ← cache breakpoint via tools block
  [ system prompt (frozen)      ]  ← cache breakpoint #1 — system text block
  [ retrieved chunks block      ]  ← cache breakpoint #2 — first user msg
  [ prior turn history (varies) ]
  [ current user query (varies) ]

Why two breakpoints (not just on the chunks): the system+tools prefix is
cacheable across *every* request the agent ever makes; the chunks block is
cacheable across multi-turn conversations that retrieve the same chunks.
Different cache lifetimes, different breakpoints.

Cache hit verification: see usage.cache_read_input_tokens in the response.
If it's 0 across repeated identical-prefix requests, something is mutating
the prefix — most likely a non-deterministic chunk ordering or a timestamp
in the system prompt.
"""
from __future__ import annotations

import os
from typing import Any

import anthropic
from anthropic.types import MessageParam, ToolParam
from dotenv import load_dotenv

load_dotenv()

MODEL = os.getenv("CLAUDE_MODEL", "claude-sonnet-4-6")
MAX_TOKENS = 8192


SYSTEM_PROMPT = """You are an expert embedded-systems engineer's assistant.

Specialties: RTOS internals, ARM Cortex-M / Motorola 68000 architecture, FreeRTOS,
3GPP NB-IoT, M2M / IoT communication, FPGA / VHDL design, Linux device drivers.

Behavior rules:
- ALWAYS cite which retrieved chunk a fact came from using [chunk N] notation.
- Show concrete code examples (assembly, C, VHDL) when explaining mechanisms.
- If the retrieved chunks don't answer the question, say so explicitly and call
  the search_docs tool to look harder. Do NOT guess.
- Use format_assembly to validate any non-trivial assembly you produce.
- Use lookup_register for ARM Cortex-M peripheral registers — names like NVIC_ISER,
  SYST_RVR, SCB_VTOR — instead of relying on memory.

Style: terse, source-cited, code-heavy. No marketing fluff, no hedging filler."""


# ── Tools ────────────────────────────────────────────────────────────────────

TOOLS: list[ToolParam] = [
    {
        "name": "search_docs",
        "description": (
            "Semantic search over the embedded systems doc corpus. Use when the "
            "initial retrieval missed the right chunks, or when the user asks a "
            "follow-up that needs different context."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query"},
                "k": {
                    "type": "integer",
                    "description": "Top-K to return",
                    "default": 5,
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "lookup_register",
        "description": (
            "Look up an ARM Cortex-M peripheral register definition by name "
            "(e.g. NVIC_ISER, SYST_RVR, SCB_VTOR). Returns base address, "
            "field layout, and reset value."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Register name"},
            },
            "required": ["name"],
        },
    },
    {
        "name": "format_assembly",
        "description": (
            "Assemble a small snippet using m68k-elf-as or arm-none-eabi-as to "
            "verify syntax. Returns the assembler's stdout/stderr and exit code."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "code": {"type": "string", "description": "Assembly source"},
                "arch": {
                    "type": "string",
                    "enum": ["m68k", "arm-cortex-m"],
                    "default": "arm-cortex-m",
                },
            },
            "required": ["code"],
        },
    },
]


# ── Chunk formatting ─────────────────────────────────────────────────────────

def _format_chunks(chunks: list[dict[str, Any]]) -> str:
    """Render retrieved chunks deterministically so cache keys are stable.

    Caller MUST pass chunks in a stable order (e.g. sorted by score desc, then
    by source+page asc). If order varies between calls with the same chunk set,
    the cache won't hit — the rendered string differs byte-for-byte.
    """
    if not chunks:
        return "(no chunks retrieved — answer from general knowledge if confident, else call search_docs)"
    parts = []
    for i, c in enumerate(chunks, 1):
        src = c.get("source", "unknown")
        page = c.get("page", "?")
        text = c.get("text", "").rstrip()
        parts.append(f"[chunk {i}] source={src} page={page}\n{text}")
    return "\n\n---\n\n".join(parts)


# ── LLM wrapper ──────────────────────────────────────────────────────────────

class EmbeddedDocsLLM:
    """One-call wrapper. Caller drives the tool-use loop in agent.py."""

    def __init__(self, model: str = MODEL):
        self.client = anthropic.Anthropic()
        self.model = model

    def ask(
        self,
        user_message: str,
        retrieved_chunks: list[dict[str, Any]],
        history: list[MessageParam] | None = None,
    ) -> anthropic.types.Message:
        """Single API round-trip.

        Args:
            user_message: the current user turn (str).
            retrieved_chunks: list of dicts with keys source/page/text. Caller
                handles deduplication/ordering.
            history: prior MessageParam list (may include tool_use/tool_result
                blocks from earlier turns). Pass None for the first turn.

        Returns:
            anthropic.types.Message — caller checks .stop_reason for "tool_use"
            and dispatches to tool handlers, then re-calls .ask() with updated
            history.
        """
        history = history or []
        chunk_block = _format_chunks(retrieved_chunks)

        messages: list[MessageParam] = [
            # First user message holds the retrieved-chunk context. Cache
            # breakpoint here means follow-up turns reuse this block at ~10%
            # cost when the same chunks come back from the retriever.
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": f"Retrieved context for this conversation:\n\n{chunk_block}",
                        "cache_control": {"type": "ephemeral"},
                    },
                ],
            },
            {
                "role": "assistant",
                "content": "Context loaded. I'll cite chunks by [chunk N] and call tools when needed.",
            },
            *history,
            {"role": "user", "content": user_message},
        ]

        return self.client.messages.create(
            model=self.model,
            max_tokens=MAX_TOKENS,
            system=[
                {
                    "type": "text",
                    "text": SYSTEM_PROMPT,
                    "cache_control": {"type": "ephemeral"},
                },
            ],
            tools=TOOLS,
            thinking={"type": "adaptive"},
            output_config={"effort": "medium"},
            messages=messages,
        )


# ── Smoke test ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    """Run: python -m src.llm

    Verifies ANTHROPIC_API_KEY works and prints token / cache usage.
    """
    llm = EmbeddedDocsLLM()
    resp = llm.ask(
        user_message="In one paragraph: what is priority inversion in an RTOS, and how does priority inheritance fix it?",
        retrieved_chunks=[],
    )
    for block in resp.content:
        if block.type == "text":
            print(block.text)
        elif block.type == "thinking":
            # adaptive thinking returns thinking blocks first; skip in smoke test
            pass
        elif block.type == "tool_use":
            print(f"\n[tool_use requested] {block.name}({block.input})")

    u = resp.usage
    print(
        f"\n[usage] stop={resp.stop_reason} "
        f"input={u.input_tokens} output={u.output_tokens} "
        f"cache_read={u.cache_read_input_tokens} cache_write={u.cache_creation_input_tokens}"
    )


__all__ = ["EmbeddedDocsLLM", "TOOLS", "SYSTEM_PROMPT", "MODEL", "MAX_TOKENS"]
