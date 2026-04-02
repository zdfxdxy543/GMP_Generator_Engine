from __future__ import annotations

from .models import UserRequirement


def parse_requirement(text: str) -> UserRequirement:
    lower = text.lower()
    scenario = "generic"
    if "机器人" in text or "robot" in lower:
        scenario = "robotics"
    elif "电动汽车" in text or "ev" in lower:
        scenario = "ev"

    control_mode = "speed"
    if "位置" in text or "position" in lower:
        control_mode = "position"
    elif "电流" in text or "current" in lower:
        control_mode = "current"

    constraints: dict[str, float] = {}
    if "低纹波" in text or "low ripple" in lower:
        constraints["current_ripple_target"] = 0.08
    if "快" in text or "fast" in lower:
        constraints["settling_time_target"] = 0.18

    return UserRequirement(
        text=text,
        scenario=scenario,
        motor_type="pmsm",
        control_mode=control_mode,
        constraints=constraints,
    )
