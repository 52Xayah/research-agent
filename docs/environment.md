# Windows 开发环境

## 安装与检查

在项目根目录打开 PowerShell。已有可用的 Python 3.12 虚拟环境时可以直接复用。新环境先执行 `py -3.12 -m venv .venv`。

```powershell
.\.venv\Scripts\python.exe -m pip install -e .
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -X utf8 -m research_agent doctor
```

项目运行时只使用 Python 标准库。可编辑安装需要构建工具，首次安装可能需要从配置的 Python 软件包镜像下载。安装后也可使用 `.\.venv\Scripts\research-agent.exe doctor`。

启动 Ollama 并确保模型已经安装。可运行 `ollama list` 查看模型，缺少默认模型时可运行 `ollama pull qwen3.5:4b`。默认地址为 `http://localhost:11434`。用以下命令验证一次真实推理。

```powershell
.\.venv\Scripts\python.exe -X utf8 -B .\test_ollama.py
```

## 配置

[.env.example](../.env.example) 记录配置名和默认值。程序读取进程环境变量。在 PowerShell 中可以为当前会话设置 `$env:RESEARCH_OLLAMA_MODEL = 'qwen3.5:4b'`，其余变量同理。超时单位为秒，上下文和最大生成长度以 Token 为单位。

## Git

提交前使用 `git status --short` 核对文件。Git 忽略虚拟环境、Python 缓存、构建产物和本地 `.env`，配置示例可以提交。使用 `git config --get user.name` 和 `git config --get user.email` 检查现有提交身份。
