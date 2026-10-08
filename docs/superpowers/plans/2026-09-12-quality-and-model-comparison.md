# Quality Dataset and Model Comparison Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Expand the JD quality corpus, make deterministic fallback scoring evidence-sensitive, version all business prompts, compare multiple model profiles with real latency/token measurements, and fix duplicate follow-up reuse.

**Architecture:** Keep the modular monolith and existing immutable-version boundaries. Add a versioned Prompt registry and a standalone quality runner under `harness/`; the runner uses production contracts rather than test-only shortcuts. Logging remains sidecar-first for quality reports, with `LLMCallLog` extended for run IDs and token usage.

**Tech Stack:** Python 3.11+, FastAPI, Pydantic, SQLAlchemy, Alembic, pytest, OpenAI-compatible HTTP, JSONL, TOML.

**Spec:** `docs/superpowers/specs/2026-09-12-quality-and-model-comparison-design.md`

## Global Constraints

- Preserve existing user changes and do not revert unrelated work.
- Do not commit or create branches unless the user explicitly asks.
- All sample data must be synthetic or sanitized and contain no real personal data.
- Real model evaluation is limited to 20 representative JD cases per available model profile.
- Prompt files must not contain secrets.
- Formal scoring remains program-controlled; model output cannot directly set a score.
- The confirmed model snapshot, evidence package, and historical reports remain immutable.
- Every behavior change starts with a failing test and is verified before the next task.
- If a model is unavailable or fails, record `UNAVAILABLE` or `FAILED`; never substitute another model's result.

---

## File Structure

```text
prompts/
  manifest.json
  jd_parsing/v2/{system.txt,schema.json}
  question/v2/{system.txt,schema.json}
  analysis/v2/{system.txt,schema.json}
  profile/v2/{system.txt,schema.json}

backend/app/services/
  prompt_registry.py
  fallback_analysis.py
  llm_observability.py
  structured_llm.py

backend/tests/
  test_prompt_registry.py
  test_fallback_analysis.py
  test_llm_observability.py
  test_structured_llm.py
  test_duplicate_follow_up.py
  test_jd_reference_models.py
  test_jd_quality_metrics.py

harness/
  config.toml
  generate_jd_reference_models.py
  jd_quality.py
  model_profiles.py
  quality_runner.py
  fixtures/quality/jd_reference_models.jsonl
  reports/.gitkeep

docs/quality/
  2026-09-12-model-comparison.md
```

---

### Task 1: Versioned Prompt Registry

**Files:**
- Create: `prompts/manifest.json`
- Create: `prompts/jd_parsing/v2/system.txt`
- Create: `prompts/jd_parsing/v2/schema.json`
- Create: `prompts/question/v2/system.txt`
- Create: `prompts/question/v2/schema.json`
- Create: `prompts/analysis/v2/system.txt`
- Create: `prompts/analysis/v2/schema.json`
- Create: `prompts/profile/v2/system.txt`
- Create: `prompts/profile/v2/schema.json`
- Create: `backend/app/services/prompt_registry.py`
- Create: `backend/tests/test_prompt_registry.py`
- Modify: `backend/app/services/ai_parsing.py`
- Modify: `backend/app/services/assessment_prompts.py`
- Modify: `backend/app/services/profile_prompts.py`

**Interfaces:**
- Produces: `PromptBundle(task: str, version: str, system: str, schema: dict, sha256: str)`
- Produces: `load_prompt(task: str, version: str = "v2") -> PromptBundle`
- Produces: prompt version constants `JD_PARSE_PROMPT_VERSION`, `QUESTION_PROMPT_VERSION`, `ANALYSIS_PROMPT_VERSION`, `PROFILE_PROMPT_VERSION`

- [ ] **Step 1: Write the failing registry test**

```python
# backend/tests/test_prompt_registry.py
import pytest

from backend.app.services.prompt_registry import load_prompt


def test_prompt_registry_loads_and_hashes_known_prompt() -> None:
    prompt = load_prompt("analysis", "v2")
    assert prompt.version == "v2"
    assert prompt.system
    assert prompt.schema["type"] == "object"
    assert len(prompt.sha256) == 64


def test_prompt_registry_rejects_unknown_task() -> None:
    with pytest.raises(KeyError):
        load_prompt("missing", "v2")
```

- [ ] **Step 2: Run the test and verify the expected failure**

Run: `python -m pytest backend/tests/test_prompt_registry.py -q`

