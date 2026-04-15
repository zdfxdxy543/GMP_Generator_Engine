"""Generate a JSON controller-structure description for motor-control loops.

This script is intentionally standalone. It does not depend on the existing
controller code and is meant to describe a control architecture in a format
that can be exported, inspected, or consumed by other tools.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class LoopBlock:
    """A single control block in the controller architecture."""

    name: str
    role: str
    layer: str
    inputs: list[str] = field(default_factory=list)
    outputs: list[str] = field(default_factory=list)
    notes: str = ""


@dataclass(frozen=True)
class SignalEdge:
    """Directed connection between two controller blocks."""

    source: str
    target: str
    signal: str
    description: str = ""


def build_controller_structure(requirement: str | None = None) -> dict[str, Any]:
    """Build a formatted structure for a speed-loop plus current-loop controller."""

    blocks = [
        LoopBlock(
            name="state_machine",
            role="Enable, disable, and fault gating for the controller",
            layer="supervisory",
            outputs=["controller_enable", "fault_state", "mode_request"],
            notes="Represents the top-level run/stop/fault logic.",
        ),
        LoopBlock(
            name="speed_loop",
            role="Outer loop that converts speed error into current references",
            layer="outer_loop",
            inputs=["speed_reference", "speed_feedback", "controller_enable"],
            outputs=["iq_reference"],
            notes="Usually slower than the current loop and constrained by current limits.",
        ),
        LoopBlock(
            name="current_loop",
            role="Inner loop that regulates phase currents and produces voltage commands",
            layer="inner_loop",
            inputs=["id_reference", "iq_reference", "id_feedback", "iq_feedback", "controller_enable"],
            outputs=["vd_command", "vq_command", "vab0_command"],
            notes="Fast loop, typically executed in the interrupt context.",
        ),
        LoopBlock(
            name="observer_and_measurement",
            role="Provides speed, position, and current feedback",
            layer="feedback",
            inputs=["adc_samples", "encoder_samples"],
            outputs=["speed_feedback", "position_feedback", "id_feedback", "iq_feedback"],
            notes="Can combine encoder-based feedback with observer-based estimation.",
        ),
        LoopBlock(
            name="protection",
            role="Monitors current, voltage, and fault conditions",
            layer="safety",
            inputs=["current_feedback", "dc_bus_voltage", "temperature"],
            outputs=["fault_request", "limit_flags"],
            notes="Can clamp references or force a stop when limits are exceeded.",
        ),
        LoopBlock(
            name="modulator",
            role="Converts voltage command into PWM duty values",
            layer="actuation",
            inputs=["vab0_command", "fault_state"],
            outputs=["pwm_duty"],
            notes="Abstracts SPWM, SVPWM, or NPC modulation backends.",
        ),
    ]

    edges = [
        SignalEdge("state_machine", "speed_loop", "controller_enable", "Allows the outer loop to compute references only when the controller is enabled."),
        SignalEdge("state_machine", "current_loop", "controller_enable", "Gates the fast loop and prevents active control during faults."),
        SignalEdge("observer_and_measurement", "speed_loop", "speed_feedback", "Provides the measured or estimated speed to the outer loop."),
        SignalEdge("observer_and_measurement", "current_loop", "id_feedback/iq_feedback", "Provides current feedback to the inner loop."),
        SignalEdge("speed_loop", "current_loop", "iq_reference", "Outer loop requests torque-producing current."),
        SignalEdge("protection", "state_machine", "fault_request", "Requests a fault transition when a protection event is detected."),
        SignalEdge("current_loop", "modulator", "vab0_command", "Inner loop output is mapped into a modulation command."),
        SignalEdge("modulator", "plant", "pwm_duty", "Generates the PWM waveform applied to the power stage."),
    ]

    architecture = {
        "control_strategy": "cascaded_speed_current_control",
        "loop_hierarchy": [
            {
                "name": "speed_loop",
                "type": "outer_loop",
                "function": "Transforms speed error into torque/current demand.",
                "priority": "lower_than_current_loop",
            },
            {
                "name": "current_loop",
                "type": "inner_loop",
                "function": "Tracks current demand and outputs voltage command.",
                "priority": "highest_fast_loop",
            },
        ],
        "feedback_paths": [
            {
                "source": "encoder_or_observer",
                "target": "speed_loop",
                "signal": "speed_feedback",
            },
            {
                "source": "current_measurement",
                "target": "current_loop",
                "signal": "idq_feedback",
            },
        ],
        "actuation_paths": [
            {
                "source": "current_loop",
                "target": "modulator",
                "signal": "voltage_command",
            },
            {
                "source": "modulator",
                "target": "power_stage",
                "signal": "pwm_output",
            },
        ],
        "safety_paths": [
            {
                "source": "protection",
                "target": "state_machine",
                "signal": "fault_request",
            },
            {
                "source": "state_machine",
                "target": "current_loop",
                "signal": "enable_gate",
            },
        ],
    }

    data: dict[str, Any] = {
        "name": "controller_structure",
        "version": 1,
        "domain": "motor_control",
        "requirement": requirement,
        "summary": (
            "Formatted controller structure describing the relationship between the "
            "state machine, speed loop, current loop, measurement chain, protection, and modulation."
        ),
        "blocks": [block.__dict__ for block in blocks],
        "edges": [edge.__dict__ for edge in edges],
        "architecture": architecture,
        "design_rules": [
            "The speed loop is the outer loop and must not run faster than the current loop.",
            "The current loop is the fast inner loop and closes the feedback path around current regulation.",
            "Protection can override both loops by forcing a disable or fault transition.",
            "The modulator is an actuation layer and should not directly own control logic.",
        ],
    }

    return data


def export_structure(output_path: Path, requirement: str | None = None) -> Path:
    """Export the controller structure to a JSON file."""

    structure = build_controller_structure(requirement=requirement)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(structure, ensure_ascii=True, indent=2), encoding="utf-8")
    return output_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export a motor-control controller structure to JSON.")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(__file__).with_name("controller_structure.json"),
        help="Path to the JSON file to generate.",
    )
    parser.add_argument(
        "--requirement",
        type=str,
        default=None,
        help="Optional natural-language requirement to include in the exported structure.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    exported = export_structure(args.output, requirement=args.requirement)
    print(f"Exported controller structure to {exported}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())