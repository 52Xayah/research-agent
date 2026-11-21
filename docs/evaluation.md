# 固定样例评估

`evaluate` 使用实际模型与工具注册表。用例包括直接回答、计算、文件读取、读后计算和中文请求。每个用例启动新的对话，并使用真实的计算器与文件读取实现。固定提示、答案与期望调用位于 [cases.py](../src/research_agent/evaluation/cases.py)。

成功要求收到最终答案、答案匹配、工具名及参数按顺序完全匹配，并且执行无失败。工具名及参数的分母取每个样例期望和实际调用数的较大者。工具失败率的分母为真实分发的调用数。计算样例允许数值等价的整数和带单个零小数位的表示。

引用样例独立评估原文匹配与复查。正确结论应保留。无效引用 ID、伪造引述，以及引述真实但篡改其含义的结论应拒绝。引用样例的请求不计入工具任务耗时和 Token 统计。模型加载大小来自 Ollama 的一次运行中快照，以字节计。[Ollama 运行模型接口](https://docs.ollama.com/api/ps)

## 运行方式

```powershell
.\.venv\Scripts\python.exe -X utf8 -B -m research_agent evaluate --output .research-agent\phase11-qwen-4b.json
$env:RESEARCH_OLLAMA_MODEL = 'qwen3.5:0.8b'
.\.venv\Scripts\python.exe -X utf8 -B -m research_agent evaluate --output .research-agent\phase11-qwen-08b.json
```

评估前分别在对应 Ollama 服务中准备模型。使用工作区内独立服务时，将 `RESEARCH_OLLAMA_URL` 设置为该服务的地址，见[本地知识库与嵌入服务](retrieval.md)。测试包含可复现规则和端到端小样本，后续可增加重复运行、长文覆盖和人工评分。[0.8B 模型说明](https://ollama.com/library/qwen3.5:0.8b)

## 实测对比

2026 年 11 月 22 日，Windows、RTX 4060 Laptop GPU、Ollama 0.40.17。两组均使用 4096 上下文与 512 最大生成 Token。4B 已预热，0.8B 包含首次模型加载，两组延迟仅代表本次运行。

| 指标 | Qwen3.5 4B | Qwen3.5 0.8B |
|---|---:|---:|
| 工具任务成功 | 6/6 | 2/6 |
| 工具选择正确 | 6/6 | 3/6 |
| 精确工具参数正确 | 6/6 | 3/6 |
| 已分发调用失败 | 0/6 | 0/3 |
| 每个工具任务平均耗时 | 5.396 秒 | 1.392 秒 |
| 工具任务总输入 / 输出 Token | 5936 / 204 | 4376 / 131 |
| Ollama 显存快照 | 约 2.92 GiB | 约 0.53 GiB |
| 引用检查判定正确 | 4/4 | 3/4 |

0.8B 成功完成读取和读后计算，三道单独计算题未按要求调用工具。引用复查有一条误拒。基于这组样例，默认模型维持 4B。原始结果见 [4B JSON](../examples/evaluation/qwen-4b.json)和 [0.8B JSON](../examples/evaluation/qwen-08b.json)。
