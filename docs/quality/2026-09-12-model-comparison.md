# 2026-09-12 模型质量对比

## 运行范围

- 参考语料：192 条独立 JD，24 个岗位族，每族 8 个变体。
- 代表样例：固定抽取 20 条，覆盖 20 个岗位族。
- Prompt：`jd-parsing-v2`，SHA-256 由 `prompts/manifest.json` 和 Prompt 文件共同计算。
- 真实调用预算：每个模型 20 条。
- 运行环境：项目本地配置，未在报告中记录 API Key 或供应商原始响应正文。

## 对比结果

| 模型 | Run ID | 成功 / 总数 | 精确率 | 召回率 | F1 | 证据可追溯率 | 越界能力率 | p50 延迟 | p95 延迟 | 总 token |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| deterministic-fallback | `20260912T141859Z-deterministic-fallback` | 20 / 20 | 1.0000 | 0.7375 | 0.8405 | 1.0000 | 0.0000 | 0 ms | 0 ms | 0 |
| deepseek-chat | `20260912T141941Z-deepseek-chat` | 20 / 20 | 0.1863 | 0.2000 | 0.1916 | 1.0000 | 0.8137 | 1367 ms | 1651 ms | 10873 |
| deepseek-reasoner | `20260912T142223Z-deepseek-reasoner` | 20 / 20 | 0.1417 | 0.1500 | 0.1450 | 1.0000 | 0.8583 | 7515 ms | 10635 ms | 38690 |

## 结论

1. 三个 Profile 均完成 20 条运行，没有超时、限流、无效 JSON 或 Schema 失败。
2. 确定性基线在本课程词典覆盖的岗位上精度高，但只覆盖参考模型中的一部分能力，召回率为 73.75%。
3. 两个真实模型能把证据片段保持在 JD 原文中，证据可追溯率为 100%。
4. 真实模型生成了更多命名不同或参考模型外的能力，在当前“精确名称或别名才算命中”的严格口径下，精确率和召回率较低。该结果说明模型抽取与人工参考模型之间仍需要统一命名规范或人工复核，不能把低分直接解释为模型没有识别到相关语义。
5. `deepseek-reasoner` 的 p50/p95 延迟明显高于 `deepseek-chat`，token 消耗也更高。
6. 价格表未写入仓库，因此没有伪造费用估算；需要结合当前供应商价格另行计算。

## 复现命令

```powershell
python harness/quality_runner.py check
python harness/quality_runner.py run --model deterministic-fallback --sample-size 20
python harness/quality_runner.py run --model deepseek-chat --sample-size 20
python harness/quality_runner.py run --model deepseek-reasoner --sample-size 20
```

运行明细保存在 `harness/reports/quality/<run-id>/`，该目录默认不纳入版本控制。
