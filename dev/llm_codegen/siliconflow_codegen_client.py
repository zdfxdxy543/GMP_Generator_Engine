#!/usr/bin/env python3
import argparse
import difflib
import json
import os
import re
import sys
import urllib.error
import urllib.request
from collections import defaultdict
from datetime import datetime

from llm_settings import default_settings_path, read_llm_settings, resolve_api_key

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

C_KEYWORDS = {
    "if",
    "else",
    "for",
    "while",
    "switch",
    "return",
    "sizeof",
}

GENERIC_CTL_INCLUDES = [
    "#include <gmp_core.h>",
    "#include <xplt.peripheral.h>",
    "#include <ctrl_settings.h>",
    "#include <core/pm/function_scheduler.h>",
    "#include <ctl/framework/cia402_state_machine.h>",
    "#include <ctl/component/interface/adc_channel.h>",
    "#include <ctl/component/interface/pwm_channel.h>",
    "#include <ctl/component/interface/spwm_modulator.h>",
    "#include <ctl/component/motor_control/basic/mtr_protection.h>",
    "#include <ctl/component/motor_control/current_loop/foc_core.h>",
    "#include <ctl/component/motor_control/mechanical_loop/basic_mech_ctrl.h>",
]


def read_json(path: str):
    with open(path, "r", encoding="utf-8-sig") as f:
        return json.load(f)


def read_text_if_exists(path: str) -> str:
    if not path:
        return ""
    if not os.path.exists(path):
        return ""
    with open(path, "r", encoding="utf-8-sig") as f:
        return f.read().strip()


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


