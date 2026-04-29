"""Real tool implementations for the agent.

- search_docs:       semantic search over the indexed corpus (re-uses retriever)
- lookup_register:   ARM Cortex-M peripheral register database (built-in JSON)
- format_assembly:   shells out to arm-none-eabi-as / m68k-elf-as if installed

All tool handlers take a single dict (the unpacked tool_use input) and return
a string. is_error is set by the caller (agent.py) based on whether we raised.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from src.retriever import retrieve

PROJECT_ROOT = Path(__file__).resolve().parent.parent
REGISTER_DB = PROJECT_ROOT / "data" / "cortex-m-registers.json"


# ── search_docs ──────────────────────────────────────────────────────────────

def search_docs(query: str, k: int = 5) -> str:
    """Run an additional retrieval. Returns formatted chunks for the LLM to read."""
    chunks = retrieve(query, k=k)
    if not chunks:
        return "(no chunks found for that query — try different wording)"
    parts = []
    for i, c in enumerate(chunks, 1):
        parts.append(
            f"[chunk {i}] source={c['source']} chunk_index={c['chunk_index']} score={c['score']:.3f}\n{c['text']}"
        )
    return "\n\n---\n\n".join(parts)


# ── lookup_register ──────────────────────────────────────────────────────────

_REGISTER_CACHE: dict | None = None


def _load_registers() -> dict:
    global _REGISTER_CACHE
    if _REGISTER_CACHE is None:
        if not REGISTER_DB.exists():
            _REGISTER_CACHE = {}
        else:
            _REGISTER_CACHE = json.loads(REGISTER_DB.read_text(encoding="utf-8"))
    return _REGISTER_CACHE


def lookup_register(name: str) -> str:
    """Look up an ARM Cortex-M peripheral register by name (case-insensitive).

    Matches exact name first, then prefix, then substring.
    """
    db = _load_registers()
    if not db:
        return f"(register database not loaded — expected {REGISTER_DB})"

    name_u = name.upper().strip()
    keys = list(db.keys())

    # Exact match
    if name_u in db:
        r = db[name_u]
        return _format_register(name_u, r)

    # Prefix match
    pref = [k for k in keys if k.startswith(name_u)]
    if len(pref) == 1:
        return _format_register(pref[0], db[pref[0]])
    if pref:
        return f"Multiple matches for prefix '{name}': {', '.join(pref[:10])}\nNarrow your query."

    # Substring match
    sub = [k for k in keys if name_u in k]
    if len(sub) == 1:
        return _format_register(sub[0], db[sub[0]])
    if sub:
        return f"Multiple substring matches for '{name}': {', '.join(sub[:10])}\nNarrow your query."

    # No match — show neighbors for orientation
    return (
        f"No register named '{name}' in DB. Available registers: "
        f"{', '.join(keys[:20])}{'...' if len(keys) > 20 else ''}\n"
        f"DB covers SCB / NVIC / SysTick / MPU subset of ARMv7-M."
    )


def _format_register(name: str, r: dict) -> str:
    lines = [
        f"Register: {name}",
        f"  Address:    {r.get('address', '?')}",
        f"  Block:      {r.get('block', '?')}",
        f"  Reset:      {r.get('reset', '?')}",
        f"  Access:     {r.get('access', '?')}",
        f"  Description: {r.get('description', '?')}",
    ]
    fields = r.get("fields", {})
    if fields:
        lines.append("  Fields:")
        for fname, fdesc in fields.items():
            lines.append(f"    {fname}: {fdesc}")
    return "\n".join(lines)


# ── format_assembly ──────────────────────────────────────────────────────────

ARCH_TO_AS = {
    "arm-cortex-m": ("arm-none-eabi-as", ["-mcpu=cortex-m4", "-mthumb"]),
    "m68k": ("m68k-elf-as", ["-m68000"]),
}


def format_assembly(code: str, arch: str = "arm-cortex-m") -> str:
    """Assemble a snippet to verify syntax. Returns assembler stdout/stderr.

    If the cross-assembler isn't installed, returns a clear setup message
    rather than failing — the agent can then fall back to commenting on the
    code without claiming it was assembled.
    """
    if arch not in ARCH_TO_AS:
        return f"Unsupported arch: {arch}. Supported: {list(ARCH_TO_AS)}"

    asm_bin, default_args = ARCH_TO_AS[arch]
    asm_path = shutil.which(asm_bin)
    if asm_path is None:
        return (
            f"Assembler '{asm_bin}' not found on PATH.\n"
            f"To enable syntax checking for arch={arch}, install the cross-toolchain:\n"
            f"  arm-cortex-m: GNU Arm Embedded Toolchain (arm-none-eabi-gcc)\n"
            f"  m68k:         m68k-elf-gcc (build from binutils sources)\n"
            f"Skipping syntax check; the assistant should still review the code statically."
        )

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".S", delete=False, encoding="utf-8"
    ) as src:
        src.write(code)
        src_path = src.name

    try:
        result = subprocess.run(
            [asm_path, *default_args, src_path, "-o", os.devnull],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        if result.returncode == 0:
            return f"OK ({asm_bin}) — syntax valid for {arch}.\n{result.stderr.strip()}".strip()
        return (
            f"FAIL ({asm_bin}, exit={result.returncode}) for {arch}:\n"
            f"--- stderr ---\n{result.stderr.strip() or '(empty)'}\n"
            f"--- stdout ---\n{result.stdout.strip() or '(empty)'}"
        )
    except subprocess.TimeoutExpired:
        return f"Assembler timed out (>10s)."
    finally:
        try:
            os.unlink(src_path)
        except OSError:
            pass


# ── Dispatch table for agent.py ──────────────────────────────────────────────

TOOL_HANDLERS = {
    "search_docs": lambda inp: search_docs(**inp),
    "lookup_register": lambda inp: lookup_register(**inp),
    "format_assembly": lambda inp: format_assembly(**inp),
}


__all__ = ["TOOL_HANDLERS", "search_docs", "lookup_register", "format_assembly"]