Expected: FAIL with `ModuleNotFoundError` or missing registry data.

- [ ] **Step 3: Add prompt files and manifest**

Each `schema.json` contains a JSON object schema. Each `system.txt` contains the exact role, task, evidence, privacy, and output constraints from the approved spec. `manifest.json` has:

```json
{
  "jd_parsing": {"version": "v2", "system": "prompts/jd_parsing/v2/system.txt", "schema": "prompts/jd_parsing/v2/schema.json"},
  "question": {"version": "v2", "system": "prompts/question/v2/system.txt", "schema": "prompts/question/v2/schema.json"},
  "analysis": {"version": "v2", "system": "prompts/analysis/v2/system.txt", "schema": "prompts/analysis/v2/schema.json"},
  "profile": {"version": "v2", "system": "prompts/profile/v2/system.txt", "schema": "prompts/profile/v2/schema.json"}
}
```

- [ ] **Step 4: Implement the registry**

```python
@dataclass(frozen=True)
class PromptBundle:
    task: str
    version: str
    system: str
    schema: dict
    sha256: str


def load_prompt(task: str, version: str = "v2") -> PromptBundle:
    entry = _MANIFEST[task]
    if entry["version"] != version:
        raise KeyError(f"{task} has no prompt version {version}")
    system_path = _ROOT / entry["system"]
    schema_path = _ROOT / entry["schema"]
    system = system_path.read_text(encoding="utf-8")
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    digest = hashlib.sha256(system_path.read_bytes() + b"\0" + schema_path.read_bytes()).hexdigest()
    return PromptBundle(task, version, system, schema, digest)
```

- [ ] **Step 5: Route existing prompt builders through the registry**

`ai_parsing.py`, `assessment_prompts.py`, and `profile_prompts.py` must import the registry and use the registered system prompt. Dynamic values remain in the user payload, never appended to an unregistered system prompt.

- [ ] **Step 6: Run registry and prompt contract tests**

Run:

```powershell
python -m pytest backend/tests/test_prompt_registry.py backend/tests/test_assessment_ai_contract.py backend/tests/test_question_prompt_strategy.py -q
```

Expected: all pass.

---

### Task 2: LLM Call Observability

**Files:**
- Modify: `backend/app/models.py`
- Modify: `backend/app/main.py`
- Create: `backend/alembic/versions/20260912_llm_usage.py`
- Create: `backend/app/services/llm_observability.py`
- Create: `backend/tests/test_llm_observability.py`
- Modify: `backend/app/services/analysis.py`
- Modify: `backend/app/routes/chat.py`

**Interfaces:**
- Produces: `record_llm_call(db, *, project_id, task_type, model, prompt_version, status, latency_ms=None, error=None, run_id=None, usage=None) -> LLMCallLog`
- Extends `LLMCallLog` with `run_id: str | None` and `usage_json: dict`

- [ ] **Step 1: Write the failing persistence test**

```python
def test_llm_call_records_run_latency_and_tokens(db):
    row = record_llm_call(
        db,
        project_id="p1",
        task_type="jd_parse",
        model="deepseek-chat",
        prompt_version="jd-parsing-v2",
        status="SUCCESS",
        latency_ms=123,
        run_id="quality-001",
        usage={"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
    )
    db.commit()
    assert row.run_id == "quality-001"
    assert row.usage_json["total_tokens"] == 15
```

- [ ] **Step 2: Run the test and verify failure**

Run: `python -m pytest backend/tests/test_llm_observability.py -q`

Expected: FAIL because the helper/columns do not exist.

- [ ] **Step 3: Add columns and helper**

Add nullable `run_id` and JSON `usage_json`. Add startup-compatible SQLite `ALTER TABLE` logic and an Alembic revision with upgrade/downgrade.

- [ ] **Step 4: Update existing call sites**

`backend/app/services/analysis.py` and `backend/app/routes/chat.py` must call `record_llm_call` and pass prompt version and usage when available.

- [ ] **Step 5: Run migration and observability tests**

Run:

```powershell
python -m pytest backend/tests/test_llm_observability.py backend/tests/test_migration_scaffold.py backend/tests/test_analysis_api.py -q
```

Expected: all pass.

---

### Task 3: Evidence-Sensitive Deterministic Analysis

