from fastapi import APIRouter, Response
from db.db_manager import get_conn

router = APIRouter(prefix="/ui", tags=["ui"])


@router.get("/trades")
def trades_html():
    with get_conn() as c:
        rows = c.execute("""
            select ts, symbol, side, qty, price, notional_usd, order_id
            from paper_trades order by ts desc limit 1000;
        """).fetchall()
    html = ["<html><head><title>Trades</title><meta charset='utf-8'></head><body>"]
    html.append(
        "<h2>Recent Trades</h2><table border='1' cellpadding='6'><tr><th>ts</th><th>symbol</th><th>side</th><th>qty</th><th>price</th><th>notional_usd</th><th>order_id</th></tr>"
    )
    for r in rows:
        html.append(
            f"<tr><td>{r[0]}</td><td>{r[1]}</td><td>{r[2]}</td><td>{r[3]}</td><td>{r[4]}</td><td>{r[5]}</td><td>{r[6]}</td></tr>"
        )
    html.append("</table></body></html>")
    return Response("".join(html), media_type="text/html")
