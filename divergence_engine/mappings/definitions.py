"""Manual event-to-asset mapping definitions.

Each mapping connects a Polymarket event to related financial assets.
search_keywords are used for client-side filtering of Polymarket markets.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class EventAssetMapping:
    """A mapping from a prediction market event to financial assets."""

    event_slug: str  # Unique identifier for this mapping
    search_keywords: list[str] = field(default_factory=list)  # ALL must match (case-insensitive)
    description: str = ""
    asset_tickers: list[str] = field(default_factory=list)
    correlation_direction: str = "positive"  # "positive" or "inverse"
    weight: float = 1.0  # Confidence weight (0-1)
    category: str = "general"


# --- MVP Mapping Definitions (20 mappings) ---
# Keywords are based on actual active Polymarket market questions.

MAPPINGS: list[EventAssetMapping] = [
    # --- Monetary Policy ---
    EventAssetMapping(
        event_slug="fed-rate-cut-2026",
        search_keywords=["fed", "rate", "cut", "2026"],
        description="Fed rate cuts in 2026",
        asset_tickers=["TLT", "IEF", "SHY"],
        correlation_direction="positive",
        weight=0.9,
        category="monetary_policy",
    ),
    EventAssetMapping(
        event_slug="fed-no-rate-cut-2026",
        search_keywords=["no", "fed", "rate", "cut", "2026"],
        description="No Fed rate cuts in 2026",
        asset_tickers=["TLT", "IEF"],
        correlation_direction="inverse",
        weight=0.9,
        category="monetary_policy",
    ),

    # --- US Politics ---
    EventAssetMapping(
        event_slug="trump-2028-election",
        search_keywords=["trump", "2028", "presidential"],
        description="Trump winning 2028 US Presidential Election",
        asset_tickers=["DJT", "GEO", "SPY"],
        correlation_direction="positive",
        weight=0.7,
        category="politics",
    ),
    EventAssetMapping(
        event_slug="trump-out-president",
        search_keywords=["trump", "out", "president"],
        description="Trump leaving presidency",
        asset_tickers=["SPY", "QQQ", "DJT"],
        correlation_direction="inverse",
        weight=0.7,
        category="politics",
    ),

    # --- Macro ---
    EventAssetMapping(
        event_slug="us-recession-2026",
        search_keywords=["recession", "2026"],
        description="US recession by end of 2026",
        asset_tickers=["SPY", "QQQ", "TLT", "GLD"],
        correlation_direction="inverse",
        weight=0.9,
        category="macro",
    ),

    # --- Crypto ---
    EventAssetMapping(
        event_slug="btc-150k",
        search_keywords=["bitcoin", "150k"],
        description="Bitcoin reaching $150K",
        asset_tickers=["IBIT", "MSTR", "COIN"],
        correlation_direction="positive",
        weight=0.9,
        category="crypto",
    ),
    EventAssetMapping(
        event_slug="btc-1m",
        search_keywords=["bitcoin", "1m"],
        description="Bitcoin reaching $1M",
        asset_tickers=["IBIT", "MSTR", "COIN"],
        correlation_direction="positive",
        weight=0.5,
        category="crypto",
    ),
    EventAssetMapping(
        event_slug="kraken-ipo",
        search_keywords=["kraken", "ipo"],
        description="Kraken IPO timing",
        asset_tickers=["COIN", "IBIT"],
        correlation_direction="positive",
        weight=0.7,
        category="crypto",
    ),

    # --- Geopolitics ---
    EventAssetMapping(
        event_slug="china-invade-taiwan-2026",
        search_keywords=["china", "invade", "taiwan", "2026"],
        description="China invading Taiwan by end of 2026",
        asset_tickers=["TSM", "SMH", "AAPL", "EWY"],
        correlation_direction="inverse",
        weight=0.8,
        category="geopolitics",
    ),
    EventAssetMapping(
        event_slug="russia-ukraine-ceasefire-2026",
        search_keywords=["russia", "ukraine", "ceasefire", "2026"],
        description="Russia-Ukraine ceasefire by end of 2026",
        asset_tickers=["EWP", "VGK", "EWG"],
        correlation_direction="positive",
        weight=0.7,
        category="geopolitics",
    ),

    # --- Tech ---
    EventAssetMapping(
        event_slug="applovin-acquire-tiktok",
        search_keywords=["applovin", "tiktok"],
        description="AppLovin acquiring TikTok",
        asset_tickers=["APP", "META", "SNAP"],
        correlation_direction="positive",
        weight=0.7,
        category="tech",
    ),
    EventAssetMapping(
        event_slug="microsoft-acquire-tiktok",
        search_keywords=["microsoft", "tiktok"],
        description="Microsoft acquiring TikTok",
        asset_tickers=["MSFT", "META", "SNAP"],
        correlation_direction="positive",
        weight=0.7,
        category="tech",
    ),
    EventAssetMapping(
        event_slug="gta-vi-release",
        search_keywords=["gta", "vi", "released", "june"],
        description="GTA VI released before June 2026",
        asset_tickers=["TTWO"],
        correlation_direction="positive",
        weight=0.8,
        category="tech",
    ),

    # --- Legal/Political ---
    EventAssetMapping(
        event_slug="weinstein-prison",
        search_keywords=["weinstein", "prison"],
        description="Harvey Weinstein sentencing",
        asset_tickers=["DIS"],
        correlation_direction="inverse",
        weight=0.4,
        category="politics",
    ),
    EventAssetMapping(
        event_slug="macron-out",
        search_keywords=["macron", "out"],
        description="Macron leaving office",
        asset_tickers=["EWQ", "VGK"],
        correlation_direction="inverse",
        weight=0.6,
        category="politics",
    ),

    # --- Market/Economic ---
    EventAssetMapping(
        event_slug="trump-putin-meet-japan",
        search_keywords=["trump", "putin", "japan"],
        description="Trump-Putin meeting in Japan",
        asset_tickers=["EWJ", "SPY", "GLD"],
        correlation_direction="positive",
        weight=0.5,
        category="geopolitics",
    ),

    # --- General catch-all for popular events ---
    EventAssetMapping(
        event_slug="ceasefire-before-gta",
        search_keywords=["ceasefire", "gta"],
        description="Russia-Ukraine ceasefire before GTA VI",
        asset_tickers=["EWP", "VGK"],
        correlation_direction="positive",
        weight=0.5,
        category="geopolitics",
    ),
    EventAssetMapping(
        event_slug="china-taiwan-before-gta",
        search_keywords=["china", "taiwan", "gta"],
        description="China invading Taiwan before GTA VI",
        asset_tickers=["TSM", "SMH"],
        correlation_direction="inverse",
        weight=0.5,
        category="geopolitics",
    ),
    EventAssetMapping(
        event_slug="microstrategy-sell-btc",
        search_keywords=["microstrategy", "bitcoin"],
        description="MicroStrategy selling Bitcoin",
        asset_tickers=["MSTR", "IBIT", "COIN"],
        correlation_direction="inverse",
        weight=0.8,
        category="crypto",
    ),
    EventAssetMapping(
        event_slug="fed-1-rate-cut-2026",
        search_keywords=["1", "fed", "rate", "cut", "2026"],
        description="Exactly 1 Fed rate cut in 2026",
        asset_tickers=["TLT", "IEF"],
        correlation_direction="positive",
        weight=0.8,
        category="monetary_policy",
    ),
]


def get_all_mappings() -> list[EventAssetMapping]:
    """Return all configured event-asset mappings."""
    return MAPPINGS.copy()


def get_mappings_by_category(category: str) -> list[EventAssetMapping]:
    """Return mappings filtered by category."""
    return [m for m in MAPPINGS if m.category == category]


def get_mapping_by_slug(slug: str) -> EventAssetMapping | None:
    """Return a mapping by its event slug."""
    for m in MAPPINGS:
        if m.event_slug == slug:
            return m
    return None


def get_all_tickers() -> set[str]:
    """Return all unique asset tickers across all mappings."""
    tickers: set[str] = set()
    for m in MAPPINGS:
        tickers.update(m.asset_tickers)
    return tickers
