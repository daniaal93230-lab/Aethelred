create view if not exists v_trades as
select ts, symbol, side, qty, price, notional_usd, order_id
from paper_trades
order by ts desc;
