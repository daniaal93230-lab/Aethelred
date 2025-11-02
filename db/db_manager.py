import os, sqlite3, time, json
from typing import Any, Dict, List, Tuple, Iterable
from utils.logger import get_logger

logger = get_logger(__name__)

DB_PATH = os.getenv("AET_DB_PATH", "data/aethelred.sqlite")
os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)


def _get_conn():
    return sqlite3.connect(DB_PATH)


def get_db_path() -> str:
    """Return the resolved DB path (compat helper)."""
    return DB_PATH


def get_conn():
    """Compatibility wrapper used by API routes — returns a connection with row_factory set."""
    con = sqlite3.connect(get_db_path())
    con.row_factory = sqlite3.Row
    return con


def table_exists(name: str) -> bool:
    con = _get_conn()
    try:
        cur = con.execute("SELECT name FROM sqlite_master WHERE type IN ('table','view') AND name=?;", (name,))
        return cur.fetchone() is not None
    finally:
        con.close()


def ensure_compat_views():
    """Create compatibility views so export endpoints can read a uniform schema.
    This is defensive: if legacy or newer tables exist, create views `v_trades_compat` and
    `v_decisions_compat` that map columns into a common layout.
    """
    con = _get_conn()
    try:
        cur = con.cursor()
        # Drop any existing compat views and recreate based on current schema.
        try:
            cur.execute("DROP VIEW IF EXISTS v_trades_compat")
        except Exception:
            pass
        try:
            cur.execute("DROP VIEW IF EXISTS v_decisions_compat")
        except Exception:
            pass

        # trades compat: prefer paper_trades, else trades
        if table_exists("paper_trades"):
            cur.execute(
                """
                CREATE VIEW v_trades_compat AS
                SELECT
                  COALESCE(ts, entry_ts) AS ts,
                  COALESCE(symbol, pair) AS symbol,
                  side,
                  COALESCE(qty, quantity) AS qty,
                  entry AS entry,
                  "exit" AS exit,
                  COALESCE(pnl, pnl_usd) AS pnl,
                  COALESCE(pnl_pct, 0) AS pnl_pct,
                  COALESCE(hold_s, 0) AS hold_s
                FROM paper_trades
                """
            )
        elif table_exists("trades"):
            cur.execute(
                """
                CREATE VIEW v_trades_compat AS
                SELECT
                  COALESCE(entry_ts, ts) AS ts,
                  COALESCE(pair, symbol) AS symbol,
                  side,
                  NULL AS qty,
                  entry AS entry,
                  "exit" AS exit,
                  COALESCE(pnl, pnl_usd) AS pnl,
                  COALESCE(pnl_pct, 0) AS pnl_pct,
                  COALESCE(hold_s, 0) AS hold_s
                FROM trades
                """
            )

        # decisions compat
        if table_exists("decisions"):
            cur.execute(
                """
                CREATE VIEW v_decisions_compat AS
                SELECT
                  COALESCE(ts, timestamp) AS ts,
                  symbol,
                  COALESCE(raw_signal, signal) AS raw_signal,
                  COALESCE(final_action, action) AS final_action,
                  COALESCE(veto_reason, reason) AS veto_reason,
                  COALESCE(model_version, '') AS model_version,
                  COALESCE(features_hash, '') AS features_hash
                FROM decisions
                """
            )
        elif table_exists("decision_log"):
            cur.execute(
                """
                CREATE VIEW v_decisions_compat AS
                SELECT
                  COALESCE(ts, timestamp) AS ts,
                  symbol,
                  COALESCE(raw_signal, signal) AS raw_signal,
                  COALESCE(final_action, action) AS final_action,
                  COALESCE(veto_reason, reason) AS veto_reason,
                  COALESCE(model_version, '') AS model_version,
                  COALESCE(features_hash, '') AS features_hash
                FROM decision_log
                """
            )

        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


_INIT_LOGGED = False


