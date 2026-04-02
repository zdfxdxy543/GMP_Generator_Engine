# src

English

This folder contains the Python package source code. The package exposes a CLI that parses requirements, builds a GMP-style controller structure, validates the generated output, and runs the optimization loop.

中文

这个目录存放 Python 包源码。项目通过这里提供的 CLI 完成需求解析、GMP 风格结构生成、结果校验以及优化迭代。

## Flow / 流程

1. `cli.py` receives command-line arguments.  
2. `parser.py` interprets the requirement text.  
3. `generator.py` renders the controller files.  
4. `validators.py` checks the output structure and optional compile command.  
5. `optimizer.py` performs parameter and structure iteration.  
6. `simulator.py` provides the backend interface and mock runner.
