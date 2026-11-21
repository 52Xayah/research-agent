# 研究、恢复与报告

## 本地研究

完成[嵌入服务配置](retrieval.md)后，在 PowerShell 的项目根目录运行。

```powershell
.\.venv\Scripts\python.exe -X utf8 -B -m research_agent research '对比 SQLite WAL 与回滚日志。仅说明并发读取、WAL 检查点与崩溃后的日志恢复方式。' --root .\examples\research
```

研究命令生成任务 ID 和 Markdown 路径。默认数据库为 `.research-agent/state.sqlite3`，报告位于其相邻的 `reports` 目录。使用 `--db` 或 `--output` 可指定路径。报告中的本地文件路径相对于 `--root`，PDF 标注页码，文本标注行号。

## 联网研究

使用 `--online` 启用英文维基百科。设置 `RESEARCH_WIKI_CONTACT` 为你希望公开给服务方的项目链接、邮箱或维基用户标识。仅查询词和页面查询会发给维基百科。需要缩短查询时可显式指定 `--query`。

```powershell
$env:RESEARCH_WIKI_CONTACT = 'https://your-project.example/contact'
.\.venv\Scripts\python.exe -X utf8 -B -m research_agent research 'Explain what SQLite is and why it can be embedded in applications' --online --query SQLite
```

搜索最多两个结果，通过同一站点的 API 读取页面导言。网页引用优先使用可定位的修订版。返回为空、限流或读取失败时，报告会记录问题；同时提供 `--root` 时可以用已得到的本地证据继续。维基百科适合概览，技术结论可结合授权目录中的一手资料验证。[搜索 API](https://www.mediawiki.org/wiki/API:Search) · [TextExtracts API](https://www.mediawiki.org/wiki/Extension:TextExtracts#API) · [User-Agent 要求](https://foundation.wikimedia.org/wiki/Policy:Wikimedia_Foundation_User-Agent_Policy)

## 历史与恢复

```powershell
.\.venv\Scripts\python.exe -X utf8 -B -m research_agent history
.\.venv\Scripts\python.exe -X utf8 -B -m research_agent history RUN_ID
.\.venv\Scripts\python.exe -X utf8 -B -m research_agent research --resume RUN_ID
```

使用自定义数据库时，查询和恢复传入相同的 `--db`。恢复沿用原计划和资料配置，保留已结束的任务和证据，只继续未执行或中断的任务。继续搜集资料时会重新读取当前文件和网页。SQLite 保存了证据摘录和模型消息，`history RUN_ID` 可以用于回溯。

## 报告检查

每条分析结论必须包含已有证据 ID 和能在原文片段中找到的引述。通过引述匹配的候选项会交给一次独立模型请求复查，检查是否回答了当前问题、证据能否支持全部关键细节。报告标注单一来源、证据缺口、被移除的结论和任务失败。来源分歧需要两个不同来源的有效引述。该复查使用同一本地模型，读者仍需核对推理是否成立。

退出码 `0` 表示已生成带至少一条有效引用的报告且任务均执行完成，`2` 表示生成了缺少有效结论或含失败任务的报告。

## Phase 10 实测

- [本地 SQLite 研究报告](../examples/reports/sqlite-local.md)保留 3 条结论，引用 2 处文件位置。模型复查移除了 3 条相关性或证据支持不足的候选项。使用同一任务 ID 重新导出，报告 SHA-256 一致。
- [联网 SQLite 研究报告](../examples/reports/sqlite-web.md)通过真实搜索和页面读取，保留 1 条结论并引用维基百科修订版。其余问题的证据缺口保留在报告中。
