Param(
  [string]$HostUrl = "http://127.0.0.1:8000"
)

$ErrorActionPreference = "Stop"
$env:QA_MODE="1"

# Resolve venv python if present
$venvPy = Join-Path -Path ".venv\Scripts" -ChildPath "python.exe"
if (Test-Path $venvPy) {
  $python = (Resolve-Path $venvPy).Path
} else {
  $python = "python"
}

# Start API in background using the same shell env so QA_MODE is inherited
Write-Host "Starting API with $python -m uvicorn (QA_MODE=1)..." -ForegroundColor Cyan
$apiJob = Start-Job -ScriptBlock {
  param($py)
  & $py -m uvicorn api.app:app --host 127.0.0.1 --port 8000
} -ArgumentList $python

# Wait for /healthz up to 30s
$deadline = (Get-Date).AddSeconds(30)
while ((Get-Date) -lt $deadline) {
  try {
    $ok = Invoke-RestMethod -Method Get -Uri "$HostUrl/healthz" -TimeoutSec 2
    if ($ok.ok -eq $true) { break }
  } catch {
    Start-Sleep -Seconds 1
  }
}

try {
  $ok = Invoke-RestMethod -Method Get -Uri "$HostUrl/healthz" -TimeoutSec 2
} catch {
  Write-Host "API did not become healthy. Job state: $((Get-Job $apiJob.Id).State)" -ForegroundColor Red
  Receive-Job $apiJob -Keep | Out-String | Write-Host
  throw "Health check failed"
}

Write-Host "API healthy. Running /demo/paper_quick_run ..." -ForegroundColor Cyan
$resp = Invoke-RestMethod -Method Post -Uri "$HostUrl/demo/paper_quick_run" -TimeoutSec 20
$resp | ConvertTo-Json -Depth 6

Write-Host "Exporting trades.csv ..." -ForegroundColor Cyan
New-Item -ItemType Directory -Force -Path "exports" | Out-Null
Invoke-RestMethod -Uri "$HostUrl/export/trades.csv" -OutFile "exports/demo_trades.csv"
Write-Host "Saved to exports/demo_trades.csv" -ForegroundColor Green

Write-Host "To stop API: Stop-Job $($apiJob.Id) ; Receive-Job $($apiJob.Id) ; Remove-Job $($apiJob.Id)" -ForegroundColor Yellow
