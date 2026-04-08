#!/usr/bin/env python3
import argparse
import json
from datetime import datetime

PMSM_SPEED_KEYWORDS = [
    "永磁同步电机",
    "pmsm",
    "速度控制",
    "speed control",
    "speed loop",
]


def read_json(path: str):
    with open(path, "r", encoding="utf-8-sig") as f:
        return json.load(f)


def contains_any(text: str, keywords: list[str]) -> bool:
    t = text.lower()
    return any(k.lower() in t for k in keywords)


def make_pmsm_speed_control_structure() -> dict:
    return {
        "project": {
            "name": "nl_pmsm_speed_demo",
            "target": "GMP_CTL",
            "notes": "Generated from natural language instruction",
            "generated_at": datetime.now().isoformat(),
        },
        "modules": [
            {
                "instance_name": "motor_if",
                "canonical_id": "MC_INTERFACE__motor_control_interface_motor_universal_interface",
                "params": {},
                "schedule_hint": "init",
            },
            {
                "instance_name": "mech_ctrl",
                "canonical_id": "MECHANICAL_CONTROLLER__motor_control_mechanical_loop_basic_mech_ctrl",
                "params": {
                    "speed_limit": 1.0,
                    "cur_limit": 0.3
                },
                "schedule_hint": "fast_loop",
            },
            {
                "instance_name": "mtr_ctrl",
                "canonical_id": "CURRENT_CONTROLLER__motor_control_current_loop_foc_core",
                "params": {
                    "voltage_limit_max": 0.95,
                    "voltage_limit_min": -0.95,
                },
                "schedule_hint": "fast_loop",
            },
            {
                "instance_name": "spwm",
                "canonical_id": "CTL_TP_MODULATION_API__interface_spwm_modulator",
                "params": {},
                "schedule_hint": "fast_loop",
            },
        ],
        "links": [
            {
                "from": "motor_if.speed",
                "to": "mech_ctrl.vel_feedback",
                "signal": "speed_pu",
            },
            {
                "from": "mech_ctrl.iq_ref",
                "to": "mtr_ctrl.current_ref_q",
                "signal": "iq_ref",
            },
            {
                "from": "mtr_ctrl.vab0",
                "to": "spwm.vab0_in",
                "signal": "vab0",
            },
        ],
        "schedule": {
            "init": ["motor_if", "mech_ctrl", "mtr_ctrl", "spwm"],
            "fast_loop": ["mech_ctrl", "mtr_ctrl", "spwm"],
            "slow_loop": [],
            "fault": [],
        },
    }


def validate_canonical_ids(control: dict, kb_items: list):
    known = {x.get("canonical_id") for x in kb_items if x.get("canonical_id")}
    missing = []
    for m in control.get("modules") or []:
        cid = m.get("canonical_id")
        if cid and cid not in known:
            missing.append(cid)
    if missing:
        raise ValueError("unknown canonical_id in generated control: " + ", ".join(missing))


def build_control_from_instruction(instruction: str) -> dict:
    if contains_any(instruction, PMSM_SPEED_KEYWORDS):
        return make_pmsm_speed_control_structure()

    raise ValueError(
        "Unsupported instruction. Currently supported intents include PMSM speed control."
    )


def main():
    parser = argparse.ArgumentParser(description="Convert natural-language instruction to strict control structure JSON")
    parser.add_argument("--instruction", required=True, help="Natural-language generation instruction")
    parser.add_argument("--kb", required=True, help="Knowledge base JSON path")
    parser.add_argument("--out", required=True, help="Output control JSON path")
    args = parser.parse_args()

    kb = read_json(args.kb)
    control = build_control_from_instruction(args.instruction)
    validate_canonical_ids(control, kb)

    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(control, f, ensure_ascii=False, indent=2)

    print("Control structure generated from natural language")
    print(f"Instruction: {args.instruction}")
    print(f"Output: {args.out}")


if __name__ == "__main__":
    raise SystemExit(main())
