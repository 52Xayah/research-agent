# 本机应用和 API

安装界面、API 与可选的本地检索依赖。先启动聊天模型和嵌入模型，具体端点见[本地检索配置](retrieval.md)。

```powershell
.\.venv\Scripts\python.exe -m pip install -e '.[rag,app,test]'
```

在两个 PowerShell 窗口的项目根目录分别运行以下命令。

```powershell
# API 窗口
.\.venv\Scripts\python.exe -X utf8 -m uvicorn research_agent.app.api:app --host 127.0.0.1 --port 8000

# 界面窗口
.\.venv\Scripts\python.exe -X utf8 -m streamlit run src/research_agent/app/ui.py --server.address 127.0.0.1 --server.port 8501 --server.headless true --server.maxUploadSize 12 --browser.gatherUsageStats false
```

在 [Streamlit](http://127.0.0.1:8501) 打开研究台，上传 PDF、TXT 或 Markdown，然后在聊天框提交研究问题。从研究历史选择任务可查看进展、工具记录、报告和 Markdown 下载。选中历史任务后可以独立选择沿用已上传资料、把上一轮问题作为背景。使用旧文件时，本轮问题默认独立规划。联网需要单独勾选，并在 API 进程设置 `RESEARCH_WIKI_CONTACT`。

界面使用 `RESEARCH_API_URL` 连接 API，默认是 `http://127.0.0.1:8000`。服务状态和文档默认保存在 `.research-agent/app/`，可通过 `RESEARCH_APP_DIR` 指定专用目录。队列最多容纳 4 个未完成任务，使用单后台工作线程顺序执行。API 重启会把上次仍在队列中或执行中的任务标记为中断，之后可恢复。报告中引用的本地文件名对应该任务的资料列表。

## API

交互文档位于 [Swagger UI](http://127.0.0.1:8000/docs)。主要接口如下。

| 方法 | 路径 | 行为 |
|---|---|---|
| GET | `/health` | 检查 API 是否就绪 |
| POST | `/documents?name=notes.md` | 发送 `application/octet-stream` 原始文件，返回文件 ID |
| POST | `/jobs` | 接收 `topic`、`documents`、`online`，以及可选的 `query`、`parent_id`、`reuse_documents`、`include_previous_topic`，返回任务 ID |
| GET | `/jobs` | 最近 50 个任务的摘要 |
| GET | `/jobs/{id}` | 具体状态、子任务、资料和工具记录 |
| POST | `/jobs/{id}/resume` | 恢复中断任务 |
| GET | `/jobs/{id}/report?download=true` | 下载已生成的 UTF-8 Markdown，去掉参数可直接读取 |

单份文件最多 12 MiB，每任务最多 8 个文件、合计 32 MiB。API 和界面面向本机单用户。默认使用环回地址与单工作进程，并拒绝跨来源的浏览器写请求。[FastAPI 文档](https://fastapi.tiangolo.com/) · [Streamlit 文件上传控件](https://docs.streamlit.io/develop/api-reference/widgets/st.file_uploader)

## Phase 13 实测

通过真实 HTTP 上传 `sqlite-wal.md` 并提交一个 SQLite checkpoint 问题。后台完成 3 个子任务，记录了索引及检索操作，导出的 Markdown 含文件行号引用。浏览器从历史选中该任务后显示完成状态、子任务、报告正文及下载按钮。自动化测试覆盖上传限制、队列、跨来源请求、追问、历史和报告附件。
