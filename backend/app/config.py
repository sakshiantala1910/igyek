"""Application configuration.

Every tunable that a reviewer might want to challenge lives here rather than
being scattered through the analytics code.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import date


ELEXON_BASE_URL = os.getenv(
    "ELEXON_BASE_URL", "https://data.elexon.co.uk/bmrs/api/v1"
)

# Europe/London. GB day-ahead auctions and settlement periods are defined in
# local clock time, so every "decision deadline" and "delivery day" boundary is
# resolved in this zone and only then converted to UTC.
MARKET_TZ = "Europe/London"

# Gate closure for the GB day-ahead auctions (N2EX 09:30, EPEX SPOT GB 09:20
# local). We default to the later of the two: a forecast published after this
# could not have informed the bid.
DEFAULT_DECISION_DEADLINE = "09:30"

# The study window the client asked for: purchase decisions taken during
# January 2026. A decision on 2026-01-01 is for delivery on 2026-01-02, and a
# decision on 2026-01-31 is for delivery on 2026-02-01.
STUDY_DECISION_START = date(2026, 1, 1)
STUDY_DECISION_END = date(2026, 1, 31)

# Installed/meterable GB wind capacity visible to FUELHH, in MW. Used only to
# normalise error metrics (nMAE as % of capacity), which is the convention the
# wind-forecasting literature uses so numbers are comparable across markets.
ASSUMED_WIND_CAPACITY_MW = float(os.getenv("ASSUMED_WIND_CAPACITY_MW", "30000"))

DATA_DIR = os.getenv(
    "WINDSIGHT_DATA_DIR",
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data"),
)

# When true the service will reach out to Elexon for anything not already in the
# on-disk snapshot. Turned off on the serverless deployment, where the snapshot
# is the single source of truth and cold-start latency matters.
ALLOW_LIVE_FETCH = os.getenv("ALLOW_LIVE_FETCH", "1") not in ("0", "false", "False")


@dataclass(frozen=True)
class Settings:
    base_url: str = ELEXON_BASE_URL
    market_tz: str = MARKET_TZ
    data_dir: str = DATA_DIR
    allow_live_fetch: bool = ALLOW_LIVE_FETCH
    capacity_mw: float = ASSUMED_WIND_CAPACITY_MW
    cors_origins: tuple[str, ...] = field(
        default_factory=lambda: tuple(
            o.strip()
            for o in os.getenv("CORS_ORIGINS", "*").split(",")
            if o.strip()
        )
    )


settings = Settings()
