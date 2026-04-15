"""Standalone controller-structure exporter.

This script converts a natural-language requirement into a formatted
controller architecture description and exports it to JSON.

The generated structure is intentionally English-only and assigns a stable,
unique id to every block, edge, and path.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class Block:
    id: str
    name: str
    type: str
    role: str
    inputs: list[str] = field(default_factory=list)
    outputs: list[str] = field(default_factory=list)
    notes: str = ""


@dataclass(frozen=True)
class Edge:
    id: str
    source: str
    target: str
    signal: str
    description: str = ""


@dataclass(frozen=True)
class PathItem:
    id: str
    source: str
    target: str
    signal: str


def build_controller_structure(requirement: str) -> dict[str, Any]:
    requirement_text = requirement.strip()
    lower_requirement = requirement_text.lower()

    if "speed" in lower_requirement:
        system_name = "Speed Control System"
        primary_outer_loop = "speed_loop"
        primary_outer_loop_id = "blk_002_speed_loop"
        control_mode = "cascaded_speed_current_control"
        objective = "Track speed reference through a speed loop with an inner current loop."
    else:
        system_name = "Motor Control System"
        primary_outer_loop = "outer_loop"
        primary_outer_loop_id = "blk_002_outer_loop"
        control_mode = "cascaded_outer_inner_control"
        objective = "Provide a cascaded control architecture with outer and inner loops."

    blocks = [
        Block(
            id="blk_001_state_machine",
            name="state_machine",
            type="supervisory",
            role="Supervisory logic for enable, disable, and fault transitions",
            outputs=["controller_enable", "fault_state", "mode_request"],
            notes="Top-level run/stop/fault management.",
        ),
        Block(
            id=primary_outer_loop_id,
            name=primary_outer_loop,
            type="outer_loop",
            role="Outer loop that converts reference error into current demand",
            inputs=["reference", "feedback", "controller_enable"],
            outputs=["torque_current_reference"],
            notes="Runs slower than the inner loop and respects current limits.",
        ),
        Block(
            id="blk_003_current_loop",
            name="current_loop",
            type="inner_loop",
            role="Inner loop that regulates phase currents and generates voltage commands",
            inputs=["id_reference", "iq_reference", "id_feedback", "iq_feedback", "controller_enable"],
            outputs=["vd_command", "vq_command", "vab0_command"],
            notes="Fast loop executed in the interrupt context.",
        ),
        Block(
            id="blk_004_measurement_chain",
            name="measurement_chain",
            type="feedback",
            role="Measurement and estimation chain for speed, position, and current feedback",
            inputs=["adc_samples", "encoder_samples"],
            outputs=["speed_feedback", "position_feedback", "id_feedback", "iq_feedback"],
            notes="Can combine sensor feedback with observer-based estimation.",
        ),
        Block(
            id="blk_005_protection",
            name="protection",
            type="safety",
            role="Protection layer for current, voltage, and thermal supervision",
            inputs=["current_feedback", "dc_bus_voltage", "temperature"],
            outputs=["fault_request", "limit_flags"],
            notes="Can clamp references or force a stop when limits are exceeded.",
        ),
        Block(
            id="blk_006_modulator",
            name="modulator",
            type="actuation",
            role="Converts voltage commands into PWM duty cycles",
            inputs=["vab0_command", "fault_state"],
            outputs=["pwm_duty"],
            notes="Abstracts SPWM, SVPWM, or NPC modulation backends.",
        ),
    ]

    edges = [
        Edge(
            id="edge_001_enable_outer_loop",
            source="state_machine",
            target=primary_outer_loop,
            signal="controller_enable",
            description="Allows the outer loop to compute references only when the controller is enabled.",
        ),
        Edge(
            id="edge_002_enable_current_loop",
            source="state_machine",
            target="current_loop",
            signal="controller_enable",
            description="Gates the fast loop and prevents active control during faults.",
        ),
        Edge(
            id="edge_003_feedback_outer_loop",
            source="measurement_chain",
            target=primary_outer_loop,
            signal="speed_feedback",
            description="Provides the measured or estimated speed feedback to the outer loop.",
        ),
        Edge(
            id="edge_004_feedback_current_loop",
            source="measurement_chain",
            target="current_loop",
            signal="id_feedback/iq_feedback",
            description="Provides current feedback to the inner loop.",
        ),
        Edge(
            id="edge_005_outer_to_inner",
            source=primary_outer_loop,
            target="current_loop",
            signal="iq_reference",
            description="Outer loop requests torque-producing current from the inner loop.",
        ),
        Edge(
            id="edge_006_fault_request",
            source="protection",
            target="state_machine",
            signal="fault_request",
            description="Requests a fault transition when a protection event is detected.",
        ),
        Edge(
            id="edge_007_voltage_to_modulator",
            source="current_loop",
            target="modulator",
            signal="vab0_command",
            description="Inner loop output is mapped into a modulation command.",
        ),
        Edge(
            id="edge_008_pwm_to_plant",
            source="modulator",
            target="plant",
            signal="pwm_duty",
            description="Generates the PWM waveform applied to the power stage.",
        ),
    ]

    structure = {
        "id": "arch_001",
        "name": system_name,
        "version": 1,
        "language": "en",
        "requirement": requirement_text,
        "control_mode": control_mode,
        "objective": objective,
        "summary": "English-formatted controller structure with unique ids for each control element.",
        "blocks": [asdict(item) for item in blocks],
        "edges": [asdict(item) for item in edges],
        "layout": {
            "hierarchy": ["state_machine", primary_outer_loop, "current_loop", "modulator"],
            "feedback_chain": ["measurement_chain", primary_outer_loop, "current_loop"],
            "safety_chain": ["protection", "state_machine", primary_outer_loop, "current_loop"],
        },
        "paths": [
            asdict(PathItem("path_001_reference_feedback", "user_requirement", primary_outer_loop, "reference_to_outer_loop")),
            asdict(PathItem("path_002_outer_to_inner", primary_outer_loop, "current_loop", "torque_current_reference")),
            asdict(PathItem("path_003_inner_to_actuation", "current_loop", "modulator", "voltage_command")),
            asdict(PathItem("path_004_actuation_to_plant", "modulator", "plant", "pwm_output")),
        ],
        "design_rules": [
            "All text must be written in English.",
            "Every block, edge, and path must have a unique and stable id.",
            "The outer loop must be slower than the inner current loop.",
            "Protection must be able to override both loops through the state machine.",
            "The modulator is an actuation layer and must not contain control logic.",
        ],
        "output_format": {
            "block_id_prefix": "blk_",
            "edge_id_prefix": "edge_",
            "path_id_prefix": "path_",
        },
    }

    return structure


def export_json(output_path: Path, requirement: str) -> Path:
    payload = build_controller_structure(requirement)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, ensure_ascii=True, indent=2), encoding="utf-8")
    return output_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate an English-formatted controller-structure JSON from a requirement."
    )
    parser.add_argument(
        "requirement",
        nargs="?",
        default="I need to design a speed control system.",
        help="Natural-language requirement used to select the controller structure.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(__file__).with_name("controller_structure.json"),
        help="Path to the JSON file to generate.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    exported = export_json(args.output, args.requirement)
    print(f"Exported controller structure to {exported}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
