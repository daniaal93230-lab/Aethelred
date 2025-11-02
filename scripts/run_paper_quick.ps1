Param(
  [string]$Api = "http://127.0.0.1:8080"
)

$ErrorActionPreference = "Stop"
$env:QA_MODE = "1"
$env:SAFE_FLATTEN_ON_START = "1"

# Resolve venv python if present
$venvPy = Join-Path -Path "..\.venv\Scripts" -ChildPath "python.exe"
if (Test-Path $venvPy) {
  $python = (Resolve-Path $venvPy).Path
} else {
  $python = "python"
}

Write-Host "Starting API (QA_MODE=1) with safe startup..." -ForegroundColor Cyan
$apiProc = Start-Process -FilePath $python -ArgumentList @("-m","uvicorn","api.main:app","--host","127.0.0.1","--port","8080") -PassThru
Start-Sleep -Seconds 3

Write-Host "Starting watchdog..." -ForegroundColor Cyan
Start-Process -FilePath $python -ArgumentList @("scripts/watchdog.py","--base",$Api,"--interval","2","--failures","2") -WindowStyle Minimized | Out-Null
Start-Sleep -Seconds 1

Write-Host "Kicking demo /demo/paper_quick_run..."
try {
  Invoke-WebRequest -Method POST -Uri "$Api/demo/paper_quick_run" -ContentType "application/json" -Body "{}" | Out-Null
} catch {
  Write-Host "Failed to call demo endpoint: $($_.Exception.Message)"
}

Write-Host "Export trades.csv..."
try {
  New-Item -ItemType Directory -Force -Path "exports_download" | Out-Null
  Invoke-WebRequest -Uri "$Api/export/trades.csv" -OutFile "exports_download\trades.csv" -UseBasicParsing | Out-Null
  Invoke-WebRequest -Uri "$Api/export/decisions.csv" -OutFile "exports_download\decisions.csv" -UseBasicParsing | Out-Null
} catch {}
Write-Host "Done. Check $Api/healthz" -ForegroundColor Green
