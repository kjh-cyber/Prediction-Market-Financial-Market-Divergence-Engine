"""Data models for the Divergence Engine."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class PricePoint:
    """A single price/probability point in time."""

    timestamp: int  # unix seconds
    value: float


@dataclass
class PredictionSnapshot:
    """A snapshot of a Polymarket prediction market."""

    id: Optional[int]
    token_id: str
    event_slug: str
    question: str
    probability: float
    volume_24h: float
    timestamp: int

    @classmethod
    def from_row(cls, row) -> PredictionSnapshot:
        return cls(
            id=row["id"],
            token_id=row["token_id"],
            event_slug=row["event_slug"],
            question=row["question"],
            probability=row["probability"],
            volume_24h=row["volume_24h"],
            timestamp=row["timestamp"],
        )


@dataclass
class AssetSnapshot:
    """A snapshot of a financial asset price."""

    id: Optional[int]
    ticker: str
    open_price: Optional[float]
    high_price: Optional[float]
    low_price: Optional[float]
    close_price: float
    volume: Optional[float]
    timestamp: int

    @classmethod
    def from_row(cls, row) -> AssetSnapshot:
        return cls(
            id=row["id"],
            ticker=row["ticker"],
            open_price=row["open_price"],
            high_price=row["high_price"],
            low_price=row["low_price"],
            close_price=row["close_price"],
            volume=row["volume"],
            timestamp=row["timestamp"],
        )


@dataclass
class DriftRecord:
    """A calculated drift between prediction and financial markets."""

    id: Optional[int]
    event_slug: str
    token_id: str
    ticker: str
    delta_p: float
    delta_a: float
    delta_a_normalized: float
    drift: float
    z_score: Optional[float]
    signal_type: str  # "lead", "lag", "divergence", "convergence", "neutral"
    window_hours: int
    timestamp: int

    @classmethod
    def from_row(cls, row) -> DriftRecord:
        return cls(
            id=row["id"],
            event_slug=row["event_slug"],
            token_id=row["token_id"],
            ticker=row["ticker"],
            delta_p=row["delta_p"],
            delta_a=row["delta_a"],
            delta_a_normalized=row["delta_a_normalized"],
            drift=row["drift"],
            z_score=row["z_score"],
            signal_type=row["signal_type"],
            window_hours=row["window_hours"],
            timestamp=row["timestamp"],
        )


@dataclass
class MappingCache:
    """Cached resolution of event slug to Polymarket token ID."""

    event_slug: str
    token_id: str
    market_id: str
    question: str
    resolved_at: int
