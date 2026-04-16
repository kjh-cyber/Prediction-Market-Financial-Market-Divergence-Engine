"""Mapping registry: resolves event slugs to Polymarket token IDs."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass

from divergence_engine.collectors.polymarket import PolymarketCollector
from divergence_engine.mappings.definitions import EventAssetMapping, get_all_mappings
from divergence_engine.storage.database import get_db
from divergence_engine.storage.models import MappingCache
from divergence_engine.storage.queries import get_cached_mapping, upsert_mapping_cache

logger = logging.getLogger(__name__)

# Cache validity: 24 hours
CACHE_TTL = 86400


@dataclass
class ResolvedMapping:
    """A mapping that has been resolved to actual Polymarket token IDs."""

    mapping: EventAssetMapping
    token_id: str
    market_id: str
    question: str


class MappingRegistry:
    """Resolves and caches event-to-Polymarket-token mappings."""

    def __init__(self, collector: PolymarketCollector, db_path: str | None = None):
        self._collector = collector
        self._db_path = db_path

    def resolve_all(self, force: bool = False) -> list[ResolvedMapping]:
        """Resolve all configured mappings to Polymarket tokens."""
        resolved = []
        mappings = get_all_mappings()

        for mapping in mappings:
            result = self.resolve(mapping, force=force)
            if result:
                resolved.append(result)
            else:
                logger.warning("Could not resolve: %s", mapping.event_slug)

        logger.info("Resolved %d/%d mappings", len(resolved), len(mappings))
        return resolved

    def resolve(
        self, mapping: EventAssetMapping, force: bool = False
    ) -> ResolvedMapping | None:
        """Resolve a single mapping, using cache if available."""
        now = int(time.time())

        # Check cache first
        if not force:
            with get_db(self._db_path) as conn:
                cached = get_cached_mapping(conn, mapping.event_slug)
                if cached and (now - cached.resolved_at) < CACHE_TTL:
                    return ResolvedMapping(
                        mapping=mapping,
                        token_id=cached.token_id,
                        market_id=cached.market_id,
                        question=cached.question,
                    )

        # Search Polymarket for matching markets using client-side keyword filtering
        markets = self._collector.search_markets(mapping.search_keywords, limit=5)

        for market in markets:
            if not market.token_ids:
                continue

            # Use the YES token (first token)
            token_id = market.token_ids[0]

            # Cache the resolution
            cache_entry = MappingCache(
                event_slug=mapping.event_slug,
                token_id=token_id,
                market_id=market.id,
                question=market.question,
                resolved_at=now,
            )
            with get_db(self._db_path) as conn:
                upsert_mapping_cache(conn, cache_entry)

            return ResolvedMapping(
                mapping=mapping,
                token_id=token_id,
                market_id=market.id,
                question=market.question,
            )

        return None
