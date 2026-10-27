"""Thin client for the two Elexon BMRS Insights datasets this product uses.

Only two endpoints matter here:

* ``FUELHH``  - settlement-period (30 min) outturn generation by fuel type. We
  take ``fuelType=WIND`` only.
* ``WINDFOR`` - Elexon's national wind generation forecast. Each publication is
  a 73-point hourly curve covering roughly D-1 21:00 to D+2 21:00 UTC, and
  there are eight publications a day.

Both are filtered server-side by publish time; WINDFOR offers no filter on the
target time, so we pull by publication window and filter target times locally.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta

import httpx
import pandas as pd

from .config import settings

log = logging.getLogger(__name__)

_TIMEOUT = httpx.Timeout(60.0, connect=15.0)
_RETRY_STATUSES = {429, 500, 502, 503, 504}


def _get(path: str, params: dict) -> list[dict]:
    """GET a /stream endpoint, retrying transient failures."""
    url = f"{settings.base_url}{path}"
    last: Exception | None = None
    for attempt in range(4):
        try:
            with httpx.Client(timeout=_TIMEOUT) as client:
                resp = client.get(url, params=params)
            if resp.status_code in _RETRY_STATUSES:
                raise httpx.HTTPStatusError(
                    f"retryable {resp.status_code}", request=resp.request, response=resp
                )
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:  # noqa: BLE001 - retry anything transport-ish
            last = exc
            log.warning("Elexon %s attempt %d failed: %s", path, attempt + 1, exc)
    raise RuntimeError(f"Elexon request failed after retries: {last}")


def _iso(ts: datetime) -> str:
    return pd.Timestamp(ts).tz_convert("UTC").strftime("%Y-%m-%dT%H:%M:%SZ")


def fetch_actuals(start: datetime, end: datetime) -> pd.DataFrame:
    """Half-hourly wind outturn with ``start_time`` in [start, end).

    FUELHH is filtered by settlement date, which is a local-clock day, so we
    widen the request by a day on each side and trim precisely afterwards.
    """
    rows = _get(
        "/datasets/FUELHH/stream",
        {
            "settlementDateFrom": (start - timedelta(days=1)).strftime("%Y-%m-%d"),
            "settlementDateTo": (end + timedelta(days=1)).strftime("%Y-%m-%d"),
            "fuelType": "WIND",
        },
    )
    df = pd.DataFrame(rows)
    if df.empty:
        return pd.DataFrame(columns=["start_time", "actual_mw"])
    df["start_time"] = pd.to_datetime(df["startTime"], utc=True)
    df = df.rename(columns={"generation": "actual_mw"})
    df = df[["start_time", "actual_mw"]].dropna()
    mask = (df["start_time"] >= pd.Timestamp(start)) & (df["start_time"] < pd.Timestamp(end))
    return df.loc[mask].sort_values("start_time").reset_index(drop=True)


def fetch_forecasts(publish_from: datetime, publish_to: datetime) -> pd.DataFrame:
    """Every WINDFOR point published in [publish_from, publish_to)."""
    rows = _get(
        "/datasets/WINDFOR/stream",
        {
            "publishDateTimeFrom": _iso(publish_from),
            "publishDateTimeTo": _iso(publish_to),
        },
    )
    df = pd.DataFrame(rows)
    if df.empty:
        return pd.DataFrame(columns=["publish_time", "start_time", "forecast_mw"])
    df["publish_time"] = pd.to_datetime(df["publishTime"], utc=True)
    df["start_time"] = pd.to_datetime(df["startTime"], utc=True)
    df = df.rename(columns={"generation": "forecast_mw"})
    df = df[["publish_time", "start_time", "forecast_mw"]].dropna()
    # A publication occasionally repeats a target hour; the last value wins.
    df = df.drop_duplicates(["publish_time", "start_time"], keep="last")
    return df.sort_values(["publish_time", "start_time"]).reset_index(drop=True)
