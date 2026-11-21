# 工具系统

`BaseTool` 定义工具名称、说明、参数规则和执行方法。`ToolRegistry` 从注册的工具生成模型可用的描述，按名字找到工具，校验参数，再分发执行。未知工具、参数错误、预期工具失败和意外异常都有可区分的错误码。成功结果包含 `tool`、`ok` 和 `data`，失败结果包含 `tool`、`ok` 和 `error`。

## 工具与边界

| 工具 | 输入与行为 | 约束 |
|---|---|---|
| `calculator` | `expression`，返回计算值 | 通过 AST 解释数字、括号、一元正负号以及 `+ - * / // % **`。限制表达式长度、节点数量、中间值和幂指数。 |
| `read_file` | `path`，返回授权根目录内的相对路径与文本 | 支持 UTF-8 的 `.txt` 和 `.md`，默认上限 8192 字节。拒绝绝对路径、父目录跳转、Windows 设备路径和解析后越界的链接。 |
| `search` | `query` 和可选的 `limit`，返回标题、URL 与摘要 | 默认数量为 5，上限为 10。提供方实现接收超时预算并负责执行。未配置时返回 `search_not_configured`。 |

搜索通过 `SearchProvider` 注入。工具约定覆盖配额或服务错误，提供方可通过 `ToolError` 返回具体错误码。确认实际服务的配额、成本和可用性后接入。当前搜索验收依据是可注入接口、桩测试和未配置处理。

## 命令行验证

在工作区根目录使用 PowerShell，工具参数从标准输入读取。读取文件时通过 `--root` 明确授权目录。若在 Windows PowerShell 5.1 中传递中文 JSON，可先设置 `$OutputEncoding = [Text.UTF8Encoding]::new($false)`。

```powershell
'{"expression":"(5 + 7) * 3 - 2 ** 3"}' | .\.venv\Scripts\python.exe -X utf8 -B -m research_agent tool-run calculator
'{"path":"requirements.md"}' | .\.venv\Scripts\python.exe -X utf8 -B -m research_agent tool-run read_file --root .\docs
'{"query":"SQLite WAL"}' | .\.venv\Scripts\python.exe -X utf8 -B -m research_agent tool-run search
.\.venv\Scripts\python.exe -X utf8 -B -m unittest discover -s tests -v
```

## Phase 5 验收

- 计算器返回 `28`，文件读取结果与原文一致，越界路径和未配置搜索返回预期错误码。本地模型生成的两条调用分别经注册表执行，计算器和文件读取均成功。
- Phase 5 新增 14 项单元测试，13 项通过，文件符号链接用例因 Windows 缺少创建权限而跳过。另在工作区创建了指向授权根目录之外的 Windows 目录联接，实测读取被拒绝，并清理了测试目录。
- 全部阶段累计 27 项单元测试，26 项通过，1 项跳过。Agent 多轮工具循环安排在 Phase 6。
