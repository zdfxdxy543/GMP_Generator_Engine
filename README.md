# GMP Generator Engine

English

GMP Generator Engine is a Python CLI project that turns natural-language controller requirements into a GMP-style project skeleton, then runs validation and a first-pass optimization loop. The code is intentionally organized to match the GMP `ctl/suite` pattern so that generated output can be mapped to real control projects later.

中文

GMP Generator Engine 是一个 Python 命令行项目，用自然语言控制需求生成符合 GMP 风格的工程骨架，并继续执行校验和第一轮优化。当前结构刻意对齐 GMP 的 `ctl/suite` 组织方式，便于后续直接映射到真实控制工程。

## How it works / 工作机制

1. Parse requirement text and detect scenario, control mode, and constraints.  
   解析需求文本，识别场景、控制模式和约束。
2. Load the module catalog and KPI weights from JSON or use the default catalog.  
   从 JSON 加载模块目录与 KPI 权重，或使用默认配置。
3. Build a five-layer control structure aligned with the report and GMP naming rules.  
   按报告与 GMP 命名规则构建五层控制结构。
4. Generate a GMP suite-style output tree under `implement/common/`.  
   在 `implement/common/` 下生成 GMP 套件风格输出。
5. Validate required symbols and structure, then optionally run an external compile command.  
   校验关键符号和结构，再可选执行外部编译命令。
6. Run mock or Simulink-backed optimization through the backend adapter.  
   通过后端适配器运行 mock 或 Simulink 优化。

## Current workflow outputs / 当前工作流输出

- `implement/common/ctl_main.c`
- `implement/common/ctl_main.h`
- `implement/common/user_main.c`
- `implement/common/user_main.h`
- `structure.json`

## Key directories / 关键目录

- [src](src/ReadMe.md)
- [src/gmp_generator_engine](src/gmp_generator_engine/ReadMe.md)
- [src/gmp_generator_engine/adapters](src/gmp_generator_engine/adapters/ReadMe.md)
- [configs](configs/ReadMe.md)
- [tests](tests/ReadMe.md)
- [outputs](outputs/ReadMe.md)

## Install / 安装

```bash
pip install -e .
```

## CLI examples / 命令示例

```bash
gmp-engine generate --requirement "机器人位置控制，要求低纹波和快速响应" --out outputs/generated
gmp-engine optimize --requirement "PMSM速度控制" --rounds 4 --out outputs/optimization/best_candidate.json
gmp-engine run --requirement "机器人位置控制，要求低纹波和快速响应" --out outputs/run
```

## Reference artifacts / 参考文件

Temporary or reference-only files kept for analysis are listed in [REFERENCE_ARTIFACTS.md](REFERENCE_ARTIFACTS.md).
