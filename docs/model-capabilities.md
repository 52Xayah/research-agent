# 本地模型能力实测

## 复现

```powershell
.\.venv\Scripts\python.exe -X utf8 -B -m research_agent model-check
```

2026 年 11 月 22 日在本机运行。Python 3.12.10，Ollama 0.40.17，`qwen3.5:4b`，上下文 4096，最大输出 512 Token，请求设置 `think=false`、`temperature=0`。耗时是各用例在本机单次运行的端到端时间，包含请求开销。

| 用例 | 判定条件 | 结果 | 耗时 |
|---|---|---|---:|
| 基础聊天 | 返回指定中文短语 | 通过 | 2.75 秒 |
| 多轮对话 | 携带历史后复述第一轮给出的代号 | 通过 | 6.28 秒 |
| 流式输出 | 收到多个文本片段并有完成帧 | 通过，18 个文本片段 | 2.58 秒 |
| 结构化输出 | 返回指定字段、值及整数类型 | 通过 | 2.75 秒 |
| 基础推理 | 两步算术题得到正确结果 | 通过 | 2.31 秒 |
| 工具调用兼容性 | 原生调用包含指定工具名和参数 | 通过 | 2.97 秒 |

本轮为 6/6，覆盖短输入和单个模型。Phase 4 扩展到工具选择、参数准确率、实际执行和回传。长文推理、复杂任务成功率和性能统计留待后续阶段测量。

## 模型接口回归

`BaseLLM` 定义普通请求和文本流，统一使用 `Message`、`ToolSpec`、`ToolCall` 与 `ChatResponse`。工具调用走普通请求。流式调用逐帧返回文本，结束帧携带可用的 Token 统计。结构化结果使用 JSON 文本，调用方按自己的模式验证字段和值。

`OllamaLLM` 处理协议转换。客户端使用连接和读取超时，区分超时、传输错误和协议错误。此超时约束网络操作，整个研究任务的执行预算由后续 Agent Loop 负责。`--verbose` 可开启传输状态与耗时日志，日志省略请求和响应正文。

```powershell
.\.venv\Scripts\python.exe -X utf8 -B -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -X utf8 -B -m research_agent --verbose model-check
```

Phase 3 独立验收时，9 项模拟 HTTP 单元测试通过，覆盖中文消息序列化、Token 统计、工具消息往返、流完成与关闭、断流、无效响应、超时、连接失败和 HTTP 错误。切换到统一接口后，6 项本地模型实测均通过。

[Ollama Chat API](https://docs.ollama.com/api/chat) · [流式响应格式](https://docs.ollama.com/api/streaming) · [结构化输出](https://docs.ollama.com/capabilities/structured-outputs)