**Files:**
- Create: `backend/app/services/fallback_analysis.py`
- Create: `backend/tests/test_fallback_analysis.py`
- Modify: `backend/app/services/assessment_ai.py`
- Modify: `harness/generate_quality_samples.py`
- Modify: `backend/tests/test_quality_samples.py`

**Interfaces:**
- Produces: `analyze_deterministic_answer(answer: str, competency_id: str, competency_name: str) -> AnalysisResult`
- Produces: `FallbackFeatures(situation, ownership, action, reasoning, result, metric, reflection, specificity)`

- [ ] **Step 1: Write failing score-variety tests**

```python
def test_fallback_analysis_produces_multiple_rubric_levels():
    answers = [
        "不清楚",
        "我参与过相关工作，但只负责协助。",
        "我负责性能优化，使用了监控工具，最终加载时间从 3 秒降到 1.2 秒，并复盘了方案。",
        "当时项目存在高并发问题；我主导容量评估和方案设计，因为需要兼顾成本与可靠性，最终支持日请求量提升 3 倍，并完成复盘。",
    ]
    levels = [score_fallback_answer(answer) for answer in answers]
    assert len(set(levels)) >= 4
    assert levels[-1] != levels[0]


def test_fallback_evidence_is_grounded():
    result = analyze_deterministic_answer("我负责性能优化并降低 30% 加载时间。", "c1", "性能优化")
    assert result.evidence
    assert all(item.excerpt in "我负责性能优化并降低 30% 加载时间。" for item in result.evidence)
```

- [ ] **Step 2: Run red test**

Run: `python -m pytest backend/tests/test_fallback_analysis.py -q`

Expected: FAIL because the module does not exist.

- [ ] **Step 3: Implement feature extraction and scoring**

Use deterministic regex and phrase checks. Suggested weights:

```python
WEIGHTS = {
    "situation": 1.0,
    "ownership": 1.5,
    "action": 2.0,
    "reasoning": 1.5,
    "result": 1.5,
    "metric": 1.5,
    "reflection": 1.0,
}
```

The function must return no evidence for empty input, `UNCERTAIN` or `MISSING` observations for weak answers, and multiple grounded `POSITIVE` observations for strong answers.

- [ ] **Step 4: Replace demo-only length check**

`analyze_answer` calls `analyze_deterministic_answer` whenever AI is disabled or no key is configured.

- [ ] **Step 5: Run fallback and scoring tests**

Run:

```powershell
python -m pytest backend/tests/test_fallback_analysis.py backend/tests/test_assessment_ai_contract.py backend/tests/test_stage3_scoring.py backend/tests/test_quality_samples.py -q
```

Expected: all pass, and deterministic outputs span at least four rubric levels.

---

### Task 4: Duplicate Follow-Up Turn Fix

**Files:**
- Modify: `backend/app/agent/interview_agent.py`
- Modify: `backend/app/agent/tools/question.py`
- Create: `backend/tests/test_duplicate_follow_up.py`

**Interfaces:**
- Produces: `_question_has_answer_after(db, session_id, question) -> bool`

- [ ] **Step 1: Write the failing regression test**

```python
def test_same_follow_up_text_creates_new_turn_after_previous_answer():
    # Start a session, persist follow-up A, answer it, then process another
    # insufficient answer whose deterministic follow-up text is identical.
    ...
    assert follow_up_turns[-1].turn_index > second_answer.turn_index
    assert follow_up_turns[-1].content != follow_up_turns[0].content
```

- [ ] **Step 2: Run the regression test**

Run: `python -m pytest backend/tests/test_duplicate_follow_up.py -q`

Expected: FAIL because the old turn is reused.

- [ ] **Step 3: Implement consumed-question detection**

Before returning an existing question in `_persist_question`, query for a user turn with:

```python
AssessmentTurn.role == AssessmentTurnRole.USER
AssessmentTurn.turn_index > existing.turn_index
```

If found, do not reuse the existing question.

- [ ] **Step 4: Make repeated deterministic follow-ups distinct**

Pass `follow_up_count` from agent context into `QuestionTool.generate_follow_up`. Prefix repeated prompts with:

```python
f"第 {follow_up_count} 次补充："
```

Keep the original analysis question text after the prefix.

- [ ] **Step 5: Run agent and API regression tests**

Run:

```powershell
python -m pytest backend/tests/test_duplicate_follow_up.py backend/tests/test_interview_agent.py backend/tests/test_assessment_api.py backend/tests/test_stage2_invariants.py -q
```

Expected: all pass.

