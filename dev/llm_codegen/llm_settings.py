#!/usr/bin/env python3
import json
import os
from pathlib import Path

DEFAULT_SETTINGS = {
    "api_key": "",
    "base_url": "https://api.siliconflow.cn/v1",
    "model": "deepseek-ai/DeepSeek-V3.2",
    "temperature": 0.0,
    "timeout": 180,
    "max_kb_items": 120,
    "system_prompts": {
        "control_structure": "",
        "codegen": "",
    },
}


def default_settings_path() -> str:
    return str(Path(__file__).with_name("llm_settings.json"))


def read_llm_settings(path: str | None = None) -> dict:
    p = Path(path or default_settings_path())
    if not p.exists():
        return dict(DEFAULT_SETTINGS)
    with open(p, "r", encoding="utf-8-sig") as f:
        loaded = json.load(f)
    merged = dict(DEFAULT_SETTINGS)
    merged.update({k: v for k, v in loaded.items() if k != "system_prompts"})
    prompts = dict(DEFAULT_SETTINGS.get("system_prompts") or {})
    prompts.update((loaded.get("system_prompts") or {}))
    merged["system_prompts"] = prompts
    return merged


def resolve_api_key(settings: dict) -> str:
    return (
        str(settings.get("api_key") or "").strip()
        or os.getenv("SILICONFLOW_API_KEY", "").strip()
        or os.getenv("OPENAI_API_KEY", "").strip()
    )
