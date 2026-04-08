# 开发任务清单（MVP）

## P0
1. 对 knowledge_base/component_modules_kb.json 做 canonical_id 唯一化。
2. 给每个模块补 api_contract（init/step/attach 参数语义）。
3. 实现控制结构 schema 校验器（使用 03_control_structure.schema.json）。
4. 实现 module_id -> 元数据 解析器。

## P1
1. 实现 prompt builder（按 schedule 分块组织上下文）。
2. 让 LLM 输出函数体骨架（init/fast/slow/fault）。
3. 实现本地补全器（声明、定义、include、默认参数）。
4. 接入编译器做自动验证与错误回灌。

## P2
1. 增加硬件映射层（ADC/PWM/ENCODER 绑定规则）。
2. 支持生成多个目标文件（ctl_main.c, user_main.c 等）。
3. 增加回归测试样例（PMSM/ACM/DP）。

## 当前里程碑输出
- 已完成：方案备份与开发文件落盘。
- 下一步：先执行 P0-1（canonical_id 唯一化）。