---

### Task 5: 192-Case JD Reference Corpus

**Files:**
- Create: `harness/generate_jd_reference_models.py`
- Create: `harness/fixtures/quality/jd_reference_models.jsonl`
- Create: `backend/tests/test_jd_reference_models.py`
- Create: `harness/jd_quality.py`
- Create: `backend/tests/test_jd_quality_metrics.py`
- Modify: `harness/fixtures/quality/README.md`

**Interfaces:**
- Produces: `build_jd_reference_cases() -> list[dict]`
- Produces: `match_competencies(output_names, reference_competencies) -> dict`
- Produces: `compute_jd_metrics(rows) -> dict`

- [ ] **Step 1: Write the failing dataset contract test**

```python
def test_reference_corpus_has_192_independent_jds():
    rows = load_reference_rows()
    assert len(rows) == 192
    assert len({row["id"] for row in rows}) == 192
    assert len({row["jd_text"] for row in rows}) == 192
    assert len({row["role_family"] for row in rows}) == 24
    assert {row["seniority"] for row in rows} == {"JUNIOR", "MID", "SENIOR", "EXPERT"}
```

- [ ] **Step 2: Run red test**

Run: `python -m pytest backend/tests/test_jd_reference_models.py -q`

Expected: FAIL because the corpus is absent.

- [ ] **Step 3: Implement the curated generator**

Define 24 role profiles. For each profile create 8 variants by combining:

- seniority;
- industry context;
- responsibility emphasis;
- qualification and constraint;
- expression style;
- one adversarial instruction.

Each generated row must include a complete `reference_model` with normalized competencies, aliases, weights, indicators, evidence requirements, and exact source excerpts.

- [ ] **Step 4: Add matching metrics tests**

```python
def test_competency_metrics_use_aliases_without_text_similarity():
    reference = [{"canonical_name": "系统设计", "aliases": ["架构设计"], "weight": 1.0}]
    result = match_competencies(["架构设计", "虚构能力"], reference)
    assert result["matched"] == ["系统设计"]
    assert result["unexpected"] == ["虚构能力"]
    assert result["recall"] == 1.0
    assert result["precision"] == 0.5
```

- [ ] **Step 5: Run corpus and metrics tests**

Run:

```powershell
python harness/generate_jd_reference_models.py
python -m pytest backend/tests/test_jd_reference_models.py backend/tests/test_jd_quality_metrics.py -q
```

Expected: all pass; 192 rows, 24 role families, four seniority levels.

---

### Task 6: Structured Model Client and Quality Runner

**Files:**
- Create: `harness/config.toml`
- Create: `harness/model_profiles.py`
- Create: `harness/quality_runner.py`
- Create: `backend/app/services/structured_llm.py`
- Create: `backend/tests/test_structured_llm.py`
- Modify: `harness/.gitignore`

**Interfaces:**
- Produces: `ModelProfile(id, provider, model, base_url_env, api_key_env)`
- Produces: `StructuredLLMResult(content, latency_ms, usage, status, error)`
- Produces: `call_structured_json(profile, system_prompt, schema, user_payload, timeout=45) -> StructuredLLMResult`
- Produces CLI commands `check`, `run`, and `compare`.

- [ ] **Step 1: Write the failing transport test**

```python
def test_structured_client_records_latency_and_usage(monkeypatch):
    monkeypatch.setattr(...)
    result = call_structured_json(profile, "system", {"type": "object"}, {"input": "x"})
    assert result.status == "SUCCESS"
    assert result.latency_ms >= 0
    assert result.usage["total_tokens"] == 15
```

- [ ] **Step 2: Run red test**

Run: `python -m pytest backend/tests/test_structured_llm.py -q`

Expected: FAIL because the client does not exist.

- [ ] **Step 3: Implement profiles and the client**

The client returns structured success, `UNAVAILABLE`, `TIMEOUT`, `INVALID_JSON`, or `SCHEMA_ERROR`. It never raises raw provider exceptions to the Runner.

- [ ] **Step 4: Implement deterministic sample selection**

Use a fixed seed and stratified selection across role family, seniority, and expression style. Save selected IDs in `run.json`.

- [ ] **Step 5: Implement runner result rows**

Each JSONL result row records:

