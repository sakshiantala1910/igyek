"""The alignment rules are where this analysis is easiest to get silently wrong,
so each judgement call gets an explicit test."""
from datetime import date

import pandas as pd
import pytest

from app import align


def ts(value: str) -> pd.Timestamp:
    return pd.Timestamp(value, tz="UTC")


def test_hourly_actuals_average_both_settlement_periods():
    raw = pd.DataFrame(
        {
            "start_time": [ts("2026-01-05T00:00Z"), ts("2026-01-05T00:30Z")],
            "actual_mw": [1000.0, 2000.0],
        }
    )
    out = align.to_hourly_actuals(raw)
    assert len(out) == 1
    assert out.loc[0, "actual_mw"] == 1500.0
    assert bool(out.loc[0, "complete"]) is True


def test_hourly_actuals_flag_incomplete_hour():
    raw = pd.DataFrame(
        {"start_time": [ts("2026-01-05T00:00Z")], "actual_mw": [1000.0]}
    )
    out = align.to_hourly_actuals(raw)
    assert bool(out.loc[0, "complete"]) is False


def test_delivery_day_is_a_local_clock_day():
    # Winter: London == UTC, so the day is a clean 24h starting at 00:00Z.
    start, end = align.local_day_bounds(date(2026, 1, 15))
    assert start == ts("2026-01-15T00:00Z")
    assert end == ts("2026-01-16T00:00Z")


def test_delivery_day_handles_bst():
    # Summer: London is UTC+1, so the local day starts at 23:00Z the day before.
    start, end = align.local_day_bounds(date(2026, 7, 15))
    assert start == ts("2026-07-14T23:00Z")
    assert end == ts("2026-07-15T23:00Z")


def test_deadline_resolves_to_previous_day_in_local_time():
    deadline = align.decision_deadline_utc(date(2026, 1, 15), "09:30")
    assert deadline == ts("2026-01-14T09:30Z")


def test_vintage_is_strictly_before_the_deadline():
    """A run stamped at gate closure was not available when the bid went in."""
    forecasts = pd.DataFrame(
        {
            "publish_time": [ts("2026-01-14T07:30Z"), ts("2026-01-14T09:30Z")],
            "start_time": [ts("2026-01-15T00:00Z")] * 2,
            "forecast_mw": [100.0, 200.0],
        }
    )
    chosen = align.select_vintage(forecasts, ts("2026-01-14T09:30Z"))
    assert chosen == ts("2026-01-14T07:30Z")


def test_vintage_is_none_when_nothing_published_yet():
    forecasts = pd.DataFrame(
        {
            "publish_time": [ts("2026-01-14T15:30Z")],
            "start_time": [ts("2026-01-15T00:00Z")],
            "forecast_mw": [100.0],
        }
    )
    assert align.select_vintage(forecasts, ts("2026-01-14T09:30Z")) is None


def test_build_delivery_day_signs_error_as_forecast_minus_actual():
    forecasts = pd.DataFrame(
        {
            "publish_time": [ts("2026-01-14T07:30Z")],
            "start_time": [ts("2026-01-15T00:00Z")],
            "forecast_mw": [1200.0],
        }
    )
    actuals = pd.DataFrame(
        {
            "start_time": [ts("2026-01-15T00:00Z")],
            "actual_mw": [1000.0],
            "periods": [2],
            "complete": [True],
        }
    )
    day = align.build_delivery_day(forecasts, actuals, date(2026, 1, 15), "09:30")
    assert day.loc[0, "error_mw"] == pytest.approx(200.0)
    assert day.loc[0, "lead_hours"] == pytest.approx(16.5)


def test_build_delivery_day_is_empty_without_a_usable_vintage():
    forecasts = pd.DataFrame(
        {
            "publish_time": [ts("2026-01-14T15:30Z")],
            "start_time": [ts("2026-01-15T00:00Z")],
            "forecast_mw": [1200.0],
        }
    )
    actuals = pd.DataFrame(
        columns=["start_time", "actual_mw", "periods", "complete"]
    )
    assert align.build_delivery_day(
        forecasts, actuals, date(2026, 1, 15), "09:30"
    ).empty
