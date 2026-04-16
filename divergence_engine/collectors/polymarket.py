"""Polymarket data collector using Gamma API and CLOB API."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass

import httpx

from divergence_engine.collectors.base import BaseCollector
from divergence_engine.config import settings
from divergence_engine.storage.models import PricePoint

logger = logging.getLogger(__name__)


@dataclass
class PolymarketEvent:
    """A Polymarket event with its markets."""

    id: str
    slug: str
    title: str
    markets: list[PolymarketMarket]


@dataclass
class PolymarketMarket:
    """A single Polymarket market (binary outcome)."""

    id: str
    question: str
    slug: str
    token_ids: list[str]  # [YES token, NO token]
    outcome_prices: list[float]  # [YES price, NO price]
    volume_24h: float
    active: bool
    closed: bool


class PolymarketCollector(BaseCollector):
    """Collects prediction market data from Polymarket."""

    def __init__(self):
        self._gamma = httpx.Client(
            base_url=settings.gamma_api_url,
            timeout=settings.http_timeout,
        )
        self._clob = httpx.Client(
            base_url=settings.clob_api_url,
            timeout=settings.http_timeout,
        )
        self._market_cache: list[PolymarketMarket] | None = None

    def close(self):
        self._gamma.close()
        self._clob.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    # --- Gamma API: Market discovery ---

    def _fetch_all_active_markets(self, max_pages: int = 10) -> list[PolymarketMarket]:
        """Fetch all active, non-closed markets from Gamma API (paginated)."""
        if self._market_cache is not None:
            return self._market_cache

        all_markets: list[PolymarketMarket] = []
        for offset in range(0, max_pages * 100, 100):
            try:
                resp = self._gamma.get(
                    "/markets",
                    params={
                        "active": "true",
                        "closed": "false",
                        "limit": 100,
                        "offset": offset,
                    },
                )
                resp.raise_for_status()
                data = resp.json()
                if not data:
                    break
                all_markets.extend(self._parse_market(m) for m in data)
            except httpx.HTTPError as exc:
                logger.error("Failed to fetch markets at offset %d: %s", offset, exc)
                break

        self._market_cache = all_markets
        logger.info("Cached %d active markets from Polymarket", len(all_markets))
        return all_markets

    def search_markets(self, keywords: list[str], limit: int = 5) -> list[PolymarketMarket]:
        """Search for markets matching ALL keywords (client-side filtering)."""
        all_markets = self._fetch_all_active_markets()
        lower_keywords = [k.lower() for k in keywords]

        matches = []
        for market in all_markets:
            question_lower = market.question.lower()
            if all(kw in question_lower for kw in lower_keywords):
                if market.token_ids and not market.closed:
                    matches.append(market)

        return matches[:limit]

    def get_market(self, market_id: str) -> PolymarketMarket | None:
        """Fetch a single market by its condition ID."""
        try:
            resp = self._gamma.get(f"/markets/{market_id}")
            resp.raise_for_status()
            return self._parse_market(resp.json())
        except httpx.HTTPError as exc:
            logger.error("Failed to fetch market %s: %s", market_id, exc)
            return None

    # --- CLOB API: Price history ---

    def fetch_history(
        self, token_id: str, start_ts: int, end_ts: int, interval: str = "1h"
    ) -> list[PricePoint]:
        """Fetch price history for a single token."""
        try:
            resp = self._clob.get(
                "/prices-history",
                params={
                    "market": token_id,
                    "startTs": start_ts,
                    "endTs": end_ts,
                    "interval": interval,
                    "fidelity": 60,
                },
            )
            resp.raise_for_status()
            data = resp.json()
            history = data.get("history", [])
            return [PricePoint(timestamp=int(p["t"]), value=float(p["p"])) for p in history]
        except httpx.HTTPError as exc:
            logger.error("Failed to fetch price history for %s: %s", token_id, exc)
            return []

    def fetch_batch_history(
        self,
        token_ids: list[str],
        start_ts: int,
        end_ts: int,
        interval: str = "1h",
    ) -> dict[str, list[PricePoint]]:
        """Fetch price history for multiple tokens in a single call."""
        results: dict[str, list[PricePoint]] = {}

        # CLOB batch endpoint accepts up to 20 markets
        for i in range(0, len(token_ids), 20):
            batch = token_ids[i : i + 20]
            try:
                resp = self._clob.post(
                    "/batch-prices-history",
                    json={
                        "markets": batch,
                        "startTs": start_ts,
                        "endTs": end_ts,
                        "interval": interval,
                        "fidelity": 60,
                    },
                )
                resp.raise_for_status()
                data = resp.json()

                # Response format: {"history": {token_id: [{"t": ts, "p": price}, ...]}}
                history_map = data.get("history", {})
                if isinstance(history_map, list):
                    # Fallback: if single-token-style response
                    history_map = {}

                for tid in batch:
                    points = history_map.get(tid, [])
                    results[tid] = [
                        PricePoint(timestamp=int(p["t"]), value=float(p["p"]))
                        for p in points
                    ]
            except httpx.HTTPError as exc:
                logger.error("Failed to fetch batch history: %s", exc)
                for tid in batch:
                    results[tid] = []

        return results

    def fetch_current(self, token_id: str) -> float | None:
        """Get the current YES probability for a token."""
        now = int(time.time())
        history = self.fetch_history(token_id, now - 3600, now, interval="1h")
        if history:
            return history[-1].value
        return None

    # --- Parsing helpers ---

    def _parse_event(self, data: dict) -> PolymarketEvent:
        markets = [self._parse_market(m) for m in data.get("markets", [])]
        return PolymarketEvent(
            id=str(data.get("id", "")),
            slug=data.get("slug", ""),
            title=data.get("title", ""),
            markets=markets,
        )

    def _parse_market(self, data: dict) -> PolymarketMarket:
        # token_ids and outcome_prices come as JSON strings from the API
        token_ids_raw = data.get("clobTokenIds", "[]")
        prices_raw = data.get("outcomePrices", "[]")

        if isinstance(token_ids_raw, str):
            import json
            token_ids = json.loads(token_ids_raw)
        else:
            token_ids = token_ids_raw or []

        if isinstance(prices_raw, str):
            import json
            prices = [float(p) for p in json.loads(prices_raw)]
        else:
            prices = [float(p) for p in (prices_raw or [])]

        return PolymarketMarket(
            id=str(data.get("id", "")),
            question=data.get("question", ""),
            slug=data.get("slug", data.get("market_slug", "")),
            token_ids=token_ids,
            outcome_prices=prices,
            volume_24h=float(data.get("volume24hr", 0) or 0),
            active=bool(data.get("active", False)),
            closed=bool(data.get("closed", False)),
        )
