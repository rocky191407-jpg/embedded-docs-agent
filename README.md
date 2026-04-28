# Embedded Docs Agent

A retrieval-augmented Agent for embedded systems engineering — answer "how do I implement priority-inheritance Mutex on Motorola 68000?" with cited sources from RTOS course materials, ARM reference manuals, FreeRTOS docs, and 3GPP NB-IoT specs.

Built as the AI-side portfolio piece of an embedded systems MSc (Newcastle, 2026) — bridges low-level systems knowledge (RTOS / IoT / FPGA) with LLM tool-use and RAG.

## Why this exists

Most LLM assistants stumble on embedded questions because:
1. Their training data is heavy on web/cloud, light on bare-metal & RTOS internals
2. They don't cite — and embedded engineers need exact register names / spec section numbers
3. They don't know your course materials, your codebase, your hardware

This Agent fixes those by:
- **RAG** over a curated embedded corpus (course slides, ARM manuals, RFCs)
- **Tool use** to call out to GCC, objdump, qemu-system-arm when the answer requires running code
- **Source-cited** answers — every claim links back to chunk + page

## Demo

```bash
$ python -m src.agent "如何在 68000 汇编里实现优先级继承的 Mutex？"

[retrieving...]
  ▸ EEE8087 §4.2 TCB Design (chunk 12)
  ▸ FreeRTOS source mutex.c L120 (chunk 31)
  ▸ ARM AAPCS Priority Inheritance white-paper (chunk 7)

[answer]
1. Add `priority_original` and `priority_inherited` fields to your TCB struct (see EEE8087 §4.2)...
2. On `mutex_lock()`, if a higher-priority task is blocked on a lower-priority holder, raise the holder's
   priority to match the blocker's — temporarily — until release (FreeRTOS pattern)...

[full code example, sources, follow-up questions]
```

Web demo: (link added Day 7)

## Architecture

```
                      ┌──────────────┐
   user query ───────▶│   agent.py   │──┐
                      └──────────────┘  │
                              │          │ tool call
                              ▼          ▼
                      ┌──────────────┐  ┌──────────────┐
                      │ retriever.py │  │   tools.py   │
                      │ (Chroma RAG) │  │ (GCC/dump)   │
                      └──────────────┘  └──────────────┘
                              │                │
                              └─── llm.py ─────┘
                                  (Claude API)
```

## Status

Day 1 of 10 — scaffolding.

See [TODO.md](TODO.md) for the build plan and progress.

## Setup

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows
pip install -r requirements.txt
cp .env.example .env             # add ANTHROPIC_API_KEY
python -m src.agent "How does Round-Robin scheduling work?"
```

## Author

Wang Ruoqi — MSc Embedded Systems & IoT, Newcastle University (2026).
[github.com/rocky191407-jpg](https://github.com/rocky191407-jpg)
