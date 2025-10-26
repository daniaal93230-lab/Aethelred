DB module

SQLite-based persistence helpers and simple schema management.

Key files:
- `db/db_manager.py` — connection helpers, schema initialization, and `save_decision_row`.
- `db/models.py` — data model helpers (if present).

If you need an export, use `scripts/export_db.py` or `scripts/dump_db_exports.py`.
