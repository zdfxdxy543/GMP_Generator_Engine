param(
  [string]$Control = "dev/llm_codegen/05_control_structure_strict_example.json",
  [string]$Kb = "knowledge_base/component_modules_kb_v2.json",
  [string]$Out = "dev/llm_codegen/output/generated_body.c",
  [string]$Raw = "dev/llm_codegen/output/generated_raw.json",
  [string]$PromptOut = "dev/llm_codegen/output/generated_prompt.txt",
  [string]$Model = "deepseek-ai/DeepSeek-V3.2"
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path $Control)) { throw "Missing control file: $Control" }
if (-not (Test-Path $Kb)) { throw "Missing kb file: $Kb" }
if (-not $env:SILICONFLOW_API_KEY -and -not $env:OPENAI_API_KEY) {
  throw "Missing SILICONFLOW_API_KEY or OPENAI_API_KEY"
}

python "dev/llm_codegen/siliconflow_codegen_client.py" `
  --control $Control `
  --kb $Kb `
  --out $Out `
  --raw $Raw `
  --prompt-out $PromptOut `
  --temperature 0.0 `
  --model $Model
