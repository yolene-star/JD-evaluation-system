# 质量样例、多模型对比与测评稳定性设计

> 状态：待用户审查
>
> 适用范围：阶段四质量评估、确定性回退、Prompt 版本管理、模型调用观测和阶段二追问修复
>
> 真实模型验证预算：20 个代表 JD，每个可用模型各执行一次，最多两个真实模型 Profile

## 1. 目标

解决当前质量验证中的五个明确问题：

1. 现有 50 条 JD 样例不足以证明跨岗位泛化能力，扩展到 170 条独立 JD 并建立人工维护的参考模型。
2. 确定性回答分析只按长度和拒绝词判断，导致大量回答统一进入 9-10 档。改为基于情境、行动、依据、结果、指标和复盘等可解释特征分档。
3. Prompt 目前分散在源码和函数中。建立独立 Prompt 目录、版本清单、哈希和加载器。
4. 质量评测缺少多模型对比、真实供应商延迟和 token 统计。建立离线基线加真实模型小批评测 Runner。
5. 相同追问内容被旧问题去重逻辑复用，后续回答可能被判定为过期。修复为“问题被回答后不得再作为当前问题复用”。

## 2. 非目标

- 不把质量样例用于招聘决策、正式心理测量或人才资格审查；
- 不抓取招聘网站数据；
- 不训练或微调模型；
- 不把真实模型调用作为普通单元测试的前置条件；
- 不在全量 170 条 JD 上无条件消耗真实 API 额度；
- 不改变阶段一确认快照、阶段二证据包和阶段三历史报告的不可变边界。

## 3. 数据设计

### 3.1 JD 参考模型

新增：

```text
harness/fixtures/quality/jd_reference_models.jsonl
```

至少 170 行，每行一份独立 JD，结构如下：

```json
{
  "id": "jd-ref-001",
  "role_family": "backend",
  "role_title": "高级后端工程师",
  "seniority": "SENIOR",
  "industry": "企业软件",
  "source_type": "curated",
  "jd_text": "……",
  "reference_model": {
    "competencies": [
      {
        "canonical_name": "系统设计",
        "category": "technical",
        "weight": 0.3,
        "aliases": ["架构设计", "服务设计"],
        "indicators": ["容量与可靠性权衡"],
        "evidence_requirements": ["本人行动", "可验证结果"],
        "evidence_excerpts": ["负责核心服务设计"]
      }
    ],
    "qualifications": ["本科"],
    "constraints": ["上海"],
    "unacceptable_hallucinations": ["管理 50 人团队"]
  },
  "review": {
    "reviewed_by": "project-maintainer",
    "reviewed_at": "2026-09-12",
    "notes": "按原文人工整理，不代表外部专家认证。"
  }
}
```

覆盖要求：

- 24 个岗位族；
- 初级、中级、高级、专家四档；
- 技术、产品、数据、设计、测试、运维、运营、销售、职能等岗位；
- 中文、中英文混合、要点式、长段落、条件前置和低信息量表达；
- 正式能力权重合计为 1.0；
- `evidence_excerpts` 必须逐字存在于 `jd_text`；
- 不包含真实姓名、手机号、邮箱、公司机密或真实招聘记录。

现有 `samples.jsonl` 保留为 100 条混合回归样例；新的 170 条 JD 参考模型作为规模化评估集。

### 3.2 匹配口径

能力匹配按以下顺序：

1. 规范化名称精确匹配；
2. 参考模型别名匹配；
3. 未命中则计为漏检；
4. 输出能力如果既不在名称也不在别名集合，计为越界能力。

文本相似度不单独决定能力匹配，避免用同一模型给自己评分。

## 4. 确定性回答分析

### 4.1 特征

新增可解释特征：

```text
has_situation
has_ownership
has_action
has_reasoning
has_result
has_metric
has_reflection
specificity
```

每条特征返回布尔值或 0～1 分值，并保留原文证据片段。

### 4.2 分档

确定性分析结果至少覆盖：

- `0-2`：空回答、拒绝、只有态度表达；
- `3-4`：只有概括，没有本人行动或结果；
- `5-6`：有行动，但缺少依据、结果或指标；
- `7-8`：有情境、行动和结果，指标或复盘中有一项不足；
- `9-10`：包含情境、本人行动、依据、可验证结果、指标和复盘。

确定性分析返回的 excerpt 仍必须逐字来自用户回答。模型失败时使用该分析，但必须标记 `source=deterministic-fallback`。

## 5. Prompt 版本化

新增目录：

```text
prompts/
  manifest.json
  jd_parsing/v2/
    system.txt
    schema.json
  question/v2/
    system.txt
    schema.json
  analysis/v2/
    system.txt
    schema.json
  profile/v2/
    system.txt
    schema.json
```

`manifest.json` 保存任务、版本、文件、SHA-256 和状态。

新增 `backend/app/services/prompt_registry.py`：

- 按任务和版本加载 Prompt；
- 校验 manifest 与文件 SHA-256；
- 禁止业务服务直接拼接未登记 Prompt；
- 返回稳定的 `prompt_version` 和 `prompt_sha256` 供日志记录。

旧 Prompt 常量保留兼容期，但业务调用切换到注册表。

## 6. 模型 Profile 与质量 Runner

### 6.1 Profile

新增：

```text
harness/config.toml
```

示例：

