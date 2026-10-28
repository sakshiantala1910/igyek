import numpy as np
import pandas as pd
import pytest

from app import metrics


def frame(errors, actuals=None, dates=None):
    n = len(errors)
    actuals = actuals if actuals is not None else [10000.0] * n
    dates = dates if dates is not None else ["2026-01-05"] * n
    return pd.DataFrame(
        {
            "start_time": pd.date_range("2026-01-05", periods=n, freq="h", tz="UTC"),
            "error_mw": [float(e) for e in errors],
            "abs_error_mw": [abs(float(e)) for e in errors],
            "actual_mw": [float(a) for a in actuals],
            "forecast_mw": [float(a) + float(e) for a, e in zip(actuals, errors)],
            "delivery_date": dates,
        }
    )


def test_summary_core_statistics():
    out = metrics.summary(frame([100, -100, 300, -300]), capacity_mw=30000)
    assert out["hours"] == 4
    assert out["mae_mw"] == pytest.approx(200.0)
    assert out["bias_mw"] == pytest.approx(0.0)
    assert out["share_hours_short_pct"] == pytest.approx(50.0)


def test_summary_bias_detects_a_one_sided_lean():
    out = metrics.summary(frame([500, 400, 600, 500]), capacity_mw=30000)
    assert out["bias_mw"] == pytest.approx(500.0)
    assert out["share_hours_short_pct"] == pytest.approx(100.0)


def test_summary_is_json_safe_when_empty():
    assert metrics.summary(frame([]), capacity_mw=30000) == {"hours": 0}


def test_cover_buffer_is_the_matching_error_quantile():
    errors = list(range(0, 100))
    out = metrics.cover_recommendation(frame(errors), [0.90])
    assert out[0]["buffer_mw"] == pytest.approx(np.quantile(errors, 0.90), abs=0.01)
    # At a 90% buffer, roughly a tenth of hours remain short.
    assert out[0]["residual_short_hours"] <= 10


def test_cover_is_monotonic_in_confidence():
    rng = np.random.default_rng(0)
    out = metrics.cover_recommendation(frame(rng.normal(500, 800, 500)), [0.5, 0.9, 0.99])
    buffers = [row["buffer_mw"] for row in out]
    assert buffers == sorted(buffers)


def test_bias_correction_removes_a_constant_lean():
    """A forecast that is always 1000 MW high should be almost fully corrected."""
    dates = []
    errors = []
    for day in range(1, 26):
        dates += [f"2026-01-{day:02d}"] * 24
        errors += [1000.0] * 24
    out = metrics.rolling_bias_correction(frame(errors, dates=dates), 30000)
    assert out["available"] is True
    assert out["corrected"]["bias_mw"] == pytest.approx(0.0, abs=1.0)
    assert out["corrected"]["mae_mw"] < out["raw"]["mae_mw"]


def test_bias_correction_uses_only_prior_days():
    """Day 1 can never be corrected - there is no history behind it."""
    dates, errors = [], []
    for day in range(1, 11):
        dates += [f"2026-01-{day:02d}"] * 2
        errors += [1000.0, 1000.0]
    out = metrics.rolling_bias_correction(frame(errors, dates=dates), 30000)
    # The window ends at D-2 and needs 3 days, so the first four are dropped.
    assert out["scored_hours"] == (10 - 4) * 2


def test_bias_correction_never_sees_the_day_before_delivery():
    """The bid for D is placed on D-1, before D-1's outturn exists."""
    dates, errors = [], []
    for day, err in enumerate([1000, 1000, 1000, 1000, 1000, 9000, 1000], start=1):
        dates.append(f"2026-01-{day:02d}")
        errors.append(float(err))
    out = metrics.rolling_bias_correction(frame(errors, dates=dates), 30000)
    # Days 5-7 are corrected by 1000 each; only day 6's own spike survives.
    # Had day 6 leaked into day 7's correction, day 7 would be over-corrected.
    assert out["scored_hours"] == 3
    assert out["corrected"]["mae_mw"] == pytest.approx(8000 / 3)


def test_persistence_benchmark_scores_against_outturn_two_days_back():
    df = frame([100] * 24, actuals=[10000.0] * 24)
    lagged = pd.DataFrame(
        {
            "start_time": df["start_time"] - pd.Timedelta(days=2),
            "actual_mw": [15000.0] * 24,
        }
    )
    out = metrics.persistence_benchmark(df, lagged)
    assert out["available"] is True
    # Naive is 5000 MW out; the forecast is 100 MW out, so skill is near total.
    assert out["skill_score_pct"] > 95


def test_histogram_shares_sum_to_one_hundred():
    rng = np.random.default_rng(1)
    hist = metrics.error_histogram(frame(rng.normal(0, 1500, 400)))
    assert sum(b["share_pct"] for b in hist) == pytest.approx(100.0, abs=0.5)


def test_output_bands_are_populated_and_ordered():
    rng = np.random.default_rng(2)
    actuals = rng.uniform(1000, 18000, 400)
    bands = metrics.by_output_band(frame(rng.normal(0, 1000, 400), actuals=actuals), 30000)
    assert len(bands) == 5
    assert all(b["hours"] > 0 for b in bands)
    assert [b["band_from_mw"] for b in bands] == sorted(b["band_from_mw"] for b in bands)
