from __future__ import annotations

import random

from .models import CandidateProgram, SimulationMetrics


class SimulatorBackend:
    def run(self, candidate: CandidateProgram) -> SimulationMetrics:
        raise NotImplementedError


class MockSimulator(SimulatorBackend):
    def __init__(self, seed: int = 42) -> None:
        self._random = random.Random(seed)

    def run(self, candidate: CandidateProgram) -> SimulationMetrics:
        # Deterministic-ish mock scoring to support CLI workflow before Simulink integration.
        kp = candidate.params.get("kp", 2.0)
        ki = candidate.params.get("ki", 100.0)
        noise = self._random.uniform(-0.01, 0.01)

        overshoot = max(0.01, 0.30 - 0.05 * min(kp, 4.0) + abs(noise))
        settling_time = max(0.05, 0.45 - 0.0015 * min(ki, 250.0) + abs(noise))
        current_ripple = max(0.01, 0.18 - 0.02 * min(kp, 4.0) + abs(noise))
        steady_state_error = max(0.005, 0.08 - 0.0002 * min(ki, 250.0) + abs(noise))

        return SimulationMetrics(
            overshoot=overshoot,
            settling_time=settling_time,
            current_ripple=current_ripple,
            steady_state_error=steady_state_error,
        )
