CREATE TABLE IF NOT EXISTS trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,      -- internal unique id
    trade_id TEXT UNIQUE,                       -- exchange or internal trade unique ID
    timestamp TEXT DEFAULT (datetime('now')),  -- UTC timestamp (auto default)
    symbol TEXT NOT NULL,                       -- trading pair
    side TEXT CHECK(side IN ('buy', 'sell')) NOT NULL,  -- buy or sell only
    price REAL NOT NULL,                        -- executed price
    amount REAL NOT NULL,                       -- trade quantity (base asset)
    status TEXT NOT NULL DEFAULT 'filled',     -- trade status
    is_mock INTEGER NOT NULL DEFAULT 0         -- flag for mock trades (0 or 1)
);