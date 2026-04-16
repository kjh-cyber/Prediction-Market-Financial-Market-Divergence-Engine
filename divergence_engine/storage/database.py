"""SQLite database management for the Divergence Engine."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path

from divergence_engine.config import settings

SCHEMA = """
CREATE TABLE IF NOT EXISTS prediction_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    token_id TEXT NOT NULL,
    event_slug TEXT NOT NULL,
    question TEXT,
    probability REAL NOT NULL,
    volume_24h REAL,
    timestamp INTEGER NOT NULL,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(token_id, timestamp)
);

CREATE INDEX IF NOT EXISTS idx_pred_token_ts
    ON prediction_snapshots(token_id, timestamp);

CREATE TABLE IF NOT EXISTS asset_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker TEXT NOT NULL,
    open_price REAL,
    high_price REAL,
    low_price REAL,
    close_price REAL NOT NULL,
    volume REAL,
    timestamp INTEGER NOT NULL,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(ticker, timestamp)
);

CREATE INDEX IF NOT EXISTS idx_asset_ticker_ts
    ON asset_snapshots(ticker, timestamp);

CREATE TABLE IF NOT EXISTS drift_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_slug TEXT NOT NULL,
    token_id TEXT NOT NULL,
    ticker TEXT NOT NULL,
    delta_p REAL NOT NULL,
    delta_a REAL NOT NULL,
    delta_a_normalized REAL NOT NULL,
    drift REAL NOT NULL,
    z_score REAL,
    signal_type TEXT NOT NULL,
    window_hours INTEGER NOT NULL,
    timestamp INTEGER NOT NULL,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_drift_event_ts
    ON drift_records(event_slug, timestamp);
CREATE INDEX IF NOT EXISTS idx_drift_zscore
    ON drift_records(z_score DESC);

CREATE TABLE IF NOT EXISTS mapping_cache (
    event_slug TEXT PRIMARY KEY,
    token_id TEXT NOT NULL,
    market_id TEXT,
    question TEXT,
    resolved_at INTEGER NOT NULL,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS collection_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_type TEXT NOT NULL,
    status TEXT NOT NULL,
    markets_processed INTEGER DEFAULT 0,
    errors INTEGER DEFAULT 0,
    started_at TEXT NOT NULL,
    completed_at TEXT
);
"""


def _ensure_data_dir(db_path: str) -> None:
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)


def get_connection(db_path: str | None = None) -> sqlite3.Connection:
    """Create a new database connection."""
    path = db_path or settings.db_path
    _ensure_data_dir(path)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


@contextmanager
def get_db(db_path: str | None = None):
    """Context manager for database connections."""
    conn = get_connection(db_path)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db(db_path: str | None = None) -> None:
    """Initialize database schema."""
    with get_db(db_path) as conn:
        conn.executescript(SCHEMA)
