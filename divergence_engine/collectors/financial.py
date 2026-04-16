"""Financial market data collector using yfinance."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

import pandas as pd
import yfinance as yf

from divergence_engine.collectors.base import BaseCollector
from divergence_engine.storage.models import AssetSnapshot, PricePoint

logger = logging.getLogger(__name__)


class FinancialCollector(BaseCollector):
    """Collects financial market data via yfinance."""

    def fetch_history(
        self, ticker: str, start_ts: int, end_ts: int, interval: str = "1h"
    ) -> list[PricePoint]:
        """Fetch price history for a ticker."""
        start_dt = datetime.fromtimestamp(start_ts, tz=timezone.utc).strftime("%Y-%m-%d")
        end_dt = datetime.fromtimestamp(end_ts, tz=timezone.utc).strftime("%Y-%m-%d")

        try:
            tk = yf.Ticker(ticker)
            df = tk.history(start=start_dt, end=end_dt, interval=interval)

            if df.empty:
                logger.warning("No data returned for %s", ticker)
                return []

            points = []
            for idx, row in df.iterrows():
                ts = int(idx.timestamp())
                points.append(PricePoint(timestamp=ts, value=float(row["Close"])))
            return points

        except Exception as exc:
            logger.error("Failed to fetch history for %s: %s", ticker, exc)
            return []

    def fetch_current(self, ticker: str) -> float | None:
        """Get the current price for a ticker."""
        try:
            tk = yf.Ticker(ticker)
            info = tk.fast_info
            price = getattr(info, "last_price", None)
            if price is not None:
                return float(price)
            # Fallback: get latest from history
            df = tk.history(period="1d")
            if not df.empty:
                return float(df["Close"].iloc[-1])
            return None
        except Exception as exc:
            logger.error("Failed to fetch current price for %s: %s", ticker, exc)
            return None

    def fetch_batch_snapshots(
        self, tickers: list[str], period: str = "5d", interval: str = "1h"
    ) -> dict[str, list[AssetSnapshot]]:
        """Fetch snapshots for multiple tickers efficiently."""
        results: dict[str, list[AssetSnapshot]] = {}

        if not tickers:
            return results

        try:
            df = yf.download(
                tickers,
                period=period,
                interval=interval,
                group_by="ticker",
                progress=False,
                threads=True,
            )

            if df.empty:
                return results

            for ticker in tickers:
                snapshots = []
                try:
                    if len(tickers) == 1:
                        ticker_df = df
                    else:
                        ticker_df = df[ticker]

                    ticker_df = ticker_df.dropna(subset=["Close"])

                    for idx, row in ticker_df.iterrows():
                        ts = int(idx.timestamp())
                        snapshots.append(AssetSnapshot(
                            id=None,
                            ticker=ticker,
                            open_price=_safe_float(row.get("Open")),
                            high_price=_safe_float(row.get("High")),
                            low_price=_safe_float(row.get("Low")),
                            close_price=float(row["Close"]),
                            volume=_safe_float(row.get("Volume")),
                            timestamp=ts,
                        ))
                except (KeyError, TypeError) as exc:
                    logger.warning("Error processing %s: %s", ticker, exc)

                results[ticker] = snapshots

        except Exception as exc:
            logger.error("Batch download failed: %s", exc)

        return results

    def fetch_snapshots(
        self, ticker: str, period: str = "5d", interval: str = "1h"
    ) -> list[AssetSnapshot]:
        """Fetch snapshots for a single ticker."""
        result = self.fetch_batch_snapshots([ticker], period=period, interval=interval)
        return result.get(ticker, [])


def _safe_float(val) -> float | None:
    if val is None or pd.isna(val):
        return None
    return float(val)
