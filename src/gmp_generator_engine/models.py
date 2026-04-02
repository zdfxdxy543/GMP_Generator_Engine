from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class UserRequirement:
    text: str
    scenario: str = "generic"
    motor_type: str = "pmsm"
    control_mode: str = "speed"
    constraints: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class LayerSelection:
    name: str
    module: str
    params: dict[str, float] = field(default_factory=dict)


@dataclass(slots=True)
class ControlStructure:
    layers: list[LayerSelection]


@dataclass(slots=True)
class ProgramArtifact:
    source_code: str
    metadata: dict[str, Any]
    files: dict[str, str] = field(default_factory=dict)


@dataclass(slots=True)
class ValidationResult:
    ok: bool
    messages: list[str]


@dataclass(slots=True)
class SimulationMetrics:
    overshoot: float
    settling_time: float
    current_ripple: float
    steady_state_error: float

    def weighted_score(self, weights: dict[str, float]) -> float:
        # Lower is better for all metrics.
        return (
            self.overshoot * weights.get("overshoot", 1.0)
            + self.settling_time * weights.get("settling_time", 1.0)
            + self.current_ripple * weights.get("current_ripple", 1.0)
            + self.steady_state_error * weights.get("steady_state_error", 1.0)
        )


@dataclass(slots=True)
class CandidateProgram:
    name: str
    structure: ControlStructure
    params: dict[str, float]
    metrics: SimulationMetrics | None = None
    score: float | None = None
