"""Merge generated controller JSON into the Example C and header templates.

Reads the generated controller architecture JSON and loop-ids JSON, applies the
mapping rules from `Example/Example.txt` and `Example/Example2.txt`, and writes
generated `ctl_main.c` and `ctl_main.h` files.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import List


RULE_SNIPPETS = [
    # (match_name_contains, property, init, encoder_bind, enable)
    ("current", "real_speed", "    Setup_Motor_Current();\n", "    ctl_attach_mtr_current_ctrl_port(&mtr_ctrl, &iuvw.control_port, &udc.control_port, &pos_enc.encif, &spd_enc.encif);\n", "    ctl_enable_mtr_current_ctrl(&mtr_ctrl);\n"),
    ("current", "simulate_speed", "    Setup_Motor_Current();\n", "    ctl_attach_mtr_current_ctrl_port(&mtr_ctrl, &iuvw.control_port, &udc.control_port, &rg.enc, &spd_enc.encif);\n", "    ctl_enable_mtr_current_ctrl(&mtr_ctrl);\n"),
    ("mech", "speed", "    Setup_Mechanical_Controller();\n", "    ctl_attach_mech_ctrl(&mech_ctrl, &pos_enc.encif, &spd_enc.encif);\n", "    ctl_set_mech_ctrl_mode(&mech_ctrl, MECH_MODE_VELOCITY);\n"),
    ("mech", "position", "    Setup_Mechanical_Controller();\n", "    ctl_attach_mech_ctrl(&mech_ctrl, &pos_enc.encif, &spd_enc.encif);\n", "    ctl_set_mech_ctrl_mode(&mech_ctrl, MECH_MODE_POSITION);\n"),
]

def find_snippet(loop_name: str, prop: str):
    lname = (loop_name or "").lower()
    p = (prop or "").lower()
    for name_contains, prop_val, init, bind, enable in RULE_SNIPPETS:
        if name_contains in lname and prop_val == p:
            return init, bind, enable
    return None


def replace_section(text: str, start_marker: str, end_marker: str, insert_lines: List[str]) -> str:
    start_idx = text.find(start_marker)
    end_idx = text.find(end_marker, start_idx + len(start_marker))
    if start_idx == -1 or end_idx == -1:
        raise RuntimeError(f"markers not found: {start_marker} .. {end_marker}")

    before = text[: start_idx + len(start_marker)]
    after = text[end_idx:]

    body = "".join(insert_lines)
    return before + "\n" + body + after


def build_inserts(loop_items: List[dict]) -> tuple[List[str], List[str], List[str]]:
    inits: List[str] = []
    binds: List[str] = []
    enables: List[str] = []

    for item in loop_items:
        name = item.get("name")
        props = item.get("properties") or []
        prop = props[0] if props else ""
        matched = find_snippet(name, prop)
        if matched:
            init, bind, enable = matched
            if init and init not in inits:
                inits.append(init)
            if bind and bind not in binds:
                binds.append(bind)
            if enable and enable not in enables:
                enables.append(enable)

    return inits, binds, enables


def collect_loop_tokens(core_payload: dict, loop_payload: dict) -> tuple[bool, bool]:
    """Return flags for whether mech/current controller sections are needed."""

    names: set[str] = set()
    for item in loop_payload.get("selected_loops") or []:
        name = str(item.get("name") or "").strip().lower()
        if name:
            names.add(name)

    for block in core_payload.get("blocks") or []:
        name = str(block.get("name") or "").strip().lower()
        if name:
            names.add(name)

    needs_mech = any("mech" in name or "position" in name or "speed" in name for name in names)
    needs_current = any("current" in name for name in names)
    return needs_mech, needs_current


def generate_header(template_text: str, loop_items: List[dict]) -> str:
    """Generate ctl_main.h by rewriting the Example motor-control section."""

    start_marker = "        // Start Motor Control"
    end_marker = "        // End Motor Control"
    start_idx = template_text.find(start_marker)
    end_idx = template_text.find(end_marker, start_idx + len(start_marker))
    if start_idx == -1 or end_idx == -1:
        raise RuntimeError("unable to locate motor-control markers in header template")

    needs_mech = False
    needs_current = False
    for item in loop_items:
        name = str(item.get("name") or "").lower()
        prop = str((item.get("properties") or [""])[0]).lower()
        if "mech" in name or "position" in name or "speed" in name:
            needs_mech = True
        if "current" in name:
            needs_current = True
        if prop in {"position", "speed"}:
            needs_mech = True

    indent = "        "
    generated_lines: List[str] = []
    if needs_mech:
        generated_lines.append(f"{indent}ctl_step_mech_ctrl(&mech_ctrl);\n")
        generated_lines.append("\n")
        generated_lines.append(f"{indent}ctl_set_mtr_current_ctrl_ref(&mtr_ctrl, 0, ctl_get_mech_cmd(&mech_ctrl));\n")
        generated_lines.append("\n")
    if needs_current:
        generated_lines.append(f"{indent}ctl_step_current_controller(&mtr_ctrl);\n")
        generated_lines.append("\n")

    if not generated_lines:
        generated_lines.append(f"{indent}// controller body disabled by generated architecture\n")

    before = template_text[: start_idx + len(start_marker)]
    after = template_text[end_idx:]
    return before + "\n" + "".join(generated_lines) + after


def main(loop_ids_path: Path, template_path: Path, output_path: Path, core_path: Path | None = None, header_template_path: Path | None = None, header_output_path: Path | None = None) -> int:
    if not loop_ids_path.exists():
        print(f"missing loop ids: {loop_ids_path}")
        return 2
    if not template_path.exists():
        print(f"missing template: {template_path}")
        return 2
    if core_path is not None and not core_path.exists():
        print(f"missing core structure: {core_path}")
        return 2
    if header_template_path is not None and not header_template_path.exists():
        print(f"missing header template: {header_template_path}")
        return 2

    payload = json.loads(loop_ids_path.read_text(encoding="utf-8"))
    loops = payload.get("selected_loops") or []
    core_payload = json.loads(core_path.read_text(encoding="utf-8")) if core_path else {}

    inits, binds, enables = build_inserts(loops)

    tpl = template_path.read_text(encoding="utf-8")

    tpl = replace_section(tpl, "    // Start Controller Init", "    // End Controller Init", inits)
    tpl = replace_section(tpl, "    // Start Encoder Binding", "    // End Encoder Binding", binds)
    tpl = replace_section(tpl, "    // Start Enable", "    // End Enable", enables)

    output_path.write_text(tpl, encoding="utf-8")
    print(f"Wrote {output_path}")

    if header_template_path and header_output_path:
        header_tpl = header_template_path.read_text(encoding="utf-8")
        header_out = generate_header(header_tpl, loops)
        header_output_path.write_text(header_out, encoding="utf-8")
        print(f"Wrote {header_output_path}")

    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Merge loop-ids into ctl_main template.")
    parser.add_argument("--loop-ids", type=Path, default=Path(__file__).with_name("controller_loop_ids_generated.json"))
    parser.add_argument("--core-structure", type=Path, default=Path(__file__).with_name("controller_core_structure.json"))
    parser.add_argument("--template", type=Path, default=Path(__file__).with_name("Example").joinpath("ctl_main.c"))
    parser.add_argument("--output", type=Path, default=Path(__file__).with_name("ctl_main.generated.c"))
    parser.add_argument("--header-template", type=Path, default=Path(__file__).with_name("Example").joinpath("ctl_main.h"))
    parser.add_argument("--header-output", type=Path, default=Path(__file__).with_name("ctl_main.generated.h"))
    args = parser.parse_args()
    raise SystemExit(main(args.loop_ids, args.template, args.output, core_path=args.core_structure, header_template_path=args.header_template, header_output_path=args.header_output))
