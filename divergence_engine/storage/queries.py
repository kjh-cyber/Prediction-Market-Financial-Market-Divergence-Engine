"""Database query functions for the Divergence Engine."""

from __future__ import annotations

import sqlite3
from datetime import datetime

from divergence_engine.storage.models import (
    AssetSnapshot,
    DriftRecord,
    MappingCache,
    PredictionSnapshot,
)


# --- Prediction Snapshots ---


def insert_prediction_snapshot(conn: sqlite3.Connection, snap: PredictionSnapshot) -> None:
    conn.execute(
        """INSERT OR REPLACE INTO prediction_snapshots
           (token_id, event_slug, question, probability, volume_24h, timestamp)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (snap.token_id, snap.event_slug, snap.question, snap.probability,
         snap.volume_24h, snap.timestamp),
    )


def get_prediction_history(
    conn: sqlite3.Connection, token_id: str, since_ts: int
) -> list[PredictionSnapshot]:
    rows = conn.execute(
        """SELECT * FROM prediction_snapshots
           WHERE token_id = ? AND timestamp >= ?
           ORDER BY timestamp ASC""",
        (token_id, since_ts),
    ).fetchall()
    return [PredictionSnapshot.from_row(r) for r in rows]


def get_latest_prediction(
    conn: sqlite3.Connection, token_id: str
) -> PredictionSnapshot | None:
    row = conn.execute(
        """SELECT * FROM prediction_snapshots
           WHERE token_id = ?
           ORDER BY timestamp DESC LIMIT 1""",
        (token_id,),
    ).fetchone()
    return PredictionSnapshot.from_row(row) if row else None


# --- Asset Snapshots ---


def insert_asset_snapshot(conn: sqlite3.Connection, snap: AssetSnapshot) -> None:
    conn.execute(
        """INSERT OR REPLACE INTO asset_snapshots
           (ticker, open_price, high_price, low_price, close_price, volume, timestamp)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (snap.ticker, snap.open_price, snap.high_price, snap.low_price,
         snap.close_price, snap.volume, snap.timestamp),
    )


def get_asset_history(
    conn: sqlite3.Connection, ticker: str, since_ts: int
) -> list[AssetSnapshot]:
    rows = conn.execute(
        """SELECT * FROM asset_snapshots
           WHERE ticker = ? AND timestamp >= ?
           ORDER BY timestamp ASC""",
        (ticker, since_ts),
    ).fetchall()
    return [AssetSnapshot.from_row(r) for r in rows]


def get_latest_asset(conn: sqlite3.Connection, ticker: str) -> AssetSnapshot | None:
    row = conn.execute(
        """SELECT * FROM asset_snapshots
           WHERE ticker = ?
           ORDER BY timestamp DESC LIMIT 1""",
        (ticker,),
    ).fetchone()
    return AssetSnapshot.from_row(row) if row else None


# --- Drift Records ---


def insert_drift_record(conn: sqlite3.Connection, rec: DriftRecord) -> None:
    conn.execute(
        """INSERT INTO drift_records
           (event_slug, token_id, ticker, delta_p, delta_a, delta_a_normalized,
            drift, z_score, signal_type, window_hours, timestamp)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (rec.event_slug, rec.token_id, rec.ticker, rec.delta_p, rec.delta_a,
         rec.delta_a_normalized, rec.drift, rec.z_score, rec.signal_type,
         rec.window_hours, rec.timestamp),
    )


def get_drift_history(
    conn: sqlite3.Connection, event_slug: str, ticker: str, limit: int = 100
) -> list[DriftRecord]:
    rows = conn.execute(
        """SELECT * FROM drift_records
           WHERE event_slug = ? AND ticker = ?
           ORDER BY timestamp DESC LIMIT ?""",
        (event_slug, ticker, limit),
    ).fetchall()
    return [DriftRecord.from_row(r) for r in rows]


def get_top_divergences(
    conn: sqlite3.Connection, limit: int = 10, min_zscore: float = 0.0
) -> list[DriftRecord]:
    # Show only the latest record per (event_slug, ticker) pair
    rows = conn.execute(
        """SELECT d.* FROM drift_records d
           INNER JOIN (
               SELECT event_slug, ticker, MAX(timestamp) AS max_ts
               FROM drift_records
               GROUP BY event_slug, ticker
           ) latest ON d.event_slug = latest.event_slug
                    AND d.ticker = latest.ticker
                    AND d.timestamp = latest.max_ts
           WHERE (ABS(d.z_score) >= ? OR d.z_score IS NULL)
           ORDER BY ABS(COALESCE(d.z_score, 0)) DESC, ABS(d.drift) DESC
           LIMIT ?""",
        (min_zscore, limit),
    ).fetchall()
    return [DriftRecord.from_row(r) for r in rows]


def get_recent_drift_values(
    conn: sqlite3.Connection, event_slug: str, ticker: str, window_hours: int, limit: int = 50
) -> list[float]:
    """Get recent drift values for z-score calculation."""
    rows = conn.execute(
        """SELECT drift FROM drift_records
           WHERE event_slug = ? AND ticker = ? AND window_hours = ?
           ORDER BY timestamp DESC LIMIT ?""",
        (event_slug, ticker, window_hours, limit),
    ).fetchall()
    return [r["drift"] for r in rows]


# --- Mapping Cache ---


def upsert_mapping_cache(conn: sqlite3.Connection, cache: MappingCache) -> None:
    conn.execute(
        """INSERT OR REPLACE INTO mapping_cache
           (event_slug, token_id, market_id, question, resolved_at)
           VALUES (?, ?, ?, ?, ?)""",
        (cache.event_slug, cache.token_id, cache.market_id,
         cache.question, cache.resolved_at),
    )


def get_cached_mapping(conn: sqlite3.Connection, event_slug: str) -> MappingCache | None:
    row = conn.execute(
        "SELECT * FROM mapping_cache WHERE event_slug = ?",
        (event_slug,),
    ).fetchone()
    if row is None:
        return None
    return MappingCache(
        event_slug=row["event_slug"],
        token_id=row["token_id"],
        market_id=row["market_id"],
        question=row["question"],
        resolved_at=row["resolved_at"],
    )


# --- Collection Runs ---


def start_collection_run(conn: sqlite3.Connection, run_type: str) -> int:
    cursor = conn.execute(
        """INSERT INTO collection_runs (run_type, status, started_at)
           VALUES (?, 'started', ?)""",
        (run_type, datetime.utcnow().isoformat()),
    )
    return cursor.lastrowid


def complete_collection_run(
    conn: sqlite3.Connection, run_id: int, markets: int, errors: int
) -> None:
    conn.execute(
        """UPDATE collection_runs
           SET status = 'completed', markets_processed = ?, errors = ?,
               completed_at = ?
           WHERE id = ?""",
        (markets, errors, datetime.utcnow().isoformat(), run_id),
    )
