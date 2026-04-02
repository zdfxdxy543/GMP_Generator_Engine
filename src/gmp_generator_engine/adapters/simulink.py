from __future__ import annotations

from pathlib import Path

from ..models import CandidateProgram, SimulationMetrics
from ..simulator import SimulatorBackend


class SimulinkBackend(SimulatorBackend):
    """Placeholder adapter for Windows-Simulink joint simulation integration."""

    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root

    def run(self, candidate: CandidateProgram) -> SimulationMetrics:
        raise NotImplementedError(
            "Simulink backend is not implemented yet. "
            "Please integrate your MATLAB engine or IPC bridge here."
        )
