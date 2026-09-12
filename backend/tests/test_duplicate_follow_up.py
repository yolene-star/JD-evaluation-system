from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.agent.interview_agent import InterviewAgent
from backend.app.agent.tools.question import QuestionTool
from backend.app.db import Base
from backend.app.models import (
    AssessmentSession,
    AssessmentTurn,
    AssessmentTurnRole,
    AssessmentTurnType,
    CompetencyAssessment,
    CompetencyAssessmentStatus,
    ModelSnapshot,
    ModelVersion,
    ModelVersionStatus,
    Project,
)
from backend.app.services.assessment_ai import AnalysisResult, GeneratedQuestion


def _session():
    engine = create_engine("sqlite://", poolclass=StaticPool)
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine, expire_on_commit=False)()
    project = Project(id="p1", name="重复追问测试")
    model = ModelVersion(
        id="m1",
        project_id=project.id,
        version="v1.0",
        status=ModelVersionStatus.CONFIRMED,
    )
    db.add_all([project, model])
    db.flush()
    db.add(
        ModelSnapshot(
            model_version_id=model.id,
            version="v1.0",
            snapshot_json={
                "project_id": project.id,
                "competencies": [
                    {
                        "id": "c1",
                        "name": "性能优化",
                        "description": "",
                        "weight": 1.0,
                        "evidence_ids": [],
                    }
                ],
            },
        )
    )
    assessment = AssessmentSession(id="s1", project_id=project.id, model_version_id=model.id)
    db.add(assessment)
    db.flush()
    item = CompetencyAssessment(
        id="ca1",
        session_id=assessment.id,
        competency_id="c1",
        status=CompetencyAssessmentStatus.FOLLOW_UP,
    )
    db.add(item)
    db.flush()
    return db, assessment


def test_same_follow_up_creates_new_turn_after_previous_answer() -> None:
    db, session = _session()
    try:
        old_question = AssessmentTurn(
            session_id=session.id,
            competency_assessment_id="ca1",
            turn_index=1,
            role=AssessmentTurnRole.SYSTEM,
            turn_type=AssessmentTurnType.FOLLOW_UP,
            content="请补充项目结果",
            covered_competency_ids=["c1"],
        )
        answer = AssessmentTurn(
            session_id=session.id,
            competency_assessment_id="ca1",
            turn_index=2,
            role=AssessmentTurnRole.USER,
            turn_type=AssessmentTurnType.ANSWER,
            content="不清楚",
            covered_competency_ids=["c1"],
        )
        db.add_all([old_question, answer])
        db.flush()

        result = InterviewAgent(db)._persist_question(
            session,
            "c1",
            GeneratedQuestion(
                content="请补充项目结果",
                covered_competency_ids=["c1"],
                turn_type="FOLLOW_UP",
            ),
        )
        db.flush()
        follow_up_count = db.scalar(
            select(func.count())
            .select_from(AssessmentTurn)
            .where(
                AssessmentTurn.session_id == session.id,
                AssessmentTurn.turn_type == AssessmentTurnType.FOLLOW_UP,
            )
        )
        assert result["id"] != old_question.id
        assert follow_up_count == 2
    finally:
        db.close()


def test_repeated_follow_up_text_identifies_attempt_number() -> None:
    item = type("Competency", (), {"id": "c1", "name": "性能优化"})()
    analysis = AnalysisResult(
        answer_summary="不清楚",
        evidence=[],
        evidence_sufficiency="INSUFFICIENT",
        needs_follow_up=True,
        follow_up_reason="缺少结果",
        follow_up_question="请补充项目结果",
    )
    question = QuestionTool().generate_follow_up(
        competency=item,
        analysis=analysis,
        follow_up_count=2,
    )
    assert question.content.startswith("第 2 次补充：")