```json
{
  "case_id": "jd-ref-001",
  "model_id": "deepseek-chat",
  "prompt_version": "jd-parsing-v2",
  "status": "SUCCESS",
  "latency_ms": 1234,
  "usage": {"prompt_tokens": 100, "completion_tokens": 30, "total_tokens": 130},
  "metrics": {"precision": 0.8, "recall": 0.6, "evidence_support": 0.9},
  "error": null
}
```

- [ ] **Step 6: Run offline Runner checks**

Run:

```powershell
python harness/quality_runner.py check
python harness/quality_runner.py run --model deterministic-fallback
python -m pytest backend/tests/test_structured_llm.py -q
```

Expected: deterministic baseline completes without a key.

---

### Task 7: Real 20-Case Model Comparison

**Files:**
- Create: `docs/quality/2026-09-12-model-comparison.md`
- Generated, ignored: `harness/reports/quality/<run-id>/results.jsonl`
- Generated, ignored: `harness/reports/quality/<run-id>/summary.json`

**Interfaces:**
- Consumes: Task 6 Runner commands and Task 5 corpus.

- [ ] **Step 1: Run the deterministic baseline**

```powershell
python harness/quality_runner.py run --model deterministic-fallback
```

- [ ] **Step 2: Run 20 DeepSeek chat cases**

```powershell
python harness/quality_runner.py run --model deepseek-chat --sample-size 20
```

Expected: success rows contain latency and token usage; failures are recorded without retry loops.

- [ ] **Step 3: Run 20 DeepSeek reasoner cases**

```powershell
python harness/quality_runner.py run --model deepseek-reasoner --sample-size 20
```

Expected: if the model is unavailable or rejects structured output, the summary records `UNAVAILABLE` or `FAILED`.

- [ ] **Step 4: Compare runs**

```powershell
python harness/quality_runner.py compare --run <baseline-id> --run <chat-id> --run <reasoner-id>
```

- [ ] **Step 5: Write the summary**

Record model, prompt version, sample count, precision, recall, F1, evidence-support rate, unexpected-competency rate, p50, p95, token usage, failure count, and cost status. Include no secrets or raw prompts containing credentials.

---

### Task 8: Project Report and Documentation Update

**Files:**
- Modify: `README.md`
- Modify: `docs/requirements/阶段四：系统质量评估与持续优化.md`
- Modify: report builder used for `课程大作业报告-AI驱动的岗位胜任力测评与人才画像系统.docx`
- Modify: `课程大作业报告-AI驱动的岗位胜任力测评与人才画像系统.docx`

**Interfaces:**
- Consumes: all prior task results.

- [ ] **Step 1: Update project documentation**

Add exact commands for corpus generation, offline runner, live 20-case runs, and report aggregation. State that 192 reference JDs are project-maintainer curated, not external expert review.

- [ ] **Step 2: Update the DOCX**

Update system information, Prompt version tables, deterministic scoring explanation, corpus counts, model comparison table, latency/token table, duplicate-follow-up fix, and remaining limitations.

- [ ] **Step 3: Render and inspect**

Run:

```powershell
python -m pytest backend/tests -q
npm --prefix frontend run test
npm --prefix frontend run build
python -m pytest backend/tests/test_quality_samples.py backend/tests/test_jd_reference_models.py backend/tests/test_jd_quality_metrics.py -q
git diff --check
```

Render the DOCX through Word, inspect every page PNG, verify no blank pages, image content density, image dimensions, table headers, and accessibility.

---

## Plan Self-Review

### Spec Coverage

| Spec requirement | Implemented by |
|---|---|
| 170+ independent JD reference models | Task 5 |
| Deterministic rubric diversity | Task 3 |
| Prompt version directories and hashes | Task 1 |
| Multi-model comparison | Tasks 6-7 |
| Real latency and token statistics | Tasks 2, 6-7 |
| Duplicate follow-up fix | Task 4 |
| Project report update | Task 8 |
| No secrets or real personal data | Global constraints, Tasks 5, 7-8 |

### Type Consistency

- `PromptBundle` is produced once in Task 1 and consumed by Task 2 logging.
- `StructuredLLMResult` is produced in Task 6 and consumed by Task 7.
- `reference_model.competencies[*].canonical_name` is the common name used by the matcher in Task 5 and runner in Task 6.
- `run_id` is consistent across `LLMCallLog`, runner output, and comparison commands.

### Placeholder Scan

No `TBD`, `TODO`, "implement later", or "similar to previous task" placeholders remain. Generated report data from Tasks 6-8 is intentionally produced at execution time.
