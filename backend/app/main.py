"""HTTP API.

Four read-only endpoints, each mapping to one question the desk asks:

  /api/meta      what data am I looking at, and what can I ask for?
  /api/day       what is the forecast for tomorrow, and how wrong is it likely to be?
  /api/accuracy  how wrong has it been, over the decisions I took in January?
  /api/leadtime  would waiting for a later run have helped?
"""
from __future__ import annotations

import logging
from datetime import date, timedelta

import pandas as pd
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from . import align, metrics
from .config import (
    DEFAULT_DECISION_DEADLINE,
    MARKET_TZ,
    STUDY_DECISION_END,
    STUDY_DECISION_START,
    settings,
)
from .schemas import AccuracyResponse, DayResponse, LeadTimeResponse
from .store import get_dataset

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")

app = FastAPI(
    title="Windsight API",
    version="1.0.0",
    description=(
        "Day-ahead wind forecast and forecast-error analytics for a GB supplier's "
        "procurement desk. Data: Elexon BMRS WINDFOR and FUELHH (fuelType=WIND)."
    ),
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.cors_origins) or ["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)

# Delivery days implied by the January 2026 decision window.
STUDY_DELIVERY_START = STUDY_DECISION_START + timedelta(days=1)
STUDY_DELIVERY_END = STUDY_DECISION_END + timedelta(days=1)

DEFAULT_COVER_CONFIDENCES = [0.50, 0.75, 0.90, 0.95, 0.99]

# Days of history used to build the forward-looking uncertainty band. Trailing
# only: the band shown for delivery day D uses errors from days strictly before
# D, so what the screen shows is what the desk could genuinely have known.
BAND_LOOKBACK_DAYS = 14


def _deadline(value: str) -> str:
    try:
        hh, mm = (int(p) for p in value.split(":"))
        assert 0 <= hh <= 23 and 0 <= mm <= 59
    except Exception:
        raise HTTPException(422, f"deadline must be HH:MM, got {value!r}")
    return f"{hh:02d}:{mm:02d}"


def _iso(ts) -> str | None:
    if ts is None or pd.isna(ts):
        return None
    return pd.Timestamp(ts).tz_convert("UTC").isoformat().replace("+00:00", "Z")


def _rows_to_payload(df: pd.DataFrame) -> list[dict]:
    out = []
    for row in df.itertuples():
        out.append(
            {
                "start_time": _iso(row.start_time),
                "local_time": pd.Timestamp(row.start_time)
                .tz_convert(MARKET_TZ)
                .strftime("%Y-%m-%d %H:%M"),
                "forecast_mw": metrics._f(row.forecast_mw),
                "actual_mw": metrics._f(row.actual_mw),
                "error_mw": metrics._f(row.error_mw),
                "lead_hours": metrics._f(row.lead_hours),
                "band_low_mw": metrics._f(getattr(row, "band_low_mw", None)),
                "band_high_mw": metrics._f(getattr(row, "band_high_mw", None)),
            }
        )
    return out


def _study_frame(deadline: str, start: date, end: date) -> pd.DataFrame:
    ds = get_dataset()
    return align.build_study_frame(
        ds.forecasts, ds.hourly_actuals, start, end, deadline, MARKET_TZ
    )


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/api/meta")
def meta() -> dict:
    ds = get_dataset()
    runs = sorted(
        ds.forecasts["publish_time"].dt.tz_convert("UTC").dt.strftime("%H:%M").unique()
    )
    return {
        "data": ds.manifest,
        "market_timezone": MARKET_TZ,
        "default_deadline_local": DEFAULT_DECISION_DEADLINE,
        "assumed_capacity_mw": settings.capacity_mw,
        "decision_window": {
            "from": STUDY_DECISION_START.isoformat(),
            "to": STUDY_DECISION_END.isoformat(),
        },
        "delivery_window": {
            "from": STUDY_DELIVERY_START.isoformat(),
            "to": STUDY_DELIVERY_END.isoformat(),
        },
        "windfor_runs_utc": runs,
        "forecast_publications": int(ds.forecasts["publish_time"].nunique()),
        "actual_half_hours": int(len(ds.actuals_30m)),
        "sign_convention": (
            "error = forecast - actual; positive means wind was over-forecast, "
            "so thermal cover was under-bought and the book is short."
        ),
    }


@app.get("/api/day", response_model=DayResponse)
def day(
    delivery_date: date = Query(..., alias="date"),
    deadline: str = Query(DEFAULT_DECISION_DEADLINE),
    confidence: float = Query(0.80, ge=0.5, le=0.99),
) -> DayResponse:
    """The decision screen: tomorrow's curve, with an honest error band."""
    deadline = _deadline(deadline)
    ds = get_dataset()
    frame = align.build_delivery_day(
        ds.forecasts, ds.hourly_actuals, delivery_date, deadline, MARKET_TZ
    )
    if frame.empty:
        raise HTTPException(
            404,
            f"No WINDFOR publication at or before {deadline} on "
            f"{delivery_date - timedelta(days=1)} covering {delivery_date}.",
        )

    band = _trailing_band(ds, delivery_date, deadline, confidence)
    frame = frame.copy()
    frame["hour_local"] = frame["start_time"].dt.tz_convert(MARKET_TZ).dt.hour
    frame["band_low_mw"] = frame.apply(
        lambda r: _apply_band(r, band, "low"), axis=1
    )
    frame["band_high_mw"] = frame.apply(
        lambda r: _apply_band(r, band, "high"), axis=1
    )

    vintage = frame["publish_time"].iloc[0]
    deadline_utc = frame["deadline_utc"].iloc[0]
    history = _study_frame(
        deadline,
        max(STUDY_DECISION_START, delivery_date - timedelta(days=BAND_LOOKBACK_DAYS + 1)),
        delivery_date - timedelta(days=2),
    )

    return DayResponse(
        delivery_date=delivery_date.isoformat(),
        deadline_local=deadline,
        deadline_utc=_iso(deadline_utc),
        vintage_publish_time=_iso(vintage),
        vintage_age_minutes=metrics._f(
            (deadline_utc - vintage).total_seconds() / 60.0
        ),
        forecast_horizon_hours=metrics._f(frame["lead_hours"].max()),
        band_method=(
            f"Empirical p{int((1 - confidence) / 2 * 100)}/"
            f"p{int((1 + confidence) / 2 * 100)} of signed forecast error over the "
            f"previous {BAND_LOOKBACK_DAYS} delivery days, by hour of day "
            "(trailing only - no look-ahead)."
        ),
        band_confidence_pct=round(confidence * 100, 1),
        hours=_rows_to_payload(frame),
        summary=metrics.summary(frame, settings.capacity_mw),
        cover=metrics.cover_recommendation(history, DEFAULT_COVER_CONFIDENCES),
    )


def _trailing_band(ds, delivery_date: date, deadline: str, confidence: float) -> dict:
    """Per-hour-of-day error quantiles from the days before ``delivery_date``."""
    lo_q = (1 - confidence) / 2
    hi_q = 1 - lo_q
    start = max(
        STUDY_DECISION_START, delivery_date - timedelta(days=BAND_LOOKBACK_DAYS + 1)
    )
    end = delivery_date - timedelta(days=2)  # decision day of the last prior delivery
    if end < start:
        return {}
    hist = align.build_study_frame(
        ds.forecasts, ds.hourly_actuals, start, end, deadline, MARKET_TZ
    )
    if hist.empty:
        return {}
    hist = hist.copy()
    hist["hour_local"] = hist["start_time"].dt.tz_convert(MARKET_TZ).dt.hour
    band = {}
    for hour, g in hist.groupby("hour_local"):
        if len(g) < 3:
            continue
        band[int(hour)] = (
            float(g["error_mw"].quantile(lo_q)),
            float(g["error_mw"].quantile(hi_q)),
        )
    # Fall back to a pooled band for hours with too little history.
    band["_pooled"] = (
        float(hist["error_mw"].quantile(lo_q)),
        float(hist["error_mw"].quantile(hi_q)),
    )
    return band


def _apply_band(row, band: dict, edge: str) -> float | None:
    if not band or pd.isna(row.forecast_mw):
        return None
    lo, hi = band.get(int(row.hour_local), band.get("_pooled", (None, None)))
    if lo is None:
        return None
    # The band is on the *outturn*: if the forecast has been running high by
    # `hi` MW, the plausible outturn floor is forecast - hi.
    return max(0.0, row.forecast_mw - hi) if edge == "low" else row.forecast_mw - lo


@app.get("/api/accuracy", response_model=AccuracyResponse)
def accuracy(
    deadline: str = Query(DEFAULT_DECISION_DEADLINE),
    decision_from: date = Query(STUDY_DECISION_START, alias="from"),
    decision_to: date = Query(STUDY_DECISION_END, alias="to"),
) -> AccuracyResponse:
    deadline = _deadline(deadline)
    if decision_to < decision_from:
        raise HTTPException(422, "`to` must not be before `from`")
    ds = get_dataset()
    frame = _study_frame(deadline, decision_from, decision_to)
    if frame.empty:
        raise HTTPException(404, "No scoreable hours in that window.")
    return AccuracyResponse(
        window={
            "decision_from": decision_from.isoformat(),
            "decision_to": decision_to.isoformat(),
            "delivery_from": (decision_from + timedelta(days=1)).isoformat(),
            "delivery_to": (decision_to + timedelta(days=1)).isoformat(),
            "deadline_local": deadline,
            "scored_hours": int(len(frame)),
        },
        summary=metrics.summary(frame, settings.capacity_mw),
        persistence=metrics.persistence_benchmark(frame, ds.hourly_actuals),
        bias_correction=metrics.rolling_bias_correction(frame, settings.capacity_mw),
        cover=metrics.cover_recommendation(frame, DEFAULT_COVER_CONFIDENCES),
        histogram=metrics.error_histogram(frame),
        by_hour_of_day=metrics.by_hour_of_day(frame, MARKET_TZ),
        by_day=metrics.by_day(frame),
        by_output_band=metrics.by_output_band(frame, settings.capacity_mw),
    )


@app.get("/api/leadtime", response_model=LeadTimeResponse)
def leadtime(
    decision_from: date = Query(STUDY_DECISION_START, alias="from"),
    decision_to: date = Query(STUDY_DECISION_END, alias="to"),
) -> LeadTimeResponse:
    ds = get_dataset()
    frame = align.build_lead_time_frame(
        ds.forecasts, ds.hourly_actuals, decision_from, decision_to, MARKET_TZ
    )
    if frame.empty:
        raise HTTPException(404, "No scoreable forecast/outturn pairs in that window.")
    return LeadTimeResponse(
        window={
            "decision_from": decision_from.isoformat(),
            "decision_to": decision_to.isoformat(),
            "scored_pairs": int(len(frame)),
        },
        by_lead_time=metrics.by_lead_time(frame),
        by_publication_run=metrics.by_publication_run(frame, MARKET_TZ),
    )
