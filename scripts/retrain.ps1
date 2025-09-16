$env:PYTHONPATH="."
$syms = @(
  @{s="BTC/USDT"; tf="15m"},
  @{s="ETH/USDT"; tf="1h"},
  @{s="SOL/USDT"; tf="15m"}
)
foreach ($p in $syms) {
  python -m bot.brain --exchange binance --symbol $($p.s) --interval $($p.tf) `
    --limit 5000 --ml-train --ml-horizon 1
}
