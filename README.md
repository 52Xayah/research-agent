# Research Agent

Research Agent 面向技术调研。用户提供研究主题，系统规划子任务，调用工具收集网页与文档资料，整理证据，最终生成带来源引用的 Markdown 报告。

## 当前进度

当前里程碑为 Phase 10。命令行可规划并恢复任务，检索本地 PDF、TXT 和 Markdown，或联网读取维基百科资料，生成带可追溯引用的 Markdown 报告。进度和实测记录见[开发路线](docs/roadmap.md)。

## 目录

```text
research-agent/
├── README.md
├── docs/
│   ├── requirements.md
│   ├── architecture.md
│   ├── environment.md
│   ├── function-calling.md
│   ├── model-capabilities.md
│   ├── research.md
│   ├── retrieval.md
│   ├── roadmap.md
│   ├── tech-stack.md
│   └── tools.md
├── src/research_agent/
│   ├── __main__.py
│   ├── agent/
│   ├── config.py
│   ├── function_demo.py
│   ├── llm/
│   ├── memory.py
│   ├── parameters.py
│   ├── rag/
│   ├── research/
│   └── tools/
├── examples/
├── tests/
├── pyproject.toml
├── .env.example
├── .gitignore
├── test_ollama.py       # 现有本地模型验证脚本
├── .venv/               # 现有本地虚拟环境
└── .git/                # 本地 Git 仓库
```

## 开发与实测

在 Windows PowerShell 中进入项目根目录，按[环境说明](docs/environment.md)准备 Python 3.12 虚拟环境。执行模型实测前启动本地 Ollama，并安装默认模型 `qwen3.5:4b`。

```powershell
.\.venv\Scripts\python.exe -m pip install -e .
.\.venv\Scripts\python.exe -X utf8 -B -m research_agent doctor
.\.venv\Scripts\python.exe -X utf8 -B -m research_agent model-check
.\.venv\Scripts\python.exe -X utf8 -B -m research_agent function-demo
.\.venv\Scripts\python.exe -X utf8 -B -m research_agent agent-demo
.\.venv\Scripts\python.exe -X utf8 -B -m unittest discover -s tests -v
```

原有 [test_ollama.py](test_ollama.py) 可独立运行一次中文聊天。完整的固定工具调用样例通过 `function-check` 执行。计算器与文档读取的样例见[工具系统](docs/tools.md)。

## 项目文档

- [Windows 环境配置与运行](docs/environment.md)
- [需求与验收标准](docs/requirements.md)
- [系统架构与目录规划](docs/architecture.md)
- [15 个开发阶段与验收条件](docs/roadmap.md)
- [技术选型与本地资源策略](docs/tech-stack.md)
- [本地模型能力实测](docs/model-capabilities.md)
- [Function Calling 协议与实测](docs/function-calling.md)
- [本地知识库与检索](docs/retrieval.md)
- [研究、历史与报告](docs/research.md)
