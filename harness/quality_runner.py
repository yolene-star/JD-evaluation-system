from __future__ import annotations

import argparse
import json
import math
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.services.parsing import parse_jd
from backend.app.services.prompt_registry import load_prompt
from backend.app.services.structured_llm import ModelProfile, call_structured_json
from harness.jd_quality import match_competencies
from harness.model_profiles import get_model_profile


CORPUS = ROOT / "harness" / "fixtures" / "quality" / "jd_reference_models.jsonl"
REPORTS = ROOT / "harness" / "reports" / "quality"


def load_reference_cases() -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in CORPUS.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def select_cases(rows: list[dict[str, Any]], sample_size: int) -> list[dict[str, Any]]:
    if sample_size <= 0:
        raise ValueError("sample_size must be positive")
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[row["role_family"]].append(row)
    selected: list[dict[str, Any]] = []
    for family in sorted(grouped):
        family_rows = sorted(grouped[family], key=lambda item: item["id"])
        selected.append(family_rows[len(selected) % len(family_rows)])
        if len(selected) == sample_size:
            return selected
    index = 0
    while len(selected) < sample_size:
        candidate = rows[index % len(rows)]
        if candidate["id"] not in {item["id"] for item in selected}:
            selected.append(candidate)
        index += 1
    return selected


def _percentile(values: list[int], percentile: float) -> int:
    if not values:
        return 0
    ordered = sorted(values)
    index = max(0, math.ceil(percentile * len(ordered)) - 1)
    return ordered[index]


def aggregate_results(results: list[dict[str, Any]]) -> dict[str, Any]:
    successful = [row for row in results if row["status"] == "SUCCESS"]
    failures = Counter(row["status"] for row in results if row["status"] != "SUCCESS")
    metric_rows = [row["metrics"] for row in successful if row.get("metrics")]

    def average(name: str) -> float:
        if not metric_rows:
            return 0.0
        return sum(float(row.get(name, 0.0)) for row in metric_rows) / len(metric_rows)

    latencies = [int(row.get("latency_ms") or 0) for row in results]
    return {
        "total": len(results),
        "success": len(successful),
        "failures": dict(failures),
        "success_rate": len(successful) / len(results) if results else 0.0,
        "precision": average("precision"),
        "recall": average("recall"),
        "f1": average("f1"),
        "evidence_support": average("evidence_support"),
        "unexpected_rate": average("unexpected_rate"),
        "p50_latency_ms": _percentile(latencies, 0.5),
        "p95_latency_ms": _percentile(latencies, 0.95),
        "max_latency_ms": max(latencies, default=0),
        "total_tokens": sum(int(row.get("usage", {}).get("total_tokens", 0)) for row in results),
    }


def _metric_row(
    output_names: list[str],
    reference: dict[str, Any],
    jd_text: str,
    excerpts: list[str],
) -> dict[str, Any]:
    match = match_competencies(output_names, reference["competencies"])
    evidence_support = (
        sum(1 for excerpt in excerpts if excerpt and excerpt in jd_text) / len(excerpts)
        if excerpts
        else 1.0
    )
    unexpected_rate = len(match["unexpected"]) / len(output_names) if output_names else 1.0
    return {
        **match,
        "evidence_support": evidence_support,
        "unexpected_rate": unexpected_rate,
    }


def run_deterministic(cases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for case in cases:
        started = time.perf_counter()
        parsed = parse_jd(case["jd_text"])
        latency_ms = round((time.perf_counter() - started) * 1000)
        output_names = [item.name for item in parsed.competencies]
        excerpts = [item.excerpt for item in parsed.competencies]
        rows.append(
            {
                "case_id": case["id"],
                "model_id": "deterministic-fallback",
                "prompt_version": "deterministic",
                "status": "SUCCESS",
                "latency_ms": latency_ms,
                "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
                "output_names": output_names,
                "metrics": _metric_row(
                    output_names,
                    case["reference_model"],
                    case["jd_text"],
                    excerpts,
                ),
                "error": None,
            }
        )
    return rows


def run_model(profile: ModelProfile, cases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    prompt = load_prompt("jd_parsing", "v2")
    rows: list[dict[str, Any]] = []
    for case in cases:
        result = call_structured_json(
            profile,
            prompt.system,
            prompt.schema,
            {"jd_text": case["jd_text"]},
        )
        metrics = None
        output_names: list[str] = []
        if result.status == "SUCCESS" and result.content is not None:
            competencies = result.content.get("competencies") or []
            output_names = [
                str(item.get("name") or "")
                for item in competencies
                if isinstance(item, dict) and item.get("name")
            ]
            excerpts = [
                str(item.get("evidence_excerpt") or "")
                for item in competencies
                if isinstance(item, dict)
            ]
            metrics = _metric_row(
                output_names,
                case["reference_model"],
                case["jd_text"],
                excerpts,
            )
        rows.append(
            {
                "case_id": case["id"],
                "model_id": profile.id,
                "prompt_version": "jd-parsing-v2",
                "status": result.status,
                "latency_ms": result.latency_ms,
                "usage": result.usage,
                "output_names": output_names,
                "metrics": metrics,
                "error": result.error,
            }
        )
    return rows


def _write_run(profile: ModelProfile, cases: list[dict[str, Any]], results: list[dict[str, Any]]) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_id = f"{stamp}-{profile.id}"
    output = REPORTS / run_id
    output.mkdir(parents=True, exist_ok=True)
    (output / "run.json").write_text(
        json.dumps(
            {
                "run_id": run_id,
                "model_id": profile.id,
                "model": profile.model,
                "sample_size": len(cases),
                "case_ids": [case["id"] for case in cases],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    (output / "results.jsonl").write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in results),
        encoding="utf-8",
    )
    (output / "summary.json").write_text(
        json.dumps(aggregate_results(results), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return run_id


def command_check() -> int:
    rows = load_reference_cases()
    assert len(rows) == 192
    print(f"reference corpus OK: {len(rows)} cases")
    return 0


def command_run(model_id: str, sample_size: int) -> int:
    profile = get_model_profile(model_id)
    cases = select_cases(load_reference_cases(), sample_size)
    results = run_deterministic(cases) if profile.provider == "local" else run_model(profile, cases)
    run_id = _write_run(profile, cases, results)
    summary = aggregate_results(results)
    print(json.dumps({"run_id": run_id, **summary}, ensure_ascii=False, indent=2))
    return 0


def command_compare(run_ids: list[str]) -> int:
    summary: dict[str, Any] = {}
    for run_id in run_ids:
        path = REPORTS / run_id / "summary.json"
        summary[run_id] = json.loads(path.read_text(encoding="utf-8"))
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("check")
    run_parser = subparsers.add_parser("run")
    run_parser.add_argument("--model", required=True)
    run_parser.add_argument("--sample-size", type=int, default=20)
    compare_parser = subparsers.add_parser("compare")
    compare_parser.add_argument("--run", action="append", required=True)
    args = parser.parse_args()
    if args.command == "check":
        return command_check()
    if args.command == "run":
        return command_run(args.model, args.sample_size)
    return command_compare(args.run)


if __name__ == "__main__":
    raise SystemExit(main())
