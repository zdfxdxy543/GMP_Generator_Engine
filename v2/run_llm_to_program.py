"""End-to-end controller generation pipeline.

1) Call the LLM-backed loop-id exporter.
2) Feed the generated loop-ids JSON into the Example-based merge step.
3) Generate `ctl_main.c` and `ctl_main.h` from the Example templates.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import controller_loop_id_exporter as loop_exporter
import merge_loop_ids_into_ctl_main as merger


def main(requirement: str, loop_ids_output: Path, c_output: Path, h_output: Path, paras_output: Path, llm_config: Path) -> int:
    print("[1/2] Generating loop-ids via LLM...")
    loop_exporter.export_json(loop_ids_output, requirement, settings_path=llm_config)

    print("[2/2] Generating ctl_main.c and ctl_main.h from Example templates...")
    merger.main(
        loop_ids_path=loop_ids_output,
        template_path=Path(__file__).with_name("Example").joinpath("ctl_main.c"),
        output_path=c_output,
        header_template_path=Path(__file__).with_name("Example").joinpath("ctl_main.h"),
        header_output_path=h_output,
        paras_template_path=Path(__file__).with_name("Example").joinpath("paras.h"),
        paras_output_path=paras_output,
    )

    print(f"Pipeline completed: {loop_ids_output}, {c_output}, {h_output}, {paras_output}")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run LLM loop-id generation and then program generation.")
    parser.add_argument("requirement", nargs="?", default="需要设计高性能位置控制器")
    parser.add_argument("--loop-ids-output", type=Path, default=Path(__file__).with_name("controller_loop_ids_generated.json"))
    parser.add_argument("--c-output", type=Path, default=Path(__file__).with_name("ctl_main.generated.c"))
    parser.add_argument("--h-output", type=Path, default=Path(__file__).with_name("ctl_main.generated.h"))
    parser.add_argument("--paras-output", type=Path, default=Path(__file__).with_name("paras.generated.h"))
    parser.add_argument("--llm-config", type=Path, default=Path(__file__).with_name("llm_settings.json"))
    args = parser.parse_args()
    raise SystemExit(main(args.requirement, args.loop_ids_output, args.c_output, args.h_output, args.paras_output, args.llm_config))
