from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.db import Base
from backend.app.services.llm_observability import record_llm_call


def session_factory():
    engine = create_engine("sqlite://", poolclass=StaticPool)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)()


def test_llm_call_records_run_latency_and_tokens() -> None:
    db = session_factory()
    try:
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
    finally:
        db.close()


def test_llm_call_rejects_negative_latency() -> None:
    db = session_factory()
    try:
        try:
            record_llm_call(
                db,
                project_id="p1",
                task_type="jd_parse",
                model="deepseek-chat",
                prompt_version="jd-parsing-v2",
                status="SUCCESS",
                latency_ms=-1,
            )
        except ValueError as error:
            assert "latency" in str(error)
        else:
            raise AssertionError("negative latency should be rejected")
    finally:
        db.close()