def init_db():
    conn = _get_conn()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            trade_id TEXT UNIQUE,
            timestamp TEXT DEFAULT (datetime('now')),
            symbol TEXT NOT NULL,
            side TEXT CHECK(side IN ('buy','sell')) NOT NULL,
            price REAL NOT NULL,
            amount REAL NOT NULL,
            status TEXT NOT NULL DEFAULT 'filled',
            is_mock INTEGER NOT NULL DEFAULT 0
        )
    """)
    # equity snapshots for dashboard / metrics
    cur.execute("""
        CREATE TABLE IF NOT EXISTS equity_snapshots(
            ts INTEGER PRIMARY KEY,
            equity REAL NOT NULL
        )
    """)
    # Paper trading persistence tables
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS paper_account(
            id INTEGER PRIMARY KEY CHECK (id=1),
            cash REAL NOT NULL,
            equity REAL NOT NULL DEFAULT 0,
            updated_ts REAL NOT NULL DEFAULT (strftime('%s','now'))
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS paper_positions(
            symbol TEXT PRIMARY KEY,
            qty REAL NOT NULL,
            avg_price REAL NOT NULL,
            side TEXT GENERATED ALWAYS AS (CASE WHEN qty>0 THEN 'long' WHEN qty<0 THEN 'short' ELSE NULL END) VIRTUAL,
            entry_ts INTEGER,
            opened_ts REAL,
            last_update_ts REAL
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS paper_trades(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts REAL NOT NULL,
            symbol TEXT NOT NULL,
            side TEXT NOT NULL,
            qty REAL NOT NULL,
            price REAL NOT NULL,
            fee_usd REAL NOT NULL,
            slippage_bps REAL NOT NULL,
            run_id TEXT
        )
        """
    )
    # decision_log for analytics
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS decision_log(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts INTEGER NOT NULL,
            symbol TEXT NOT NULL,
            strategy TEXT,
            regime TEXT,
            signal TEXT,
            intent TEXT,
            size_usd REAL,
            price REAL,
            ml_p_up REAL,
            ml_vote TEXT,
            veto INTEGER,
            reasons TEXT,
            planned_stop REAL,
            planned_tp REAL,
            run_id TEXT
        )
        """
    )
    conn.commit()
    # bootstrap paper account row if empty
    try:
        cur.execute("SELECT cash FROM paper_account WHERE id=1")
        row = cur.fetchone()
        if row is None:
            starting = float(os.environ.get("PAPER_STARTING_CASH", "10000"))
            cur.execute("INSERT INTO paper_account(id,cash) VALUES(1,?)", (starting,))
            conn.commit()
    except Exception:
        # table may not exist yet if older db; safe to ignore
        pass
    # indices for performance (safe to re-run)
    try:
        cur.execute("CREATE INDEX IF NOT EXISTS ix_decision_log_ts ON decision_log(ts);")
        cur.execute("CREATE INDEX IF NOT EXISTS ix_decision_log_symbol_ts ON decision_log(symbol, ts);")
        cur.execute("CREATE INDEX IF NOT EXISTS ix_paper_trades_ts ON paper_trades(ts);")
        conn.commit()
    except Exception:
        pass
    conn.close()
    global _INIT_LOGGED
    if not _INIT_LOGGED:
        _INIT_LOGGED = True
        logger.info("Database initialized and tables ready.")

    # Attempt to add entry_ts column if missing (legacy DBs)
    try:
        with _get_conn() as _c:
            _cur = _c.cursor()
            _cur.execute("PRAGMA table_info(paper_positions)")
            cols = [r[1] for r in _cur.fetchall()]
            if "entry_ts" not in cols:
                _cur.execute("ALTER TABLE paper_positions ADD COLUMN entry_ts INTEGER")
                _c.commit()
    except Exception:
        pass


class DBManager:
    def __init__(self, *args, **kwargs):
        """Create a DBManager.

        Accepts optional db_path kwarg for tests to create an on-disk sqlite file.
        """
        db_path = kwargs.get("db_path") or os.getenv("DB_PATH") or ":memory:"
        # ensure directory exists for on-disk DBs
        try:
            d = os.path.dirname(db_path)
            if d:
                os.makedirs(d, exist_ok=True)
        except Exception:
            pass
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        # Ensure legacy `trades` table with expected column ordering exists first
        # so tests and legacy code that rely on column indices work.
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                trade_id TEXT UNIQUE,
                timestamp TEXT DEFAULT (datetime('now')),
                symbol TEXT NOT NULL,
                side TEXT CHECK(side IN ('buy','sell')) NOT NULL,
                price REAL,
                amount REAL,
                status TEXT NOT NULL DEFAULT 'filled',
                is_mock INTEGER NOT NULL DEFAULT 0
            )
            """
        )
        self._conn.commit()
        # create our minimal schema (other tables) after legacy trades; it will not replace existing `trades`
        self._ensure_minimal_schema()
        # Ensure trade_id column exists on legacy DBs (some migrations create a different 'trades' layout)
        try:
            cur = self._conn.execute("PRAGMA table_info(trades)")
            cols = [r[1] for r in cur.fetchall()]
            # Ensure legacy columns exist (some DBs have a different 'trades' layout)
            missing = [c for c in ("trade_id", "timestamp", "price", "amount", "status", "is_mock") if c not in cols]
            for col in missing:
                try:
                    if col == "trade_id":
                        self._conn.execute("ALTER TABLE trades ADD COLUMN trade_id TEXT")
                    elif col == "timestamp":
                        self._conn.execute("ALTER TABLE trades ADD COLUMN timestamp TEXT DEFAULT (datetime('now'))")
                    elif col == "price":
                        self._conn.execute("ALTER TABLE trades ADD COLUMN price REAL")
                    elif col == "amount":
                        self._conn.execute("ALTER TABLE trades ADD COLUMN amount REAL")
                    elif col == "status":
                        self._conn.execute("ALTER TABLE trades ADD COLUMN status TEXT DEFAULT 'filled'")
                    elif col == "is_mock":
                        self._conn.execute("ALTER TABLE trades ADD COLUMN is_mock INTEGER DEFAULT 0")
                except Exception:
                    # ignore failures (e.g., column exists in another form)
                    pass
            try:
                self._conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS ux_trades_trade_id ON trades(trade_id)")
            except Exception:
                pass
            self._conn.commit()
        except Exception:
            pass
        # Postgres adapter (optional) selected by DB_URL environment variable
        PG_PREFIXES = ("postgres://", "postgresql://")
        self._pg = None
        try:
            db_url = os.getenv("DB_URL", "") or ""
            if any(db_url.startswith(p) for p in PG_PREFIXES):
                from db.pg_adapter import PgAdapter

                self._pg = PgAdapter(db_url)
        except Exception:
            # Fail gracefully — continue using sqlite fallback
            self._pg = None
        # Postgres adapter (optional) selected by DB_URL environment variable
        self._pg = None
        try:
            db_url = os.getenv("DB_URL", "") or ""
            if any(db_url.startswith(p) for p in PG_PREFIXES):
                from db.pg_adapter import PgAdapter

                self._pg = PgAdapter(db_url)
        except Exception:
            # Fail gracefully — continue using sqlite fallback
            self._pg = None

    # --- Utility clock ---
    def now_ts(self) -> int:
        if getattr(self, "_pg", None):
            return self._pg.now_ts()
        import time

        return int(time.time())

    # --- Trades iteration (CSV export source) ---
    def iter_trades(self) -> Iterable[Dict[str, Any]]:
        if getattr(self, "_pg", None):
            yield from self._pg.iter_trades()
            return
        try:
            cur = self._conn.execute(
                "select ts_open, ts_close, symbol, side, qty, entry, exit, pnl_usd as pnl, return_pct as pnl_pct, fee_usd, slippage_bps, note from trades order by ts_close nulls last, ts_open"
            )
            for r in cur.fetchall():
                yield dict(r)
        except Exception:
            yield from []

    # --- Legacy helpers used by tests / other modules ---
    def insert_trade(self, trade_id, symbol, side, price, amount, status="filled", is_mock=0):
        """Insert a simple trade into the legacy `trades` table.

        Duplicate trade_id values are ignored.
        """
        try:
            side_clean = str(side).lower()
            timestamp = time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime())
            cur = self._conn.execute(
                """
                INSERT OR IGNORE INTO trades
                (trade_id, symbol, side, price, amount, timestamp, status, is_mock)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (trade_id, symbol, side_clean, price, amount, timestamp, status, int(is_mock)),
            )
            self._conn.commit()
            return cur.lastrowid
        except sqlite3.IntegrityError:
            return None

    def fetch_all_trades(self):
        cur = self._conn.execute("SELECT * FROM trades ORDER BY timestamp DESC")
        return cur.fetchall()

    def close(self):
        try:
            self._conn.close()
        except Exception:
            pass

    # --- Training jobs queue (very small stub, replace with real queue in prod) ---
    def enqueue_job(self, kind: str, job: str, notes: str | None = None) -> dict:
        if getattr(self, "_pg", None):
            return self._pg.enqueue_job(kind=kind, job=job, notes=notes)

        self._conn.execute(
            "insert into jobs(kind, job, notes, status, ts_created) values (?, ?, ?, 'queued', ?)",
            (kind, job, notes, self.now_ts()),
        )
        self._conn.commit()
        cur = self._conn.execute("select id, kind, job from jobs order by id desc limit 1")
        row = cur.fetchone()
        return {"id": f"{row['kind']}-{row['id']}", "job": row["job"], "notes": notes}

    def dequeue_job(self, kind: str = "train") -> dict | None:
        if getattr(self, "_pg", None):
            return self._pg.dequeue_job(kind=kind)

        cur = self._conn.execute(
            "select id, kind, job, notes from jobs where status='queued' and kind=? order by id asc limit 1", (kind,)
        )
        row = cur.fetchone()
        if not row:
            return None
        self._conn.execute("update jobs set status='running', ts_started=? where id=?", (self.now_ts(), row["id"]))
        self._conn.commit()
        return dict(row)

    def complete_job(self, job_id: int, ok: bool, notes: str | None = None):
        if getattr(self, "_pg", None):
            self._pg.complete_job(job_id=job_id, ok=ok, notes=notes)
            return

        status = "done" if ok else "failed"
        self._conn.execute(
            "update jobs set status=?, ts_finished=?, notes=coalesce(?, notes) where id=?",
            (status, self.now_ts(), notes, job_id),
        )
        self._conn.commit()

    # --- Performance summaries for today ---
    def realized_pnl_today_usd(self) -> float:
        if getattr(self, "_pg", None):
            return self._pg.realized_pnl_today_usd()

        # prefer view if available, fall back to direct aggregate
        try:
            cur = self._conn.execute("select realized_pnl_today_usd from v_realized_pnl_today_usd")
            row = cur.fetchone()
            if row:
                return float(row[0])
        except Exception:
            pass
        try:
            cur = self._conn.execute(
                "select coalesce(sum(pnl_usd), 0.0) from trades where ts_close >= ?",
                (self._start_of_day_ts(),),
            )
            return float(cur.fetchone()[0] or 0.0)
        except Exception:
            return 0.0

    def trade_count_today(self) -> int:
        if getattr(self, "_pg", None):
            return self._pg.trade_count_today()

        try:
            cur = self._conn.execute("select trade_count_today from v_trade_count_today")
            row = cur.fetchone()
            if row:
                return int(row[0])
        except Exception:
            pass
        try:
            cur = self._conn.execute(
                "select count(1) from trades where ts_close >= ?",
                (self._start_of_day_ts(),),
            )
            return int(cur.fetchone()[0] or 0)
        except Exception:
            return 0

    # --- Helpers and bootstrap ---
    def _ensure_minimal_schema(self):
        self._conn.executescript(
            """
            create table if not exists trades(
              id integer primary key autoincrement,
              ts_open integer,
              ts_close integer,
              symbol text,
              side text,
              qty real,
              entry real,
              exit real,
              pnl_usd real,
              return_pct real,
              fee_usd real,
              slippage_bps real,
              note text
            );
            create table if not exists jobs(
              id integer primary key autoincrement,
              kind text not null,
              job text not null,
              notes text,
              status text not null default 'queued',
              ts_created integer,
              ts_started integer,
              ts_finished integer
            );
            """
        )
        self._conn.commit()

    def _start_of_day_ts(self) -> int:
        import datetime, time

        dt = datetime.datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        return int(time.mktime(dt.timetuple()))


def save_equity_snapshot(equity: float, ts: int | None = None):
    init_db()
    if ts is None:
        ts = int(time.time())
    conn = _get_conn()
    cur = conn.cursor()
    cur.execute("INSERT OR REPLACE INTO equity_snapshots(ts,equity) VALUES(?,?)", (int(ts), float(equity)))
    conn.commit()
    conn.close()


def load_last_equity() -> float | None:
    init_db()
    conn = _get_conn()
    cur = conn.cursor()
    try:
        cur.execute("SELECT equity FROM equity_snapshots ORDER BY ts DESC LIMIT 1")
    except sqlite3.OperationalError:
        # legacy DB without table; treat as empty
        conn.close()
        return None
    row = cur.fetchone()
    conn.close()
    return float(row[0]) if row else None


def load_equity_series(limit: int | None = None, n: int | None = None) -> list[tuple[int, float]]:
    """
    Return up to `limit` (or `n`) points of (ts, equity) ordered ascending.
    Accepts either `limit` or legacy `n` for compatibility.
    """
    init_db()
    eff = int(limit if limit is not None else (n if n is not None else 200))
    conn = _get_conn()
    cur = conn.cursor()
    try:
        cur.execute("SELECT ts, equity FROM equity_snapshots ORDER BY ts DESC LIMIT ?", (eff,))
    except sqlite3.OperationalError:
        # Table missing; return empty series
        conn.close()
        return []
    rows = cur.fetchall()
    conn.close()
    out = []
    for ts, eq in rows:
        try:
            ts_i = int(ts) if ts is not None else 0
        except Exception:
            ts_i = 0
        try:
            eq_f = float(eq) if eq is not None else 0.0
        except Exception:
            eq_f = 0.0
        out.append((ts_i, eq_f))
    return list(reversed(out))


# --- Decision log helpers ---
def save_decision_row(row: Dict[str, Any]) -> None:
    """
    Insert a single decision row.
    Expected keys: ts, symbol, strategy, regime, signal, intent, size_usd, price,
                   ml_p_up, ml_vote, veto, reasons, planned_stop, planned_tp, run_id
    """
    init_db()
    with _get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO decision_log
            (ts,symbol,strategy,regime,signal,intent,size_usd,price,ml_p_up,ml_vote,veto,reasons,planned_stop,planned_tp,run_id)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                int(row.get("ts")),
                row.get("symbol"),
                row.get("strategy"),
                row.get("regime"),
                row.get("signal"),
                row.get("intent"),
                None if row.get("size_usd") is None else float(row.get("size_usd")),
                None if row.get("price") is None else float(row.get("price")),
                None if row.get("ml_p_up") is None else float(row.get("ml_p_up")),
                row.get("ml_vote"),
                1 if row.get("veto") else 0,
                row.get("reasons"),
                None if row.get("planned_stop") is None else float(row.get("planned_stop")),
                None if row.get("planned_tp") is None else float(row.get("planned_tp")),
                row.get("run_id"),
            ),
        )
        conn.commit()


# --- Risk veto logging helpers ---
def ensure_veto_table() -> None:
    with _get_conn() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS risk_veto_log(
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              ts TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
              run_id TEXT,
              symbol TEXT,
              side TEXT,
              qty REAL,
              notional REAL,
              reason TEXT,
              details TEXT
            )
            """
        )
        conn.commit()


