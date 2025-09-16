# run_retrain_nightly.ps1
param(
  [int]$Hour = 3,
  [int]$Minute = 0
)
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
$env:PYTHONPATH = $PSScriptRoot

function Wait-Until($h, $m) {
  $now = Get-Date
  $next = Get-Date -Hour $h -Minute $m -Second 0
  if ($next -le $now) { $next = $next.AddDays(1) }
  $sleep = [int]($next - $now).TotalSeconds
  Write-Host "Sleeping $sleep sec until $next ..." -ForegroundColor DarkGray
  Start-Sleep -Seconds $sleep
}

while ($true) {
  Wait-Until -h $Hour -m $Minute

  $jobs = @(
    @{
      name="BTC 1h";
      args="--exchange binance --symbol BTC/USDT --interval 1h --limit 5000 --profile easy --wf-train 1000 --wf-test 400 --wf-step 200 --trend-long --trend-no-short --risk 0.02 --atr-len 14 --max-pos 1.0 --paper-ledger --paper-file btc_ledger.csv --paper-state-file btc_state.json --emit-json --emit-json-file btc_signal.json"
    },
    @{
      name="ETH 1h";
      args="--exchange binance --symbol ETH/USDT --interval 1h --limit 5000 --profile easy --wf-train 1000 --wf-test 400 --wf-step 200 --trend-long --trend-no-short --risk 0.02 --atr-len 14 --max-pos 1.0 --paper-ledger --paper-file eth_ledger.csv --paper-state-file eth_state.json --emit-json --emit-json-file eth_signal.json"
    },
    @{
      name="SOL 15m";
      args="--exchange binance --symbol SOL/USDT --interval 15m --limit 5000 --profile easy --wf-train 600 --wf-test 240 --wf-step 120 --trend-long --trend-no-short --risk 0.01 --slip-bps 2.0 --atr-len 14 --max-pos 1.0 --paper-ledger --paper-file sol_ledger.csv --paper-state-file sol_state.json --emit-json --emit-json-file sol_signal.json"
    }
  )

  foreach ($j in $jobs) {
    Write-Host ("[{0}] retrain pass…" -f $j.name) -ForegroundColor Cyan
    python -m bot.brain $j.args
  }

  # small buffer after runs
  Start-Sleep -Seconds 30
}
