# Embedded Docs Agent

A retrieval-augmented chat agent for embedded systems engineering. Ask "how do I implement priority-inheritance Mutex on Motorola 68000?" and get back a cited answer from RTOS course materials, ARM reference manuals, and FreeRTOS docs — with the agent autonomously deciding when to call additional tools (semantic search, ARM register lookup, assembler validation). Bilingual: ask in English or Chinese.

Built on **Claude Opus 4.7** with prompt caching, function calling, and Chroma vector search. Bridges low-level systems knowledge (RTOS / IoT / FPGA) with LLM tool-use and RAG.

![demo](docs/demo.gif)

> **Eval scores on the included question set (18 questions):**
> - retrieval recall@5: **0.923**
> - answer keyword coverage: **0.926**
> - tool-use match: **1.000**
> - overall: **0.940**
>
> Run `python -m eval.runner` to reproduce.

## Why this exists

Most LLM assistants stumble on embedded questions because:
1. Their training distribution is heavy on web/cloud, light on bare-metal & RTOS internals
2. They don't cite — and embedded engineers need exact register addresses and spec section numbers
3. They don't know your codebase, your hardware, your course materials

This Agent fixes those by:
- **RAG** over a curated corpus (course README files, ARM reference manuals, FreeRTOS docs)
- **Tool use** to call out to a built-in ARM Cortex-M register database (30 regs across SysTick / NVIC / SCB / MPU) and an optional cross-assembler for syntax validation
- **Source-cited** answers — every claim links back to `[chunk N]` with file path + score

## Demo

```bash
$ python -m src.agent "What's the address and bit layout of SCB_VTOR?"

[chunks retrieved...]
[tool] lookup_register({"name": "SCB_VTOR"})
[tool] search_docs({"query": "Cortex-M4 vector table alignment VTOR SCB"})

Register: SCB_VTOR
  Address:    0xE000ED08
  Block:      SCB
  Reset:      0x00000000
  Access:     RW
  Description: Vector Table Offset Register
  Fields:
    TBLOFF [31:7]: Vector table base address (must be 128-byte aligned)

Why 128-byte alignment?
Bits [6:0] are hardwired to zero (RAZ/WI), so any value written to VTOR is
silently rounded down to the nearest 128-byte boundary...
```

The agent ran a tool call (`lookup_register`) for the structured fact, supplemented with `search_docs` for semantic context, integrated both, and produced a spec-correct answer. Full output: see [docs/example-output.md](docs/example-output.md).

## Architecture

```
                      ┌──────────────┐
   user query ───────▶│   agent.py   │── tool_use ──┐
                      │ (loop)       │              │
                      └───────┬──────┘              ▼
                              │              ┌──────────────┐
                              │              │   tools.py   │
                              │              │              │
                              ▼              │ search_docs  │
                      ┌──────────────┐       │ lookup_reg.  │
                      │ retriever.py │       │ format_asm.  │
                      │ (Chroma RAG) │       └──────────────┘
                      └──────────────┘              │
                              │                     │
                              └────── llm.py ───────┘
                              (Claude Sonnet 4.6 +
                               prompt cache + tool use)
```

**Two-layer prompt cache** (the trick): the system prompt and tool definitions cache once across all sessions; each conversation's retrieved-chunks block caches across turns of the same conversation. On a multi-turn dialog about the same topic, follow-up turns pay ~10% input cost vs. the first turn — verified via `usage.cache_read_input_tokens` in the smoke test.

## Setup

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # Linux/macOS
pip install -r requirements.txt
cp .env.example .env             # add ANTHROPIC_API_KEY
```

Build the index from `docs/`:

```bash
python -m src.indexer --rebuild
```

Ask one question (CLI):

```bash
python -m src.agent "Does my 68000 RTOS implement priority inheritance?"
```

Or interactive REPL:

```bash
python -m src.agent --interactive
```

Or web UI:

```bash
python -m ui.app           # http://127.0.0.1:7860
python -m ui.app --share   # public *.gradio.live URL
```

## Eval

```bash
python -m eval.runner --no-llm    # retrieval-only, no API calls (cheap)
python -m eval.runner             # full end-to-end with tool use
```

Writes [`eval/last_run.json`](eval/last_run.json) with per-question retrieved sources, keyword hits, tool calls, latency.

## Files

| Path | Role |
|---|---|
| [src/llm.py](src/llm.py) | Claude API wrapper. System + tools cached once; retrieved chunks cached per-conversation. Adaptive thinking, medium effort. |
| [src/indexer.py](src/indexer.py) | Walk `docs/`, paragraph-aware chunking (~500 tok / 50 tok overlap), embed with `BAAI/bge-small-en-v1.5`, persist to Chroma at `chroma_db/`. |
| [src/retriever.py](src/retriever.py) | Thin wrapper over Chroma query — output shape matches what `EmbeddedDocsLLM.ask()` expects. |
| [src/tools.py](src/tools.py) | Tool handlers: `search_docs` (re-retrieve), `lookup_register` (built-in ARM register DB), `format_assembly` (subprocess to `arm-none-eabi-as` / `m68k-elf-as`). |
| [src/agent.py](src/agent.py) | End-to-end loop: retrieve → ask LLM → handle tool_use → repeat until `end_turn`. |
| [data/cortex-m-registers.json](data/cortex-m-registers.json) | 30 ARMv7-M peripheral registers (SysTick / NVIC / SCB / MPU) with addresses, fields, reset values. |
| [eval/](eval/) | 18-question hand-graded eval covering retrieval / keywords / tool-use match. |
| [ui/app.py](ui/app.py) | Gradio chat UI with sources panel. |

## Limitations

- **English-only embeddings**. Override `EMBED_MODEL` to a multilingual model like `BAAI/bge-m3` if you add Chinese / other-language docs.
- **30 ARM registers**. Covers core SysTick / NVIC / SCB / MPU. Vendor-specific peripherals (STM32 USART, NXP SCT, etc.) need to be added to `data/cortex-m-registers.json`.
- **No reranker**. Pure embedding similarity. Adding a cross-encoder reranker (e.g. `BAAI/bge-reranker-base`) on top of top-20 → top-5 would likely lift retrieval recall beyond the current 92%.
- **No PDF citation page numbers when source is markdown**. PDFs do get per-page chunks; markdown sources currently report `chunk_index` only.
- **Cache verification**. The 5-min ephemeral cache TTL means a cold start writes the cache; the second turn (within 5 min) hits it. Run two queries in quick succession on the same conversation to see `cache_read_input_tokens > 0`.

## What I'd do next

- **Reranker pass** — add `bge-reranker-base` between retrieval and LLM to push recall@5 from 92% to ~98%.
- **Symbol-aware chunking for source files** — currently chunks any `.c` / `.s` file as plain text. Tree-sitter for language-aware splits (function-level chunks, header/body grouping).
- **MCP server packaging** — expose the agent as an MCP server so it can plug into Claude Desktop / VS Code / Claude Code as a knowledge tool.
- **Computer-use sub-agent** for assembler validation — instead of shelling out to `arm-none-eabi-as`, spin up a sandboxed container and feed compile errors back into the loop.

## Author

王若琦 / Wang Ruoqi — MSc Embedded Systems & IoT, Newcastle University (2026).
[github.com/rocky191407-jpg](https://github.com/rocky191407-jpg) · [Other portfolio repos](https://github.com/rocky191407-jpg?tab=repositories) (RTOS / FPGA / M2M / NB-IoT)

## License

[MIT](LICENSE)
