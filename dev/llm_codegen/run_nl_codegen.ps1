param(
  [string]$Instruction = "生成永磁同步电机速度控制程序",
  [string]$Kb = "knowledge_base/component_modules_kb_v2.json",
  [string]$LlmConfig = "dev/llm_codegen/llm_settings.json",
  [string]$ControlOut = "dev/llm_codegen/output/control_from_nl.json",
  [string]$ControlRaw = "dev/llm_codegen/output/control_raw_from_nl.json",
  [string]$ControlPromptOut = "dev/llm_codegen/output/control_prompt_from_nl.txt",
  [string]$Out = "dev/llm_codegen/output/generated_ctl_main_from_nl.c",
  [string]$Raw = "dev/llm_codegen/output/generated_raw_from_nl.json",
  [string]$PromptOut = "dev/llm_codegen/output/generated_prompt_from_nl.txt",
  [string]$Model = ""
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path $Kb)) { throw "Missing kb file: $Kb" }
if (-not (Test-Path $LlmConfig)) { throw "Missing llm config file: $LlmConfig" }

$llmCfg = Get-Content $LlmConfig -Raw | ConvertFrom-Json
$apiKeyFromConfig = "$($llmCfg.api_key)"
if (-not $apiKeyFromConfig -and -not $env:SILICONFLOW_API_KEY -and -not $env:OPENAI_API_KEY) {
  throw "Missing api_key in $LlmConfig and no SILICONFLOW_API_KEY/OPENAI_API_KEY in env"
}

$modelToUse = if ($Model) { $Model } else { "$($llmCfg.model)" }

python "dev/llm_codegen/nl_instruction_to_control.py" `
  --instruction $Instruction `
  --kb $Kb `
  --llm-config $LlmConfig `
  --out $ControlOut `
  --raw $ControlRaw `
  --prompt-out $ControlPromptOut `
  --model $modelToUse
if ($LASTEXITCODE -ne 0) {
  throw "Stage-1 failed: nl_instruction_to_control.py exited with code $LASTEXITCODE"
}

python "dev/llm_codegen/siliconflow_codegen_client.py" `
  --control $ControlOut `
  --kb $Kb `
  --llm-config $LlmConfig `
  --out $Out `
  --raw $Raw `
  --prompt-out $PromptOut `
  --render-profile ctl_main `
  --model $modelToUse
if ($LASTEXITCODE -ne 0) {
  throw "Stage-2 failed: siliconflow_codegen_client.py exited with code $LASTEXITCODE"
}
