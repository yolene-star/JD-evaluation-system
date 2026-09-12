from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

import pytest
from pydantic import ValidationError

from backend.app.services.assessment_ai import GeneratedQuestion, analyze_answer, validate_source_excerpt
from backend.app.services.assessment_contracts import ConfirmedCompetency, ConfirmedModelSnapshot
from backend.app.services.parsing import parse_jd
from backend.app.services.scoring import score_competency


SAMPLE_PATH = Path(__file__).resolve().parents[2] / "harness" / "fixtures" / "quality" / "samples.jsonl"
EXPECTED_TOTAL = 100
EXPECTED_DISTRIBUTION = {
    "jd_parse": 50,
    "answer_analysis": 35,
    "scoring_boundary": 5,
    "excerpt_validation": 5,
    "question_contract": 5,
}
PII_PATTERN = re.compile(r"\b1[3-9]\d{9}\b|[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}")


def load_samples() -> list[dict]:
    if not SAMPLE_PATH.is_file():
        return []
    return [
        json.loads(line)
        for line in SAMPLE_PATH.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def test_quality_sample_dataset_contract() -> None:
    assert SAMPLE_PATH.is_file(), f"missing quality sample dataset: {SAMPLE_PATH}"
    samples = load_samples()
    assert len(samples) == EXPECTED_TOTAL
    assert len({sample["id"] for sample in samples}) == EXPECTED_TOTAL
    assert Counter(sample["type"] for sample in samples) == EXPECTED_DISTRIBUTION

    required = {"id", "type", "tags", "input", "expected", "notes"}
    for sample in samples:
        assert required <= sample.keys()
        assert sample["tags"], sample["id"]
        assert sample["notes"].strip(), sample["id"]
        assert not PII_PATTERN.search(json.dumps(sample, ensure_ascii=False)), sample["id"]


@pytest.mark.parametrize("sample", load_samples(), ids=lambda sample: sample["id"])
def test_quality_sample_behavior(sample: dict) -> None:
    sample_type = sample["type"]
    if sample_type == "jd_parse":
        _assert_jd_parse(sample)
    elif sample_type == "answer_analysis":
        _assert_answer_analysis(sample)
    elif sample_type == "scoring_boundary":
        _assert_scoring_boundary(sample)
    elif sample_type == "excerpt_validation":
        _assert_excerpt_validation(sample)
    elif sample_type == "question_contract":
        _assert_question_contract(sample)
    else:
        raise AssertionError(f"unsupported sample type: {sample_type}")


def _assert_jd_parse(sample: dict) -> None:
    text = sample["input"]
    result = parse_jd(text)
    assert {item.name for item in result.competencies} == set(sample["expected"]["competencies"])
    assert set(result.qualifications) == set(sample["expected"]["qualifications"])
    assert set(result.constraints) == set(sample["expected"]["constraints"])
    assert all(item.excerpt in text for item in result.competencies)
    assert all(item.evidence_ids for item in result.competencies)


def _assert_answer_analysis(sample: dict) -> None:
    competency_name = sample["expected"]["competency"]
    snapshot = ConfirmedModelSnapshot(
        "m1",
        "p1",
        "v1.0",
        (ConfirmedCompetency("c1", competency_name, "", 1.0, ()),),
    )
    result = analyze_answer(snapshot, snapshot.competencies[0], [], [], sample["input"])
    assert result.evidence_sufficiency == sample["expected"]["evidence_sufficiency"]
    assert result.needs_follow_up is sample["expected"]["needs_follow_up"]
    assert len(result.evidence) >= sample["expected"]["evidence_count_min"]
    assert all(validate_source_excerpt(sample["input"], item.excerpt) for item in result.evidence)
    assert all(item.competency_id == "c1" for item in result.evidence)


def _assert_scoring_boundary(sample: dict) -> None:
    payload = sample["input"]
    result = score_competency(
        competency_id="c1",
        status=payload["status"],
        rubric=payload["rubric"],
        observations=payload["observations"],
    )
    for field in ("score", "attainment", "level"):
        assert getattr(result, field) == sample["expected"][field]


def _assert_excerpt_validation(sample: dict) -> None:
    payload = sample["input"]
    assert validate_source_excerpt(payload["answer"], payload["excerpt"]) is sample["expected"]["valid"]


def _assert_question_contract(sample: dict) -> None:
    payload = sample["input"]
    if sample["expected"]["valid"]:
        result = GeneratedQuestion.model_validate(payload)
        assert result.covered_competency_ids == payload["covered_competency_ids"]
    else:
        with pytest.raises(ValidationError):
            GeneratedQuestion.model_validate(payload)
