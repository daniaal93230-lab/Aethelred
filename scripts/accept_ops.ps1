param(
  [string]$Base = "http://127.0.0.1:8080"
)

Function Invoke-JsonPost {
  param([string]$Url, [hashtable]$Body)
  $json = $Body | ConvertTo-Json -Compress
  return Invoke-WebRequest -Method POST -Uri $Url -ContentType "application/json" -Body $json
}

Write-Host "Ensure the API is started with QA enabled: set the env var QA_DEV_ENGINE=1 (or QA_MODE=1) before launching uvicorn. Then press Enter to continue..."
Read-Host

Write-Host "1) Trigger QA demo endpoint to open a tiny in-memory position"
Invoke-JsonPost "$Base/demo/paper_quick_run" @{ symbol="BTCUSDT"; qty=0.001; price=100 } | Out-Null

Write-Host "2) Verify health"
Invoke-WebRequest "$Base/healthz" | Out-Null

Write-Host "3) Start watchdog"
Start-Process -FilePath "python" -ArgumentList "scripts/watchdog.py --base $Base --interval 2 --failures 2"

Write-Host "4) Simulate crash"
# Adjust the process name to match your runner process
Get-Process | Where-Object { $_.ProcessName -like "*aethelred*" } | Stop-Process -Force

Start-Sleep -Seconds 5

Write-Host "5) Watchdog should have posted /flatten. Check positions now"
$positions = Invoke-WebRequest "$Base/metrics_json"
Write-Output $positions.Content

Write-Host "6) Check runtime snapshot file"
Get-Content "account_runtime.json"
