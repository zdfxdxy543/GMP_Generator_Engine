import argparse
import json

from gmp_generator_engine.cli import cmd_optimize, cmd_run
from gmp_generator_engine.knowledge_base import load_catalog, load_kpi_weights


def test_load_catalog_and_weights_from_json(tmp_path) -> None:
    catalog_file = tmp_path / "catalog.json"
    weights_file = tmp_path / "weights.json"

    catalog_file.write_text(
        json.dumps(
            {
                "trajectory": ["a"],
                "mech": ["b"],
                "distributor": ["c"],
                "current": ["d"],
                "observer": ["e"],
            }
        ),
        encoding="utf-8",
    )
    weights_file.write_text(
        json.dumps(
            {
                "overshoot": 0.4,
                "settling_time": 0.3,
                "current_ripple": 0.2,
                "steady_state_error": 0.1,
            }
        ),
        encoding="utf-8",
    )

    catalog = load_catalog(catalog_file)
    weights = load_kpi_weights(weights_file)

    assert catalog.trajectory == ["a"]
    assert catalog.observer == ["e"]
    assert weights["overshoot"] == 0.4
    assert weights["steady_state_error"] == 0.1


def test_cmd_run_creates_outputs(tmp_path) -> None:
    args = argparse.Namespace(
        requirement="PMSM速度控制",
        out=str(tmp_path),
        catalog=None,
        kpi_weights=None,
        rounds=2,
        seed=42,
        backend="mock",
        simulink_project_root=".",
        compile_cmd=None,
    )

    rc = cmd_run(args)
    assert rc == 0
    assert (tmp_path / "generated" / "implement" / "common" / "ctl_main.c").exists()
    assert (tmp_path / "generated" / "implement" / "common" / "ctl_main.h").exists()
    assert (tmp_path / "generated" / "implement" / "common" / "user_main.c").exists()
    assert (tmp_path / "generated" / "implement" / "common" / "user_main.h").exists()
    assert (tmp_path / "optimization" / "best_candidate.json").exists()


def test_cmd_optimize_simulink_placeholder_returns_error(tmp_path) -> None:
    out_file = tmp_path / "result.json"
    args = argparse.Namespace(
        requirement="PMSM速度控制",
        rounds=2,
        seed=42,
        catalog=None,
        kpi_weights=None,
        backend="simulink",
        simulink_project_root=".",
        out=str(out_file),
    )

    rc = cmd_optimize(args)
    assert rc == 2
    assert not out_file.exists()