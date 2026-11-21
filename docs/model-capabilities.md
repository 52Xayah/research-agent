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

[Ollama Chat API](https://docs.ollama.com/api/chat) · [流式响应格式](https://docs.ollama.com/api/streaming) · [结构化输出](https://docs.ollama.com/capabilities/structured-outputs)
