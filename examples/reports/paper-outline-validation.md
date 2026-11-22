# 真实论文目录验收

使用 `research` 命令分别处理两篇原始数字 PDF，并对照人工核对的标题与起始页。下表转录实际 Markdown 的标题、层级、PDF 物理页序和引用编号。引用编号在每份报告内独立编号，对应的标题来源页为所在行页范围的起始页。

> 请求 · 请列出当前上传论文的全部章节标题，并说明每个章节包含的主要内容，尽可能提供对应页码。

## Generalized Category Discovery

扫描 **10/10 页**，标题和起始页匹配 **16/16 项**，共 **9 个引用位置**。

第 3 节的方法原文要点覆盖对比学习和半监督 K-means。第 4 节保留 4.1 至 4.5 的实验结构。

| 层级 | 标题 | PDF 页序 | 标题来源 |
|---:|---|---:|---|
| 1 | Abstract | 1 | `S1` |
| 1 | 1. Introduction | 1–2 | `S1` |
| 1 | 2. Related work | 2–3 | `S2` |
| 1 | 3. Generalized category discovery | 3–5 | `S3` |
| 2 | 3.1. Our approach | 3–4 | `S3` |
| 2 | 3.2. Estimating the class number in unlabelled data | 4–5 | `S4` |
| 2 | 3.3. Two strong baselines | 5 | `S5` |
| 1 | 4. Experiments | 5–8 | `S5` |
| 2 | 4.1. Experimental setup | 5–6 | `S5` |
| 2 | 4.2. Comparison with the baselines | 6 | `S6` |
| 2 | 4.3. Estimating the number of classes | 6 | `S6` |
| 2 | 4.4. Ablation study | 6–7 | `S6` |
| 2 | 4.5. Qualitative results | 7–8 | `S7` |
| 1 | 5. Conclusion | 8 | `S8` |
| 1 | Acknowledgements | 8 | `S8` |
| 1 | References | 9–10 | `S9` |

## Learning Semi-supervised Gaussian Mixture Models for Generalized Category Discovery

扫描 **11/11 页**，标题和起始页匹配 **15/15 项**，共 **10 个引用位置**。

第 3.2 节合并了两行标题并覆盖第 4–5 页。其要点来自第 4 页正文，说明半监督高斯混合模型用于估计类原型和未知类别数。算法框中的 `13 end` 已排除。

| 层级 | 标题 | PDF 页序 | 标题来源 |
|---:|---|---:|---|
| 1 | Abstract | 1 | `S1` |
| 1 | 1. Introduction | 1–2 | `S1` |
| 1 | 2. Related work | 2–3 | `S2` |
| 1 | 3. Method | 3–5 | `S3` |
| 2 | 3.1. Representation learning | 3–4 | `S3` |
| 2 | 3.2. Class number and prototypes estimation with semi-supervised Gaussian mixture model | 4–5 | `S4` |
| 1 | 4. Experiments | 5–9 | `S5` |
| 2 | 4.1. Experimental setup | 5–6 | `S5` |
| 2 | 4.2. Comparison with the state-of-the-art | 6–7 | `S6` |
| 2 | 4.3. Novel class number estimation | 7–8 | `S7` |
| 2 | 4.4. Training complexity | 8 | `S8` |
| 2 | 4.5. Ablation study | 8–9 | `S8` |
| 1 | 5. Conclusion | 9 | `S9` |
| 1 | Acknowledgements | 9 | `S9` |
| 1 | References | 10–11 | `S10` |

## 验收边界

两份数字 PDF 的目录和源页定位均通过。该结果针对目录任务，正文摘要使用代表性原文作为要点。原始文件和带大段引述的完整报告由上传者在本机管理。
