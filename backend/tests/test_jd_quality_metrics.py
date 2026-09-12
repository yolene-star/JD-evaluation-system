from harness.jd_quality import match_competencies


def test_competency_metrics_use_aliases_without_text_similarity() -> None:
    reference = [
        {
            "canonical_name": "系统设计",
            "aliases": ["架构设计"],
            "weight": 1.0,
        }
    ]
    result = match_competencies(["架构设计", "虚构能力"], reference)
    assert result["matched"] == ["系统设计"]
    assert result["unexpected"] == ["虚构能力"]
    assert result["recall"] == 1.0
    assert result["precision"] == 0.5
    assert result["f1"] == 2 / 3


def test_competency_metrics_report_missing_reference_items() -> None:
    reference = [
        {"canonical_name": "需求分析", "aliases": ["需求梳理"], "weight": 0.6},
        {"canonical_name": "数据分析", "aliases": [], "weight": 0.4},
    ]
    result = match_competencies(["需求梳理"], reference)
    assert result["matched"] == ["需求分析"]
    assert result["missing"] == ["数据分析"]
    assert result["recall"] == 0.5
