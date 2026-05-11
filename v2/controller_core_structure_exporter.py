"""Pure LLM-driven controller-core structure exporter.

This script does not use keyword rules, scenario templates, or fallback
structures. It sends the natural-language requirement directly to the model
and exports the model's JSON response as the controller-core design.

The model is instructed to design controller-body loops only, such as speed,
position, torque, voltage, current, and power loops, while keeping the output
English-formatted and assigning unique ids to every block and edge.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

try:
    import winreg
except ImportError:  # pragma: no cover - non-Windows fallback
    winreg = None

DEFAULT_SETTINGS = {
    "api_key": "",
    "base_url": "https://api.siliconflow.cn/v1",
    "model": "deepseek-ai/DeepSeek-V3.2",
    "temperature": 0.0,
    "timeout": 180,
    "system_prompts": {
        "controller_core": (
            "You are an expert controller architecture designer. "
            "Design controller-body structure only from the user's natural-language requirement. "
            "Do not use scenario templates, heuristics, or default loop sets. "
            "Return strict JSON only, with English text only in the design fields. "
            "Every block, edge, and path must have a unique stable id."
        ),
    },
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
    def read_scope(name: str, scope: str) -> str:
        if scope == "process":
            return os.getenv(name, "").strip()

        if winreg is None:
            return ""

        try:
            root = winreg.HKEY_CURRENT_USER if scope == "user" else winreg.HKEY_LOCAL_MACHINE
            subkey = r"Environment" if scope == "user" else r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment"
            with winreg.OpenKey(root, subkey) as key:
                value, _ = winreg.QueryValueEx(key, name)
                return str(value).strip()
        except OSError:
            return ""

    return (
        read_scope("SILICONFLOW_API_KEY", "process")
        or read_scope("SILICONFLOW_API_KEY", "user")
        or read_scope("SILICONFLOW_API_KEY", "machine")
        or read_scope("OPENAI_API_KEY", "process")
        or read_scope("OPENAI_API_KEY", "user")
        or read_scope("OPENAI_API_KEY", "machine")
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
        "Task: Design a controller-core structure from a Chinese natural-language requirement.\n"
        "Hard constraints:\n"
        "1) Return STRICT JSON object only, no markdown, no prose.\n"
        "2) The design must be generated by the model; do not use any preset scenario template or fallback structure.\n"
        "3) Output must be English-formatted in all design fields.\n"
        "4) Only controller-body loops are allowed: examples include position, speed, torque, voltage, current, and power loops.\n"
        "5) Do not include protection, modulation, state machine, or power-stage blocks unless the requirement explicitly asks for them.\n"
        "6) Every block, edge, and path must have a unique stable id.\n"
        "7) Infer the minimum necessary loop hierarchy from the requirement and make the hierarchy explicit.\n"
        "8) Prefer controller architectures such as position -> speed -> torque -> current -> voltage when the requirement implies a cascaded control chain.\n"
        "9) Do not invent non-control infrastructure.\n"
        "10) The JSON root must contain at least: id, name, version, language, requirement, summary, control_scope, blocks, edges, layout, design_rules, output_format.\n\n"
        f"Natural-language requirement:\n{requirement.strip()}\n\n"
        "Expected output example shape:\n"
        "{\"id\":\"...\",\"name\":\"...\",\"version\":1,\"language\":\"en\",\"requirement\":\"...\",\"summary\":\"...\",\"control_scope\":\"controller_body_only\",\"blocks\":[],\"edges\":[],\"layout\":{},\"design_rules\":[],\"output_format\":{}}\n"
    )


def parse_response_json(text: str) -> dict[str, Any]:
    cleaned = strip_code_fence(text)
    data = json.loads(cleaned)
    if not isinstance(data, dict):
        raise ValueError("model response is not a JSON object")
    return data


def validate_structure(structure: dict[str, Any]) -> None:
    required_keys = ["id", "name", "version", "language", "requirement", "summary", "control_scope", "blocks", "edges", "layout", "design_rules", "output_format"]
    missing = [key for key in required_keys if key not in structure]
    if missing:
        raise ValueError(f"missing required keys: {', '.join(missing)}")
    if not isinstance(structure.get("blocks"), list):
        raise ValueError("blocks must be a list")
    if not isinstance(structure.get("edges"), list):
        raise ValueError("edges must be a list")
    if not isinstance(structure.get("layout"), dict):
        raise ValueError("layout must be an object")
    if not isinstance(structure.get("design_rules"), list):
        raise ValueError("design_rules must be a list")
    if not isinstance(structure.get("output_format"), dict):
        raise ValueError("output_format must be an object")


def _is_mechanical_loop_name(text: str) -> bool:
    low = (text or "").lower()
    return "speed" in low or "position" in low


def _rewrite_mechanical_name(text: str) -> str:
    if not _is_mechanical_loop_name(text):
        return text
    return re.sub(r"(?i)(speed|position)", "mech", text)


def _normalize_mechanical_structure(structure: dict[str, Any]) -> dict[str, Any]:
    """Normalize speed/position loop names to a single mech loop for backward compatibility."""

    blocks = structure.get("blocks") or []
    edges = structure.get("edges") or []
    layout = structure.get("layout") or {}

    mech_candidates: list[tuple[int, dict[str, Any], str, str, bool]] = []
    for index, block in enumerate(blocks):
        block_id = str(block.get("id") or "")
        block_name = str(block.get("name") or "")
        has_position = "position" in block_id.lower() or "position" in block_name.lower()
        has_speed = "speed" in block_id.lower() or "speed" in block_name.lower()
        if has_position or has_speed:
            mech_candidates.append((index, block, block_id, block_name, has_position))

    if not mech_candidates:
        return structure

    keep_position = any(item[4] for item in mech_candidates)
    kept_candidate: tuple[int, dict[str, Any], str, str, bool] | None = None
    dropped_ids: set[str] = set()
    dropped_names: set[str] = set()

    for candidate in mech_candidates:
        index, block, block_id, block_name, has_position = candidate
        is_speed_only = "speed" in block_id.lower() or "speed" in block_name.lower()
        if keep_position:
            if is_speed_only and not has_position:
                dropped_ids.add(block_id)
                dropped_names.add(block_name)
                continue
            if kept_candidate is None and has_position:
                kept_candidate = candidate
                continue
            if has_position:
                dropped_ids.add(block_id)
                dropped_names.add(block_name)
                continue
            if is_speed_only:
                dropped_ids.add(block_id)
                dropped_names.add(block_name)
                continue
        else:
            if is_speed_only and kept_candidate is None:
                kept_candidate = candidate
                continue
            if is_speed_only:
                dropped_ids.add(block_id)
                dropped_names.add(block_name)
                continue
            if has_position:
                dropped_ids.add(block_id)
                dropped_names.add(block_name)

    if kept_candidate is None:
        return structure

    kept_index, kept_block, kept_id, kept_name, _ = kept_candidate
    mech_id = _rewrite_mechanical_name(kept_id)
    mech_name = _rewrite_mechanical_name(kept_name)

    block_name_map: dict[str, str] = {}
    block_id_map: dict[str, str] = {}

    normalized_blocks: list[dict[str, Any]] = []
    for index, block in enumerate(blocks):
        block_id = str(block.get("id") or "")
        block_name = str(block.get("name") or "")

        if block_id in dropped_ids or block_name in dropped_names:
            continue

        updated_block = dict(block)
        if index == kept_index:
            if block_id:
                block_id_map[block_id] = mech_id
                updated_block["id"] = mech_id
            if block_name:
                block_name_map[block_name] = mech_name
                updated_block["name"] = mech_name
        elif _is_mechanical_loop_name(block_id) or _is_mechanical_loop_name(block_name):
            updated_block["id"] = _rewrite_mechanical_name(block_id)
            updated_block["name"] = _rewrite_mechanical_name(block_name)
            if block_id:
                block_id_map[block_id] = updated_block["id"]
            if block_name:
                block_name_map[block_name] = updated_block["name"]

        normalized_blocks.append(updated_block)

    normalized_edges: list[dict[str, Any]] = []
    for edge in edges:
        if not isinstance(edge, dict):
            continue
        source = str(edge.get("source") or "")
        target = str(edge.get("target") or "")
        if source in dropped_names or target in dropped_names:
            continue

        updated_edge = dict(edge)
        if source in block_name_map:
            updated_edge["source"] = block_name_map[source]
        elif _is_mechanical_loop_name(source):
            updated_edge["source"] = _rewrite_mechanical_name(source)

        if target in block_name_map:
            updated_edge["target"] = block_name_map[target]
        elif _is_mechanical_loop_name(target):
            updated_edge["target"] = _rewrite_mechanical_name(target)

        edge_id = str(updated_edge.get("id") or "")
        if edge_id:
            for old, new in {**block_name_map, **block_id_map}.items():
                if old and old in edge_id:
                    edge_id = edge_id.replace(old, new)
            if _is_mechanical_loop_name(edge_id):
                edge_id = _rewrite_mechanical_name(edge_id)
            updated_edge["id"] = edge_id

        normalized_edges.append(updated_edge)

    def _normalize_layout_value(value: Any) -> Any:
        if isinstance(value, list):
            normalized: list[Any] = []
            seen: set[str] = set()
            for item in value:
                if not isinstance(item, str):
                    normalized.append(item)
                    continue
                if item in dropped_names:
                    continue
                rewritten = block_name_map.get(item, item)
                if _is_mechanical_loop_name(rewritten):
                    rewritten = _rewrite_mechanical_name(rewritten)
                if rewritten in seen:
                    continue
                seen.add(rewritten)
                normalized.append(rewritten)
            return normalized
        if isinstance(value, dict):
            return {key: _normalize_layout_value(val) for key, val in value.items()}
        return value

    normalized_layout = _normalize_layout_value(layout)

    structure["blocks"] = normalized_blocks
    structure["edges"] = normalized_edges
    structure["layout"] = normalized_layout
    return structure


def build_controller_core_structure(requirement: str, settings: dict[str, Any]) -> dict[str, Any]:
    api_key = resolve_api_key(settings)
    if not api_key:
        raise RuntimeError("missing API key in llm settings or environment")

    system_prompt = settings.get("system_prompts", {}).get("controller_core") or DEFAULT_SETTINGS["system_prompts"]["controller_core"]
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

    structure = parse_response_json(text)
    structure = _normalize_mechanical_structure(structure)
    validate_structure(structure)
    return structure


def export_json(output_path: Path, requirement: str, settings_path: str | Path | None = None) -> Path:
    settings = read_llm_settings(settings_path)
    payload = build_controller_core_structure(requirement, settings)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return output_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export a controller-core JSON design using a large language model.")
    parser.add_argument(
        "requirement",
        nargs="?",
        default="我需要设计一款速度控制系统",
        help="Natural-language requirement for the controller-core design.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(__file__).with_name("controller_core_structure.json"),
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
    print(f"Exported controller core structure to {exported}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
