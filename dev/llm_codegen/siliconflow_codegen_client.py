#!/usr/bin/env python3
import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from collections import defaultdict
from datetime import datetime

DEFAULT_MODEL = "deepseek-ai/DeepSeek-V3.2"
DEFAULT_BASE_URL = "https://api.siliconflow.cn/v1"
DEFAULT_SYSTEM_PROMPT = (
    "You are an expert embedded control code generator. "
    "Generate deterministic C function-body logic only, no declarations or definitions. "
    "Return strict JSON only. Never output markdown fences or explanatory text."
)

FORBIDDEN_PHRASES = [
    "assuming",
    "placeholder",
    "not found",
    "todo",
    "tbd",
]


def read_json(path: str):
    with open(path, "r", encoding="utf-8-sig") as f:
        return json.load(f)


def build_kb_indexes(kb_items: list):
    by_canonical = {}
    by_module = defaultdict(list)
    by_group = defaultdict(list)

    for item in kb_items:
        cid = item.get("canonical_id")
        mid = item.get("module_id")
        if cid:
            by_canonical[cid] = item
        if mid:
            by_module[mid].append(item)
        for gid in item.get("group_ids") or []:
            by_group[gid].append(item)

    return by_canonical, by_module, by_group


def has_step_api(item: dict) -> bool:
    api = item.get("api_contract") or {}
    return len(api.get("step") or []) > 0


def dedupe_candidates(candidates: list) -> list:
    seen = set()
    out = []
    for item in candidates:
        cid = item.get("canonical_id")
        if not cid or cid in seen:
            continue
        seen.add(cid)
        out.append(item)
    return out


def resolve_modules(control: dict, kb_items: list):
    by_canonical, by_module, by_group = build_kb_indexes(kb_items)
    resolved = []
    errors = []

    for mod in control.get("modules") or []:
        instance_name = mod.get("instance_name")
        schedule_hint = mod.get("schedule_hint")
        canonical_id = mod.get("canonical_id")
        module_id = mod.get("module_id")

        if canonical_id:
            item = by_canonical.get(canonical_id)
            if not item:
                errors.append(f"unresolved canonical_id: {canonical_id} ({instance_name})")
                continue
            candidates = [item]
        else:
            candidates = []
            if module_id:
                candidates.extend(by_module.get(module_id) or [])
                candidates.extend(by_group.get(module_id) or [])

            candidates = dedupe_candidates(candidates)

            # Prefer exact module_id matches over broad group-id matches.
            exact = [c for c in candidates if c.get("module_id") == module_id]
            if exact:
                candidates = exact

            if schedule_hint in ("fast_loop", "slow_loop"):
                with_step = [c for c in candidates if has_step_api(c)]
                if with_step:
                    candidates = with_step

            if len(candidates) == 0:
                errors.append(f"unresolved module_id: {module_id} ({instance_name})")
                continue

            if len(candidates) > 1:
                ids = [c.get("canonical_id") for c in candidates]
                errors.append(f"ambiguous module_id: {module_id} ({instance_name}) candidates={ids}")
                continue

        chosen = candidates[0]
        if schedule_hint in ("fast_loop", "slow_loop") and not has_step_api(chosen):
            errors.append(
                f"missing step api for loop module: {instance_name} ({chosen.get('canonical_id')})"
            )
            continue

        resolved.append(
            {
                "instance_name": instance_name,
                "schedule_hint": schedule_hint,
                "params": mod.get("params") or {},
                "canonical_id": chosen.get("canonical_id"),
                "module_id": chosen.get("module_id"),
                "module_name": chosen.get("module_name"),
                "file": chosen.get("file"),
                "api_contract": chosen.get("api_contract") or {},
            }
        )

    if errors:
        raise ValueError("module resolution failed: " + " | ".join(errors))

    return resolved


