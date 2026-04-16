"""Main pipeline orchestration: collect -> analyze -> output."""

from __future__ import annotations

import logging
import time

from divergence_engine.analysis.drift import compute_full_drift
from divergence_engine.analysis.signals import classify_signal
from divergence_engine.analysis.zscore import calculate_zscore, detect_anomaly
from divergence_engine.collectors.financial import FinancialCollector
from divergence_engine.collectors.polymarket import PolymarketCollector
from divergence_engine.config import settings
from divergence_engine.mappings.definitions import get_all_mappings, get_all_tickers
from divergence_engine.mappings.registry import MappingRegistry, ResolvedMapping
from divergence_engine.storage.database import get_db, init_db
from divergence_engine.storage.models import AssetSnapshot, DriftRecord, PredictionSnapshot
from divergence_engine.storage.queries import (
    get_recent_drift_values,
    insert_asset_snapshot,
    insert_drift_record,
    insert_prediction_snapshot,
)

logger = logging.getLogger(__name__)


class Pipeline:
    """Orchestrates the full data collection and analysis pipeline."""

    def __init__(self, db_path: str | None = None):
        self.db_path = db_path or settings.db_path
        self.poly_collector = PolymarketCollector()
        self.fin_collector = FinancialCollector()
        self.registry = MappingRegistry(self.poly_collector, self.db_path)

    def initialize(self) -> None:
        """Initialize the database."""
        init_db(self.db_path)

    def resolve_mappings(self, force: bool = False) -> list[ResolvedMapping]:
        """Resolve all event-asset mappings to Polymarket tokens."""
        return self.registry.resolve_all(force=force)

    def collect(self, resolved: list[ResolvedMapping]) -> dict:
        """Run data collection for all resolved mappings.

        Returns stats: {pred_count, asset_count, errors}
        """
        stats = {"pred_count": 0, "asset_count": 0, "errors": 0}
        now = int(time.time())
        lookback = settings.default_window_hours * 3600 * 7  # 7x window for history
        start_ts = now - lookback

        # --- Collect Polymarket data (individual fetches for reliability) ---
        seen_tokens: set[str] = set()
        with get_db(self.db_path) as conn:
            for rm in resolved:
                if rm.token_id in seen_tokens:
                    continue
                seen_tokens.add(rm.token_id)

                history = self.poly_collector.fetch_history(
                    rm.token_id, start_ts, now, interval="1h"
                )
                for point in history:
                    snap = PredictionSnapshot(
                        id=None,
                        token_id=rm.token_id,
                        event_slug=rm.mapping.event_slug,
                        question=rm.question,
                        probability=point.value,
                        volume_24h=0.0,
                        timestamp=point.timestamp,
                    )
                    try:
                        insert_prediction_snapshot(conn, snap)
                        stats["pred_count"] += 1
                    except Exception as exc:
                        logger.debug("Duplicate or error inserting prediction: %s", exc)

        # --- Collect financial data ---
        all_tickers = list(get_all_tickers())
        batch_snapshots = self.fin_collector.fetch_batch_snapshots(
            all_tickers, period="7d", interval="1h"
        )

        with get_db(self.db_path) as conn:
            for ticker, snapshots in batch_snapshots.items():
                for snap in snapshots:
                    try:
                        insert_asset_snapshot(conn, snap)
                        stats["asset_count"] += 1
                    except Exception as exc:
                        logger.debug("Duplicate or error inserting asset: %s", exc)

        return stats

    def analyze(
        self,
        resolved: list[ResolvedMapping],
        window_hours: int | None = None,
    ) -> dict:
        """Run drift analysis for all resolved mappings.

        Returns stats: {total_pairs, anomalies, records}
        """
        window = window_hours or settings.default_window_hours
        now = int(time.time())
        lookback = window * 3600
        start_ts = now - lookback

        stats = {"total_pairs": 0, "anomalies": 0, "records": []}

        with get_db(self.db_path) as conn:
            for rm in resolved:
                for ticker in rm.mapping.asset_tickers:
                    stats["total_pairs"] += 1

                    # Get prediction history
                    from divergence_engine.storage.queries import (
                        get_asset_history,
                        get_prediction_history,
                    )

                    pred_history = get_prediction_history(conn, rm.token_id, start_ts)
                    asset_history = get_asset_history(conn, ticker, start_ts)

                    if len(pred_history) < 2 or len(asset_history) < 2:
                        logger.debug(
                            "Insufficient data for %s / %s (pred=%d, asset=%d)",
                            rm.mapping.event_slug, ticker,
                            len(pred_history), len(asset_history),
                        )
                        continue

                    # Build price point lists
                    from divergence_engine.storage.models import PricePoint

                    prob_points = [
                        PricePoint(timestamp=p.timestamp, value=p.probability)
                        for p in pred_history
                    ]
                    asset_prices = [a.close_price for a in asset_history]

                    # Calculate drift
                    result = compute_full_drift(
                        prob_points, asset_prices,
                        direction=rm.mapping.correlation_direction,
                        window_hours=window,
                    )

                    if result is None:
                        continue

                    # Get historical drift for Z-score
                    past_drifts = get_recent_drift_values(
                        conn, rm.mapping.event_slug, ticker, window, limit=50
                    )
                    z_score = calculate_zscore(result["drift"], past_drifts)
                    is_anomaly = detect_anomaly(z_score, settings.zscore_threshold)

                    if is_anomaly:
                        stats["anomalies"] += 1

                    # Classify signal
                    signal = classify_signal(
                        delta_p=result["delta_p"],
                        delta_a_normalized=result["delta_a_normalized"],
                        drift=result["drift"],
                        z_score=z_score,
                        direction=rm.mapping.correlation_direction,
                    )

                    # Store drift record
                    record = DriftRecord(
                        id=None,
                        event_slug=rm.mapping.event_slug,
                        token_id=rm.token_id,
                        ticker=ticker,
                        delta_p=result["delta_p"],
                        delta_a=result["delta_a"],
                        delta_a_normalized=result["delta_a_normalized"],
                        drift=result["drift"],
                        z_score=z_score,
                        signal_type=signal.signal_type.value,
                        window_hours=window,
                        timestamp=now,
                    )

                    insert_drift_record(conn, record)
                    stats["records"].append(record)

        return stats

    def close(self):
        self.poly_collector.close()
