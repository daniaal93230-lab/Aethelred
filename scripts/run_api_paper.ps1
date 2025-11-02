Param(
  [string]$Api = "http://127.0.0.1:8080"
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

# Env for supervised paper session
$env:MODE = "paper"
$env:SAFE_FLATTEN_ON_START = "1"
$env:QA_DEV_ENGINE = "1"

# Prefer venv python if present
$venvPy = Join-Path -Path "..\.venv\Scripts" -ChildPath "python.exe"
if (Test-Path $venvPy) { $python = (Resolve-Path $venvPy).Path } else { $python = "python" }

Write-Host "Starting API on :8080 with MODE=paper, QA_DEV_ENGINE=1..." -ForegroundColor Cyan
Start-Process -FilePath "powershell" -ArgumentList @(
  "-NoProfile","-WindowStyle","Minimized",
  "-Command","uvicorn api.main:app --host 127.0.0.1 --port 8080 --reload"
) | Out-Null
Start-Sleep -Seconds 2

Write-Host "Starting watchdog..." -ForegroundColor Cyan
Start-Process -FilePath $python -ArgumentList @("scripts/watchdog.py","--base",$Api,"--interval","2","--failures","2") `
  -WindowStyle Minimized | Out-Null
Start-Sleep -Seconds 1

Write-Host "Kick demo /demo/paper_quick_run..." -ForegroundColor Cyan
try {
  Invoke-WebRequest -Method POST -Uri "$Api/demo/paper_quick_run" -ContentType "application/json" -Body "{}" | Out-Null
} catch {
  Write-Warning "Demo endpoint failed: $($_.Exception.Message)"
}

Write-Host "Visor tip: streamlit run apps/visor/streamlit_app.py (VISOR_API_BASE=$Api)" -ForegroundColor DarkGray
Write-Host "Done. Check /healthz and /runtime/account_runtime.json" -ForegroundColor Green
