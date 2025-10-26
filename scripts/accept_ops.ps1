param(
  [string]$Base = "http://127.0.0.1:8080"
)

Function Invoke-JsonPost {
  param([string]$Url, [hashtable]$Body)
  $json = $Body | ConvertTo-Json -Compress
  return Invoke-WebRequest -Method POST -Uri $Url -ContentType "application/json" -Body $json
}

Write-Host "Start engine in another terminal. Then press Enter to continue..."
Read-Host

Write-Host "1) Open a small test position"
Invoke-JsonPost "$Base/order/market" @{ symbol="BTCUSDT"; side="buy"; qty=0.001 } | Out-Null

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
