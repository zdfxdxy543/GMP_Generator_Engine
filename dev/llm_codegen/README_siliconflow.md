# SiliconFlow DeepSeek-V3.2 调用程序

本目录新增了一个可直接调用硅基流动模型的程序，用于根据控制结构 + 知识库生成控制程序主体代码。

## 文件
- siliconflow_codegen_client.py: Python 调用客户端
- run_codegen.ps1: PowerShell 快速启动脚本
- nl_instruction_to_control.py: 自然语言 -> 严格控制结构 JSON
- run_nl_codegen.ps1: 自然语言一键生成脚本
- .env.example: 环境变量模板

## 环境准备
1. 安装 Python 3.9+
2. 设置环境变量

Windows PowerShell 示例:
$env:SILICONFLOW_API_KEY = "你的Key"

## 默认模型
deepseek-ai/DeepSeek-V3.2

## 快速运行
在仓库根目录执行:

powershell -ExecutionPolicy Bypass -File dev/llm_codegen/run_codegen.ps1

### 自然语言控制生成
powershell -ExecutionPolicy Bypass -File dev/llm_codegen/run_nl_codegen.ps1 -Instruction "生成永磁同步电机速度控制程序"

自然语言模式默认输出:
- dev/llm_codegen/output/control_from_nl.json
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
2. base_url 默认: https://api.siliconflow.cn/v1。
3. 仅生成函数体主体，声明与定义应由本地补全程序处理。
4. 新流程会先做模块解析与校验，若模块在 fast/slow loop 缺少 step API 会直接报错，不再输出占位垃圾代码。
