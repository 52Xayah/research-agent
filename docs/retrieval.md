# 本地知识库与检索

在项目根目录安装可选依赖，并在可用的 Ollama 服务中准备 EmbeddingGemma。模型服务与聊天服务可共用端口，也可独立运行。

```powershell
.\.venv\Scripts\python.exe -m pip install -e '.[rag]'
ollama pull embeddinggemma
.\.venv\Scripts\python.exe -X utf8 -B -m research_agent rag-search .\examples\research 'How do WAL checkpoints work?' --limit 2
```

如需把模型保存在本项目内，在单独的 PowerShell 窗口启动嵌入服务。该窗口随服务运行。

```powershell
$env:OLLAMA_HOST = '127.0.0.1:11435'
$env:OLLAMA_MODELS = Join-Path (Get-Location).Path '.research-agent/ollama-models'
ollama serve
```

在另一个 PowerShell 窗口拉取模型，并为项目指定嵌入端点。聊天默认继续使用 `11434`。

```powershell
$env:OLLAMA_HOST = '127.0.0.1:11435'
ollama pull embeddinggemma
$env:RESEARCH_EMBED_URL = 'http://127.0.0.1:11435'
.\.venv\Scripts\python.exe -X utf8 -B -m research_agent rag-search .\examples\research 'What does SQLite WAL do?'
```

文本保留行号，PDF 使用 PyMuPDF 逐页提取文字，片段逐批交给本地模型。FAISS 在内存中保存归一化向量，以内积计算余弦相似度。命令启动时从指定资料重建索引。扫描件 OCR 和重排序可在后续加入。[Ollama Embedding API](https://docs.ollama.com/api/embed) · [EmbeddingGemma 模型卡](https://gemma.ai/models/embeddinggemma/model-card-v1/) · [FAISS 安装文档](https://github.com/facebookresearch/faiss/blob/main/INSTALL.md)

默认读取 24 个文件以内、最多 256 个片段，单个文件最大 12 MiB，数字 PDF 最多 40 页。无法解析或超限的文件列入 `issues`。

## Phase 9 实测

使用 Windows、CPU FAISS 1.16.0、PyMuPDF 1.28.2 和本地 EmbeddingGemma（768 维），对 TXT、Markdown 和程序生成的数字 PDF 共 5 个片段建库。一次冷启动建库耗时 21.41 秒。

| 固定查询 | 实际 Top 1 | 相似度 |
|---|---|---:|
| SQLite WAL 长读事务与 checkpoint | `sqlite-wal.md` 第 1–7 行 | 0.7369 |
| CSV 分隔符转义 | `csv-format.txt` 第 1–3 行 | 0.5875 |
| 光纤如何引导光传播 | `optics.pdf` 第 1 页 | 0.6534 |

三条查询的 Top 1 均命中预期文件。样本量为 3，耗时与相似度仅对应本次实测。
