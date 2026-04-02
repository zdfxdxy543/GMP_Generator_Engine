from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class ModuleCatalog:
    trajectory: list[str]
    mech: list[str]
    distributor: list[str]
    current: list[str]
    observer: list[str]

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ModuleCatalog:
        return cls(
            trajectory=list(data.get("trajectory", [])),
            mech=list(data.get("mech", [])),
            distributor=list(data.get("distributor", [])),
            current=list(data.get("current", [])),
            observer=list(data.get("observer", [])),
        )


def _default_catalog_data() -> dict[str, list[str]]:
    return {
        "trajectory": [
            "ctl_step_ramp_generator",
            "ctl_step_s_curve_generator",
        ],
        "mech": [
            "ctl_step_mech_ctrl",
            "ctl_step_vel_pos_ctrl",
        ],
        "distributor": [
            "ctl_step_spm_fw_distributor",
            "ctl_set_mtr_current_ctrl_ref",
        ],
        "current": [
            "ctl_step_foc_core",
            "ctl_step_current_controller",
        ],
        "observer": [
            "ctl_step_spd_calculator",
            "ctl_step_pmsm_fo",
            "ctl_step_pmsm_esmo",
        ],
    }


def default_catalog() -> ModuleCatalog:
    """Default module candidates mapped to GMP naming conventions."""
    return ModuleCatalog.from_dict(_default_catalog_data())


def default_kpi_weights() -> dict[str, float]:
    return {
        "overshoot": 0.35,
        "settling_time": 0.25,
        "current_ripple": 0.20,
        "steady_state_error": 0.20,
    }


def load_catalog(path: str | Path | None = None) -> ModuleCatalog:
    if not path:
        return default_catalog()

    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    return ModuleCatalog.from_dict(payload)


def load_kpi_weights(path: str | Path | None = None) -> dict[str, float]:
    if not path:
        return default_kpi_weights()

    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    return {
        "overshoot": float(payload["overshoot"]),
        "settling_time": float(payload["settling_time"]),
        "current_ripple": float(payload["current_ripple"]),
        "steady_state_error": float(payload["steady_state_error"]),
    }
