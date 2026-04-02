# adapters

English

This folder contains backend adapters. The current code includes a Simulink placeholder so the optimization pipeline can switch from mock simulation to real Windows-Simulink integration later.

中文

这个目录存放后端适配器。当前已经保留 Simulink 占位实现，后续可以把 mock 仿真平滑切换成真实的 Windows-Simulink 联仿接口。

## Expected adapter contract / 适配器约定

- Input: a generated candidate program.  
- Output: simulation metrics used by the optimizer.  
- Failure mode: raise a clear `NotImplementedError` until a real backend is connected.
