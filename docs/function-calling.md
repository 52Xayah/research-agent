# 原生 Function Calling

```powershell
.\.venv\Scripts\python.exe -X utf8 -B -m research_agent function-demo
.\.venv\Scripts\python.exe -X utf8 -B -m research_agent function-check
```

Demo 中有两个只读查询工具，数据来自代码内的固定字典。模型先收到两个工具描述和参数的 JSON Schema。程序接收一条原生 `tool_calls` 调用，校验工具名与参数，再查找对应结果。第二次请求包含原始助手调用和带 `tool_name` 的工具消息，由模型返回结果。这个 Demo 每个样例最多执行一次工具调用和一次结果回传。

参数声明同时生成 JSON Schema 和运行时校验，支持字符串、整数、有限实数、布尔值、必填字段、长度和数值边界。未知字段、错误类型和越界值在执行前拒绝。单元测试覆盖有效与无效参数、工具消息回传、无效请求停止执行。[Ollama 工具调用协议](https://docs.ollama.com/capabilities/tool-calling)

## 固定测试集

完整提示和预期值位于 [function_demo.py](../src/research_agent/function_demo.py)。每个样例独立启动对话，两种工具同时可供选择。

| 样例 | 请求 | 预期工具参数 | 回传预期值 |
|---|---|---|---|
| 1 | 查询项目状态 | `lookup_project(code="R-27")` | `amber` |
| 2 | 查询库存数量 | `lookup_inventory(sku=381)` | `19` |
| 3 | 中文查询项目状态 | `lookup_project(code="T-105")` | `blue` |
| 4 | 中文查询库存数量 | `lookup_inventory(sku=642)` | `73` |
| 5 | 查询项目状态 | `lookup_project(code="CN-42")` | `green` |
| 6 | 查询库存数量 | `lookup_inventory(sku=904)` | `58` |

统计工具选择正确数、工具和参数均正确数，以及执行并回传后满足答案格式的数量。最终答案比较会忽略首尾空白、大小写及末尾句号。运行参数沿用[模型实测](model-capabilities.md)。

## 实测记录

| 版本 | 工具选择 | 工具与参数均正确 | 回传与答案格式 |
|---|---:|---:|---:|
| 初次运行 | 6/6 | 6/6 | 4/6 |
| 增加系统级回传格式说明 | 6/6 | 6/6 | 5/6 |
| 明确样例 5 的输出要求 | 6/6 | 6/6 | 6/6 |

初次运行的第 5、6 个样例包含正确结果，但附加了叙述。系统级说明让第 6 个样例按格式返回。第 5 个样例的原始提示未要求仅返回状态值，最终固定测试集在该样例中明确了输出要求。本组为本地小样本，结果仅反映这些工具、提示和参数下的表现。
