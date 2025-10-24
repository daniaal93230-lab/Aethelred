from db.db_manager import _get_conn


def _ensure_table_defaults(c) -> None:
    c.execute(
        """
                CREATE TABLE IF NOT EXISTS risk_state (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
    )
    # seed defaults
    c.execute(
        """
                INSERT OR IGNORE INTO risk_state(key, value) VALUES
                    ('kill_switch', 'off'),
                    ('daily_loss_breaker', 'off'),
                    ('heartbeat_misses', '0'),
                    ('run_id', 'INIT')
                """
    )


class RiskKV:
    def get(self, key: str, default: str = "") -> str:
        with _get_conn() as c:
            _ensure_table_defaults(c)
            row = c.execute("select value from risk_state where key=?;", (key,)).fetchone()
            return row[0] if row else default

    def set(self, key: str, value: str):
        with _get_conn() as c:
            _ensure_table_defaults(c)
            c.execute(
                """
                insert into risk_state(key,value) values(?,?)
                on conflict(key) do update set value=excluded.value, updated_at=current_timestamp;
                """,
                (key, value),
            )
            c.commit()
