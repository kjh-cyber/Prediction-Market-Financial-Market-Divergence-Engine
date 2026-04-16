"""Event-to-financial-indicator mapping definitions.

Each mapping connects a Polymarket event to MULTIPLE financial indicators
across different asset classes (equities, bonds, commodities, forex, crypto, volatility).

The engine uses financial market signals to detect Polymarket entry opportunities:
when financial indicators move but Polymarket probability hasn't adjusted yet.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class EventAssetMapping:
    """A mapping from a prediction market event to financial indicators."""

    event_slug: str
    search_keywords: list[str] = field(default_factory=list)
    description: str = ""
    asset_tickers: list[str] = field(default_factory=list)
    correlation_direction: str = "positive"  # "positive" or "inverse"
    weight: float = 1.0
    category: str = "general"


# ============================================================
# yfinance ticker reference:
#   Stocks/ETFs : SPY, QQQ, TLT, ...
#   Bonds/Rates : ^TNX (10Y yield), ^TYX (30Y), ^FVX (5Y)
#   Commodities : GC=F (gold), CL=F (oil), SI=F (silver), HG=F (copper)
#   Forex       : DX-Y.NYB (DXY), EURUSD=X, USDJPY=X, USDCNY=X
#   Crypto      : BTC-USD, ETH-USD
#   Volatility  : ^VIX
#   Yield Curve : calculated from ^TNX - ^IRX (10Y - 3M)
# ============================================================

MAPPINGS: list[EventAssetMapping] = [

    # ===== MONETARY POLICY =====
    EventAssetMapping(
        event_slug="fed-rate-cut-2026",
        search_keywords=["fed", "rate", "cut", "2026"],
        description="Fed rate cuts in 2026",
        asset_tickers=[
            "TLT",        # 장기채 ETF (금리 인하 → 가격 상승)
            "IEF",        # 중기채 ETF
            "^TNX",       # 10년물 금리 (인하 기대 → 금리 하락)
            "DX-Y.NYB",   # 달러인덱스 (인하 → 달러 약세)
            "GC=F",       # 금 (인하 → 금 상승)
        ],
        correlation_direction="positive",
        weight=0.9,
        category="monetary_policy",
    ),
    EventAssetMapping(
        event_slug="fed-no-rate-cut-2026",
        search_keywords=["no", "fed", "rate", "cut", "2026"],
        description="No Fed rate cuts in 2026",
        asset_tickers=[
            "^TNX",       # 10년물 금리 (인하 없음 → 금리 유지/상승)
            "TLT",        # 장기채 (인하 없음 → 하락)
            "DX-Y.NYB",   # 달러인덱스 (인하 없음 → 달러 강세)
        ],
        correlation_direction="positive",
        weight=0.9,
        category="monetary_policy",
    ),
    EventAssetMapping(
        event_slug="fed-1-rate-cut-2026",
        search_keywords=["1", "fed", "rate", "cut", "2026"],
        description="Exactly 1 Fed rate cut in 2026",
        asset_tickers=["TLT", "IEF", "^TNX"],
        correlation_direction="positive",
        weight=0.8,
        category="monetary_policy",
    ),

    # ===== MACRO / RECESSION =====
    EventAssetMapping(
        event_slug="us-recession-2026",
        search_keywords=["recession", "2026"],
        description="US recession by end of 2026",
        asset_tickers=[
            "SPY",        # S&P 500 (침체 → 하락)
            "QQQ",        # 나스닥 (침체 → 하락)
            "^VIX",       # 공포지수 (침체 우려 → 상승)
            "TLT",        # 장기채 (안전자산 → 상승)
            "GC=F",       # 금 (안전자산 → 상승)
            "HG=F",       # 구리 (경기 바로미터 → 하락)
            "XLF",        # 금융 섹터 (침체 → 하락)
        ],
        correlation_direction="inverse",
        weight=0.95,
        category="macro",
    ),

    # ===== US POLITICS =====
    EventAssetMapping(
        event_slug="trump-2028-election",
        search_keywords=["trump", "2028", "presidential"],
        description="Trump winning 2028 US Presidential Election",
        asset_tickers=[
            "DJT",        # Trump Media
            "GEO",        # 민영 교도소 (트럼프 수혜주)
            "SPY",        # 시장 전반
            "XLE",        # 에너지 섹터 (규제 완화 기대)
        ],
        correlation_direction="positive",
        weight=0.7,
        category="politics",
    ),
    EventAssetMapping(
        event_slug="trump-out-president",
        search_keywords=["trump", "out", "president"],
        description="Trump leaving presidency",
        asset_tickers=[
            "DJT",        # Trump Media (직격탄)
            "SPY",        # 시장 불확실성
            "^VIX",       # 변동성 급등
            "GC=F",       # 금 (안전자산 수요)
        ],
        correlation_direction="inverse",
        weight=0.7,
        category="politics",
    ),
    EventAssetMapping(
        event_slug="macron-out",
        search_keywords=["macron", "out"],
        description="Macron leaving office",
        asset_tickers=[
            "EWQ",        # France ETF
            "VGK",        # Europe ETF
            "EURUSD=X",   # 유로/달러 환율
        ],
        correlation_direction="inverse",
        weight=0.6,
        category="politics",
    ),

    # ===== CRYPTO =====
    EventAssetMapping(
        event_slug="btc-150k",
        search_keywords=["bitcoin", "150k"],
        description="Bitcoin reaching $150K",
        asset_tickers=[
            "BTC-USD",    # 비트코인 현물 (가장 직접적)
            "IBIT",       # BTC ETF
            "MSTR",       # MicroStrategy
            "COIN",       # Coinbase
        ],
        correlation_direction="positive",
        weight=0.95,
        category="crypto",
    ),
    EventAssetMapping(
        event_slug="btc-1m",
        search_keywords=["bitcoin", "1m"],
        description="Bitcoin reaching $1M",
        asset_tickers=["BTC-USD", "IBIT", "MSTR"],
        correlation_direction="positive",
        weight=0.5,
        category="crypto",
    ),
    EventAssetMapping(
        event_slug="microstrategy-sell-btc",
        search_keywords=["microstrategy", "bitcoin"],
        description="MicroStrategy selling Bitcoin",
        asset_tickers=[
            "MSTR",       # MicroStrategy (직접)
            "BTC-USD",    # BTC 매도 압력
            "IBIT",       # BTC ETF
        ],
        correlation_direction="inverse",
        weight=0.8,
        category="crypto",
    ),
    EventAssetMapping(
        event_slug="kraken-ipo",
        search_keywords=["kraken", "ipo"],
        description="Kraken IPO timing",
        asset_tickers=["COIN", "BTC-USD"],
        correlation_direction="positive",
        weight=0.7,
        category="crypto",
    ),

    # ===== GEOPOLITICS =====
    EventAssetMapping(
        event_slug="china-invade-taiwan-2026",
        search_keywords=["china", "invade", "taiwan", "2026"],
        description="China invading Taiwan by end of 2026",
        asset_tickers=[
            "TSM",        # TSMC (직격탄)
            "SMH",        # 반도체 ETF
            "EWY",        # 한국 ETF (지정학 리스크)
            "USDCNY=X",   # 위안화 (침공 → 위안화 약세)
            "GC=F",       # 금 (지정학 리스크 → 상승)
            "CL=F",       # 유가 (공급망 불안 → 상승)
            "^VIX",       # 공포지수
        ],
        correlation_direction="inverse",
        weight=0.85,
        category="geopolitics",
    ),
    EventAssetMapping(
        event_slug="russia-ukraine-ceasefire-2026",
        search_keywords=["russia", "ukraine", "ceasefire", "2026"],
        description="Russia-Ukraine ceasefire by end of 2026",
        asset_tickers=[
            "VGK",        # 유럽 ETF (평화 → 상승)
            "EWG",        # 독일 ETF (에너지 안정)
            "CL=F",       # 유가 (평화 → 하락)
            "EURUSD=X",   # 유로 (평화 → 유로 강세)
        ],
        correlation_direction="positive",
        weight=0.7,
        category="geopolitics",
    ),
    EventAssetMapping(
        event_slug="trump-putin-meet-japan",
        search_keywords=["trump", "putin", "japan"],
        description="Trump-Putin meeting in Japan",
        asset_tickers=[
            "EWJ",        # 일본 ETF
            "USDJPY=X",   # 엔/달러
            "GC=F",       # 금 (지정학 이벤트)
        ],
        correlation_direction="positive",
        weight=0.5,
        category="geopolitics",
    ),
    EventAssetMapping(
        event_slug="ceasefire-before-gta",
        search_keywords=["ceasefire", "gta"],
        description="Russia-Ukraine ceasefire before GTA VI",
        asset_tickers=["VGK", "CL=F", "EURUSD=X"],
        correlation_direction="positive",
        weight=0.5,
        category="geopolitics",
    ),
    EventAssetMapping(
        event_slug="china-taiwan-before-gta",
        search_keywords=["china", "taiwan", "gta"],
        description="China invading Taiwan before GTA VI",
        asset_tickers=["TSM", "SMH", "^VIX", "GC=F"],
        correlation_direction="inverse",
        weight=0.5,
        category="geopolitics",
    ),

    # ===== TECH / M&A =====
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

    # ===== LEGAL =====
    EventAssetMapping(
        event_slug="weinstein-prison",
        search_keywords=["weinstein", "prison"],
        description="Harvey Weinstein sentencing",
        asset_tickers=["DIS"],
        correlation_direction="inverse",
        weight=0.4,
        category="politics",
    ),
]


def get_all_mappings() -> list[EventAssetMapping]:
    return MAPPINGS.copy()


def get_mappings_by_category(category: str) -> list[EventAssetMapping]:
    return [m for m in MAPPINGS if m.category == category]


def get_mapping_by_slug(slug: str) -> EventAssetMapping | None:
    for m in MAPPINGS:
        if m.event_slug == slug:
            return m
    return None


def get_all_tickers() -> set[str]:
    tickers: set[str] = set()
    for m in MAPPINGS:
        tickers.update(m.asset_tickers)
    return tickers
