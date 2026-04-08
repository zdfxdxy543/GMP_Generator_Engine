# LLM + 本地补全 架构说明

## 目标
将“控制结构设计”自动转换为控制程序主体，并由本地引擎工程化补全，降低大模型一次成品压力。

## 总体流程
1. 用户输入控制结构 JSON。
2. 结构解析器读取节点（modules）、连线（links）、调度（schedule）。
3. 本地 ID 解析器按 module_id 查询知识库。
4. Prompt Builder 将结构 + 模块元数据组织成生成上下文。
5. LLM 生成函数体主体代码（不含声明定义）。
6. Local Completer 补齐声明、类型、依赖、宏、接口绑定。
7. Validator 编译与规则检查，失败信息回灌 LLM。

## 关键组件
- Control Structure Parser
- Module Registry Resolver
- Prompt Builder
- LLM Code Generator
- Local Declaration/Definition Completer
- Compiler & Lint Validator

## 关键数据对象
- control_structure.json：输入控制结构
- component_modules_kb.json：模块知识库
- generated_body.c：LLM 生成的函数体片段
- completed_output/*：本地补全后的可编译工程文件

## 约束
1. module_id 必须可解析且唯一映射。
2. 每个 module instance 必须有 instance_name。
3. links 必须能形成有向无环图（允许显式反馈环但要标记）。
4. schedule 中必须指定 fast_loop 与 init 阶段。

## 验证门禁
1. Schema 校验通过。
2. 模块 ID 解析成功率 100%。
3. 函数体生成后无未定义符号（由本地补全保证）。
4. 至少通过一次编译检查。
