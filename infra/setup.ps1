# Creates all Azure resources for MatchMind (~$5-15, kept under budget if you cache outputs).
# Usage:  powershell -ExecutionPolicy Bypass -File .\infra\setup.ps1   (after `az login`). Safe to re-run.
$rg = "matchmind-rg"; $loc = "eastus2"; $ai = "matchmind-resource"; $project = "matchmind"; $tr = "matchmind-tr"
$model = "gpt-5-mini"; $modelVersion = "2025-08-07"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path

az group create -n $rg -l $loc -o none

# Foundry (AIServices) resource. Created from JSON because public network access must be set explicitly.
$aiExists = az cognitiveservices account show -n $ai -g $rg --query name -o tsv 2>$null
if (-not $aiExists) { az resource create -g $rg -n $ai --resource-type Microsoft.CognitiveServices/accounts --is-full-object --properties "@$here\ai-account.json" -o none }
az cognitiveservices account deployment create -n $ai -g $rg --deployment-name $model --model-name $model --model-version $modelVersion --model-format OpenAI --sku-name GlobalStandard --sku-capacity 50 -o none

$trExists = az cognitiveservices account show -n $tr -g $rg --query name -o tsv 2>$null
if (-not $trExists) { az cognitiveservices account create -n $tr -g $rg -l $loc --kind TextTranslation --sku F0 --yes -o none }

$endpoint = az cognitiveservices account show -n $ai -g $rg --query properties.endpoint -o tsv
$aiKey = az cognitiveservices account keys list -n $ai -g $rg --query key1 -o tsv
$trKey = az cognitiveservices account keys list -n $tr -g $rg --query key1 -o tsv
if (-not $aiKey) { Write-Host "AI resource not ready - check errors above." -ForegroundColor Red; exit 1 }

@"
AZURE_OPENAI_ENDPOINT=$endpoint
AZURE_OPENAI_KEY=$aiKey
MODEL_SMART=$model
MODEL_FAST=$model
TRANSLATOR_KEY=$trKey
TRANSLATOR_REGION=$loc
FOUNDRY_PROJECT_ENDPOINT=https://$ai.services.ai.azure.com/api/projects/$project
"@ | ForEach-Object { [IO.File]::WriteAllText("$here\..\.env", $_, (New-Object Text.UTF8Encoding $false)) }
az cognitiveservices account deployment list -n $ai -g $rg --query "[].{deployment:name, state:properties.provisioningState}" -o table
Write-Host "Wrote .env. Run 'az group delete -n $rg' after judging." -ForegroundColor Green
