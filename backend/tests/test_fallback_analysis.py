from backend.app.services.fallback_analysis import analyze_deterministic_answer
from backend.app.services.scoring import score_competency


ANSWERS = [
    "不清楚",
    "我参与过相关工作，负责协助团队优化流程，最终按时完成基础任务。",
    "我负责性能优化，使用了监控工具，最终加载时间从 3 秒降到 1.2 秒，并复盘了方案。",
    "当时项目存在高并发问题；我主导容量评估和方案设计，因为需要兼顾成本与可靠性，最终支持日请求量提升 3 倍，并完成复盘。",
]


def _score(answer: str) -> float:
    analysis = analyze_deterministic_answer(answer, "c1", "性能优化")
    result = score_competency(
        competency_id="c1",
        status="EXHAUSTED",
        rubric={"indicators": []},
        observations=[item.model_dump() for item in analysis.evidence],
    )
    return float(result.score or 0)


def test_fallback_analysis_produces_multiple_rubric_levels() -> None:
    scores = [_score(answer) for answer in ANSWERS]
    assert len(set(scores)) >= 4, scores
    assert scores[-1] == 10.0
    assert scores[0] == 0.0


def test_fallback_evidence_is_grounded() -> None:
    answer = "我负责性能优化并降低 30% 加载时间。"
    result = analyze_deterministic_answer(answer, "c1", "性能优化")
    assert result.evidence
    assert all(item.excerpt in answer for item in result.evidence)
    assert all(item.competency_id == "c1" for item in result.evidence)


def test_empty_answer_produces_no_evidence() -> None:
    result = analyze_deterministic_answer("", "c1", "性能优化")
    assert result.evidence == []
    assert result.evidence_sufficiency == "INSUFFICIENT"
    assert result.needs_follow_up is True
