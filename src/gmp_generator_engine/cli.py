from __future__ import annotations

import argparse
import json
from pathlib import Path

from .generator import generate_program, write_artifacts
from .knowledge_base import load_catalog, load_kpi_weights
from .models import CandidateProgram
from .optimizer import optimize
from .parser import parse_requirement
from .simulator import MockSimulator, SimulatorBackend
from .validators import validate_compile, validate_structure
from .adapters.simulink import SimulinkBackend


def _build_backend(args: argparse.Namespace) -> SimulatorBackend:
    if args.backend == "mock":
        return MockSimulator(seed=args.seed)
    return SimulinkBackend(project_root=Path(args.simulink_project_root))


def _candidate_payload(best: CandidateProgram) -> dict[str, object]:
    return {
        "name": best.name,
        "params": best.params,
        "score": best.score,
        "metrics": {
            "overshoot": best.metrics.overshoot if best.metrics else None,
            "settling_time": best.metrics.settling_time if best.metrics else None,
            "current_ripple": best.metrics.current_ripple if best.metrics else None,
            "steady_state_error": best.metrics.steady_state_error if best.metrics else None,
        },
        "layers": [
            {
                "name": layer.name,
                "module": layer.module,
                "params": layer.params,
            }
            for layer in best.structure.layers
        ],
    }


def cmd_generate(args: argparse.Namespace) -> int:
    req = parse_requirement(args.requirement)
    catalog = load_catalog(args.catalog)
    artifact = generate_program(req, catalog)

    out_dir = Path(args.out)
    write_artifacts(artifact, out_dir)

    structure_check = validate_structure(artifact)
    compile_check = validate_compile(out_dir, args.compile_cmd)

    print(f"Generated files in: {out_dir}")
    print(f"Structure validation: {structure_check.ok} | {structure_check.messages}")
    print(f"Compile validation: {compile_check.ok} | {compile_check.messages}")
    return 0 if (structure_check.ok and compile_check.ok) else 1


def cmd_optimize(args: argparse.Namespace) -> int:
    req = parse_requirement(args.requirement)
    catalog = load_catalog(args.catalog)
    weights = load_kpi_weights(args.kpi_weights)
    backend = _build_backend(args)

    try:
        best = optimize(
            req=req,
            catalog=catalog,
            simulator=backend,
            weights=weights,
            rounds=args.rounds,
        )
    except NotImplementedError as exc:
        print(f"Optimization failed: {exc}")
        return 2

    payload = _candidate_payload(best)

    out_file = Path(args.out)
    out_file.parent.mkdir(parents=True, exist_ok=True)
    out_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Optimization result saved to: {out_file}")
    print(f"Best score: {best.score:.6f}")
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    req = parse_requirement(args.requirement)
    catalog = load_catalog(args.catalog)
    weights = load_kpi_weights(args.kpi_weights)
    artifact = generate_program(req, catalog)

    out_root = Path(args.out)
    generated_dir = out_root / "generated"
    write_artifacts(artifact, generated_dir)

    structure_check = validate_structure(artifact)
    compile_check = validate_compile(generated_dir, args.compile_cmd)

    print(f"Generated files in: {generated_dir}")
    print(f"Structure validation: {structure_check.ok} | {structure_check.messages}")
    print(f"Compile validation: {compile_check.ok} | {compile_check.messages}")

    if not (structure_check.ok and compile_check.ok):
        return 1

    backend = _build_backend(args)
    try:
        best = optimize(
            req=req,
            catalog=catalog,
            simulator=backend,
            weights=weights,
            rounds=args.rounds,
        )
    except NotImplementedError as exc:
        print(f"Optimization failed: {exc}")
        return 2

    payload = _candidate_payload(best)

    out_file = out_root / "optimization" / "best_candidate.json"
    out_file.parent.mkdir(parents=True, exist_ok=True)
    out_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Optimization result saved to: {out_file}")
    print(f"Best score: {best.score:.6f}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="gmp-engine",
        description="Generate and optimize GMP-style motor control program skeletons.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    gen = sub.add_parser("generate", help="Generate ctl_main.c and structure.json from requirement text")
    gen.add_argument("--requirement", required=True, help="Natural language requirement")
    gen.add_argument("--out", default="outputs/generated", help="Output directory")
    gen.add_argument("--catalog", default=None, help="Path to module catalog JSON")
    gen.add_argument(
        "--compile-cmd",
        default=None,
        help="Optional compile command to validate generated program",
    )
    gen.set_defaults(func=cmd_generate)

    opt = sub.add_parser("optimize", help="Run parameter+structure optimization (mock simulator)")
    opt.add_argument("--requirement", required=True, help="Natural language requirement")
    opt.add_argument("--rounds", type=int, default=3, help="Optimization rounds")
    opt.add_argument("--seed", type=int, default=42, help="Random seed for mock simulator")
    opt.add_argument("--catalog", default=None, help="Path to module catalog JSON")
    opt.add_argument("--kpi-weights", default=None, help="Path to KPI weights JSON")
    opt.add_argument(
        "--backend",
        choices=["mock", "simulink"],
        default="mock",
        help="Simulation backend",
    )
    opt.add_argument(
        "--simulink-project-root",
        default=".",
        help="Simulink project root (used when backend=simulink)",
    )
    opt.add_argument("--out", default="outputs/optimization/best_candidate.json", help="Output JSON file")
    opt.set_defaults(func=cmd_optimize)

    run = sub.add_parser("run", help="Generate + validate + optimize in one command")
    run.add_argument("--requirement", required=True, help="Natural language requirement")
    run.add_argument("--out", default="outputs/run", help="Output root directory")
    run.add_argument("--catalog", default=None, help="Path to module catalog JSON")
    run.add_argument("--kpi-weights", default=None, help="Path to KPI weights JSON")
    run.add_argument("--rounds", type=int, default=3, help="Optimization rounds")
    run.add_argument("--seed", type=int, default=42, help="Random seed for mock simulator")
    run.add_argument(
        "--backend",
        choices=["mock", "simulink"],
        default="mock",
        help="Simulation backend",
    )
    run.add_argument(
        "--simulink-project-root",
        default=".",
        help="Simulink project root (used when backend=simulink)",
    )
    run.add_argument("--compile-cmd", default=None, help="Optional compile command")
    run.set_defaults(func=cmd_run)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    raise SystemExit(args.func(args))


if __name__ == "__main__":
    main()
