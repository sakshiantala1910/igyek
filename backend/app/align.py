"""Turning two raw Elexon feeds into the one table the desk actually reasons about.

Three judgement calls live in this module, and they are the ones worth
reviewing:

1. **Resolution.** WINDFOR is hourly; FUELHH is half-hourly. We bring actuals
   *up* to hourly (mean of the two settlement periods) rather than interpolating
   the forecast down. Interpolating a forecast invents information it never
   contained; averaging an outturn does not. An hour is only scored when both
   of its settlement periods are present.

2. **Delivery day.** A "day" is a local-clock day in Europe/London, because
   that is how the day-ahead auction product and the settlement calendar are
   defined - not a UTC day.

3. **Vintage.** For a decision taken before gate closure on D-1, the only
   forecast that existed is the latest WINDFOR publication at or before that
   deadline. Scoring the desk against a forecast published later would flatter
   the numbers and is the single most common way this analysis goes wrong.
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta

import pandas as pd

from .config import MARKET_TZ



def to_hourly_actuals(actuals_30m: pd.DataFrame) -> pd.DataFrame:
    """Average the two settlement periods in each hour into a single MW value."""
    if actuals_30m.empty:
        return pd.DataFrame(columns=["start_time", "actual_mw", "periods"])
    df = actuals_30m.copy()
    df["start_time"] = df["start_time"].dt.floor("h")
    grouped = df.groupby("start_time")["actual_mw"].agg(["mean", "count"])
    grouped = grouped.rename(columns={"mean": "actual_mw", "count": "periods"})
    grouped = grouped.reset_index()
    # Only complete hours are scoreable. Partial hours (clock change, missing
    # period) are kept but flagged so the API can exclude them explicitly.
    grouped["complete"] = grouped["periods"] == 2
    return grouped


def local_day_bounds(day: date, tz: str = MARKET_TZ) -> tuple[pd.Timestamp, pd.Timestamp]:
    """UTC half-open interval covering one local-clock day."""
    start = pd.Timestamp(datetime.combine(day, time(0, 0)), tz=tz).tz_convert("UTC")
    end = pd.Timestamp(
        datetime.combine(day + timedelta(days=1), time(0, 0)), tz=tz
    ).tz_convert("UTC")
    return start, end


def decision_deadline_utc(
    delivery_day: date, deadline: str, tz: str = MARKET_TZ
) -> pd.Timestamp:
    """Gate closure for delivery on ``delivery_day``: a local time on D-1."""
    hh, mm = (int(part) for part in deadline.split(":"))
    decision_day = delivery_day - timedelta(days=1)
    return pd.Timestamp(
        datetime.combine(decision_day, time(hh, mm)), tz=tz
    ).tz_convert("UTC")


def select_vintage(
    forecasts: pd.DataFrame, deadline_utc: pd.Timestamp
) -> pd.Timestamp | None:
    """The publication a trader would have had in front of them at the deadline.

    Strictly *before* the deadline, not at it. The 09:30 WINDFOR run is stamped
    at the same minute as N2EX gate closure; treating it as usable would score
    the desk against information it did not have when the bid went in.
    """
    available = forecasts.loc[forecasts["publish_time"] < deadline_utc, "publish_time"]
    if available.empty:
        return None
    return available.max()


def build_delivery_day(
    forecasts: pd.DataFrame,
    hourly_actuals: pd.DataFrame,
    delivery_day: date,
    deadline: str,
    tz: str = MARKET_TZ,
) -> pd.DataFrame:
    """One scored delivery day: hourly forecast, outturn and error.

    ``error_mw`` is signed forecast minus actual. **Positive means the forecast
    was too high**, so the desk bought too little thermal cover and was short in
    real time. That sign convention is used consistently everywhere downstream.
    """
    day_start, day_end = local_day_bounds(delivery_day, tz)
    deadline_utc = decision_deadline_utc(delivery_day, deadline, tz)
    vintage = select_vintage(forecasts, deadline_utc)
    if vintage is None:
        return _empty_day_frame()

    curve = forecasts.loc[
        (forecasts["publish_time"] == vintage)
        & (forecasts["start_time"] >= day_start)
        & (forecasts["start_time"] < day_end),
        ["start_time", "forecast_mw"],
    ]
    if curve.empty:
        return _empty_day_frame()

    merged = curve.merge(hourly_actuals, on="start_time", how="left")
    merged["delivery_date"] = delivery_day.isoformat()
    merged["publish_time"] = vintage
    merged["deadline_utc"] = deadline_utc
    merged["lead_hours"] = (
        (merged["start_time"] - vintage).dt.total_seconds() / 3600.0
    )
    merged["error_mw"] = merged["forecast_mw"] - merged["actual_mw"]
    merged["abs_error_mw"] = merged["error_mw"].abs()
    merged["complete"] = merged["complete"].fillna(False)
    return merged.sort_values("start_time").reset_index(drop=True)


def build_study_frame(
    forecasts: pd.DataFrame,
    hourly_actuals: pd.DataFrame,
    decision_start: date,
    decision_end: date,
    deadline: str,
    tz: str = MARKET_TZ,
) -> pd.DataFrame:
    """Score every delivery day whose purchase decision falls in the window."""
    frames = []
    day = decision_start
    while day <= decision_end:
        frames.append(
            build_delivery_day(
                forecasts, hourly_actuals, day + timedelta(days=1), deadline, tz
            )
        )
        day += timedelta(days=1)
    if not frames:
        return _empty_day_frame()
    out = pd.concat(frames, ignore_index=True)
    return out.dropna(subset=["actual_mw"]).reset_index(drop=True)


def build_lead_time_frame(
    forecasts: pd.DataFrame,
    hourly_actuals: pd.DataFrame,
    decision_start: date,
    decision_end: date,
    tz: str = MARKET_TZ,
) -> pd.DataFrame:
    """Every (publication, target hour) pair scored, for lead-time analysis.

    This is what answers "would waiting for the 11:30 run have helped?" - a
    question the desk can act on, because the EPEX intraday auction sits after
    it.
    """
    first_day, _ = local_day_bounds(decision_start + timedelta(days=1), tz)
    _, last_day = local_day_bounds(decision_end + timedelta(days=1), tz)
    scoped = forecasts.loc[
        (forecasts["start_time"] >= first_day) & (forecasts["start_time"] < last_day)
    ]
    merged = scoped.merge(hourly_actuals, on="start_time", how="inner")
    merged = merged.loc[merged["complete"]].copy()
    merged["lead_hours"] = (
        (merged["start_time"] - merged["publish_time"]).dt.total_seconds() / 3600.0
    )
    merged["error_mw"] = merged["forecast_mw"] - merged["actual_mw"]
    merged["abs_error_mw"] = merged["error_mw"].abs()
    return merged.reset_index(drop=True)


def _empty_day_frame() -> pd.DataFrame:
    return pd.DataFrame(
        columns=[
            "start_time",
            "forecast_mw",
            "actual_mw",
            "periods",
            "complete",
            "delivery_date",
            "publish_time",
            "deadline_utc",
            "lead_hours",
            "error_mw",
            "abs_error_mw",
        ]
    )
