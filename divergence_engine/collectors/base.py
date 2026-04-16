"""Base collector interface."""

from __future__ import annotations

from abc import ABC, abstractmethod

from divergence_engine.storage.models import PricePoint


class BaseCollector(ABC):
    """Abstract base for data collectors."""

    @abstractmethod
    def fetch_history(self, identifier: str, start_ts: int, end_ts: int) -> list[PricePoint]:
        ...

    @abstractmethod
    def fetch_current(self, identifier: str) -> float | None:
        ...