def insert_veto_log(payload: Dict[str, Any]) -> None:
    ensure_veto_table()
    run_id = os.getenv("RUN_ID") or ""
    with _get_conn() as conn:
        conn.execute(
            """
            INSERT INTO risk_veto_log(run_id, symbol, side, qty, notional, reason, details)
            VALUES(?,?,?,?,?,?,?)
            """,
            (
                run_id,
                payload.get("symbol"),
                payload.get("side"),
                float(payload.get("qty") or 0.0),
                float(payload.get("notional") or 0.0),
                payload.get("reason"),
                json.dumps(payload.get("details") or {}),
            ),
        )
        conn.commit()


def fetch_recent_decisions(limit: int = 200) -> List[Dict[str, Any]]:
    init_db()
    conn = _get_conn()
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute(
        """
        SELECT ts,symbol,strategy,regime,signal,intent,size_usd,price,ml_p_up,ml_vote,veto,reasons,planned_stop,planned_tp,run_id
        FROM decision_log
        ORDER BY ts DESC
        LIMIT ?
        """,
        (int(limit),),
    )
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


# --- Paper trading helpers ---
def get_cash() -> float:
    """Return current paper cash balance."""
    init_db()
    with _get_conn() as conn:
        cur = conn.cursor()
        cur.execute("SELECT cash FROM paper_account WHERE id=1")
        row = cur.fetchone()
        return float(row[0]) if row else 0.0


