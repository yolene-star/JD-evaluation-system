"""Versioned prompt metadata for the stage-three narrative adapter."""

from .prompt_registry import PROFILE_PROMPT_VERSION as _PROFILE_PROMPT_VERSION, load_prompt


PROFILE_PROMPT_VERSION = _PROFILE_PROMPT_VERSION


def build_profile_prompt(facts: dict) -> str:
    return (
        load_prompt("profile", "v2").system
        + "\n\n"
        f"\n事实：{facts}"
    )
