"""Pure LLM-driven loop-id selector for controller design.

This script asks the LLM to select only the control loops needed by the
natural-language requirement and returns loop ids only. It does not generate
full architecture, topology, edges, or detailed block structure.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

DEFAULT_SETTINGS = {
    "api_key": "",
    "base_url": "https://api.siliconflow.cn/v1",
    "model": "deepseek-ai/DeepSeek-V3.2",
    "temperature": 0.0,
    "timeout": 180,
    "system_prompts": {
        "loop_selector": (
            "You are an expert control-loop selector. "
            "Given a natural-language controller requirement, output only the selected control loops and stable ids. "
            "Do not output full architecture. Return strict JSON only."
        )
    },
}


CANONICAL_LOOP_IDS = {
    "position_loop": "loop_position_001",
    "speed_loop": "loop_speed_001",
    "torque_loop": "loop_torque_001",
    "current_loop": "loop_current_001",
    "voltage_loop": "loop_voltage_001",
    "power_loop": "loop_power_001",
}


def default_settings_path() -> Path:
    return Path(__file__).with_name("llm_settings.json")


def read_llm_settings(path: str | Path | None = None) -> dict[str, Any]:
    config_path = Path(path or default_settings_path())
    if not config_path.exists():
        return dict(DEFAULT_SETTINGS)

    with open(config_path, "r", encoding="utf-8-sig") as handle:
        loaded = json.load(handle)

    merged = dict(DEFAULT_SETTINGS)
    merged.update({key: value for key, value in loaded.items() if key != "system_prompts"})

    prompts = dict(DEFAULT_SETTINGS.get("system_prompts") or {})
    prompts.update(loaded.get("system_prompts") or {})
    merged["system_prompts"] = prompts
    return merged


def resolve_api_key(settings: dict[str, Any]) -> str:
    return (
        str(settings.get("api_key") or "").strip()
        or os.getenv("SILICONFLOW_API_KEY", "").strip()
        or os.getenv("OPENAI_API_KEY", "").strip()
    )


def strip_code_fence(text: str) -> str:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```[a-zA-Z0-9_\-]*\n", "", cleaned)
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3]
    return cleaned.strip()


def call_chat(api_key: str, base_url: str, model: str, system_prompt: str, user_prompt: str, temperature: float, timeout: int) -> dict[str, Any]:
    url = base_url.rstrip("/") + "/chat/completions"
    payload = {
        "model": model,
        "temperature": temperature,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    }
    data = json.dumps(payload).encode("utf-8")

    request = urllib.request.Request(
        url,
        data=data,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read().decode("utf-8")
            return json.loads(body)
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"HTTPError {error.code}: {detail}") from error
    except urllib.error.URLError as error:
        raise RuntimeError(f"URLError: {error}") from error


def extract_text(response_json: dict[str, Any]) -> str:
    choices = response_json.get("choices") or []
    if not choices:
        return ""
    message = choices[0].get("message") or {}
    return message.get("content") or ""


def build_user_prompt(requirement: str) -> str:
    return (
        "Task: Select control loops only for the requirement.\n"
        "Hard constraints:\n"
        "1) Return STRICT JSON object only, no markdown, no prose.\n"
        "2) Return only loop selection, not full structure.\n"
        "3) Use English for loop names.\n"
        "4) The root keys must be exactly: requirement, language, selected_loops.\n"
        "5) selected_loops must be a non-empty array.\n"
        "6) Each item in selected_loops must contain exactly: id, name.\n"
        "7) id format must be: loop_XXX (example: loop_speed_001).\n"
        "8) Use only controller loops, such as position_loop, speed_loop, torque_loop, current_loop, voltage_loop, power_loop.\n"
        "9) Keep the set minimal but practical for the requirement.\n"
        "10) For motor speed control scenarios, prefer speed_loop + current_loop unless the requirement clearly asks for more loops.\n\n"
        f"Natural-language requirement:\n{requirement.strip()}\n\n"
        "Output JSON template:\n"
        "{\"requirement\":\"...\",\"language\":\"en\",\"selected_loops\":[{\"id\":\"loop_speed_001\",\"name\":\"speed_loop\"},{\"id\":\"loop_current_001\",\"name\":\"current_loop\"}]}\n"
    )


def parse_loop_json(text: str) -> dict[str, Any]:
    cleaned = strip_code_fence(text)
    data = json.loads(cleaned)
    if not isinstance(data, dict):
        raise ValueError("model response is not a JSON object")
    return data


def validate_loop_selection(payload: dict[str, Any]) -> None:
    required_keys = ["requirement", "language", "selected_loops"]
    missing = [key for key in required_keys if key not in payload]
    if missing:
        raise ValueError(f"missing required keys: {', '.join(missing)}")

    selected_loops = payload.get("selected_loops")
    if not isinstance(selected_loops, list) or not selected_loops:
        raise ValueError("selected_loops must be a non-empty list")

    id_seen: set[str] = set()
    for item in selected_loops:
        if not isinstance(item, dict):
            raise ValueError("each selected loop must be an object")
        if set(item.keys()) != {"id", "name"}:
            raise ValueError("each selected loop must contain exactly id and name")

        loop_id = str(item.get("id") or "").strip()
        loop_name = str(item.get("name") or "").strip()

        if not re.match(r"^loop_[a-z0-9_]+$", loop_id):
            raise ValueError(f"invalid loop id format: {loop_id}")
        if not loop_name.endswith("_loop"):
            raise ValueError(f"invalid loop name format: {loop_name}")
        if loop_id in id_seen:
            raise ValueError(f"duplicate loop id: {loop_id}")
        id_seen.add(loop_id)


def canonicalize_loop_selection(payload: dict[str, Any]) -> dict[str, Any]:
    """Normalize loop ids to stable deterministic ids by loop name."""

    normalized: list[dict[str, str]] = []
    seen_names: set[str] = set()

    for item in payload.get("selected_loops") or []:
        loop_name = str(item.get("name") or "").strip().lower()
        if not loop_name or loop_name in seen_names:
            continue
        seen_names.add(loop_name)

        canonical_id = CANONICAL_LOOP_IDS.get(loop_name)
        if not canonical_id:
            # Keep unknown loop names deterministic across runs.
            digest = hashlib.sha1(loop_name.encode("utf-8")).hexdigest()[:8]
            canonical_id = f"loop_custom_{digest}"

        normalized.append({"id": canonical_id, "name": loop_name})

    # Keep output order deterministic for the same loop set.
    normalized.sort(key=lambda x: x["id"])

    out = {
        "requirement": payload.get("requirement"),
        "language": "en",
        "selected_loops": normalized,
    }
    return out


def select_loops(requirement: str, settings: dict[str, Any]) -> dict[str, Any]:
    api_key = resolve_api_key(settings)
    if not api_key:
        raise RuntimeError("missing API key in llm settings or environment")

    system_prompt = settings.get("system_prompts", {}).get("loop_selector") or DEFAULT_SETTINGS["system_prompts"]["loop_selector"]
    temperature = float(settings.get("temperature", 0.0))
    timeout = int(settings.get("timeout", 180))
    model = str(settings.get("model") or DEFAULT_SETTINGS["model"])
    base_url = str(settings.get("base_url") or DEFAULT_SETTINGS["base_url"])

    response_json = call_chat(
        api_key=api_key,
        base_url=base_url,
        model=model,
        system_prompt=system_prompt,
        user_prompt=build_user_prompt(requirement),
        temperature=temperature,
        timeout=timeout,
    )

    text = extract_text(response_json)
    if not text.strip():
        raise RuntimeError("empty model response")

    payload = parse_loop_json(text)
    validate_loop_selection(payload)
    return canonicalize_loop_selection(payload)


def export_json(output_path: Path, requirement: str, settings_path: str | Path | None = None) -> Path:
    settings = read_llm_settings(settings_path)
    payload = select_loops(requirement, settings)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return output_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export selected loop ids using a large language model.")
    parser.add_argument(
        "requirement",
        nargs="?",
        default="需要设计吸尘器电机控制器",
        help="Natural-language requirement for loop selection.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(__file__).with_name("controller_loop_ids.json"),
        help="Path to the JSON file to generate.",
    )
    parser.add_argument(
        "--llm-config",
        type=Path,
        default=default_settings_path(),
        help="Path to the LLM settings JSON file.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    exported = export_json(args.output, args.requirement, settings_path=args.llm_config)
    print(f"Exported selected loop ids to {exported}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