```toml
[[models]]
id = "deterministic-fallback"
provider = "local"

[[models]]
id = "deepseek-chat"
provider = "openai-compatible"
model = "deepseek-chat"
base_url_env = "LLM_BASE_URL"
api_key_env = "DEEPSEEK_API_KEY"

[[models]]
id = "deepseek-reasoner"
provider = "openai-compatible"
model = "deepseek-reasoner"
base_url_env = "LLM_BASE_URL"
api_key_env = "DEEPSEEK_API_KEY"
```

未配置密钥、模型不可用或供应商拒绝时，Runner 记录 `UNAVAILABLE`，不得用其他模型结果冒充。

### 6.2 CLI

新增：

```text
harness/quality_runner.py
```

支持：

```powershell
python harness/quality_runner.py check
python harness/quality_runner.py run --model deterministic-fallback
python harness/quality_runner.py run --model deepseek-chat --sample-size 20
python harness/quality_runner.py run --model deepseek-reasoner --sample-size 20
python harness/quality_runner.py compare --run <baseline-run-id> --run <model-run-id>
```

`--sample-size 20` 使用固定种子抽取代表样例，抽取结果写入 RunContext，保证可复现。

### 6.3 指标

每次 Run 输出：

- JSON 结构成功率；
- 能力精确率、召回率和 F1；
- 证据片段可追溯率；
- 越界能力率；
- 条件抽取准确率；
- p50、p95 和最大延迟；
- 输入、输出和总 token；
- 超时、限流、网络和 Schema 失败数；
- 估算费用，未知价格时返回 `null`。

### 6.4 产物

运行产物写入：

```text
harness/reports/quality/<run-id>/
```

该目录默认忽略。人工整理后的汇总可写入：

```text
docs/quality/
```

## 7. 调用日志

扩展 `LLMCallLog`：

```text
run_id: String(80), nullable
usage_json: JSON, default {}
```

记录：

- 模型；
- 任务类型；
- Prompt 版本和 SHA-256；
- 状态；
- 延迟；
- token；
- 错误；
- Run ID。

该扩展保持旧数据兼容。提供 Alembic revision，并在 SQLite 启动兼容逻辑中增加列。

## 8. 重复追问修复

### 8.1 缺陷

`_persist_question` 仅按内容和覆盖能力去重。第二次生成相同追问文本时返回旧问题，而旧问题后面已经存在用户回答，后续回答会被认为对应过期问题。

### 8.2 规则

问题只有在以下条件同时满足时才允许复用：

1. 内容与覆盖能力相同；
2. 是当前最新系统问题；
3. 该问题之后没有用户回答。

如果问题之后已有用户回答，则创建新的 AssessmentTurn，即使文本相同。

确定性追问文案增加追问序号或缺口信息，减少重复感：

```text
第 2 次补充：请针对上一回答未覆盖的“可验证结果”补充具体指标。
```

## 9. 错误与安全

- 真实模型调用超时 45 秒，最多手动重试一次；
- 不在日志写入 API Key、完整简历或实际招聘记录；
- 样例全部为脱敏教学数据；
- Prompt 文件禁止包含密钥；
- Runner 只允许配置内模型；
- 失败不推进正式测评状态；
- 真实调用预算由 `--sample-size` 控制，默认 20；
- 供应商价格未知时不估算费用。

## 10. 测试

### 10.1 单元与契约

- 170 条 JD 数量、唯一性和参考模型 Schema；
- 权重合计、证据逐字可追溯、无敏感信息；
- 能力匹配器精确率与召回率计算；
- 确定性分析覆盖 0-2、3-4、5-6、7-8、9-10 五档；
- Prompt manifest 哈希校验；
- Prompt 缺失或哈希不匹配时明确失败；
- `LLMCallLog` token 和 run_id 持久化；
- 相同追问在有回答后创建新轮次；
- 同一问题尚无回答时仍保持幂等复用。

### 10.2 Runner

- 固定样本抽取可复现；
- 不可用模型记录 `UNAVAILABLE`；
- 超时、无效 JSON、Schema 错误和证据失败分别计数；
- 离线基线可在无 API Key 时运行；
- 对比报告包含多个 Run 的指标。

### 10.3 回归

- 后端全量 pytest；
- 前端 Vitest；
- 前端生产构建；
- `git diff --check`；
- Word 项目书渲染和图片内容密度检查。

## 11. 验收标准

- `jd_reference_models.jsonl` 至少 170 条独立 JD，覆盖至少 24 个岗位族；
- 每条 JD 都有人工维护的参考模型，权重和证据可验证；
- 确定性回退不再把所有较长回答统一评为满分；
- 所有业务 Prompt 从独立版本目录加载并记录 SHA-256；
- 至少完成 `deterministic-fallback`、`deepseek-chat` 和 `deepseek-reasoner` 三个 Profile 的 Runner 运行；
- 真实模型各执行 20 条代表样例，失败或不可用如实记录；
- 调用日志包含延迟和 token，汇总报告包含 p50/p95；
- 重复追问回归测试通过；
- 全量测试、前端构建和项目书渲染通过；
- 项目书更新为真实结果，不再声称样例不足或雷达图必定全为 10 分。

## 12. 风险

- DeepSeek 模型名称或接口能力可能变化，Runner 必须按运行时结果记录；
- 170 条参考模型由项目维护者整理，不等于外部专家双盲标注；
- 真实调用会产生费用和延迟，因此仅运行 20 条代表样例；
- 确定性特征评分适合教学和回归，不替代心理测量或专业评分；
- 模型输出可能包含供应商差异，不能用一次运行得出永久结论。
