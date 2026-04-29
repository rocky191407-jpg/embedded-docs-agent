"""Gradio chat UI for the Embedded Docs Agent.

Usage:
    python -m ui.app          # binds to http://127.0.0.1:7860
    python -m ui.app --share  # public *.gradio.live URL (for sharing the demo)

Layout:
    Left  — chat history (Markdown rendered)
    Right — collapsible "Sources" panel showing retrieved chunks per turn

State is per-session (Gradio's gr.State); reload the page to start over.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

import gradio as gr
from anthropic.types import MessageParam

from src.llm import EmbeddedDocsLLM
from src.retriever import retrieve
from src.tools import TOOL_HANDLERS

PROJECT_ROOT = Path(__file__).resolve().parent.parent
MAX_TOOL_LOOPS = 8

EXAMPLES = [
    "Does my 68000 RTOS implement priority inheritance?",
    "What's the address and bit layout of SCB_VTOR? Why 128-byte alignment?",
    "What FPGA codec did my audio FIR project use, and at what I2C clock speed?",
    "How do I trigger software interrupt IRQ12 on Cortex-M4?",
    "我的 68000 RTOS 实现了优先级继承吗？如果没有，怎么补?",
    "SCB_VTOR 寄存器的地址和位定义是什么？为什么需要 128 字节对齐?",
    "解释我 M2M 项目里 PID 控制器和 RTOS 调度器的区别。",
]


def _format_sources(chunks: list[dict]) -> str:
    if not chunks:
        return "_No retrieved chunks._"
    lines = []
    for i, c in enumerate(chunks, 1):
        lines.append(
            f"**[chunk {i}]** `{c['source']}` _(idx {c['chunk_index']}, score {c['score']:.3f})_"
        )
        preview = c["text"][:300].replace("\n", " ")
        lines.append(f"> {preview}{'...' if len(c['text']) > 300 else ''}")
        lines.append("")
    return "\n".join(lines)


def chat_fn(message: str, history: list, agent_history: list[MessageParam]):
    """One turn. history is gradio's [(user, assistant), ...]; agent_history is the
    canonical MessageParam list with tool_use blocks preserved."""
    if not message.strip():
        return "", history, agent_history, "_(empty query)_"

    llm = EmbeddedDocsLLM()
    chunks = retrieve(message, k=5)
    sources_md = _format_sources(chunks)

    current_user_msg: str | list[dict] = message
    final_text = ""

    for _ in range(MAX_TOOL_LOOPS):
        resp = llm.ask(
            user_message=current_user_msg,
            retrieved_chunks=chunks,
            history=agent_history,
        )
        agent_history.append({"role": "user", "content": current_user_msg})
        agent_history.append({"role": "assistant", "content": resp.content})

        if resp.stop_reason == "end_turn":
            text_parts = [b.text for b in resp.content if b.type == "text"]
            final_text = "\n".join(text_parts)
            break

        if resp.stop_reason == "tool_use":
            tool_results = []
            for block in resp.content:
                if block.type != "tool_use":
                    continue
                handler = TOOL_HANDLERS.get(block.name)
                try:
                    result = handler(block.input) if handler else f"(unknown tool: {block.name})"
                    is_err = handler is None
                except Exception as e:
                    result = f"tool error: {e}"
                    is_err = True
                tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": result,
                        "is_error": is_err,
                    }
                )
            current_user_msg = tool_results
            continue

        final_text = f"_(stopped: {resp.stop_reason})_"
        break

    history = history + [
        {"role": "user", "content": message},
        {"role": "assistant", "content": final_text},
    ]
    return "", history, agent_history, sources_md


def build_app() -> gr.Blocks:
    with gr.Blocks(title="Embedded Docs Agent") as app:
        gr.Markdown(
            "# Embedded Docs Agent\n"
            "_RAG + tool-use over RTOS / FPGA / IoT documentation. "
            "Built on Claude Sonnet 4.6._"
        )

        with gr.Row():
            with gr.Column(scale=2):
                chatbot = gr.Chatbot(
                    label="Conversation",
                    height=500,
                    # Gradio 6 defaults to messages dict format; data is now
                    # [{"role": "user|assistant", "content": "..."}, ...]
                )
                msg = gr.Textbox(
                    placeholder="Ask about RTOS, ARM Cortex-M, FPGA, NB-IoT...",
                    label="Your question",
                    lines=2,
                )
                with gr.Row():
                    submit = gr.Button("Send", variant="primary")
                    clear = gr.Button("Clear")
                gr.Examples(examples=EXAMPLES, inputs=msg, label="Example questions")
            with gr.Column(scale=1):
                gr.Markdown("### Retrieved sources")
                sources_box = gr.Markdown("_(no query yet)_")

        agent_state = gr.State([])  # canonical MessageParam history

        submit.click(chat_fn, [msg, chatbot, agent_state], [msg, chatbot, agent_state, sources_box])
        msg.submit(chat_fn, [msg, chatbot, agent_state], [msg, chatbot, agent_state, sources_box])
        clear.click(lambda: ([], [], "_(cleared)_"), None, [chatbot, agent_state, sources_box])

    return app


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--share", action="store_true", help="Create a public *.gradio.live URL")
    parser.add_argument("--port", type=int, default=7860)
    args = parser.parse_args()

    app = build_app()
    app.launch(
        server_port=args.port,
        share=args.share,
        inbrowser=True,
        theme=gr.themes.Soft(),
    )


if __name__ == "__main__":
    main()
