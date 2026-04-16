"""Configuration and settings for the Divergence Engine."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class Settings:
    # Database
    db_path: str = os.getenv("DB_PATH", str(PROJECT_ROOT / "data" / "divergence.db"))

    # Polymarket APIs
    gamma_api_url: str = os.getenv("GAMMA_API_URL", "https://gamma-api.polymarket.com")
    clob_api_url: str = os.getenv("CLOB_API_URL", "https://clob.polymarket.com")

    # Analysis
    zscore_threshold: float = float(os.getenv("ZSCORE_THRESHOLD", "2.0"))
    drift_min_threshold: float = float(os.getenv("DRIFT_MIN_THRESHOLD", "0.05"))
    default_window_hours: int = int(os.getenv("DEFAULT_WINDOW_HOURS", "24"))

    # Collection
    collect_interval: int = int(os.getenv("COLLECT_INTERVAL", "300"))

    # HTTP
    http_timeout: float = 30.0
    http_retries: int = 3


settings = Settings()
