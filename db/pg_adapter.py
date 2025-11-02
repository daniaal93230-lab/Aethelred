from __future__ import annotations
from typing import Iterable, Dict, Any, Optional

try:
    import psycopg
except Exception as _e:  # pragma: no cover
    psycopg = None


class PgAdapter:
    """
    Postgres adapter that provides the surface used by DBManager.
    Enabled when DB_URL starts with postgres.
    """

    def __init__(self, dsn: str):
        if psycopg is None:
            raise RuntimeError("psycopg not installed. Add psycopg[binary] to requirements.txt")
        self._dsn = dsn
        self._conn = psycopg.connect(self._dsn, autocommit=True)

    # clock
    def now_ts(self) -> int:
        with self._conn.cursor() as cur:
            cur.execute("select extract(epoch from now())::bigint")
            return int(cur.fetchone()[0])

    # trades iterator backing /export/trades.csv
    def iter_trades(self) -> Iterable[Dict[str, Any]]:
        sql = """
          select
            ts_open, ts_close, symbol, side, qty, entry, exit,
            coalesce(pnl_usd, pnl) as pnl,
            coalesce(return_pct, pnl_pct) as pnl_pct,
            coalesce(fee_usd, 0.0) as fee_usd,
            coalesce(slippage_bps, 0.0) as slippage_bps,
            note
          from trades
          order by ts_close nulls last, ts_open
        """
        with self._conn.cursor(row_factory=psycopg.rows.dict_row) as cur:
            cur.execute(sql)
            for row in cur:
                yield dict(row)

    # training jobs queue
    def enqueue_job(self, kind: str, job: str, notes: Optional[str] = None) -> Dict[str, Any]:
        with self._conn.cursor(row_factory=psycopg.rows.dict_row) as cur:
            cur.execute(
                "insert into jobs(kind, job, notes, status, ts_created) values (%s, %s, %s, 'queued', extract(epoch from now())::bigint) returning id, kind, job",
                (kind, job, notes),
            )
            r = cur.fetchone()
            return {"id": f"{r['kind']}-{r['id']}", "job": r["job"], "notes": notes}

    def dequeue_job(self, kind: str = "train") -> Optional[Dict[str, Any]]:
        with self._conn.cursor(row_factory=psycopg.rows.dict_row) as cur:
            cur.execute(
                """
                update jobs
                set status='running', ts_started=extract(epoch from now())::bigint
                where id = (
                  select id from jobs where status='queued' and kind=%s order by id asc limit 1
                )
                returning id, kind, job, notes
                """,
                (kind,),
            )
            r = cur.fetchone()
            return dict(r) if r else None

    def complete_job(self, job_id: int | str, ok: bool, notes: Optional[str] = None):
        # accept either numeric id or KIND-ID strings
        if isinstance(job_id, str) and "-" in job_id:
            job_id = int(job_id.split("-")[-1])
        with self._conn.cursor() as cur:
            cur.execute(
                "update jobs set status=%s, ts_finished=extract(epoch from now())::bigint, notes=coalesce(%s, notes) where id=%s",
                ("done" if ok else "failed", notes, job_id),
            )

    # realized pnl and trade count today
    def realized_pnl_today_usd(self) -> float:
        # prefer view if present
        try:
            with self._conn.cursor() as cur:
                cur.execute("select realized_pnl_today_usd from v_realized_pnl_today_usd")
                r = cur.fetchone()
                if r:
                    return float(r[0])
        except Exception:
            pass
        with self._conn.cursor() as cur:
            cur.execute(
                """
                select coalesce(sum(pnl_usd), 0.0)
                from trades
                where ts_close >= extract(epoch from date_trunc('day', now() at time zone 'UTC'))
                """
            )
            return float(cur.fetchone()[0] or 0.0)

    def trade_count_today(self) -> int:
        try:
            with self._conn.cursor() as cur:
                cur.execute("select trade_count_today from v_trade_count_today")
                r = cur.fetchone()
                if r:
                    return int(r[0])
        except Exception:
            pass
        with self._conn.cursor() as cur:
            cur.execute(
                """
                select count(1)
                from trades
                where ts_close >= extract(epoch from date_trunc('day', now() at time zone 'UTC'))
                """
            )
            return int(cur.fetchone()[0] or 0)
