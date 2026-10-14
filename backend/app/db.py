"""SQLite storage: one row per generation, plus key and credit snapshots."""
import sqlite3
from contextlib import contextmanager

from .config import DATA_DIR, DB_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS generations (
    id                TEXT PRIMARY KEY,
    ts                INTEGER NOT NULL,      -- creation time, unix seconds (UTC)
    model             TEXT,
    api_key           TEXT,                  -- key name as reported by the analytics API
    provider          TEXT,
    app               TEXT,
    user              TEXT,
    user_email        TEXT,
    finish_reason     TEXT,
    origin            TEXT,
    streamed          INTEGER,
    requests          INTEGER,
    cost              REAL,                  -- total_usage, USD
    byok_cost         REAL,
    cost_upstream     REAL,
    cost_cache        REAL,
    cost_web          REAL,
    cost_file         REAL,
    cost_data         REAL,
    tokens_total      INTEGER,
    tokens_prompt     INTEGER,
    tokens_completion INTEGER,
    tokens_reasoning  INTEGER,
    tokens_cached     INTEGER,
    latency_ms        REAL,
    ttft_ms           REAL,
    gen_time_ms       REAL,
    throughput        REAL,
    updated_at        INTEGER
);
CREATE INDEX IF NOT EXISTS idx_gen_ts ON generations(ts);
CREATE INDEX IF NOT EXISTS idx_gen_key_ts ON generations(api_key, ts);
CREATE INDEX IF NOT EXISTS idx_gen_model_ts ON generations(model, ts);

CREATE TABLE IF NOT EXISTS api_keys (
    hash                  TEXT PRIMARY KEY,
    name                  TEXT,
    label                 TEXT,
    disabled              INTEGER,
    limit_usd             REAL,
    limit_remaining       REAL,
    limit_reset           TEXT,
    include_byok_in_limit INTEGER,
    usage                 REAL,
    usage_daily           REAL,
    usage_weekly          REAL,
    usage_monthly         REAL,
    byok_usage            REAL,
    created_at            TEXT,
    updated_at            TEXT,
    expires_at            TEXT,
    last_used_at          TEXT,
    workspace_id          TEXT,
    present               INTEGER,           -- 0 once the key no longer exists on OpenRouter
    seen_at               INTEGER
);

CREATE TABLE IF NOT EXISTS credit_snapshots (
    ts            INTEGER PRIMARY KEY,
    total_credits REAL,
    total_usage   REAL
);

CREATE TABLE IF NOT EXISTS sync_state (
    k TEXT PRIMARY KEY,
    v TEXT
);
"""


def connect(check_same_thread: bool = True) -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=30, check_same_thread=check_same_thread)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout=30000")
    return conn


@contextmanager
def session():
    """Connection that commits on success, rolls back on error, and always closes."""
    conn = connect()
    try:
        with conn:
            yield conn
    finally:
        conn.close()


def init() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with session() as conn:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.executescript(SCHEMA)


def get_state(conn: sqlite3.Connection, key: str, default=None):
    row = conn.execute("SELECT v FROM sync_state WHERE k = ?", (key,)).fetchone()
    return row["v"] if row else default


def set_state(conn: sqlite3.Connection, key: str, value) -> None:
    conn.execute(
        "INSERT INTO sync_state (k, v) VALUES (?, ?) ON CONFLICT(k) DO UPDATE SET v = excluded.v",
        (key, None if value is None else str(value)),
    )
