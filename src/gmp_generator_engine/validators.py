from __future__ import annotations

import subprocess
from pathlib import Path

from .models import ProgramArtifact, ValidationResult


_REQUIRED_LAYER_NAMES = {"trajectory", "mech", "distributor", "current", "observer"}


def validate_structure(artifact: ProgramArtifact) -> ValidationResult:
    layers = artifact.metadata.get("layers", [])
    layer_names = {x.get("name") for x in layers}
    missing = sorted(_REQUIRED_LAYER_NAMES - layer_names)

    messages: list[str] = []
    if missing:
        messages.append(f"missing required layers: {', '.join(missing)}")
    required_symbols = ["ctl_init", "ctl_mainloop", "ctl_dispatch"]
    for symbol in required_symbols:
        if symbol not in artifact.source_code:
            messages.append(f"generated source does not include {symbol}")

    return ValidationResult(ok=not messages, messages=messages or ["structure validation passed"])


def validate_compile(out_dir: Path, compile_command: str | None = None) -> ValidationResult:
    # Optional compile hook, because local GMP build toolchain may vary.
    if not compile_command:
        return ValidationResult(ok=True, messages=["compile validation skipped (no command provided)"])

    result = subprocess.run(
        compile_command,
        cwd=out_dir,
        shell=True,
        capture_output=True,
        text=True,
        check=False,
    )

    if result.returncode == 0:
        return ValidationResult(ok=True, messages=["compile validation passed"])

    stderr = result.stderr.strip() or result.stdout.strip() or "unknown compile error"
    return ValidationResult(ok=False, messages=[stderr])
