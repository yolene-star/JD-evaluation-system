from __future__ import annotations

import os
import tomllib
from pathlib import Path

from backend.app.config import load_local_env
from backend.app.services.structured_llm import ModelProfile


ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = Path(__file__).resolve().parent / "config.toml"


def load_model_profiles() -> list[ModelProfile]:
    load_local_env(ROOT / "backend" / ".env")
    config = tomllib.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    profiles: list[ModelProfile] = []
    for item in config.get("models", []):
        profiles.append(
            ModelProfile(
                id=str(item["id"]),
                provider=str(item["provider"]),
                model=str(item["model"]),
                base_url=os.getenv(str(item.get("base_url_env", ""))) or "",
                api_key=os.getenv(str(item.get("api_key_env", ""))) or None,
            )
        )
    return profiles


def get_model_profile(model_id: str) -> ModelProfile:
    for profile in load_model_profiles():
        if profile.id == model_id:
            return profile
    raise KeyError(f"unknown model profile: {model_id}")
