from harness.quality_runner import aggregate_results, select_cases


def test_sample_selection_is_deterministic_and_unique() -> None:
    rows = [
        {
            "id": f"jd-ref-{index:03d}",
            "role_family": f"role-{index % 24}",
            "seniority": ["JUNIOR", "MID", "SENIOR", "EXPERT"][index % 4],
        }
        for index in range(1, 193)
    ]
    first = select_cases(rows, 20)
    second = select_cases(rows, 20)
    assert [row["id"] for row in first] == [row["id"] for row in second]
    assert len({row["id"] for row in first}) == 20
    assert len({row["role_family"] for row in first}) >= 20


def test_aggregate_results_reports_latency_and_quality() -> None:
    results = [
        {
            "status": "SUCCESS",
            "latency_ms": 100,
            "usage": {"total_tokens": 10},
            "metrics": {"precision": 1.0, "recall": 0.5, "f1": 0.6667},
        },
        {
            "status": "SUCCESS",
            "latency_ms": 300,
            "usage": {"total_tokens": 20},
            "metrics": {"precision": 0.5, "recall": 1.0, "f1": 0.6667},
        },
        {
            "status": "TIMEOUT",
            "latency_ms": 45000,
            "usage": {"total_tokens": 0},
            "metrics": None,
        },
    ]
    summary = aggregate_results(results)
    assert summary["total"] == 3
    assert summary["success"] == 2
    assert summary["failures"] == {"TIMEOUT": 1}
    assert summary["p50_latency_ms"] == 300
    assert summary["p95_latency_ms"] == 45000
    assert summary["total_tokens"] == 30
    assert summary["precision"] == 0.75
