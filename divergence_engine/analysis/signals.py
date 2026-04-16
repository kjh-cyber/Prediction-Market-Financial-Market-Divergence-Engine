"""Signal classification for divergence events.

Classifies the relationship between prediction market and financial market
movements into actionable signal types.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class SignalType(str, Enum):
    """Types of signals detected from drift analysis."""

    LEAD = "lead"          # PM moved first, asset hasn't followed
    LAG = "lag"            # Asset moved first, PM hasn't adjusted
    DIVERGENCE = "divergence"  # Moving in opposite directions
    CONVERGENCE = "convergence"  # Both moving together as expected
    NEUTRAL = "neutral"    # No significant movement


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
    """Classify the signal based on drift analysis.

    Args:
        delta_p: Change in prediction market probability.
        delta_a_normalized: Normalized change in asset price.
        drift: Calculated drift value.
        z_score: Z-score of the drift (may be None).
        direction: Expected correlation direction ("positive" or "inverse").
        p_threshold: Minimum absolute ΔP to consider significant.
        a_threshold: Minimum absolute normalized ΔA to consider significant.
    """
    # Adjust asset direction for inverse correlation
    effective_a = -delta_a_normalized if direction == "inverse" else delta_a_normalized

    p_significant = abs(delta_p) >= p_threshold
    a_significant = abs(effective_a) >= a_threshold

    # Neither moved significantly
    if not p_significant and not a_significant:
        return SignalResult(
            signal_type=SignalType.NEUTRAL,
            delta_p=delta_p,
            delta_a_normalized=delta_a_normalized,
            drift=drift,
            z_score=z_score,
            description="No significant movement in either market",
        )

    # PM moved but asset hasn't
    if p_significant and not a_significant:
        direction_str = "up" if delta_p > 0 else "down"
        return SignalResult(
            signal_type=SignalType.LEAD,
            delta_p=delta_p,
            delta_a_normalized=delta_a_normalized,
            drift=drift,
            z_score=z_score,
            description=f"Prediction market moved {direction_str}, asset has not yet reacted",
        )

    # Asset moved but PM hasn't
    if a_significant and not p_significant:
        direction_str = "up" if effective_a > 0 else "down"
        return SignalResult(
            signal_type=SignalType.LAG,
            delta_p=delta_p,
            delta_a_normalized=delta_a_normalized,
            drift=drift,
            z_score=z_score,
            description=f"Asset moved {direction_str}, prediction market has not adjusted",
        )

    # Both moved — check if they agree or diverge
    same_direction = (delta_p > 0 and effective_a > 0) or (delta_p < 0 and effective_a < 0)

    if same_direction:
        return SignalResult(
            signal_type=SignalType.CONVERGENCE,
            delta_p=delta_p,
            delta_a_normalized=delta_a_normalized,
            drift=drift,
            z_score=z_score,
            description="Markets moving in alignment",
        )
    else:
        pm_dir = "up" if delta_p > 0 else "down"
        asset_dir = "up" if effective_a > 0 else "down"
        return SignalResult(
            signal_type=SignalType.DIVERGENCE,
            delta_p=delta_p,
            delta_a_normalized=delta_a_normalized,
            drift=drift,
            z_score=z_score,
            description=f"Prediction market {pm_dir} but asset {asset_dir} — disagreement detected",
        )


def rank_by_significance(signals: list[SignalResult]) -> list[SignalResult]:
    """Rank signals by significance (highest abs Z-score first)."""
    def sort_key(s: SignalResult) -> float:
        z = abs(s.z_score) if s.z_score is not None else 0.0
        # Boost non-neutral signals
        type_boost = 0.0 if s.signal_type == SignalType.NEUTRAL else 1.0
        return z + type_boost

    return sorted(signals, key=sort_key, reverse=True)
