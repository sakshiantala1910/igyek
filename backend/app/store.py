"""Data access: an on-disk snapshot first, Elexon only as a fallback.

The study window (January 2026 decisions) is historical and immutable, so the
honest thing is to pin it. A committed snapshot means the deployed demo is
reproducible, loads in milliseconds on a cold serverless start, and cannot be
broken by a BMRS outage during a client walkthrough. ``python -m app.ingest``
rebuilds it from the live API, and the API reports the snapshot's provenance on
``/api/meta`` so nobody has to wonder which data they are looking at.

Gzipped CSV rather than Parquet on purpose: it keeps ``pyarrow`` out of the
dependency tree, which matters for the serverless bundle size limit.
"""
from __future__ import annotations

import json
import logging
import os
from datetime import date, datetime, timedelta, timezone
from functools import lru_cache

import pandas as pd

from . import elexon
from .align import to_hourly_actuals
from .config import (
    STUDY_DECISION_END,
    STUDY_DECISION_START,
    settings,
)

log = logging.getLogger(__name__)

FORECAST_FILE = "windfor.csv.gz"
ACTUAL_FILE = "fuelhh.csv.gz"
MANIFEST_FILE = "snapshot.json"

# A WINDFOR run published up to 3 days before the first delivery hour still
# covers it, and runs published during the window cover the tail; pad both ends.
PUBLISH_PAD_DAYS = 3


class Dataset:
    """Everything the API layer needs, loaded once per process."""

    def __init__(
        self,
        forecasts: pd.DataFrame,
        actuals_30m: pd.DataFrame,
        manifest: dict,
    ) -> None:
        self.forecasts = forecasts
        self.actuals_30m = actuals_30m
        self.hourly_actuals = to_hourly_actuals(actuals_30m)
        self.manifest = manifest

    @property
    def source(self) -> str:
        return self.manifest.get("source", "unknown")


def _paths() -> tuple[str, str, str]:
    d = settings.data_dir
    return (
        os.path.join(d, FORECAST_FILE),
        os.path.join(d, ACTUAL_FILE),
        os.path.join(d, MANIFEST_FILE),
    )


def snapshot_exists() -> bool:
    fc, ac, _ = _paths()
    return os.path.exists(fc) and os.path.exists(ac)


def _publish_window(
    decision_start: date, decision_end: date
) -> tuple[datetime, datetime]:
    start = datetime.combine(
        decision_start - timedelta(days=PUBLISH_PAD_DAYS),
        datetime.min.time(),
        tzinfo=timezone.utc,
    )
    end = datetime.combine(
        decision_end + timedelta(days=PUBLISH_PAD_DAYS),
        datetime.min.time(),
        tzinfo=timezone.utc,
    )
    return start, end


def build_snapshot(
    decision_start: date = STUDY_DECISION_START,
    decision_end: date = STUDY_DECISION_END,
) -> dict:
    """Pull the study window from Elexon and write it to ``data/``."""
    os.makedirs(settings.data_dir, exist_ok=True)
    pub_from, pub_to = _publish_window(decision_start, decision_end)

    log.info("Fetching WINDFOR %s -> %s", pub_from, pub_to)
    forecasts = elexon.fetch_forecasts(pub_from, pub_to)

    # Delivery days run from decision_start+1 to decision_end+1 inclusive.
    actual_from = datetime.combine(
        decision_start, datetime.min.time(), tzinfo=timezone.utc
    )
    actual_to = datetime.combine(
        decision_end + timedelta(days=3), datetime.min.time(), tzinfo=timezone.utc
    )
    log.info("Fetching FUELHH/WIND %s -> %s", actual_from, actual_to)
    actuals = elexon.fetch_actuals(actual_from, actual_to)

    fc_path, ac_path, mf_path = _paths()
    forecasts.to_csv(fc_path, index=False, compression="gzip")
    actuals.to_csv(ac_path, index=False, compression="gzip")

    manifest = {
        "source": "elexon-bmrs",
        "built_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "decision_start": decision_start.isoformat(),
        "decision_end": decision_end.isoformat(),
        "forecast_rows": int(len(forecasts)),
        "forecast_publications": int(forecasts["publish_time"].nunique()),
        "actual_rows": int(len(actuals)),
        "datasets": ["WINDFOR", "FUELHH(fuelType=WIND)"],
        "endpoint": settings.base_url,
    }
    with open(mf_path, "w") as fh:
        json.dump(manifest, fh, indent=2)
    log.info("Snapshot written: %s", manifest)
    return manifest


def _read_snapshot() -> Dataset:
    fc_path, ac_path, mf_path = _paths()
    forecasts = pd.read_csv(fc_path, parse_dates=["publish_time", "start_time"])
    actuals = pd.read_csv(ac_path, parse_dates=["start_time"])
    for df, cols in ((forecasts, ["publish_time", "start_time"]), (actuals, ["start_time"])):
        for col in cols:
            if df[col].dt.tz is None:
                df[col] = df[col].dt.tz_localize("UTC")
            else:
                df[col] = df[col].dt.tz_convert("UTC")
    manifest = {"source": "snapshot"}
    if os.path.exists(mf_path):
        with open(mf_path) as fh:
            manifest = {**json.load(fh), "source": "snapshot"}
    return Dataset(forecasts, actuals, manifest)


@lru_cache(maxsize=1)
def get_dataset() -> Dataset:
    """Process-wide dataset, built on first request."""
    if snapshot_exists():
        log.info("Loading snapshot from %s", settings.data_dir)
        return _read_snapshot()
    if not settings.allow_live_fetch:
        raise RuntimeError(
            "No snapshot in data/ and live fetching is disabled. "
            "Run `python -m app.ingest` to build one."
        )
    log.warning("No snapshot found - fetching from Elexon on the fly")
    build_snapshot()
    return _read_snapshot()


def reset_cache() -> None:
    get_dataset.cache_clear()
