# 质量测试样例集

质量目录包含两套教学实验数据，不包含真实个人信息。

## 混合回归样例

`samples.jsonl` 包含 100 条教学实验用样例，数据分布如下：

| 类型 | 数量 | 用途 |
|---|---:|---|
| `jd_parse` | 50 | 验证 JD 能力、资历、地点约束和原文证据 |
| `answer_analysis` | 35 | 验证充分回答、短回答、拒绝回答和提示注入 |
| `scoring_boundary` | 5 | 验证未完成、满覆盖、半覆盖、负向和不确定证据 |
| `excerpt_validation` | 5 | 验证正式证据必须能在回答原文中定位 |
| `question_contract` | 5 | 验证问题覆盖 1 至 3 个唯一能力项 |

执行检查：

```powershell
python harness/generate_quality_samples.py
python -m pytest backend/tests/test_quality_samples.py -q
```

## JD 参考模型

`jd_reference_models.jsonl` 包含 192 条独立 JD：

- 24 个岗位族，每族 8 个变体；
- `JUNIOR`、`MID`、`SENIOR`、`EXPERT` 四个资历层级；
- 人工维护的能力权重、别名、指标、证据要求和原文片段；
- 能力权重合计为 1.0，证据片段逐字存在于 JD 原文。

生成与检查：

```powershell
python harness/generate_jd_reference_models.py
python -m pytest backend/tests/test_jd_reference_models.py backend/tests/test_jd_quality_metrics.py -q
```

参考模型由项目维护者整理，不代表外部专家双盲认证。确定性回退按情境、行动、依据、结果、指标和复盘特征分档，不能替代真实大模型的专业评价质量。
