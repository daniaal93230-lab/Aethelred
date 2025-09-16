# run_paper_loop.ps1
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
$env:PYTHONPATH = $PSScriptRoot

# Map each bot to its cadence (seconds)
$bots = @(
    @{
        name   = "BTC 1h"
        sleepS = 300   # every 5 minutes
        args = "--exchange binance --symbol BTC/USDT --interval 1h --limit 3000 --profile easy --trend-long --trend-no-short --risk 0.02 --paper-ledger --paper-file btc_binance_ledger.csv --paper-state-file btc_binance_state.json --emit-json --emit-json-file btc_binance_signal.json"
        log    = "btc_loop.log"
    },
    @{
        name   = "ETH 1h"
        sleepS = 300
        args = "--exchange binance --symbol ETH/USDT --interval 1h --limit 3000 --profile easy --trend-long --trend-no-short --risk 0.02 --paper-ledger --paper-file eth_binance_ledger.csv --paper-state-file eth_binance_state.json --emit-json --emit-json-file eth_binance_signal.json"
        log    = "eth_loop.log"
    },
    @{
        name   = "SOL 15m"
        sleepS = 90
        args = "--exchange binance --symbol SOL/USDT --interval 15m --limit 5000 --profile easy --trend-long --trend-no-short --risk 0.01 --slip-bps 2.0 --paper-ledger --paper-file sol_binance_ledger.csv --paper-state-file sol_binance_state.json --emit-json --emit-json-file sol_binance_signal.json"
        log    = "sol_loop.log"
    }
)

foreach ($b in $bots) {
    $title = "Aethelred Loop - $($b.name)"
    $cmd = @"
cd "$PSScriptRoot"
`$env:PYTHONPATH = "$PSScriptRoot"
while ($true) {
  python -m bot.brain $($b.args) | Tee-Object -FilePath "$($b.log)" -Append
  Start-Sleep -Seconds $($b.sleepS)
}
"@
    Start-Process -FilePath "powershell" -ArgumentList @(
        "-NoLogo","-NoExit","-Command",
        "`$host.UI.RawUI.WindowTitle = `"$title`"; $cmd"
    ) -WorkingDirectory $PSScriptRoot -WindowStyle Minimized
}

Write-Host "Looping bots launched. Logs: *_loop.log" -ForegroundColor Green