def set_cash(new_cash: float) -> None:
    init_db()
    with _get_conn() as conn:
        cur = conn.cursor()
        cur.execute("UPDATE paper_account SET cash=? WHERE id=1", (float(new_cash),))
        conn.commit()


def get_positions() -> Dict[str, Dict[str, float]]:
    """Return dict mapping symbol -> {qty, avg_price}."""
    init_db()
    with _get_conn() as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        try:
            cur.execute("SELECT symbol, qty, avg_price, entry_ts, opened_ts, last_update_ts FROM paper_positions")
        except sqlite3.OperationalError:
            return {}
        out: Dict[str, Dict[str, float]] = {}
        for r in cur.fetchall():
            qty_v = float(r["qty"]) if r["qty"] is not None else 0.0
            avg_v = float(r["avg_price"]) if r["avg_price"] is not None else 0.0
            entry_v = int(r["entry_ts"]) if r["entry_ts"] is not None else None
            opened_v = float(r["opened_ts"]) if r["opened_ts"] is not None else None
            upd_v = float(r["last_update_ts"]) if r["last_update_ts"] is not None else None
            out[r["symbol"]] = {
                "qty": qty_v,
                "avg_price": avg_v,
                "entry_ts": entry_v,
                "opened_ts": opened_v,
                "last_update_ts": upd_v,
            }
        return out


