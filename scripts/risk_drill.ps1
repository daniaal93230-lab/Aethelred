param([int]$Hours=4)
Write-Host "Risk drill gauges"
try {
  $cfg = Invoke-RestMethod -Uri http://localhost:8080/risk/config -Method GET
  $met = Invoke-RestMethod -Uri http://localhost:8080/metrics_json -Method GET
  $vet = Invoke-RestMethod -Uri "http://localhost:8080/risk/veto_stats?hours=$Hours" -Method GET
  Write-Host "Profile:" ($cfg.profile | Out-String)
  Write-Host "Kill switch:" $cfg.kill_switch
  Write-Host ("Daily loss limit pct: {0}" -f $cfg.daily_loss_limit_pct)
  Write-Host ("Per-trade risk pct: {0}" -f $cfg.per_trade_risk_pct)
  Write-Host ("Leverage cap: {0}" -f $cfg.max_leverage)
  $p = $met.risk.portfolio
  Write-Host ("Equity: {0}  Notional: {1}  MaxExposure: {2}  Lev: {3}" -f $p.equity_now, $p.total_notional_usd, $p.max_exposure_usd, $p.leverage)
  Write-Host "Veto counts (last $Hours h):"
  $vet.counts | ForEach-Object { Write-Host ("{0} -> {1}" -f $_.reason, $_.n) }
} catch {
  Write-Error $_.Exception.Message
  exit 1
}
exit 0
