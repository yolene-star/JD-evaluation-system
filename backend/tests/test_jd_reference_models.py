import json
import re
from collections import Counter
from pathlib import Path

import pytest


CORPUS = (
    Path(__file__).resolve().parents[2]
    / "harness"
    / "fixtures"
    / "quality"
    / "jd_reference_models.jsonl"
)
PII_PATTERN = re.compile(r"\b1[3-9]\d{9}\b|[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}")


def load_rows() -> list[dict]:
    return [
        json.loads(line)
        for line in CORPUS.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def test_reference_corpus_has_192_independent_jds() -> None:
    assert CORPUS.is_file()
    rows = load_rows()
    assert len(rows) == 192
    assert len({row["id"] for row in rows}) == 192
    assert len({row["jd_text"] for row in rows}) == 192
    assert len({row["role_family"] for row in rows}) == 24
    assert {row["seniority"] for row in rows} == {"JUNIOR", "MID", "SENIOR", "EXPERT"}


def test_reference_models_are_weighted_and_traceable() -> None:
    for row in load_rows():
        model = row["reference_model"]
        assert model["competencies"]
        assert abs(sum(item["weight"] for item in model["competencies"]) - 1.0) < 1e-9
        assert len({item["canonical_name"] for item in model["competencies"]}) == len(model["competencies"])
        for item in model["competencies"]:
            assert item["indicators"]
            assert item["evidence_requirements"]
            assert item["evidence_excerpts"]
            assert all(excerpt in row["jd_text"] for excerpt in item["evidence_excerpts"])


def test_reference_corpus_has_no_real_pii() -> None:
    serialized = CORPUS.read_text(encoding="utf-8")
    assert not PII_PATTERN.search(serialized)


def test_role_families_have_eight_variants() -> None:
    counts = Counter(row["role_family"] for row in load_rows())
    assert set(counts.values()) == {8}
