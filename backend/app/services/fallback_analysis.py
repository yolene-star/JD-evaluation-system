from __future__ import annotations

import re
from dataclasses import dataclass

from ..models import EvidenceType
from .assessment_ai import AnalysisResult, EvidenceResult


REFUSAL_PATTERN = re.compile(r"^(我不会|不会|不知道|没有经验|暂无经验|不清楚)[。！!，,、\s]*$")
METRIC_PATTERN = re.compile(
    r"\d+(?:\.\d+)?\s*(?:%|％|倍|毫秒|ms|秒|分钟|小时|天|周|月|次|人|个|元|万元)"
)


@dataclass(frozen=True)
class FallbackFeatures:
    situation: bool
    ownership: bool
    action: bool
    reasoning: bool
    result: bool
    metric: bool
    reflection: bool
    specificity: bool

    @property
    def score(self) -> float:
        values = {
            "situation": 1.0,
            "ownership": 1.5,
            "action": 1.5,
            "reasoning": 1.5,
            "result": 1.5,
            "metric": 1.5,
            "reflection": 0.5,
            "specificity": 1.0,
        }
        return min(10.0, sum(value for name, value in values.items() if getattr(self, name)))


def extract_fallback_features(answer: str) -> FallbackFeatures:
    text = answer.strip()
    return FallbackFeatures(
        situation=any(word in text for word in ("当时", "背景", "项目", "场景", "情境", "面临")),
        ownership=bool(
            re.search(
                r"我.{0,8}(?:负责|主导|设计|实现|推动|协调|完成|承担|参与|制定|通过)",
                text,
            )
        ),
        action=any(
            word in text
            for word in ("优化", "设计", "实现", "开发", "分析", "协调", "推动", "交付", "改进", "部署", "上线")
        ),
        reasoning=any(word in text for word in ("因为", "依据", "权衡", "考虑到", "目标", "为了", "判断")),
        result=any(
            word in text
            for word in ("最终", "结果", "完成", "上线", "交付", "提升", "降低", "减少", "改善", "达成")
        ),
        metric=bool(METRIC_PATTERN.search(text)),
        reflection=any(word in text for word in ("复盘", "反思", "改进", "后续", "总结")),
        specificity=len(text) >= 30 and len(re.split(r"[。！？!?；;\n]+", text)) >= 1,
    )


def _positive_snippets(answer: str, features: FallbackFeatures) -> list[str]:
    text = answer.strip()
    snippets = [text] if text else []
    metric = METRIC_PATTERN.search(text)
    if metric and metric.group() not in snippets:
        snippets.append(metric.group())
    for pattern in (
        r"(?:最终|结果|完成|上线|交付|提升|降低|减少|改善|达成)[^。！？!?；;]{0,40}",
        r"我(?:负责|主导|设计|实现|推动|协调|完成|承担|制定)[^。！？!?；;]{0,40}",
    ):
        match = re.search(pattern, text)
        if match and match.group().strip() not in snippets:
            snippets.append(match.group().strip())
    if features.reasoning and text not in snippets:
        snippets.append(text)
    return [snippet for snippet in snippets if snippet and snippet in text]


def analyze_deterministic_answer(answer: str, competency_id: str, competency_name: str) -> AnalysisResult:
    text = answer.strip()
    if not text:
        return AnalysisResult(
            answer_summary="未提供回答",
            evidence=[],
            evidence_sufficiency="INSUFFICIENT",
            needs_follow_up=True,
            follow_up_reason="回答为空，缺少可验证证据",
            follow_up_question=f"请描述一次与你目标岗位相关的实际经历，重点说明你在{competency_name}中的具体做法、依据和结果。",
        )
    if REFUSAL_PATTERN.search(text):
        return AnalysisResult(
            answer_summary=text,
            evidence=[
                EvidenceResult(
                    competency_id=competency_id,
                    type=EvidenceType.UNCERTAIN,
                    excerpt=text,
                    summary="回答表示暂时没有可提供的证据",
                    confidence=0.2,
                )
            ],
            evidence_sufficiency="INSUFFICIENT",
            needs_follow_up=True,
            follow_up_reason="缺少本人行动、判断依据和可验证结果",
            follow_up_question=f"请从一个小而具体的例子开始，说明你在{competency_name}中做了什么、依据是什么、结果如何。",
        )

    features = extract_fallback_features(text)
    score = features.score
    snippets = _positive_snippets(text, features)
    evidence: list[EvidenceResult] = []
    if score >= 4:
        positive_count = 1 if score < 7 else 3
        for snippet in snippets[:positive_count]:
            evidence.append(
                EvidenceResult(
                    competency_id=competency_id,
                    type=EvidenceType.POSITIVE,
                    excerpt=snippet,
                    summary="确定性分析识别到回答中的行动、依据或结果特征",
                    confidence=min(0.9, 0.45 + score / 20),
                )
            )
    if 4 <= score < 9:
        missing_name = "量化结果" if not features.metric else "复盘或改进"
        evidence.append(
            EvidenceResult(
                competency_id=competency_id,
                type=EvidenceType.MISSING,
                excerpt=text,
                summary=f"回答未提供完整的{missing_name}",
                confidence=0.5,
            )
        )

    sufficient = score >= 9
    if sufficient:
        return AnalysisResult(
            answer_summary=text,
            evidence=evidence,
            evidence_sufficiency="SUFFICIENT",
            needs_follow_up=False,
            matched_evidence_requirements=[
                name
                for name, present in (
                    ("本人行动", features.ownership or features.action),
                    ("判断依据", features.reasoning),
                    ("可验证结果", features.result or features.metric),
                )
                if present
            ],
        )
    return AnalysisResult(
        answer_summary=text,
        evidence=evidence,
        evidence_sufficiency="UNCERTAIN" if score >= 4 else "INSUFFICIENT",
        needs_follow_up=True,
        follow_up_reason="回答仍需补充具体依据、可验证结果或复盘",
        follow_up_question=f"请补充说明你在{competency_name}中的具体做法、判断依据和可验证结果。",
        missing_evidence_requirements=[
            name
            for name, missing in (
                ("本人行动", not (features.ownership or features.action)),
                ("判断依据", not features.reasoning),
                ("可验证结果", not (features.result or features.metric)),
                ("复盘改进", not features.reflection),
            )
            if missing
        ],
    )