def build_user_prompt(control: dict, resolved_modules: list, extra_instruction: str, render_profile: str) -> str:
    schedule = control.get("schedule") or {}
    links = control.get("links") or []
    compact_modules = json.dumps(resolved_modules, ensure_ascii=False, indent=2)
    compact_schedule = json.dumps(schedule, ensure_ascii=False, indent=2)
    compact_links = json.dumps(links, ensure_ascii=False, indent=2)
    allowed_calls = []
    for mod in resolved_modules:
        api = mod.get("api_contract") or {}
        for x in api.get("step") or []:
            fn = x.get("function")
            if fn:
                allowed_calls.append(fn)
        for x in api.get("attach") or []:
            fn = x.get("function")
            if fn:
                allowed_calls.append(fn)
    allowed_calls = sorted(set(allowed_calls))
    compact_allowed = json.dumps(allowed_calls, ensure_ascii=False)

    profile_hint = ""
    if render_profile == "ctl_main":
        profile_hint = (
            "Profile target: ctl_main style. init maps to ctl_init(), fast_loop/slow_loop map to ctl_dispatch().\n"
        )

    return (
        "Task: Generate control function-body statements for init/fast_loop/slow_loop/fault.\n"
        + profile_hint
        + "Hard constraints:\n"
        + "1) Return STRICT JSON object only, no markdown, no prose.\n"
        + "2) JSON keys MUST be exactly: init, fast_loop, slow_loop, fault.\n"
        + "3) Each value is C statements only (no outer braces, no declarations, no comments).\n"
        + "4) Use only function names from api_contract.step/api_contract.attach for each module.\n"
        + "5) Never invent new API names.\n"
        + "6) Respect schedule order exactly.\n"
        + "7) For required fast_loop/slow_loop calls only: if API missing, emit ERROR_UNRESOLVED_API(instance_name).\n\n"
        + "Resolved modules JSON:\n"
        + compact_modules
        + "\n\n"
        + "Allowed function names JSON:\n"
        + compact_allowed
        + "\n\n"
        + "Links JSON:\n"
        + compact_links
        + "\n\n"
        + "Schedule JSON:\n"
        + compact_schedule
        + "\n\n"
        + "Output JSON template:\n"
        + "{\"init\":\"...\",\"fast_loop\":\"...\",\"slow_loop\":\"...\",\"fault\":\"...\"}\n\n"
        + "Extra instruction:\n"
        + (extra_instruction or "")
        + "\n"
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


def strip_code_fence(text: str) -> str:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```[a-zA-Z0-9_\-]*\n", "", cleaned)
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3]
    return cleaned.strip()


def parse_sections(text: str) -> dict:
    cleaned = strip_code_fence(text)
    data = json.loads(cleaned)
    if not isinstance(data, dict):
        raise ValueError("model response is not a JSON object")

    required = ["init", "fast_loop", "slow_loop", "fault"]
    for key in required:
        if key not in data:
            raise ValueError(f"missing output section: {key}")
        if not isinstance(data[key], str):
            raise ValueError(f"output section is not string: {key}")
    return data


def normalize_body(body: str) -> str:
    body = strip_code_fence(body)
    body = body.strip()
    if body.startswith("{") and body.endswith("}"):
        body = body[1:-1].strip()
    return body


def indent_block(code: str) -> str:
    code = normalize_body(code)
    if not code:
        return ""
    return "\n".join("    " + line for line in code.splitlines())


def render_c_output(sections: dict) -> str:
    init_body = indent_block(sections.get("init", ""))
    fast_body = indent_block(sections.get("fast_loop", ""))
    slow_body = indent_block(sections.get("slow_loop", ""))
    fault_body = indent_block(sections.get("fault", ""))
    return (
        "// init function body\n"
        "{\n"
        f"{init_body}\n"
        "}\n\n"
        "// fast_loop function body\n"
        "{\n"
        f"{fast_body}\n"
        "}\n\n"
        "// slow_loop function body\n"
        "{\n"
        f"{slow_body}\n"
        "}\n\n"
        "// fault function body\n"
        "{\n"
        f"{fault_body}\n"
        "}\n"
    )


def render_ctl_main_output(sections: dict) -> str:
    init_body = indent_block(sections.get("init", ""))
    fast_body = indent_block(sections.get("fast_loop", ""))
    slow_body = indent_block(sections.get("slow_loop", ""))
    fault_body = indent_block(sections.get("fault", ""))

    dispatch_extra = ""
    if slow_body:
        dispatch_extra += "\n    // slow-loop body from schedule\n" + slow_body + "\n"
    if fault_body:
        dispatch_extra += "\n    // fault body from schedule\n" + fault_body + "\n"

    return (
        "// generated ctl_main-style code body\n\n"
        "void ctl_init(void)\n"
        "{\n"
        f"{init_body}\n"
        "}\n\n"
        "GMP_STATIC_INLINE void ctl_dispatch(void)\n"
        "{\n"
        f"{fast_body}{dispatch_extra}\n"
        "}\n\n"
        "void ctl_mainloop(void)\n"
        "{\n"
        "    cia402_dispatch(&cia402_sm);\n"
        "}\n"
    )


def quality_gate(rendered_c: str, sections: dict, control: dict, resolved_modules: list):
    lower = rendered_c.lower()
    for phrase in FORBIDDEN_PHRASES:
        if phrase in lower:
            raise RuntimeError(f"forbidden phrase in output: {phrase}")

    by_instance = {m["instance_name"]: m for m in resolved_modules}
    schedule = control.get("schedule") or {}

    allowed_fn = set(["ERROR_UNRESOLVED_API"])
    for mod in resolved_modules:
        api = mod.get("api_contract") or {}
        for x in api.get("step") or []:
            fn = x.get("function")
            if fn:
                allowed_fn.add(fn)
        for x in api.get("attach") or []:
            fn = x.get("function")
            if fn:
                allowed_fn.add(fn)

    def _find_calls(text: str):
        # Match C-like function call names.
        return re.findall(r"\b([A-Za-z_][A-Za-z0-9_]*)\s*\(", text)

    for phase_name, phase_text in sections.items():
        for fn in _find_calls(phase_text):
            if fn not in allowed_fn:
                raise RuntimeError(f"illegal function call in {phase_name}: {fn}")

    # For loop phases, each scheduled module with step APIs must appear at least once.
    for phase in ("fast_loop", "slow_loop"):
        phase_text = sections.get(phase, "")
        for inst in schedule.get(phase) or []:
            mod = by_instance.get(inst)
            if not mod:
                raise RuntimeError(f"scheduled instance not resolved: {inst}")
            step_items = (mod.get("api_contract") or {}).get("step") or []
            expected_names = [x.get("function") for x in step_items if x.get("function")]
            if not expected_names:
                raise RuntimeError(f"no step api for scheduled loop instance: {inst}")
            if not any(name in phase_text for name in expected_names):
                raise RuntimeError(
                    f"missing required step call in {phase}: {inst}, expected one of {expected_names}"
                )


def _pick_autocall(step_items: list, instance_name: str) -> str:
    for step in step_items:
        fn = step.get("function")
        sig = step.get("signature") or ""
        # Prefer single-pointer-argument functions, safe for &instance calling.
        if fn and re.match(r"^\w+\([^,]*\*[^,]*\)$", sig):
            return f"{fn}(&{instance_name});"
    return f"ERROR_UNRESOLVED_API({instance_name});"


def ensure_required_calls(sections: dict, control: dict, resolved_modules: list) -> dict:
    repaired = dict(sections)
    by_instance = {m["instance_name"]: m for m in resolved_modules}
    schedule = control.get("schedule") or {}

    for phase in ("fast_loop", "slow_loop"):
        phase_text = (repaired.get(phase) or "").strip()
        lines = [x for x in phase_text.splitlines() if x.strip()] if phase_text else []

        for inst in schedule.get(phase) or []:
            mod = by_instance.get(inst)
            if not mod:
                lines.append(f"ERROR_UNRESOLVED_API({inst});")
                continue

            step_items = (mod.get("api_contract") or {}).get("step") or []
            expected_names = [x.get("function") for x in step_items if x.get("function")]
            if any(name in phase_text for name in expected_names):
                continue

            if step_items:
                lines.append(_pick_autocall(step_items, inst))
            else:
                lines.append(f"ERROR_UNRESOLVED_API({inst});")

        repaired[phase] = "\n".join(lines)

    return repaired


def sanitize_sections(sections: dict, control: dict, resolved_modules: list) -> dict:
    cleaned = dict(sections)
    by_instance = {m["instance_name"]: m for m in resolved_modules}
    schedule = control.get("schedule") or {}

    # init phase: drop unresolved placeholders to keep output close to ctl_main style.
    init_lines = []
    for line in (cleaned.get("init") or "").splitlines():
        if "ERROR_UNRESOLVED_API(" in line:
            continue
        init_lines.append(line)
    cleaned["init"] = "\n".join([x for x in init_lines if x.strip()])

    # fast/slow phase: if a valid step call exists for an instance, remove unresolved line for that instance.
    for phase in ("fast_loop", "slow_loop"):
        text = cleaned.get(phase) or ""
        lines = text.splitlines()

        valid_called = set()
        for inst in schedule.get(phase) or []:
            mod = by_instance.get(inst)
            if not mod:
                continue
            step_items = (mod.get("api_contract") or {}).get("step") or []
            names = [x.get("function") for x in step_items if x.get("function")]
            if any(name in text for name in names):
                valid_called.add(inst)

        out_lines = []
        for line in lines:
            m = re.search(r"ERROR_UNRESOLVED_API\(([^)]+)\)", line)
            if m and m.group(1).strip() in valid_called:
                continue
            out_lines.append(line)

        cleaned[phase] = "\n".join([x for x in out_lines if x.strip()])

    return cleaned


def main():
    parser = argparse.ArgumentParser(description="SiliconFlow DeepSeek-V3.2 codegen client")
    parser.add_argument("--control", required=True, help="Path to control structure JSON")
    parser.add_argument("--kb", required=True, help="Path to v2 knowledge base JSON")
    parser.add_argument("--out", required=True, help="Output C body file path")
    parser.add_argument("--raw", default="", help="Optional path to save raw response JSON")
    parser.add_argument("--prompt-out", default="", help="Optional path to save final user prompt")
    parser.add_argument(
        "--render-profile",
        default="generic",
        choices=["generic", "ctl_main"],
        help="Output rendering profile",
    )
    parser.add_argument("--extra", default="", help="Extra instruction for this generation")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="Model name")
    parser.add_argument("--base-url", default=os.getenv("SILICONFLOW_BASE_URL", DEFAULT_BASE_URL), help="SiliconFlow base URL")
    parser.add_argument("--temperature", type=float, default=0.2, help="Sampling temperature")
    parser.add_argument("--timeout", type=int, default=180, help="HTTP timeout seconds")
    parser.add_argument("--system", default=DEFAULT_SYSTEM_PROMPT, help="System prompt")
    args = parser.parse_args()

    api_key = os.getenv("SILICONFLOW_API_KEY") or os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("ERROR: Missing SILICONFLOW_API_KEY (or OPENAI_API_KEY).", file=sys.stderr)
        return 2

    control = read_json(args.control)
    kb = read_json(args.kb)
    resolved_modules = resolve_modules(control, kb)

    user_prompt = build_user_prompt(control, resolved_modules, args.extra, args.render_profile)
    if args.prompt_out:
        os.makedirs(os.path.dirname(os.path.abspath(args.prompt_out)), exist_ok=True)
        with open(args.prompt_out, "w", encoding="utf-8") as f:
            f.write(user_prompt)

    resp_json = call_chat(
        api_key=api_key,
        base_url=args.base_url,
        model=args.model,
        system_prompt=args.system,
        user_prompt=user_prompt,
        temperature=args.temperature,
        timeout=args.timeout,
    )

    text = extract_text(resp_json)
    if not text:
        print("ERROR: Empty model response content.", file=sys.stderr)
        return 3

    try:
        sections = parse_sections(text)
    except Exception as e:
        raise RuntimeError(f"invalid model output format: {e}") from e

    sections = ensure_required_calls(sections, control, resolved_modules)
    sections = sanitize_sections(sections, control, resolved_modules)

    if args.render_profile == "ctl_main":
        rendered = render_ctl_main_output(sections)
    else:
        rendered = render_c_output(sections)
    quality_gate(rendered, sections, control, resolved_modules)

    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        f.write(rendered)

    if args.raw:
        os.makedirs(os.path.dirname(os.path.abspath(args.raw)), exist_ok=True)
        with open(args.raw, "w", encoding="utf-8") as f:
            json.dump(resp_json, f, ensure_ascii=False, indent=2)

    print("Generation success")
    print(f"Model: {args.model}")
    print(f"Output: {args.out}")
    if args.raw:
        print(f"Raw: {args.raw}")
    if args.prompt_out:
        print(f"Prompt: {args.prompt_out}")
    print(f"Time: {datetime.now().isoformat()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
