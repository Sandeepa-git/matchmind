# Deploys MatchMind to Azure:
#   backend  -> Azure Functions (Flex Consumption, pay-per-use)
#   frontend -> Azure Static Web Apps (Free)
# Usage (from the matchmind folder, after setup.ps1):  powershell -ExecutionPolicy Bypass -File .\infra\deploy.ps1
# Safe to re-run: existing resources are reused and the code is redeployed.
# Note: no $ErrorActionPreference = "Stop" - in Windows PowerShell 5 it turns az warnings on stderr into
# fatal errors. Each step checks $LASTEXITCODE instead.
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$root = Resolve-Path "$here\.."
$rg = "matchmind-rg"; $loc = "eastus2"
$suffix = (az account show --query id -o tsv).Substring(0, 6)
$storage = "matchmindst$suffix"; $func = "matchmind-api-$suffix"; $web = "matchmind-web"

function Exists($cmd) {
    $old = $ErrorActionPreference; $ErrorActionPreference = "SilentlyContinue"
    $r = Invoke-Expression "$cmd 2>`$null"
    $ErrorActionPreference = $old
    return [bool]$r
}
function Check($step) { if ($LASTEXITCODE -ne 0) { Write-Host "FAILED: $step" -ForegroundColor Red; exit 1 } }

# --- settings from .env --------------------------------------------------------------------
$envVars = @{}
Get-Content "$root\.env" -Encoding UTF8 | Where-Object { $_ -match "^\s*([A-Z_]+)=(.*)$" } |
    ForEach-Object { $envVars[$Matches[1]] = $Matches[2].Trim() }
if (-not $envVars["AZURE_OPENAI_KEY"]) { throw ".env is missing AZURE_OPENAI_KEY - run setup.ps1 first" }

# --- backend: Function App ------------------------------------------------------------------
Write-Host "1/5 Storage account + Function App..." -ForegroundColor Cyan
if (Exists "az functionapp show -n $func -g $rg --query name -o tsv") {
    Write-Host "    using existing Function App $func"
} else {
    if (-not (Exists "az storage account show -n $storage -g $rg --query name -o tsv")) {
        az storage account create -n $storage -g $rg -l $loc --sku Standard_LRS --allow-blob-public-access false -o none
        Check "storage account"
    }
    az functionapp create -n $func -g $rg --storage-account $storage --flexconsumption-location $loc `
        --runtime python --runtime-version 3.11 --instance-memory 2048 -o none
    Check "function app create"
}

Write-Host "2/5 App settings..." -ForegroundColor Cyan
$settings = @("MATCHMIND_CACHE_DIR=/tmp/matchmind-cache")
foreach ($k in "AZURE_OPENAI_ENDPOINT", "AZURE_OPENAI_KEY", "MODEL_SMART", "MODEL_FAST", "TRANSLATOR_KEY", "TRANSLATOR_REGION", "FOUNDRY_PROJECT_ENDPOINT") {
    if ($envVars[$k]) { $settings += "$k=$($envVars[$k])" }
}
az functionapp config appsettings set -n $func -g $rg --settings @settings -o none
Check "app settings"

Write-Host "3/5 Deploying API code (remote build, ~2-4 min)..." -ForegroundColor Cyan
$zip = Join-Path $env:TEMP "matchmind-api.zip"
Remove-Item $zip -Force -ErrorAction SilentlyContinue
python "$here\make_api_zip.py" (Join-Path $root "api") $zip
Check "zip API"
az functionapp deployment source config-zip -n $func -g $rg --src $zip --build-remote true -o none
Check "API deployment"
$apiHost = az functionapp show -n $func -g $rg --query "properties.defaultHostName" -o tsv 2>$null
if (-not $apiHost -or $apiHost -eq "None") { $apiHost = az functionapp show -n $func -g $rg --query defaultHostName -o tsv 2>$null }
$apiUrl = "https://$apiHost"

# --- frontend: Static Web App -----------------------------------------------------------------
Write-Host "4/5 Static Web App + frontend build..." -ForegroundColor Cyan
if (-not (Exists "az staticwebapp show -n $web -g $rg --query name -o tsv")) {
    az staticwebapp create -n $web -g $rg -l $loc --sku Free -o none
    Check "static web app create"
}
$webUrl = "https://" + (az staticwebapp show -n $web -g $rg --query defaultHostname -o tsv)
$token = az staticwebapp secrets list -n $web -g $rg --query properties.apiKey -o tsv

Push-Location "$root\web"
$env:VITE_API_BASE = $apiUrl
npm ci --silent
npm run build
if ($LASTEXITCODE -ne 0) { Pop-Location; Check "frontend build" }
Remove-Item Env:VITE_API_BASE
npx --yes @azure/static-web-apps-cli@2.0.1 deploy ./dist --deployment-token $token --env production
Pop-Location

Write-Host "5/5 CORS (allow the website to call the API)..." -ForegroundColor Cyan
az functionapp cors add -n $func -g $rg --allowed-origins $webUrl "http://localhost:5173" -o none 2>$null

Write-Host ""
Write-Host "API:      $apiUrl/api/state?minute=30" -ForegroundColor Green
Write-Host "Website:  $webUrl" -ForegroundColor Green
