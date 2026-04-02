# gmp_generator_engine package

English

This package implements the main engine logic. It keeps the domain model, requirement parser, controller generator, validator, optimizer, and simulation backend isolated so each part can be replaced independently.

中文

这个包实现引擎主逻辑。这里把领域模型、需求解析、控制器生成、校验、优化和仿真后端拆成独立模块，便于单独替换和扩展。

## Module roles / 模块职责

- `models.py`: shared dataclasses for requirements, structures, candidates, and metrics.  
- `knowledge_base.py`: default module catalog and KPI weight loading.  
- `parser.py`: requirement interpretation.  
- `generator.py`: GMP-style file generation.  
- `validators.py`: structure and compile checks.  
- `optimizer.py`: parameter and structure iteration.  
- `simulator.py`: backend interface and mock implementation.
