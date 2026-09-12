from __future__ import annotations

import re
from typing import Iterable


def normalize_name(value: str) -> str:
    return re.sub(r"[\s\-_/（）()·]+", "", value).lower()


def match_competencies(
    output_names: Iterable[str],
    reference_competencies: list[dict],
) -> dict:
    lookup: dict[str, str] = {}
    canonical_names: list[str] = []
    for item in reference_competencies:
        canonical = str(item["canonical_name"])
        canonical_names.append(canonical)
        for name in [canonical, *(item.get("aliases") or [])]:
            lookup[normalize_name(str(name))] = canonical

    matched: list[str] = []
    unexpected: list[str] = []
    for raw_name in output_names:
        normalized = normalize_name(str(raw_name))
        canonical = lookup.get(normalized)
        if canonical is None:
            unexpected.append(str(raw_name))
            continue
        if canonical not in matched:
            matched.append(canonical)

    missing = [name for name in canonical_names if name not in matched]
    true_positive = len(matched)
    precision = true_positive / (true_positive + len(unexpected)) if true_positive + len(unexpected) else 0.0
    recall = true_positive / len(canonical_names) if canonical_names else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {
        "matched": matched,
        "missing": missing,
        "unexpected": unexpected,
        "precision": precision,
        "recall": recall,
        "f1": f1,
    }
