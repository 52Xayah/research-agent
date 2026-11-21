# Windows 本机部署与交付

## 安装

准备 Python 3.12 与 Ollama。首次配置时在项目根目录创建虚拟环境并安装所需功能。

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e '.[rag,app,test]'
.\.venv\Scripts\python.exe -m pip check
ollama pull qwen3.5:4b
```

系统默认使用现有 Ollama 聊天服务的 `11434` 端口。嵌入模型可在同一服务中安装，也可用项目自己的 `11435` 服务。下面是一组使用项目目录存放模型的步骤。

1. 在第一个 PowerShell 窗口运行 `.\scripts\start-local.ps1 -Service embedding`。
2. 首次准备嵌入模型时，在另一个窗口执行 `$env:OLLAMA_HOST = '127.0.0.1:11435'`，再执行 `ollama pull embeddinggemma`。
3. 在 API 窗口运行 `.\scripts\start-local.ps1 -Service api`。
4. 在界面窗口运行 `.\scripts\start-local.ps1 -Service ui`，然后打开 [研究台](http://127.0.0.1:8501)。

脚本支持 `-EmbeddingPort`、`-ApiPort` 和 `-UiPort`。共享聊天和嵌入服务时，在 API 窗口设置 `$env:RESEARCH_EMBED_URL = 'http://127.0.0.1:11434'`。使用 Ctrl+C 停止对应终端里的服务。单工作进程、持久状态、文件和队列限制见[本机应用](application.md)。

## 验收与构建

```powershell
.\.venv\Scripts\python.exe -X utf8 -B -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -X utf8 -B -m research_agent doctor
.\.venv\Scripts\python.exe -X utf8 -B -m research_agent agent-demo
.\.venv\Scripts\python.exe -X utf8 -B -m research_agent evaluate --output .research-agent\release-evaluation.json
.\.venv\Scripts\python.exe -m pip wheel --no-deps --wheel-dir dist .
```

单元测试和 wheel 构建可以脱离模型执行。评估使用真实模型。CI 定义在 [.github/workflows/ci.yml](../.github/workflows/ci.yml)，以 Windows 和 Python 3.12 安装依赖、运行单元测试并构建 wheel。GitHub 项目准备工作在本地完成。

## 优化与边界

复查请求会列出候选项各自的引用 ID，共享证据只传一次。本机使用 Qwen3.5 4B 对两条引用相同片段的结论复查，输入从 422 降到 293 Token，减少约 31%。旧请求和新请求均保留正确结论并拒绝错误结论。这是单次受控样例。保护提示会增加工具对话的输入量，整个研究流程的节省取决于共享证据比例。[压缩实测 JSON](../examples/evaluation/review-context.json) · [发布回归 JSON](../examples/evaluation/release-qwen-4b.json)

项目采用单机、单用户运行，资料缺口和模型判断记录在报告中。扫描 PDF 需要先做 OCR。联网资料来自配置的英文维基百科接口。对完成报告仍应核对引用和推理。
