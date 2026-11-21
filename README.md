# Research Agent

Research Agent 面向技术调研。用户提供研究主题，系统规划子任务，调用工具收集网页与文档资料，整理证据，最终生成带来源引用的 Markdown 报告。

## 当前进度

当前里程碑为 Phase 0，等待阶段确认。工作区已有 Python 3.12 虚拟环境和 [Ollama 验证脚本](test_ollama.py)。脚本已通过本地 `/api/chat` 接口调用 `qwen3.5:4b` 并返回中文回复。项目环境配置从 Phase 1 开始，模型能力和 Agent 功能按[开发路线](docs/roadmap.md)逐阶段验收。

## 目录

```text
research-agent/
├── README.md
├── docs/
│   ├── requirements.md
│   ├── architecture.md
│   ├── roadmap.md
│   └── tech-stack.md
├── test_ollama.py       # 现有本地模型验证脚本
├── .venv/               # 现有本地虚拟环境
└── .git/                # 本地 Git 仓库
```

## 运行现有验证脚本

在 Windows PowerShell 中进入项目根目录。运行前确认本地 Ollama 服务已启动，且已安装 `qwen3.5:4b`。

```powershell
.\.venv\Scripts\python.exe -X utf8 -B .\test_ollama.py
```

脚本会向模型发送一条中文提示，并输出回复。它是本地连通性验证入口，后续由 Phase 2 的模型能力测试覆盖多轮、流式、结构化输出与工具调用。

## 项目文档

- [需求与验收标准](docs/requirements.md)
- [系统架构与目录规划](docs/architecture.md)
- [15 个开发阶段与验收条件](docs/roadmap.md)
- [技术选型与本地资源策略](docs/tech-stack.md)