def upsert_position(symbol: str, qty_delta: float, price: float) -> None:
    """Adjust position by qty_delta at execution price; maintain VWAP; delete on zero qty."""
    init_db()
    with _get_conn() as conn:
        cur = conn.cursor()
        cur.execute("SELECT qty, avg_price, entry_ts, opened_ts FROM paper_positions WHERE symbol= ?", (symbol,))
        row = cur.fetchone()
        if row is None:
            if abs(qty_delta) > 0:
                now = time.time()
                cur.execute(
                    "INSERT INTO paper_positions(symbol,qty,avg_price,entry_ts,opened_ts,last_update_ts) VALUES(?,?,?,?,?,strftime('%s','now'))",
                    (symbol, float(qty_delta), float(price), int(now), float(now)),
                )
        else:
            old_qty, old_avg = float(row[0]), float(row[1])
            old_entry_ts = None if row[2] is None else int(row[2])
            new_qty = old_qty + float(qty_delta)
            if abs(new_qty) < 1e-12:
                cur.execute("DELETE FROM paper_positions WHERE symbol= ?", (symbol,))
            elif (old_qty >= 0 and qty_delta >= 0) or (old_qty <= 0 and qty_delta <= 0):
                # increasing same-direction position -> update VWAP
                new_avg = (old_qty * old_avg + float(qty_delta) * float(price)) / new_qty
                cur.execute(
                    "UPDATE paper_positions SET qty=?, avg_price=?, entry_ts=?, last_update_ts=strftime('%s','now') WHERE symbol= ?",
                    (new_qty, new_avg, old_entry_ts if old_entry_ts is not None else int(time.time()), symbol),
                )
            else:
                # reducing or flipping; if flip (sign change), reset avg and entry_ts
                if (old_qty > 0 and new_qty < 0) or (old_qty < 0 and new_qty > 0):
                    now = time.time()
                    cur.execute(
                        "UPDATE paper_positions SET qty=?, avg_price=?, entry_ts=?, opened_ts=?, last_update_ts=strftime('%s','now') WHERE symbol= ?",
                        (new_qty, float(price), int(now), float(now), symbol),
                    )
                else:
                    cur.execute(
                        "UPDATE paper_positions SET qty=?, last_update_ts=strftime('%s','now') WHERE symbol= ?",
                        (new_qty, symbol),
                    )
        conn.commit()


