from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[3]
MANIFEST_PATH = PROJECT_ROOT / "prompts" / "manifest.json"


@dataclass(frozen=True)
class PromptBundle:
    task: str
    version: str
    system: str
    schema: dict[str, Any]
    sha256: str


@lru_cache(maxsize=1)
def _manifest() -> dict[str, dict[str, str]]:
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


@lru_cache(maxsize=None)
def load_prompt(task: str, version: str = "v2") -> PromptBundle:
    manifest = _manifest()
    if task not in manifest:
        raise KeyError(f"unknown prompt task: {task}")
    entry = manifest[task]
    if entry["version"] != version:
        raise KeyError(f"{task} has no prompt version {version}")
    system_path = PROJECT_ROOT / entry["system"]
    schema_path = PROJECT_ROOT / entry["schema"]
    system_bytes = system_path.read_bytes()
    schema_bytes = schema_path.read_bytes()
    system = system_bytes.decode("utf-8")
    schema = json.loads(schema_bytes.decode("utf-8"))
    digest = hashlib.sha256(system_bytes + b"\0" + schema_bytes).hexdigest()
    return PromptBundle(task=task, version=version, system=system, schema=schema, sha256=digest)


JD_PARSE_PROMPT_VERSION = "jd-parsing-v2"
QUESTION_PROMPT_VERSION = "question-v2"
ANALYSIS_PROMPT_VERSION = "analysis-v2"
PROFILE_PROMPT_VERSION = "profile-v2"
