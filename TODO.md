# Embedded Docs Agent — 10 天开发计划

## Day 1 — 项目骨架 + 数据收集（4-6h）

- [x] 仓库目录结构 + README + LICENSE + .gitignore
- [x] requirements.txt + .env.example
- [ ] 创建 GitHub repo（`gh repo create rocky191407-jpg/embedded-docs-agent --public --source=. --push`）
- [ ] 安装 deps：`python -m venv .venv && .venv\Scripts\activate && pip install -r requirements.txt`
- [ ] 申请 / 拷贝 Anthropic API key 到 `.env`
- [ ] 收集 3-5 份起步文档放进 `docs/`：
    - `docs/newcastle/EEE8087-rtos-notes.md` — 你 RTOS 课件笔记摘录（自己写 / 抓课件）
    - `docs/freertos/FreeRTOS-Reference.pdf` — 官方下载
    - `docs/arm/Cortex-M4-Generic-User-Guide.pdf` — ARM 官方
    - `docs/nbiot/3GPP-TS36.300-summary.md` — 你毕业论文用的 NB-IoT 规范摘录
- [ ] 写一个 `src/llm.py` smoke test：调一次 Claude API，打印响应

## Day 2 — 文档分块 + embedding + 向量库

- [ ] `src/indexer.py`：
    - 读 `docs/` 下所有 `.md` `.pdf` `.txt`
    - 分块（500-800 token，10% overlap）
    - 用 sentence-transformers 算 embedding
    - 存到 Chroma 持久化目录
- [ ] CLI: `python -m src.indexer --rebuild` 重建索引
- [ ] CLI: `python -m src.indexer --query "RTOS scheduling"` 测试 top-k 检索

## Day 3 — 基础 RAG pipeline

- [ ] `src/retriever.py`：query → embed → Chroma top-5 → 返回带 metadata 的 chunks
- [ ] `src/agent.py`：
    - 接 user query
    - 调 retriever 拿 chunks
    - 拼成 prompt 调 Claude
    - 输出回答 + 引用源
- [ ] CLI: `python -m src.agent "<问题>"` 跑通
- [ ] 测 5 个真实问题，看引用准不准

## Day 4 — 升级到 Tool Use（不只是 RAG）

- [ ] `src/tools.py`：定义工具
    - `search_docs(query, k=5)` — 文档检索（让 LLM 自己决定何时检索）
    - `lookup_arm_register(name)` — 给个寄存器名返回手册 entry
    - `format_assembly(code)` — 调 m68k-elf-as 或 arm-none-eabi-as 验证语法
- [ ] `src/agent.py` 改用 Claude function calling
- [ ] 多轮：Agent 决策何时 retrieve、何时直接答、何时调工具

## Day 5 — 多轮对话 + 上下文管理

- [ ] `src/agent.py` 加 session 状态
- [ ] CLI: `python -m src.agent --interactive` 进入聊天模式
- [ ] 上下文窗口管理（>50k token 时压缩历史）

## Day 6 — Eval set

- [ ] `eval/questions.yaml`：20 个问题 + ground-truth source chunks
- [ ] `eval/runner.py`：跑全部问题，输出 retrieval recall@k + 回答相似度
- [ ] 在 README 贴出 metrics

## Day 7 — Gradio Web Demo

- [ ] `ui/app.py`：聊天界面，左边对话 / 右边引用源
- [ ] `python -m ui.app` 起本地服务
- [ ] 录 30s gif 放进 README

## Day 8 — README + 架构图

- [ ] 用 mermaid 画架构图
- [ ] README 加 Performance / Limitations / Future Work
- [ ] LICENSE / CONTRIBUTING / Acknowledgements

## Day 9 — CI

- [ ] `.github/workflows/test.yml`：每 push 跑 `eval/runner.py` 一次（轻量版，不调外部 API）
- [ ] `pyproject.toml` + ruff + black

## Day 10 — Deploy + 简历更新

- [ ] HuggingFace Spaces 部署一个公开 demo（可选）
- [ ] 把这个项目加进简历 [王若琦个人简历_修订.docx](C:/Users/rocky/Desktop/AI/jobs/cv/成品/CN/王若琦个人简历_修订.docx) 项目经历
- [ ] 重新生成 PDF + 替换 9 个未投投递包

## 注意事项

- 每天 commit + push（即使是 WIP），保留绿点连续性
- 提交信息：`feat:` / `fix:` / `docs:` 标准格式
- 不要写 `claude-code` / `Co-Authored-By: Claude` 之类（HR 看到可能扣分）
