param(
  [string]$Control = "dev/llm_codegen/05_control_structure_strict_example.json",
  [string]$Kb = "knowledge_base/component_modules_kb_v2.json",
  [string]$LlmConfig = "dev/llm_codegen/llm_settings.json",
  [string]$Out = "dev/llm_codegen/output/generated_body.c",
  [string]$Raw = "dev/llm_codegen/output/generated_raw.json",
  [string]$PromptOut = "dev/llm_codegen/output/generated_prompt.txt",
  [string]$Model = ""
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path $Control)) { throw "Missing control file: $Control" }
if (-not (Test-Path $Kb)) { throw "Missing kb file: $Kb" }
if (-not (Test-Path $LlmConfig)) { throw "Missing llm config file: $LlmConfig" }

$llmCfg = Get-Content $LlmConfig -Raw | ConvertFrom-Json
$apiKeyFromConfig = "$($llmCfg.api_key)"
if (-not $apiKeyFromConfig -and -not $env:SILICONFLOW_API_KEY -and -not $env:OPENAI_API_KEY) {
  throw "Missing api_key in $LlmConfig and no SILICONFLOW_API_KEY/OPENAI_API_KEY in env"
}

$modelToUse = if ($Model) { $Model } else { "$($llmCfg.model)" }

python "dev/llm_codegen/siliconflow_codegen_client.py" `
  --control $Control `
  --kb $Kb `
  --llm-config $LlmConfig `
  --out $Out `
  --raw $Raw `
  --prompt-out $PromptOut `
  --model $modelToUse