def _table_has_columns(table: str, required: list[str]) -> bool:
    try:
        with _get_conn() as c:
            cur = c.cursor()
            cur.execute(f"PRAGMA table_info({table})")
            cols = {r[1] for r in cur.fetchall()}
            return all(col in cols for col in required)
    except Exception:
        return False


def insert_paper_trade(
    ts: int,
    symbol: str,
    side: str,
    qty: float,
    price: float,
    fees_bps: float,
    slippage_bps: float | None = None,
    run_id: str | None = None,
) -> float:
    """Insert a paper trade and return computed fees. Strict schema enforcement to avoid silent truncation."""
    init_db()
    required = ["ts", "symbol", "side", "qty", "price", "fee_usd", "slippage_bps", "run_id"]
    if not _table_has_columns("paper_trades", required):
        raise RuntimeError("paper_trades schema is outdated. Run migration.")
    notional = float(qty) * float(price)
    fees = abs(notional) * float(fees_bps) / 10000.0
    with _get_conn() as conn:
        cur = conn.cursor()
        try:
            cur.execute(
                """
                INSERT INTO paper_trades(ts, symbol, side, qty, price, fee_usd, slippage_bps, run_id)
                VALUES(?,?,?,?,?,?,?,?)
                """,
                (
                    float(ts),
                    symbol,
                    side.lower(),
                    float(qty),
                    float(price),
                    float(fees),
                    float(slippage_bps or 0.0),
                    str(run_id or ""),
                ),
            )
            conn.commit()
        except Exception as e:
            msg = str(e).lower()
            if "no column" in msg and ("slippage_bps" in msg or "fee_usd" in msg or "run_id" in msg):
                raise RuntimeError("paper_trades schema is outdated. Run migration.") from e
            raise
    return float(fees)


def verify_schema() -> None:
    """Verify required columns exist; raise with actionable message if mismatched."""
    required = {
        "paper_positions": ["qty", "avg_price", "opened_ts", "last_update_ts"],
        "paper_trades": ["ts", "fee_usd", "slippage_bps", "run_id"],
        "paper_account": ["equity", "updated_ts"],
    }
    for table, cols in required.items():
        if not _table_has_columns(table, cols):
            raise RuntimeError(f"Schema check failed: missing columns in {table}. Run migration.")


def mark_to_market(mid_prices: Dict[str, float]) -> Tuple[float, float, float, Dict[str, Dict[str, float]]]:
    """Compute equity, cash, exposure, and return positions; snapshot equity."""
    init_db()
    cash = get_cash()
    positions = get_positions()
    exposure = 0.0
    for sym, pos in positions.items():
        px = mid_prices.get(sym)
        if px is None:
            continue
        exposure += float(pos.get("qty", 0.0)) * float(px)
    equity = float(cash) + float(exposure)
    try:
        save_equity_snapshot(float(equity), int(time.time()))
    except Exception:
        pass
    return float(equity), float(cash), float(exposure), positions
