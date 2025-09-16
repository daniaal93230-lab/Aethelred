# run_paper.ps1
$ErrorActionPreference = "Stop"

# Always operate from the script's folder
Set-Location $PSScriptRoot
$env:PYTHONPATH = $PSScriptRoot

# Define the bots you want to run
$bots = @(
    @{
        name   = "BTC 1h"
        args   = "--exchange binance --symbol BTC/USDT --interval 1h --limit 3000 --profile easy --trend-long --trend-no-short --risk 0.02 --paper-ledger --paper-file btc_ledger.csv --paper-state-file btc_state.json --emit-json --emit-json-file btc_signal.json"
        log    = "btc.log"
    },
    @{
        name   = "ETH 1h"
        args   = "--exchange binance --symbol ETH/USDT --interval 1h --limit 3000 --profile easy --trend-long --trend-no-short --risk 0.02 --paper-ledger --paper-file eth_ledger.csv --paper-state-file eth_state.json --emit-json --emit-json-file eth_signal.json"
        log    = "eth.log"
    },
    @{
        name   = "SOL 15m"
        args   = "--exchange binance --symbol SOL/USDT --interval 15m --limit 5000 --profile easy --trend-long --trend-no-short --risk 0.01 --slip-bps 2.0 --paper-ledger --paper-file sol_ledger.csv --paper-state-file sol_state.json --emit-json --emit-json-file sol_signal.json"
        log    = "sol.log"
    }
)

foreach ($b in $bots) {
    $title = "Aethelred - $($b.name)"
    $cmd   = "cd `"$PSScriptRoot`"; `$env:PYTHONPATH = `"$PSScriptRoot`"; python -m bot.brain $($b.args) | Tee-Object -FilePath `"$($b.log)`" -Append"
    Start-Process -FilePath "powershell" -ArgumentList @(
        "-NoLogo",
        "-NoExit",
        "-Command",
        "`$host.UI.RawUI.WindowTitle = `"$title`"; $cmd"
    ) -WorkingDirectory $PSScriptRoot -WindowStyle Minimized
}

Write-Host "Launched $($bots.Count) paper bots. Logs: *.log in $PSScriptRoot" -ForegroundColor Green
