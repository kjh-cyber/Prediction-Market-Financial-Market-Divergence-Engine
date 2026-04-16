"""Z-score based anomaly detection on drift values."""

from __future__ import annotations

import numpy as np


def calculate_zscore(current_drift: float, drift_history: list[float]) -> float | None:
    """Calculate Z-score for the current drift value.

    Z = (current - mean) / std

    Returns None if insufficient history.
    """
    if len(drift_history) < 5:
        return None

    arr = np.array(drift_history)
    mean = float(np.mean(arr))
    std = float(np.std(arr))

    if std < 1e-10:
        return 0.0

    return (current_drift - mean) / std


def detect_anomaly(z_score: float | None, threshold: float = 2.0) -> bool:
    """Check if a Z-score indicates an anomaly."""
    if z_score is None:
        return False
    return abs(z_score) >= threshold


def rolling_zscore(values: list[float], window: int = 20) -> list[float | None]:
    """Calculate rolling Z-scores for a series of values."""
    results: list[float | None] = []

    for i in range(len(values)):
        if i < window:
            results.append(None)
            continue

        window_data = values[i - window : i]
        z = calculate_zscore(values[i], window_data)
        results.append(z)

    return results