def build_user_prompt(control: dict, resolved_modules: list, extra_instruction: str, render_profile: str, experience_text: str) -> str:
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

    prompt = (
        "Task: Generate control function-body statements for init/fast_loop/slow_loop/fault.\n"
        + profile_hint
        + "Hard constraints:\n"
        + "1) Return STRICT JSON object only, no markdown, no prose.\n"
        + "2) JSON keys MUST be exactly: init, fast_loop, slow_loop, fault.\n"
        + "3) Each value is C statements only (no outer braces, no declarations, no comments).\n"
        + "4) Use only function names from api_contract.step/api_contract.attach for each module.\n"
        + "5) Never invent new API names.\n"
        + "6) Respect schedule order exactly.\n"
        + "7) For required fast_loop/slow_loop calls, emit runnable C statements only; NEVER use ERROR_UNRESOLVED_API placeholders.\n\n"
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

    if experience_text:
        prompt += "\nGeneration experience guidance (must follow when not conflicting with hard constraints):\n"
        prompt += experience_text + "\n"

    return prompt


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


def clean_llm_code_text(text: str) -> str:
    cleaned = strip_code_fence(text).strip()

    # Some model responses wrap file content in JSON, e.g. {"file_content":"...\\n..."}.
    # Unwrap these payloads so written files keep real line breaks.
    probe = cleaned
    for _ in range(2):
        try:
            obj = json.loads(probe)
        except Exception:
            break

        if isinstance(obj, dict):
            if isinstance(obj.get("file_content"), str):
                return obj["file_content"].strip()
            if isinstance(obj.get("content"), str):
                return obj["content"].strip()
            break

        if isinstance(obj, str):
            probe = obj.strip()
            continue

        break

    return cleaned


def _normalize_escaped_file_text(text: str) -> str:
    out = text.strip()

    # Case 1: JSON-string style payload: "...\n...\"..."
    if len(out) >= 2 and out[0] == '"' and out[-1] == '"':
        try:
            decoded = json.loads(out)
            if isinstance(decoded, str):
                out = decoded
        except Exception:
            pass

    # Case 2: raw escaped blob (no real newlines, lots of escape sequences).
    has_real_newline = "\n" in out
    has_escaped_newline = "\\n" in out
    if (not has_real_newline) and has_escaped_newline:
        out = out.replace("\\r\\n", "\n")
        out = out.replace("\\n", "\n")
        out = out.replace("\\t", "    ")
        out = out.replace('\\"', '"')

    # Common cleanup for serialized responses.
    out = out.replace("\r\n", "\n")
    out = out.rstrip() + "\n"
    return out


def build_project_context(control: dict, resolved_modules: list) -> str:
    schedule = control.get("schedule") or {}
    links = control.get("links") or []
    return (
        "Resolved modules JSON:\n"
        + json.dumps(resolved_modules, ensure_ascii=False, indent=2)
        + "\n\nSchedule JSON:\n"
        + json.dumps(schedule, ensure_ascii=False, indent=2)
        + "\n\nLinks JSON:\n"
        + json.dumps(links, ensure_ascii=False, indent=2)
        + "\n"
    )


def _file_prompt_header(file_name: str) -> str:
    return (
        f"Task: Generate exactly one complete file: {file_name}.\n"
        "Hard constraints:\n"
        "1) Return file content only, no markdown fences, no prose.\n"
        "2) Keep C/C header syntax valid and compilable.\n"
        "3) Use only known API names from resolved modules; do not invent APIs.\n"
        "4) Keep style close to GMP ctl_main/user_main references.\n"
        "5) Include function declarations/definitions needed for this file only.\n\n"
    )


def build_single_file_prompt(file_key: str, control: dict, resolved_modules: list, generated_so_far: dict, validation_feedback: str = "", experience_text: str = "") -> str:
    ctx = build_project_context(control, resolved_modules)
    feedback_block = ""
    if validation_feedback:
        feedback_block = (
            "\nPrevious validation failure to fix in this retry:\n"
            + validation_feedback
            + "\n"
        )

    if file_key == "ctl_main.h":
        prompt = (
            _file_prompt_header("ctl_main.h")
            + "Required content:\n"
            + "- Include required ctl/component/framework headers.\n"
            + "- Extern declarations for controller global instances.\n"
            + "- Prototypes: ctl_init, ctl_mainloop, clear_all_controllers, tsk_protect, ctl_enable_pwm, ctl_disable_pwm.\n"
            + "- Inline dispatch function prototype/definition location should be header-friendly.\n\n"
            + ctx
            + feedback_block
        )
        if experience_text:
            prompt += "\nGeneration experience guidance:\n" + experience_text + "\n"
        return prompt

    if file_key == "ctl_main.c":
        dep = generated_so_far.get("ctl_main.h", "")
        prompt = (
            _file_prompt_header("ctl_main.c")
            + "Required content:\n"
            + "- Include gmp headers + ctl_main.h.\n"
            + "- Define all global controller instances declared in ctl_main.h.\n"
            + "- Implement ctl_init, ctl_mainloop, clear_all_controllers, tsk_protect, ctl_enable_pwm, ctl_disable_pwm.\n"
            + "- Initialize CiA402 and motor protection path.\n"
            + "- Bind tunable parameter apply hook in ctl_init.\n\n"
            + "Reference from previously generated ctl_main.h:\n"
            + dep
            + "\n\n"
            + ctx
            + feedback_block
        )
        if experience_text:
            prompt += "\nGeneration experience guidance:\n" + experience_text + "\n"
        return prompt

    if file_key == "user_main.h":
        prompt = (
            _file_prompt_header("user_main.h")
            + "Required content:\n"
            + "- Include scheduler/AT core headers.\n"
            + "- Extern declarations for user_main global objects.\n"
            + "- Prototypes: init, mainloop, setup_peripheral, ctl_init, ctl_mainloop.\n"
            + "- Keep C extern guard style.\n\n"
            + ctx
            + feedback_block
        )
        if experience_text:
            prompt += "\nGeneration experience guidance:\n" + experience_text + "\n"
        return prompt

    if file_key == "user_main.c":
        dep_h = generated_so_far.get("user_main.h", "")
        dep_ctl_h = generated_so_far.get("ctl_main.h", "")
        prompt = (
            _file_prompt_header("user_main.c")
            + "Required content:\n"
            + "- Include gmp_core.h, user_main.h, ctl_main.h.\n"
            + "- Create scheduler and task table that includes tsk_protect.\n"
            + "- Implement init() and mainloop() around scheduler dispatch.\n"
            + "- Keep communication part minimal and non-blocking.\n\n"
            + "Reference from previously generated user_main.h:\n"
            + dep_h
            + "\n\nReference from previously generated ctl_main.h:\n"
            + dep_ctl_h
            + "\n\n"
            + ctx
            + feedback_block
        )
        if experience_text:
            prompt += "\nGeneration experience guidance:\n" + experience_text + "\n"
        return prompt

    raise ValueError(f"unsupported file key: {file_key}")


def _validate_single_file_output(file_name: str, text: str):
    if not text.strip():
        raise RuntimeError(f"empty output for {file_name}")

    required_patterns = {
        "ctl_main.h": [
            r"\bctl_init\s*\(",
            r"\bctl_mainloop\s*\(",
            r"\bclear_all_controllers\s*\(",
        ],
        "ctl_main.c": [
            r"\bctl_init\s*\(",
            r"\bctl_mainloop\s*\(",
            r"\btsk_protect\s*\(",
        ],
        "user_main.h": [
            r"\binit\s*\(",
            r"\bmainloop\s*\(",
            r"\bsetup_peripheral\s*\(",
        ],
        "user_main.c": [
            r"\binit\s*\(",
            r"\bmainloop\s*\(",
            r"\bgmp_scheduler_dispatch\s*\(",
        ],
    }
    for pattern in required_patterns.get(file_name, []):
        if re.search(pattern, text) is None:
            raise RuntimeError(f"missing required pattern in {file_name}: {pattern}")


def generate_four_project_files(api_key: str, base_url: str, model: str, system_prompt: str, temperature: float, timeout: int, control: dict, resolved_modules: list, output_dir: str, max_attempts_per_file: int = 3, experience_text: str = ""):
    file_order = ["ctl_main.h", "ctl_main.c", "user_main.h", "user_main.c"]
    generated = {}
    raw_by_file = {}
    prompt_by_file = {}

    os.makedirs(output_dir, exist_ok=True)

    for file_name in file_order:
        last_error = ""
        success = False
        for attempt in range(1, max(1, max_attempts_per_file) + 1):
            user_prompt = build_single_file_prompt(file_name, control, resolved_modules, generated, last_error, experience_text)
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
                last_error = f"empty model response for {file_name}"
                continue

            cleaned = clean_llm_code_text(text)
            cleaned = _normalize_escaped_file_text(cleaned)
            try:
                _validate_single_file_output(file_name, cleaned)
            except Exception as e:
                last_error = str(e)
                continue

            generated[file_name] = cleaned
            raw_by_file[file_name] = resp_json
            prompt_by_file[file_name] = user_prompt
            out_path = os.path.join(output_dir, file_name)
            with open(out_path, "w", encoding="utf-8") as f:
                f.write(cleaned)
            print(f"[project4] generated {file_name} ({attempt}/{max_attempts_per_file}) -> {out_path}")
            success = True
            break

        if not success:
            raise RuntimeError(f"failed to generate valid file after retries: {file_name}; last_error={last_error}")

    return generated, raw_by_file, prompt_by_file


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


def _sanitize_ident(text: str) -> str:
    s = re.sub(r"[^A-Za-z0-9_]", "_", text or "")
    if not s:
        return "unnamed"
    if not re.match(r"^[A-Za-z_]", s):
        s = "p_" + s
    return s


def _extract_type_from_signature(signature: str) -> str | None:
    m = re.search(r"\(([^)]*)\)", signature or "")
    if not m:
        return None
    args = [x.strip() for x in m.group(1).split(",")]
    if not args or args[0] in ("", "void"):
        return None

    first = args[0]
    # Example accepted forms: "foo_t* x", "const foo_t *x"
    m2 = re.match(r"^(?:const\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*\*\s*[A-Za-z_][A-Za-z0-9_]*$", first)
    if not m2:
        return None
    return m2.group(1)


def _infer_instance_type(mod: dict) -> str | None:
    api = mod.get("api_contract") or {}
    for entry in (api.get("step") or []):
        t = _extract_type_from_signature(entry.get("signature") or "")
        if t:
            return t
    for entry in (api.get("attach") or []):
        t = _extract_type_from_signature(entry.get("signature") or "")
        if t:
            return t
    return None


def _build_instance_declarations(resolved_modules: list) -> str:
    lines = [
        "// auto-generated instance declarations",
    ]
    for mod in resolved_modules:
        inst = mod.get("instance_name")
        if not inst:
            continue
        type_name = _infer_instance_type(mod)
        if type_name:
            lines.append(f"static {type_name} {inst};")
        else:
            lines.append(f"// unresolved type for instance: {inst} ({mod.get('canonical_id')})")
            # Keep symbol available even when KB lacks enough type metadata.
            lines.append(f"static uint8_t {inst};")
    return "\n".join(lines)


def _build_framework_globals(resolved_modules: list) -> str:
    lower_names = {str(m.get("instance_name") or "").lower() for m in resolved_modules}
    lines = [
        "// framework globals",
        "cia402_sm_t cia402_sm;",
        "volatile fast_gt flag_system_running = 0;",
        "volatile fast_gt flag_error = 0;",
    ]
    if "protection" not in lower_names and "motor_protection" not in lower_names:
        lines.append("ctl_mtr_protect_t protection;")
    return "\n".join(lines)


def _pick_protection_instance(resolved_modules: list) -> str:
    for mod in resolved_modules:
        name = str(mod.get("instance_name") or "")
        low = name.lower()
        cid = str(mod.get("canonical_id") or "").lower()
        if "protect" in low or "protection" in low or "protect" in cid:
            return name
    return "protection"


def _validate_resolved_instance_types(control: dict, resolved_modules: list):
    by_instance = {m.get("instance_name"): m for m in resolved_modules}
    schedule = control.get("schedule") or {}
    unresolved = []
    # Enforce hard typing only for loop phases that must be runnable.
    for phase in ("fast_loop", "slow_loop"):
        for inst in (schedule.get(phase) or []):
            mod = by_instance.get(inst)
            if not mod:
                unresolved.append((phase, inst, "instance not resolved from KB"))
                continue
            if _infer_instance_type(mod) is None:
                unresolved.append((phase, inst, f"missing inferable instance type ({mod.get('canonical_id')})"))

    if unresolved:
        details = " | ".join([f"{p}:{i}: {r}" for p, i, r in unresolved])
        raise RuntimeError("unresolved typed instances in scheduled path: " + details)


def _build_clear_all_controllers(resolved_modules: list) -> str:
    lines = [
        "void clear_all_controllers(void)",
        "{",
    ]
    for mod in resolved_modules:
        inst = mod.get("instance_name")
        api = mod.get("api_contract") or {}
        steps = [x.get("function") for x in (api.get("step") or []) if x.get("function")]
        if not inst:
            continue
        for fn in steps:
            clear_fn = fn.replace("ctl_step_", "ctl_clear_")
            lines.append(f"    // Optional clear hook: {clear_fn}(&{inst});")
            break
    lines.append("}")
    return "\n".join(lines)


def _build_framework_hooks(protection_name: str) -> str:
    return (
        "gmp_task_status_t tsk_protect(gmp_task_t* tsk)\n"
        "{\n"
        "    GMP_UNUSED_VAR(tsk);\n"
        "#ifdef ENABLE_MOTOR_FAULT_PROTECTION\n"
        f"    if (ctl_dispatch_mtr_protect_slow(&{protection_name}))\n"
        "    {\n"
        "        cia402_fault_request(&cia402_sm);\n"
        "    }\n"
        "#endif\n"
        "    return GMP_TASK_DONE;\n"
        "}\n\n"
        "void ctl_enable_pwm(void)\n"
        "{\n"
        "    ctl_fast_enable_output();\n"
        "}\n\n"
        "void ctl_disable_pwm(void)\n"
        "{\n"
        "    ctl_fast_disable_output();\n"
        "}\n"
    )


def _closest_allowed_name(fn: str, allowed: list[str]) -> str | None:
    if not allowed:
        return None
    choices = difflib.get_close_matches(fn, allowed, n=1, cutoff=0.78)
    return choices[0] if choices else None


def _repair_and_restrict_calls(sections: dict, resolved_modules: list) -> dict:
    allowed = []
    for mod in resolved_modules:
        api = mod.get("api_contract") or {}
        for x in (api.get("step") or []):
            fn = x.get("function")
            if fn:
                allowed.append(fn)
        for x in (api.get("attach") or []):
            fn = x.get("function")
            if fn:
                allowed.append(fn)
    allowed = sorted(set(allowed))

    repaired = {}
    for phase in ("init", "fast_loop", "slow_loop", "fault"):
        src = sections.get(phase) or ""
        out_lines = []
        for line in src.splitlines():
            updated = line
            calls = re.findall(r"\b([A-Za-z_][A-Za-z0-9_]*)\s*\(", line)
            drop_line = False
            for fn in calls:
                if fn in C_KEYWORDS or fn in allowed:
                    continue
                fixed = _closest_allowed_name(fn, allowed)
                if fixed:
                    updated = re.sub(rf"\b{re.escape(fn)}\b", fixed, updated)
                else:
                    # Restrict unknown/nonexistent function calls from generated code.
                    drop_line = True
                    break
            if not drop_line and updated.strip():
                out_lines.append(updated)
        repaired[phase] = "\n".join(out_lines)

    return repaired


def _to_c_scalar(value):
    if isinstance(value, bool):
        return "bool", "true" if value else "false"
    if isinstance(value, int) and not isinstance(value, bool):
        return "int32_t", str(value)
    if isinstance(value, float):
        text = f"{value:.9g}"
        if "." not in text and "e" not in text and "E" not in text:
            text += ".0"
        return "float", text + "f"
    return None, None


def _build_tunable_storage(resolved_modules: list) -> str:
    fields = []
    for mod in resolved_modules:
        inst = mod.get("instance_name") or "module"
        params = mod.get("params") or {}
        if not isinstance(params, dict):
            continue
        for k, v in params.items():
            c_type, c_val = _to_c_scalar(v)
            if not c_type:
                continue
            field = _sanitize_ident(f"{inst}__{k}")
            fields.append((field, c_type, c_val, inst, k))

    if not fields:
        return (
            "// no scalar tunable parameters were found in control.modules[*].params\n"
            "typedef struct\n"
            "{\n"
            "    uint8_t reserved;\n"
            "} ctl_tunable_params_t;\n\n"
            "ctl_tunable_params_t g_ctl_tunable_params = { 0 };\n\n"
            "void ctl_update_tunable_params(const ctl_tunable_params_t* src)\n"
            "{\n"
            "    if (!src) {\n"
            "        return;\n"
            "    }\n"
            "    g_ctl_tunable_params = *src;\n"
            "}\n\n"
            "void ctl_apply_tunable_params(void)\n"
            "{\n"
            "    // Bind g_ctl_tunable_params to instance fields in your project-specific code.\n"
            "    (void)g_ctl_tunable_params;\n"
            "}\n"
        )

    struct_lines = ["typedef struct", "{"]
    init_lines = ["ctl_tunable_params_t g_ctl_tunable_params =", "{"]
    for field, c_type, c_val, _, _ in fields:
        struct_lines.append(f"    {c_type} {field};")
        init_lines.append(f"    .{field} = {c_val},")
    struct_lines.append("} ctl_tunable_params_t;")
    init_lines.append("};")

    apply_hint = [
        "void ctl_apply_tunable_params(void)",
        "{",
        "    // Project-specific binding hook for external tuning parameters.",
    ]
    for field, _, _, inst, key in fields:
        apply_hint.append(f"    // Example: {inst}.{key} = g_ctl_tunable_params.{field};")
    apply_hint.append("    (void)g_ctl_tunable_params;")
    apply_hint.append("}")

    return (
        "// externally tunable parameter storage\n"
        + "\n".join(struct_lines)
        + "\n\n"
        + "\n".join(init_lines)
        + "\n\n"
        + "void ctl_update_tunable_params(const ctl_tunable_params_t* src)\n"
        + "{\n"
        + "    if (!src) {\n"
        + "        return;\n"
        + "    }\n"
        + "    g_ctl_tunable_params = *src;\n"
        + "}\n\n"
        + "\n".join(apply_hint)
        + "\n"
    )


def render_ctl_main_output(sections: dict, resolved_modules: list) -> str:
    init_body = indent_block(sections.get("init", ""))
    fast_body = indent_block(sections.get("fast_loop", ""))
    slow_body = indent_block(sections.get("slow_loop", ""))
    fault_body = indent_block(sections.get("fault", ""))
    declarations = _build_instance_declarations(resolved_modules)
    globals_block = _build_framework_globals(resolved_modules)
    tunable_storage = _build_tunable_storage(resolved_modules)
    clear_helpers = _build_clear_all_controllers(resolved_modules)
    protection_name = _pick_protection_instance(resolved_modules)
    framework_hooks = _build_framework_hooks(protection_name)

    includes = "\n".join(GENERIC_CTL_INCLUDES)

    dispatch_extra = ""
    if slow_body:
        dispatch_extra += "\n    // slow-loop body from schedule\n" + slow_body + "\n"
    if fault_body:
        dispatch_extra += "\n    // fault body from schedule\n" + fault_body + "\n"

    return (
        "// generated ctl_main-style code body\n\n"
        + includes
        + "\n\n"
        + declarations
        + "\n\n"
        + globals_block
        + "\n\n"
        + tunable_storage
        + "\n"
        "void ctl_init(void)\n"
        "{\n"
        "    ctl_disable_pwm();\n"
        "    init_cia402_state_machine(&cia402_sm);\n"
        f"    ctl_init_mtr_protect(&{protection_name}, CONTROLLER_FREQUENCY);\n"
        "    ctl_apply_tunable_params();\n"
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
        "\n"
        + clear_helpers
        + "\n\n"
        + framework_hooks
    )


def quality_gate(rendered_c: str, sections: dict, control: dict, resolved_modules: list):
    lower = rendered_c.lower()
    for phrase in FORBIDDEN_PHRASES:
        if phrase in lower:
            raise RuntimeError(f"forbidden phrase in output: {phrase}")
    if "ERROR_UNRESOLVED_API(" in rendered_c:
        raise RuntimeError("non-runnable output: contains ERROR_UNRESOLVED_API placeholder")

    by_instance = {m["instance_name"]: m for m in resolved_modules}
    schedule = control.get("schedule") or {}

    allowed_fn = set()
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

    # Only enforce strict API whitelist on loop phases.
    for phase_name in ("fast_loop", "slow_loop"):
        phase_text = sections.get(phase_name, "")
        for fn in _find_calls(phase_text):
            if fn in C_KEYWORDS:
                continue
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


def _pick_autocall(step_items: list, instance_name: str) -> str | None:
    for step in step_items:
        fn = step.get("function")
        sig = step.get("signature") or ""
        # Prefer single-pointer-argument functions, safe for &instance calling.
        if fn and re.match(r"^\w+\s*\([^,]*\*[^,]*\)\s*$", sig):
            return f"{fn}(&{instance_name});"
    return None


def _has_instance_call(text: str, fn_name: str, instance_name: str) -> bool:
    pattern = rf"\b{re.escape(fn_name)}\s*\(\s*&?\s*{re.escape(instance_name)}\b"
    return re.search(pattern, text) is not None


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
                raise RuntimeError(f"scheduled instance not resolved: {inst}")

            step_items = (mod.get("api_contract") or {}).get("step") or []
            expected_names = [x.get("function") for x in step_items if x.get("function")]
            current_text = "\n".join(lines)
            if any(_has_instance_call(current_text, name, inst) for name in expected_names):
                continue

            # Function name may exist with malformed/non-matching arguments. Remove and repair.
            if any(re.search(rf"\b{re.escape(name)}\s*\(", current_text) for name in expected_names):
                filtered = []
                for line in lines:
                    if any(re.search(rf"\b{re.escape(name)}\s*\(", line) for name in expected_names):
                        continue
                    filtered.append(line)
                lines = filtered

            if step_items:
                stmt = _pick_autocall(step_items, inst)
                if not stmt:
                    raise RuntimeError(
                        f"non-runnable step API for scheduled instance: {inst}; cannot auto-generate safe call"
                    )
                lines.append(stmt)
            else:
                raise RuntimeError(f"no step api for scheduled loop instance: {inst}")

        repaired[phase] = "\n".join(lines)

    return repaired


def sanitize_sections(sections: dict, control: dict, resolved_modules: list) -> dict:
    cleaned = dict(sections)
    by_instance = {m["instance_name"]: m for m in resolved_modules}
    schedule = control.get("schedule") or {}

    # init phase: keep only non-empty lines.
    init_lines = []
    for line in (cleaned.get("init") or "").splitlines():
        init_lines.append(line)
    cleaned["init"] = "\n".join([x for x in init_lines if x.strip()])

    # fast/slow phase: compact blank lines only.
    for phase in ("fast_loop", "slow_loop"):
        text = cleaned.get(phase) or ""
        cleaned[phase] = "\n".join([x for x in text.splitlines() if x.strip()])

    return cleaned


def main():
    parser = argparse.ArgumentParser(description="SiliconFlow DeepSeek-V3.2 codegen client")
    parser.add_argument("--control", required=True, help="Path to control structure JSON")
    parser.add_argument("--kb", required=True, help="Path to v2 knowledge base JSON")
    parser.add_argument("--out", required=True, help="Output C body file path")
    parser.add_argument("--llm-config", default=default_settings_path(), help="Path to LLM settings JSON")
    parser.add_argument("--raw", default="", help="Optional path to save raw response JSON")
    parser.add_argument("--prompt-out", default="", help="Optional path to save final user prompt")
    parser.add_argument(
        "--render-profile",
        default="generic",
        choices=["generic", "ctl_main", "project4"],
        help="Output rendering profile",
    )
    parser.add_argument("--out-dir", default="", help="Output directory for multi-file generation mode")
    parser.add_argument("--extra", default="", help="Extra instruction for this generation")
    parser.add_argument("--model", default="", help="Model name (overrides llm config)")
    parser.add_argument("--base-url", default="", help="SiliconFlow base URL (overrides llm config)")
    parser.add_argument("--temperature", type=float, default=None, help="Sampling temperature (overrides llm config)")
    parser.add_argument("--timeout", type=int, default=None, help="HTTP timeout seconds (overrides llm config)")
    parser.add_argument("--system", default="", help="System prompt (overrides llm config)")
    parser.add_argument("--max-file-attempts", type=int, default=None, help="Max retries per file in project4 mode (overrides llm config)")
    parser.add_argument("--experience-md", default="dev/llm_codegen/generation_experience.md", help="Path to generation experience markdown file")
    args = parser.parse_args()

    llm_cfg = read_llm_settings(args.llm_config)
    model = args.model or str(llm_cfg.get("model") or "")
    base_url = args.base_url or str(llm_cfg.get("base_url") or "")
    temperature = args.temperature if args.temperature is not None else float(llm_cfg.get("temperature") or 0.0)
    timeout = args.timeout if args.timeout is not None else int(llm_cfg.get("timeout") or 180)
    max_file_attempts = args.max_file_attempts if args.max_file_attempts is not None else int(llm_cfg.get("max_project4_file_attempts") or 3)
    system_prompt = args.system or str((llm_cfg.get("system_prompts") or {}).get("codegen") or DEFAULT_SYSTEM_PROMPT)
    experience_text = read_text_if_exists(args.experience_md)

    api_key = resolve_api_key(llm_cfg)
    if not api_key:
        print("ERROR: Missing api_key in llm_settings.json (or SILICONFLOW_API_KEY/OPENAI_API_KEY).", file=sys.stderr)
        return 2

    control = read_json(args.control)
    kb = read_json(args.kb)
    resolved_modules = resolve_modules(control, kb)
    _validate_resolved_instance_types(control, resolved_modules)

    if args.render_profile == "project4":
        generated, raw_by_file, prompt_by_file = generate_four_project_files(
            api_key=api_key,
            base_url=base_url,
            model=model,
            system_prompt=system_prompt,
            temperature=temperature,
            timeout=timeout,
            control=control,
            resolved_modules=resolved_modules,
            output_dir=(args.out_dir or os.path.dirname(os.path.abspath(args.out)) or os.getcwd()),
            max_attempts_per_file=max_file_attempts,
            experience_text=experience_text,
        )

        output_dir = args.out_dir or os.path.dirname(os.path.abspath(args.out)) or os.getcwd()

        # Keep compatibility: write a small manifest into --out.
        manifest = {
            "mode": "project4",
            "files": [os.path.join(output_dir, x) for x in ["ctl_main.h", "ctl_main.c", "user_main.h", "user_main.c"]],
            "generated_at": datetime.now().isoformat(),
        }
        os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(manifest, f, ensure_ascii=False, indent=2)

        if args.raw:
            os.makedirs(os.path.dirname(os.path.abspath(args.raw)), exist_ok=True)
            with open(args.raw, "w", encoding="utf-8") as f:
                json.dump(raw_by_file, f, ensure_ascii=False, indent=2)

        if args.prompt_out:
            os.makedirs(os.path.dirname(os.path.abspath(args.prompt_out)), exist_ok=True)
            with open(args.prompt_out, "w", encoding="utf-8") as f:
                for file_name in ["ctl_main.h", "ctl_main.c", "user_main.h", "user_main.c"]:
                    f.write(f"===== PROMPT {file_name} =====\n")
                    f.write(prompt_by_file[file_name])
                    f.write("\n\n")

        print("Generation success (project4)")
        print(f"Model: {model}")
        print(f"Output directory: {output_dir}")
        for file_name in ["ctl_main.h", "ctl_main.c", "user_main.h", "user_main.c"]:
            print(f"File: {os.path.join(output_dir, file_name)}")
        if args.raw:
            print(f"Raw: {args.raw}")
        if args.prompt_out:
            print(f"Prompt: {args.prompt_out}")
        print(f"Time: {datetime.now().isoformat()}")
        return 0

    user_prompt = build_user_prompt(control, resolved_modules, args.extra, args.render_profile, experience_text)
    if args.prompt_out:
        os.makedirs(os.path.dirname(os.path.abspath(args.prompt_out)), exist_ok=True)
        with open(args.prompt_out, "w", encoding="utf-8") as f:
            f.write(user_prompt)

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
        print("ERROR: Empty model response content.", file=sys.stderr)
        return 3

    try:
        sections = parse_sections(text)
    except Exception as e:
        raise RuntimeError(f"invalid model output format: {e}") from e

    sections = _repair_and_restrict_calls(sections, resolved_modules)
    sections = ensure_required_calls(sections, control, resolved_modules)
    sections = sanitize_sections(sections, control, resolved_modules)

    if args.render_profile == "ctl_main":
        rendered = render_ctl_main_output(sections, resolved_modules)
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
    print(f"Model: {model}")
    print(f"Output: {args.out}")
    if args.raw:
        print(f"Raw: {args.raw}")
    if args.prompt_out:
        print(f"Prompt: {args.prompt_out}")
    print(f"Time: {datetime.now().isoformat()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
