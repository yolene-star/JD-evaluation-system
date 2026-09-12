import pytest

from backend.app.services.prompt_registry import load_prompt


def test_prompt_registry_loads_and_hashes_known_prompt() -> None:
    prompt = load_prompt("analysis", "v2")
    assert prompt.version == "v2"
    assert prompt.system
    assert prompt.schema["type"] == "object"
    assert len(prompt.sha256) == 64


def test_prompt_registry_rejects_unknown_task() -> None:
    with pytest.raises(KeyError):
        load_prompt("missing", "v2")


def test_prompt_registry_rejects_unknown_version() -> None:
    with pytest.raises(KeyError):
        load_prompt("analysis", "v99")
