"""Signal classification for Polymarket entry opportunities.

Detects when financial markets have moved but Polymarket probability
hasn't adjusted yet → arbitrage / entry opportunity.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class SignalType(str, Enum):
    """Types of signals — focused on Polymarket entry opportunities."""

    BUY_YES = "BUY YES"      # Financial indicators say probability should be HIGHER
    BUY_NO = "BUY NO"        # Financial indicators say probability should be LOWER
    PRICED_IN = "PRICED IN"  # Both markets already aligned
    NEUTRAL = "NEUTRAL"      # No significant movement


@dataclass
class SignalResult:
    """Result of signal classification."""

    signal_type: SignalType
    delta_p: float
    delta_a_normalized: float
    drift: float
    z_score: float | None
    description: str


def classify_signal(
    delta_p: float,
    delta_a_normalized: float,
    drift: float,
    z_score: float | None,
    direction: str = "positive",
    p_threshold: float = 0.03,
    a_threshold: float = 0.03,
) -> SignalResult:
    """Classify the signal as a Polymarket entry opportunity.

    Core logic:
    - Financial indicator moved significantly but PM didn't → ENTRY opportunity
    - Both moved in alignment → already PRICED IN
    - Neither moved → NEUTRAL

    For "positive" correlation: indicator ↑ means probability should ↑
    For "inverse" correlation: indicator ↑ means probability should ↓
    """
    # Adjust asset direction for inverse correlation
    effective_a = -delta_a_normalized if direction == "inverse" else delta_a_normalized

    p_significant = abs(delta_p) >= p_threshold
    a_significant = abs(effective_a) >= a_threshold

    # Neither moved
    if not p_significant and not a_significant:
        return SignalResult(
            signal_type=SignalType.NEUTRAL,
            delta_p=delta_p,
            delta_a_normalized=delta_a_normalized,
            drift=drift,
            z_score=z_score,
            description="No significant movement",
        )

    # Financial indicator moved but PM hasn't → ENTRY OPPORTUNITY
    if a_significant and not p_significant:
        if effective_a > 0:
            return SignalResult(
                signal_type=SignalType.BUY_YES,
                delta_p=delta_p,
                delta_a_normalized=delta_a_normalized,
                drift=drift,
                z_score=z_score,
                description="Financial indicators ↑ but PM probability hasn't risen → BUY YES",
            )
        else:
            return SignalResult(
                signal_type=SignalType.BUY_NO,
                delta_p=delta_p,
                delta_a_normalized=delta_a_normalized,
                drift=drift,
                z_score=z_score,
                description="Financial indicators ↓ but PM probability hasn't dropped → BUY NO",
            )

    # PM moved but financial indicators haven't → PM may be overreacting
    if p_significant and not a_significant:
        if delta_p > 0:
            return SignalResult(
                signal_type=SignalType.BUY_NO,
                delta_p=delta_p,
                delta_a_normalized=delta_a_normalized,
                drift=drift,
                z_score=z_score,
                description="PM probability ↑ but financial indicators don't confirm → fade with NO",
            )
        else:
            return SignalResult(
                signal_type=SignalType.BUY_YES,
                delta_p=delta_p,
                delta_a_normalized=delta_a_normalized,
                drift=drift,
                z_score=z_score,
                description="PM probability ↓ but financial indicators don't confirm → fade with YES",
            )

    # Both moved — check alignment
    same_direction = (delta_p > 0 and effective_a > 0) or (delta_p < 0 and effective_a < 0)

    if same_direction:
        return SignalResult(
            signal_type=SignalType.PRICED_IN,
            delta_p=delta_p,
            delta_a_normalized=delta_a_normalized,
            drift=drift,
            z_score=z_score,
            description="Already priced in — both markets aligned",
        )
    else:
        # Disagreement: trust financial markets over PM
        if effective_a > 0:
            return SignalResult(
                signal_type=SignalType.BUY_YES,
                delta_p=delta_p,
                delta_a_normalized=delta_a_normalized,
                drift=drift,
                z_score=z_score,
                description="Markets disagree — financial indicators say YES, PM says NO",
            )
        else:
            return SignalResult(
                signal_type=SignalType.BUY_NO,
                delta_p=delta_p,
                delta_a_normalized=delta_a_normalized,
                drift=drift,
                z_score=z_score,
                description="Markets disagree — financial indicators say NO, PM says YES",
            )


def rank_by_significance(signals: list[SignalResult]) -> list[SignalResult]:
    """Rank signals by significance (highest abs Z-score first)."""
    def sort_key(s: SignalResult) -> float:
        z = abs(s.z_score) if s.z_score is not None else 0.0
        type_boost = 2.0 if s.signal_type in (SignalType.BUY_YES, SignalType.BUY_NO) else 0.0
        return z + type_boost

    return sorted(signals, key=sort_key, reverse=True)
