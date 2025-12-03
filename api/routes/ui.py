from fastapi import APIRouter, Response
from typing import List
from sqlite3 import Row

from db.db_manager import get_conn

router = APIRouter(prefix="/ui", tags=["ui"])


@router.get("/trades")
def trades_html() -> Response:
    """
    Return a small HTML table of recent paper trades.

    Mypy-strict notes:
    - We annotate return type as Response.
    - Rows from sqlite are treated as sequences (Row).
    - HTML is accumulated as List[str].
    """
    with get_conn() as c:
        rows: List[Row] = c.execute(
            """
            select ts, symbol, side, qty, price, notional_usd, order_id
            from paper_trades
            order by ts desc
            limit 1000;
            """
        ).fetchall()

    html: List[str] = [
        "<html><head><title>Trades</title><meta charset='utf-8'></head><body>",
        "<h2>Recent Trades</h2>",
        (
            "<table border='1' cellpadding='6'>"
            "<tr>"
            "<th>ts</th><th>symbol</th><th>side</th>"
            "<th>qty</th><th>price</th><th>notional_usd</th><th>order_id</th>"
            "</tr>"
        ),
    ]

    for r in rows:
        ts = r[0]
        symbol = r[1]
        side = r[2]
        qty = r[3]
        price = r[4]
        notional = r[5]
        order_id = r[6]

        html.append(
            f"<tr>"
            f"<td>{ts}</td><td>{symbol}</td><td>{side}</td>"
            f"<td>{qty}</td><td>{price}</td><td>{notional}</td><td>{order_id}</td>"
            f"</tr>"
        )

    html.append("</table></body></html>")
    return Response("".join(html), media_type="text/html")
