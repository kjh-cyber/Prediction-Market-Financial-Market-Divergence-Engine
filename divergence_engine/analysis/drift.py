"""Core drift calculation between prediction and financial markets.

Drift = ΔP - normalized(ΔA)

Where:
- ΔP = change in prediction market probability
- ΔA = change in asset price, normalized by volatility
"""

from __future__ import annotations

import numpy as np

from divergence_engine.storage.models import PricePoint


def calculate_delta_p(history: list[PricePoint], window_hours: int = 24) -> float | None:
    """Calculate the change in probability over a time window.

    Returns the difference between the latest and earliest probability
    within the specified window. Values are already in [0, 1] range.
    """
    if len(history) < 2:
        return None

    latest = history[-1].value
    earliest = history[0].value
    return latest - earliest


def calculate_delta_a(prices: list[float], window_hours: int = 24) -> float | None:
    """Calculate the percentage change in asset price over a time window.

    Returns the percentage change as a decimal (e.g., 0.05 = 5% increase).
    """
    if len(prices) < 2:
        return None

    latest = prices[-1]
    earliest = prices[0]

    if earliest == 0:
        return None

    return (latest - earliest) / earliest


def normalize_asset_change(delta_a: float, historical_volatility: float) -> float:
    """Normalize asset price change to be comparable with probability changes.

    Uses volatility-adjusted scaling so that a 1-sigma move maps to roughly
    the same magnitude as a typical prediction market move (~5-10%).
    """
    if historical_volatility <= 0:
        return delta_a

    # Number of standard deviations this move represents
    z_move = delta_a / historical_volatility

    # Scale: 1 sigma -> 0.05, 2 sigma -> 0.10, 3 sigma -> 0.15
    # This maps typical asset moves into the prediction market's scale
    return z_move * 0.05


def calculate_historical_volatility(prices: list[float]) -> float:
    """Calculate the standard deviation of percentage returns.

    Uses simple returns (not log returns) for interpretability.
    """
    if len(prices) < 3:
        return 0.01  # Fallback minimum

    arr = np.array(prices)
    returns = np.diff(arr) / arr[:-1]

    if len(returns) == 0:
        return 0.01

    return float(np.std(returns)) or 0.01


def calculate_drift(
    delta_p: float,
    normalized_delta_a: float,
    direction: str = "positive",
) -> float:
    """Calculate the drift between prediction market and financial market.

    For "positive" correlation: both should move in the same direction.
    For "inverse" correlation: they should move in opposite directions.

    Drift = ΔP - direction_adjusted(normalized_ΔA)
    """
    if direction == "inverse":
        adjusted_a = -normalized_delta_a
    else:
        adjusted_a = normalized_delta_a

    return delta_p - adjusted_a


def compute_full_drift(
    prob_history: list[PricePoint],
    asset_prices: list[float],
    direction: str = "positive",
    window_hours: int = 24,
) -> dict | None:
    """Compute the full drift analysis for a single event-asset pair.

    Returns a dict with all intermediate values, or None if insufficient data.
    """
    delta_p = calculate_delta_p(prob_history, window_hours)
    delta_a = calculate_delta_a(asset_prices, window_hours)

    if delta_p is None or delta_a is None:
        return None

    vol = calculate_historical_volatility(asset_prices)
    delta_a_norm = normalize_asset_change(delta_a, vol)
    drift = calculate_drift(delta_p, delta_a_norm, direction)

    return {
        "delta_p": delta_p,
        "delta_a": delta_a,
        "delta_a_normalized": delta_a_norm,
        "drift": drift,
        "volatility": vol,
    }
