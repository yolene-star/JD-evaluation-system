import json

import pytest

from backend.app.services.structured_llm import ModelProfile, call_structured_json


class FakeResponse:
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def read(self) -> bytes:
        return json.dumps(
            {
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {"competencies": [], "requirements": [], "constraints": []},
                                ensure_ascii=False,
                            )
                        }
                    }
                ],
                "usage": {
                    "prompt_tokens": 10,
                    "completion_tokens": 5,
                    "total_tokens": 15,
                },
            },
            ensure_ascii=False,
        ).encode("utf-8")


def profile() -> ModelProfile:
    return ModelProfile(
        id="test-model",
        provider="openai-compatible",
        model="test-chat",
        base_url="https://example.invalid",
        api_key="test-key",
    )


def test_structured_client_records_latency_and_usage(monkeypatch) -> None:
    monkeypatch.setattr(
        "backend.app.services.structured_llm.urlopen",
        lambda *_args, **_kwargs: FakeResponse(),
    )
    result = call_structured_json(
        profile(),
        "system",
        {"type": "object"},
        {"input": "x"},
    )
    assert result.status == "SUCCESS"
    assert result.content["competencies"] == []
    assert result.latency_ms >= 0
    assert result.usage["total_tokens"] == 15


def test_structured_client_validates_schema(monkeypatch) -> None:
    class InvalidResponse(FakeResponse):
        def read(self) -> bytes:
            return json.dumps(
                {
                    "choices": [{"message": {"content": "{\"wrong\": true}"}}],
                    "usage": {"total_tokens": 4},
                }
            ).encode("utf-8")

    monkeypatch.setattr(
        "backend.app.services.structured_llm.urlopen",
        lambda *_args, **_kwargs: InvalidResponse(),
    )
    result = call_structured_json(
        profile(),
        "system",
        {"type": "object", "required": ["competencies"]},
        {"input": "x"},
    )
    assert result.status == "SCHEMA_ERROR"
    assert result.content is None
