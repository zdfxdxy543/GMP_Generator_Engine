# SiliconFlow DeepSeek-V3.2 调用程序

本目录包含自然语言到控制程序的两阶段流程：
1. 先结合控制器设计知识库，从自然语言生成严格控制结构配置 JSON（模块、环路关系、调度）。
2. 再根据该配置 + 知识库生成控制程序主体代码。

## 文件
- siliconflow_codegen_client.py: Python 调用客户端
- run_codegen.ps1: PowerShell 快速启动脚本
- nl_instruction_to_control.py: 自然语言 + 控制器设计知识库 -> 严格控制结构 JSON
- run_nl_codegen.ps1: 自然语言一键生成脚本
- llm_settings.json: 统一 LLM 配置（model/base_url/temperature/timeout/api_key/system prompts）
- .env.example: 环境变量模板

## 环境准备
1. 安装 Python 3.9+
2. 编辑 dev/llm_codegen/llm_settings.json

示例:
"api_key": "你的Key"

说明:
- 所有大模型调用默认从 llm_settings.json 读取配置。
- 若 api_key 为空，才会回退读取环境变量 SILICONFLOW_API_KEY 或 OPENAI_API_KEY。

## 默认模型
deepseek-ai/DeepSeek-V3.2

## 快速运行
在仓库根目录执行:

powershell -ExecutionPolicy Bypass -File dev/llm_codegen/run_codegen.ps1

### 自然语言控制生成
powershell -ExecutionPolicy Bypass -File dev/llm_codegen/run_nl_codegen.ps1 -Instruction "生成永磁同步电机速度控制程序"

自然语言模式默认输出:
- dev/llm_codegen/output/control_from_nl.json
- dev/llm_codegen/output/control_raw_from_nl.json
- dev/llm_codegen/output/control_prompt_from_nl.txt
- dev/llm_codegen/output/generated_ctl_main_from_nl.c
- dev/llm_codegen/output/generated_raw_from_nl.json
- dev/llm_codegen/output/generated_prompt_from_nl.txt

默认使用严格示例输入:
- dev/llm_codegen/05_control_structure_strict_example.json

输出文件默认位置:
- dev/llm_codegen/output/generated_body.c
- dev/llm_codegen/output/generated_raw.json
- dev/llm_codegen/output/generated_prompt.txt

## 手动运行
python dev/llm_codegen/siliconflow_codegen_client.py \
  --control dev/llm_codegen/05_control_structure_strict_example.json \
  --kb knowledge_base/component_modules_kb_v2.json \
  --out dev/llm_codegen/output/generated_body.c \
  --raw dev/llm_codegen/output/generated_raw.json \
  --prompt-out dev/llm_codegen/output/generated_prompt.txt \
  --temperature 0.0 \
  --model deepseek-ai/DeepSeek-V3.2

## 说明
1. 程序调用的是 OpenAI 兼容接口: /chat/completions。
2. base_url/model/temperature/timeout/api_key 统一由 dev/llm_codegen/llm_settings.json 管理。
3. 第一阶段会先基于知识库候选模块生成控制结构，并对 canonical_id/module_id 与调度一致性做严格校验。
4. 第一阶段包含“可运行硬约束”：fast_loop/slow_loop 中的模块必须具备可自动调用的 step API，不满足会直接失败。
5. 第二阶段仅生成函数体主体，声明与定义应由本地补全程序处理。
6. 第二阶段禁止输出 ERROR_UNRESOLVED_API 占位；若无法生成可运行调用会直接报错退出。
