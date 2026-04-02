# GMP Generator Engine

A Python CLI engine for generating GMP-style motor controller skeleton code from natural language requirements, then running a first-pass optimization loop.

## What this project implements (v0.1)

- Natural-language requirement parsing.
- Five-layer controller structure generation aligned with the report:
	- trajectory planning layer
	- speed/position mechanical layer
	- current command distribution layer
	- current control layer
	- observer/encoder layer
- Program artifact generation:
	- `ctl_main.c` skeleton
	- `structure.json` metadata
- Validation chain:
	- structure consistency check
	- optional compile command hook
- Optimization module:
	- parameter iteration + structure iteration
	- KPI scoring with four metrics:
		- overshoot
		- settling time
		- current ripple
		- steady-state error
- Simulink adapter placeholder for future integration.

## Install

```bash
pip install -e .
```

## CLI Usage

Generate controller skeleton from requirement text:

```bash
gmp-engine generate --requirement "机器人位置控制，要求低纹波和快速响应" --out outputs/generated
```

Generated code follows GMP suite style in `implement/common/` with these files:

- `implement/common/ctl_main.c`
- `implement/common/ctl_main.h`
- `implement/common/user_main.c`
- `implement/common/user_main.h`

Run optimization (mock simulator):

```bash
gmp-engine optimize --requirement "PMSM速度控制" --rounds 4 --out outputs/optimization/best_candidate.json
```

Run full pipeline in one command (generate + validate + optimize):

```bash
gmp-engine run --requirement "机器人位置控制，要求低纹波和快速响应" --out outputs/run
```

Optional compile validation during generation:

```bash
gmp-engine generate --requirement "PMSM速度控制" --compile-cmd "make"
```

Use external module catalog and KPI weights:

```bash
gmp-engine run \
	--requirement "电动汽车驱动，快速响应" \
	--catalog configs/module_catalog.json \
	--kpi-weights configs/kpi_weights.json
```

## Output files

- `outputs/generated/ctl_main.c`
- `outputs/generated/implement/common/ctl_main.c`
- `outputs/generated/implement/common/ctl_main.h`
- `outputs/generated/implement/common/user_main.c`
- `outputs/generated/implement/common/user_main.h`
- `outputs/generated/structure.json`
- `outputs/optimization/best_candidate.json`
- `outputs/run/generated/ctl_main.c`
- `outputs/run/generated/implement/common/ctl_main.c`
- `outputs/run/generated/implement/common/ctl_main.h`
- `outputs/run/generated/implement/common/user_main.c`
- `outputs/run/generated/implement/common/user_main.h`
- `outputs/run/generated/structure.json`
- `outputs/run/optimization/best_candidate.json`

## GMP mapping notes

The default module catalog follows GMP CTL naming style and project conventions from `ctl/suite` and `ctl/component`, so generated layer entries are directly mappable to GMP implementation points such as `ctl_dispatch()` in controller common code.

## Next integration target

Implement `src/gmp_generator_engine/adapters/simulink.py` to replace the mock simulator with your Windows-Simulink joint-simulation backend.

Default editable config files are provided in:

- `configs/module_catalog.json`
- `configs/kpi_weights.json`

Temporary/reference artifacts kept for this phase are listed in:

- `REFERENCE_ARTIFACTS.md`
