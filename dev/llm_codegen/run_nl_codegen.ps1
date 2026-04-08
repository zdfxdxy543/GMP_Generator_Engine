param(
  [string]$Instruction = "生成永磁同步电机速度控制程序",
  [string]$Kb = "knowledge_base/component_modules_kb_v2.json",
  [string]$ControlOut = "dev/llm_codegen/output/control_from_nl.json",
  [string]$Out = "dev/llm_codegen/output/generated_ctl_main_from_nl.c",
  [string]$Raw = "dev/llm_codegen/output/generated_raw_from_nl.json",
  [string]$PromptOut = "dev/llm_codegen/output/generated_prompt_from_nl.txt",
  [string]$Model = "deepseek-ai/DeepSeek-V3.2"
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path $Kb)) { throw "Missing kb file: $Kb" }
if (-not $env:SILICONFLOW_API_KEY -and -not $env:OPENAI_API_KEY) {
  throw "Missing SILICONFLOW_API_KEY or OPENAI_API_KEY"
}

python "dev/llm_codegen/nl_instruction_to_control.py" `
  --instruction $Instruction `
  --kb $Kb `
  --out $ControlOut

python "dev/llm_codegen/siliconflow_codegen_client.py" `
  --control $ControlOut `
  --kb $Kb `
  --out $Out `
  --raw $Raw `
  --prompt-out $PromptOut `
  --render-profile ctl_main `
  --temperature 0.0 `
  --model $Model
