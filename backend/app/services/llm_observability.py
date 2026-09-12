from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from ..models import LLMCallLog


def record_llm_call(
    db: Session,
    *,
    project_id: str,
    task_type: str,
    model: str,
    prompt_version: str,
    status: str,
    latency_ms: int | None = None,
    error: str | None = None,
    run_id: str | None = None,
    usage: dict[str, Any] | None = None,
) -> LLMCallLog:
    if latency_ms is not None and latency_ms < 0:
        raise ValueError("latency_ms must be non-negative")
    row = LLMCallLog(
        project_id=project_id,
        run_id=run_id,
        task_type=task_type,
        model=model,
        prompt_version=prompt_version,
        status=status,
        latency_ms=latency_ms,
        usage_json=dict(usage or {}),
        error=error,
    )
    db.add(row)
    return row
