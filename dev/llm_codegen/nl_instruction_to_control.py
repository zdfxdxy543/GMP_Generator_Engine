#!/usr/bin/env python3
import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from collections import defaultdict
from datetime import datetime

from llm_settings import default_settings_path, read_llm_settings, resolve_api_key

DEFAULT_SYSTEM_PROMPT = (
    "You are an expert control-system architecture assistant. "
    "Given a natural-language target and a controller design knowledge base, "
    "generate only strict control-structure JSON without markdown or prose."
)


def read_json(path: str):
    with open(path, "r", encoding="utf-8-sig") as f:
        return json.load(f)


def strip_code_fence(text: str) -> str:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```[a-zA-Z0-9_\-]*\n", "", cleaned)
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3]
    return cleaned.strip()


def build_kb_indexes(kb_items: list):
    by_canonical = {}
    by_module = defaultdict(list)
    for item in kb_items:
        cid = item.get("canonical_id")
        mid = item.get("module_id")
        if cid:
            by_canonical[cid] = item
        if mid:
            by_module[mid].append(item)
    return by_canonical, by_module


def _text_contains(item: dict, terms: list[str]) -> bool:
    hay = " ".join(
        [
            str(item.get("canonical_id") or ""),
            str(item.get("module_id") or ""),
            str(item.get("module_name") or ""),
            str(item.get("domain") or ""),
            " ".join(str(x) for x in item.get("group_ids") or []),
        ]
    ).lower()
    return any(t in hay for t in terms)


def pick_design_candidates(kb_items: list, instruction: str, limit: int) -> list:
    terms = [
        x.lower()
        for x in re.findall(r"[A-Za-z0-9_\u4e00-\u9fff]+", instruction)
        if len(x.strip()) >= 2
    ]
    matched = [item for item in kb_items if _text_contains(item, terms)]
    if not matched:
        matched = kb_items
    # Keep the prompt bounded while preserving deterministic order.
    return matched[:limit]


def compact_kb_for_prompt(candidates: list) -> list:
    out = []
    for item in candidates:
        api = item.get("api_contract") or {}
        step = [x.get("function") for x in (api.get("step") or []) if x.get("function")]
        attach = [x.get("function") for x in (api.get("attach") or []) if x.get("function")]
        out.append(
            {
                "canonical_id": item.get("canonical_id"),
                "module_id": item.get("module_id"),
                "module_name": item.get("module_name"),
                "domain": item.get("domain"),
                "schedule_hint": (api.get("lifecycle") or {}).get("schedule_hint"),
                "step_functions": step,
                "attach_functions": attach,
            }
        )
    return out


def build_id_whitelists(kb_items: list) -> tuple[list[str], list[str]]:
    all_ids = []
    runnable_loop_ids = []
    for item in kb_items:
        cid = item.get("canonical_id")
        if not cid:
            continue
        all_ids.append(cid)
        if has_autocallable_step_api(item):
            runnable_loop_ids.append(cid)
    return sorted(set(all_ids)), sorted(set(runnable_loop_ids))


def build_user_prompt(
    instruction: str,
    kb_candidates: list,
    all_ids: list[str],
    runnable_loop_ids: list[str],
    validation_feedback: str = "",
) -> str:
    kb_compact = json.dumps(compact_kb_for_prompt(kb_candidates), ensure_ascii=False, indent=2)
    all_ids_json = json.dumps(all_ids, ensure_ascii=False)
    runnable_ids_json = json.dumps(runnable_loop_ids, ensure_ascii=False)
    return (
        "Task: Build a strict control structure JSON from a natural-language controller requirement.\n"
        "You must infer modules, control-loop hierarchy, and inter-module links.\n"
        "Output constraints:\n"
        "1) Return STRICT JSON object only, no markdown, no prose.\n"
        "2) Root keys must be exactly: project, modules, links, schedule.\n"
        "3) modules[*] must include: instance_name and either canonical_id or module_id.\n"
        "4) schedule must include: init, fast_loop, slow_loop, fault (arrays of instance_name).\n"
        "5) links describe signal/data flow between modules, especially control-loop relationships.\n"
        "6) Prefer canonical_id from KB whenever possible.\n"
        "7) Do not invent canonical_id/module_id not present in the KB.\n"
        "8) Keep instance_name C-identifier compliant.\n"
        "9) project.target must be GMP_CTL.\n\n"
        "10) All canonical_id values MUST be selected from the provided ALLOWED_CANONICAL_IDS list.\n"
        "11) Modules in fast_loop/slow_loop MUST use canonical_id from RUNNABLE_LOOP_CANONICAL_IDS only.\n"
        "12) Do NOT place library/aggregate modules (e.g., *_LIB, intrinsic root, digital_power root) into fast_loop/slow_loop.\n\n"
        "Natural-language requirement:\n"
        f"{instruction}\n\n"
        "ALLOWED_CANONICAL_IDS (full whitelist):\n"
        f"{all_ids_json}\n\n"
        "RUNNABLE_LOOP_CANONICAL_IDS (loop-only whitelist):\n"
        f"{runnable_ids_json}\n\n"
        "Controller design KB candidates (JSON):\n"
        f"{kb_compact}\n\n"
        "Output JSON template:\n"
        "{\"project\":{\"name\":\"...\",\"target\":\"GMP_CTL\",\"notes\":\"...\"},\"modules\":[],\"links\":[],\"schedule\":{\"init\":[],\"fast_loop\":[],\"slow_loop\":[],\"fault\":[]}}\n"
        + (
            "\nPrevious validation failure to fix in this retry:\n"
            + validation_feedback
            + "\n"
            if validation_feedback
            else ""
        )
    )


def call_chat(api_key: str, base_url: str, model: str, system_prompt: str, user_prompt: str, temperature: float, timeout: int):
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

    req = urllib.request.Request(
        url,
        data=data,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8")
            return json.loads(body)
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"HTTPError {e.code}: {detail}") from e
    except urllib.error.URLError as e:
        raise RuntimeError(f"URLError: {e}") from e


def extract_text(resp_json: dict) -> str:
    choices = resp_json.get("choices") or []
    if not choices:
        return ""
    msg = choices[0].get("message") or {}
    return msg.get("content") or ""


def parse_control_json(text: str) -> dict:
    cleaned = strip_code_fence(text)
    data = json.loads(cleaned)
    if not isinstance(data, dict):
        raise ValueError("model output must be a JSON object")
    return data


def normalize_control_structure(control: dict) -> dict:
    project = control.get("project") or {}
    modules = control.get("modules") or []
    links = control.get("links") or []
    schedule = control.get("schedule") or {}

    out = {
        "project": {
            "name": project.get("name") or "nl_controller_design",
            "target": "GMP_CTL",
            "notes": project.get("notes") or "Generated from natural language using controller design KB",
            "generated_at": datetime.now().isoformat(),
        },
        "modules": modules,
        "links": links,
        "schedule": {
            "init": schedule.get("init") or [],
            "fast_loop": schedule.get("fast_loop") or [],
            "slow_loop": schedule.get("slow_loop") or [],
            "fault": schedule.get("fault") or [],
        },
    }
    return out


def has_autocallable_step_api(item: dict) -> bool:
    api = item.get("api_contract") or {}
    for step in api.get("step") or []:
        fn = step.get("function")
        sig = (step.get("signature") or "").strip()
        # Keep it aligned with stage-2 auto-call policy: single pointer argument only.
        if fn and re.match(r"^\w+\s*\([^,]*\*[^,]*\)\s*$", sig):
            return True
    return False


def validate_and_resolve_modules(control: dict, kb_items: list):
    by_canonical, by_module = build_kb_indexes(kb_items)
    instance_seen = set()
    resolved_by_instance = {}
    errors = []

    for mod in control.get("modules") or []:
        name = mod.get("instance_name")
        if not name or not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", name):
            errors.append(f"invalid instance_name: {name}")
            continue
        if name in instance_seen:
            errors.append(f"duplicate instance_name: {name}")
            continue
        instance_seen.add(name)

        cid = mod.get("canonical_id")
        mid = mod.get("module_id")
        if not cid and not mid:
            errors.append(f"module missing canonical_id/module_id: {name}")
            continue

        if cid:
            if cid not in by_canonical:
                errors.append(f"unknown canonical_id: {cid} ({name})")
            else:
                resolved_by_instance[name] = by_canonical[cid]
        elif mid:
            cands = by_module.get(mid) or []
            if len(cands) == 0:
                errors.append(f"unknown module_id: {mid} ({name})")
            elif len(cands) > 1:
                ids = [x.get("canonical_id") for x in cands if x.get("canonical_id")]
                errors.append(f"ambiguous module_id: {mid} ({name}) candidates={ids}")
            else:
                mod["canonical_id"] = cands[0].get("canonical_id")
                resolved_by_instance[name] = cands[0]

    if errors:
        raise ValueError("control validation failed: " + " | ".join(errors))

    known = {m.get("instance_name") for m in control.get("modules") or []}
    for phase in ("init", "fast_loop", "slow_loop", "fault"):
        for name in control.get("schedule", {}).get(phase) or []:
            if name not in known:
                raise ValueError(f"schedule references unknown instance: {phase}:{name}")

    # Hard runnable constraint: loop modules must have auto-callable step APIs.
    for phase in ("fast_loop", "slow_loop"):
        for name in control.get("schedule", {}).get(phase) or []:
            item = resolved_by_instance.get(name)
            if not item:
                raise ValueError(f"unresolved loop instance: {phase}:{name}")
            if not has_autocallable_step_api(item):
                cid = item.get("canonical_id")
                raise ValueError(
                    "non-runnable loop module in control structure: "
                    f"{phase}:{name} ({cid}) does not provide a single-pointer step signature"
                )


def main():
    parser = argparse.ArgumentParser(description="Convert natural-language instruction to strict control structure JSON")
    parser.add_argument("--instruction", required=True, help="Natural-language generation instruction")
    parser.add_argument("--kb", required=True, help="Controller design knowledge base JSON path")
    parser.add_argument("--out", required=True, help="Output control JSON path")
    parser.add_argument("--llm-config", default=default_settings_path(), help="Path to LLM settings JSON")
    parser.add_argument("--raw", default="", help="Optional path to save raw model response JSON")
    parser.add_argument("--prompt-out", default="", help="Optional path to save final prompt")
    parser.add_argument("--model", default="", help="Model name (overrides llm config)")
    parser.add_argument("--base-url", default="", help="SiliconFlow base URL (overrides llm config)")
    parser.add_argument("--temperature", type=float, default=None, help="Sampling temperature (overrides llm config)")
    parser.add_argument("--timeout", type=int, default=None, help="HTTP timeout seconds (overrides llm config)")
    parser.add_argument("--system", default="", help="System prompt (overrides llm config)")
    parser.add_argument("--max-kb-items", type=int, default=None, help="Maximum KB candidates passed into prompt (overrides llm config)")
    parser.add_argument("--max-attempts", type=int, default=None, help="Max retry attempts for stage-1 generation; <=0 means retry until success")
    args = parser.parse_args()

    llm_cfg = read_llm_settings(args.llm_config)
    model = args.model or str(llm_cfg.get("model") or "")
    base_url = args.base_url or str(llm_cfg.get("base_url") or "")
    temperature = args.temperature if args.temperature is not None else float(llm_cfg.get("temperature") or 0.0)
    timeout = args.timeout if args.timeout is not None else int(llm_cfg.get("timeout") or 180)
    max_kb_items = args.max_kb_items if args.max_kb_items is not None else int(llm_cfg.get("max_kb_items") or 120)
    system_prompt = args.system or str((llm_cfg.get("system_prompts") or {}).get("control_structure") or DEFAULT_SYSTEM_PROMPT)

    api_key = resolve_api_key(llm_cfg)
    if not api_key:
        print("ERROR: Missing api_key in llm_settings.json (or SILICONFLOW_API_KEY/OPENAI_API_KEY).", file=sys.stderr)
        return 2

    kb = read_json(args.kb)
    kb_candidates = pick_design_candidates(kb, args.instruction, max_kb_items)
    all_ids, runnable_loop_ids = build_id_whitelists(kb)
    max_attempts = args.max_attempts if args.max_attempts is not None else int(llm_cfg.get("max_control_structure_attempts") or 0)

    last_error = ""
    control = None
    resp_json = None
    user_prompt = ""
    attempt = 0
    while True:
        attempt += 1
        if max_attempts > 0 and attempt > max_attempts:
            break

        user_prompt = build_user_prompt(
            args.instruction,
            kb_candidates,
            all_ids,
            runnable_loop_ids,
            last_error,
        )

        try:
            resp_json = call_chat(
                api_key=api_key,
                base_url=base_url,
                model=model,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                temperature=temperature,
                timeout=timeout,
            )

            text = extract_text(resp_json)
            if not text:
                raise RuntimeError("Empty model response content.")

            control = normalize_control_structure(parse_control_json(text))
            validate_and_resolve_modules(control, kb)
            suffix = f"/{max_attempts}" if max_attempts > 0 else ""
            print(f"Control structure generation validated on attempt {attempt}{suffix}")
            break
        except Exception as e:
            last_error = str(e)
            control = None
            suffix = f"/{max_attempts}" if max_attempts > 0 else ""
            print(f"Stage-1 attempt {attempt}{suffix} failed: {last_error}", file=sys.stderr)
            # Retry indefinitely by default unless a positive max-attempts is configured.
            time.sleep(1.0)

    if control is None:
        raise RuntimeError(
            "Failed to generate runnable control structure after retries: " + last_error
        )

    if args.prompt_out:
        os.makedirs(os.path.dirname(os.path.abspath(args.prompt_out)), exist_ok=True)
        with open(args.prompt_out, "w", encoding="utf-8") as f:
            f.write(user_prompt)

    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(control, f, ensure_ascii=False, indent=2)

    if args.raw:
        os.makedirs(os.path.dirname(os.path.abspath(args.raw)), exist_ok=True)
        with open(args.raw, "w", encoding="utf-8") as f:
            json.dump(resp_json, f, ensure_ascii=False, indent=2)

    print("Control structure generated from natural language")
    print(f"Instruction: {args.instruction}")
    print(f"KB candidates: {len(kb_candidates)}")
    print(f"Allowed canonical ids: {len(all_ids)}")
    print(f"Runnable loop canonical ids: {len(runnable_loop_ids)}")
    print(f"Output: {args.out}")
    if args.raw:
        print(f"Raw: {args.raw}")
    if args.prompt_out:
        print(f"Prompt: {args.prompt_out}")
    print(f"Time: {datetime.now().isoformat()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
