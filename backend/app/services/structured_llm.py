from __future__ import annotations

import json
import socket
import time
from dataclasses import dataclass
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


@dataclass(frozen=True)
class ModelProfile:
    id: str
    provider: str
    model: str
    base_url: str
    api_key: str | None = None
    timeout_seconds: int = 45


@dataclass(frozen=True)
class StructuredLLMResult:
    content: dict[str, Any] | None
    latency_ms: int
    usage: dict[str, int]
    status: str
    error: str | None = None


def _matches_type(value: Any, expected: str) -> bool:
    if expected == "object":
        return isinstance(value, dict)
    if expected == "array":
        return isinstance(value, list)
    if expected == "string":
        return isinstance(value, str)
    if expected == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if expected == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected == "boolean":
        return isinstance(value, bool)
    if expected == "null":
        return value is None
    return True


def validate_payload(schema: dict[str, Any], value: Any, path: str = "$") -> None:
    expected = schema.get("type")
    if expected is not None:
        options = expected if isinstance(expected, list) else [expected]
        if not any(_matches_type(value, option) for option in options):
            raise ValueError(f"{path} expected {expected}")
    if "enum" in schema and value not in schema["enum"]:
        raise ValueError(f"{path} is outside enum")
    if isinstance(value, dict):
        for name in schema.get("required", []):
            if name not in value:
                raise ValueError(f"{path}.{name} is required")
        for name, child_schema in schema.get("properties", {}).items():
            if name in value:
                validate_payload(child_schema, value[name], f"{path}.{name}")
    if isinstance(value, list):
        if len(value) < schema.get("minItems", 0):
            raise ValueError(f"{path} has too few items")
        if "maxItems" in schema and len(value) > schema["maxItems"]:
            raise ValueError(f"{path} has too many items")
        item_schema = schema.get("items")
        if item_schema:
            for index, item in enumerate(value):
                validate_payload(item_schema, item, f"{path}[{index}]")


def call_structured_json(
    profile: ModelProfile,
    system_prompt: str,
    schema: dict[str, Any],
    user_payload: dict[str, Any],
    *,
    timeout: int | None = None,
    transport: Callable[..., Any] | None = None,
) -> StructuredLLMResult:
    if profile.provider == "local":
        return StructuredLLMResult(
            content=None,
            latency_ms=0,
            usage={"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
            status="UNAVAILABLE",
            error="local profile must be handled by its deterministic runner",
        )
    if not profile.api_key:
        return StructuredLLMResult(
            content=None,
            latency_ms=0,
            usage={"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
            status="UNAVAILABLE",
            error=f"missing API key for {profile.id}",
        )

    payload = {
        "model": profile.model,
        "temperature": 0.1,
        "response_format": {"type": "json_object"},
        "messages": [
            {
                "role": "system",
                "content": f"{system_prompt}\n\nJSON Schema：{json.dumps(schema, ensure_ascii=False)}",
            },
            {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)},
        ],
    }
    started = time.perf_counter()
    try:
        if transport is not None:
            response_body = transport(payload)
        else:
            request = Request(
                profile.base_url.rstrip("/") + "/v1/chat/completions",
                data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                headers={
                    "Authorization": f"Bearer {profile.api_key}",
                    "Content-Type": "application/json",
                },
            )
            with urlopen(request, timeout=timeout or profile.timeout_seconds) as response:
                response_body = response.read().decode("utf-8")
        body = json.loads(response_body)
        content = body["choices"][0]["message"]["content"]
        if isinstance(content, str):
            content = json.loads(content)
        if not isinstance(content, dict):
            raise ValueError("model content is not a JSON object")
        validate_payload(schema, content)
        usage = body.get("usage") or {}
        latency_ms = round((time.perf_counter() - started) * 1000)
        return StructuredLLMResult(
            content=content,
            latency_ms=latency_ms,
            usage={
                "prompt_tokens": int(usage.get("prompt_tokens", 0) or 0),
                "completion_tokens": int(usage.get("completion_tokens", 0) or 0),
                "total_tokens": int(usage.get("total_tokens", 0) or 0),
            },
            status="SUCCESS",
        )
    except (socket.timeout, TimeoutError) as exc:
        return StructuredLLMResult(
            content=None,
            latency_ms=round((time.perf_counter() - started) * 1000),
            usage={"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
            status="TIMEOUT",
            error=str(exc)[:300],
        )
    except json.JSONDecodeError as exc:
        return StructuredLLMResult(
            content=None,
            latency_ms=round((time.perf_counter() - started) * 1000),
            usage={"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
            status="INVALID_JSON",
            error=str(exc)[:300],
        )
    except ValueError as exc:
        return StructuredLLMResult(
            content=None,
            latency_ms=round((time.perf_counter() - started) * 1000),
            usage={"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
            status="SCHEMA_ERROR",
            error=str(exc)[:300],
        )
    except (HTTPError, URLError, OSError) as exc:
        return StructuredLLMResult(
            content=None,
            latency_ms=round((time.perf_counter() - started) * 1000),
            usage={"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
            status="FAILED",
            error=str(exc)[:300],
        )
