"""Error metrics, framed for a procurement desk rather than for a modeller.

The desk's question is never "what is the MAPE". It is: *how much thermal cover
do I buy on top of the wind forecast so that I am short no more often than I am
willing to be?* Everything here builds toward that answer.

Sign convention throughout: ``error = forecast - actual``.
  * error > 0  -> wind over-forecast -> under-procured -> **short** in delivery
  * error < 0  -> wind under-forecast -> over-procured -> long, sold back cheap
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .config import MARKET_TZ

QUANTILES = [0.05, 0.10, 0.25, 0.50, 0.75, 0.90, 0.95]


def _f(value) -> float | None:
    """Make numpy/NaN values JSON-safe."""
    if value is None:
        return None
    value = float(value)
    return None if not np.isfinite(value) else round(value, 2)


def summary(df: pd.DataFrame, capacity_mw: float) -> dict:
    """Headline accuracy for a set of scored hours."""
    scored = df.dropna(subset=["error_mw"])
    n = len(scored)
    if n == 0:
        return {"hours": 0}

    err = scored["error_mw"].to_numpy(dtype=float)
    actual = scored["actual_mw"].to_numpy(dtype=float)
    mean_actual = float(np.mean(actual))
    mae = float(np.mean(np.abs(err)))
    rmse = float(np.sqrt(np.mean(err**2)))

    return {
        "hours": n,
        "days": int(scored["delivery_date"].nunique()) if "delivery_date" in scored else None,
        "mean_actual_mw": _f(mean_actual),
        "mean_forecast_mw": _f(scored["forecast_mw"].mean()),
        "mae_mw": _f(mae),
        "rmse_mw": _f(rmse),
        # Bias is the metric that matters most for procurement: a desk can
        # price around random noise, but a persistent lean costs money every day.
        "bias_mw": _f(np.mean(err)),
        "nmae_pct_of_capacity": _f(100.0 * mae / capacity_mw) if capacity_mw else None,
        "nmae_pct_of_mean_output": _f(100.0 * mae / mean_actual) if mean_actual else None,
        "nrmse_pct_of_capacity": _f(100.0 * rmse / capacity_mw) if capacity_mw else None,
        "max_over_forecast_mw": _f(np.max(err)),
        "max_under_forecast_mw": _f(np.min(err)),
        "share_hours_short_pct": _f(100.0 * float(np.mean(err > 0))),
        # One hour at one MW of error is one MWh mis-procured.
        "gross_misprocurement_mwh": _f(float(np.sum(np.abs(err)))),
        "net_misprocurement_mwh": _f(float(np.sum(err))),
        "error_quantiles_mw": {
            f"p{int(q * 100):02d}": _f(np.quantile(err, q)) for q in QUANTILES
        },
    }


def persistence_benchmark(df: pd.DataFrame, hourly_actuals: pd.DataFrame) -> dict:
    """Skill of WINDFOR against the cheapest possible alternative.

    The naive forecast is the outturn for the same hour two days earlier - the
    most recent full day that is certainly known by gate closure on D-1. If
    WINDFOR cannot beat that, it is not worth building a product around.
    """
    scored = df.dropna(subset=["error_mw"]).copy()
    if scored.empty:
        return {"available": False}

    lagged = hourly_actuals[["start_time", "actual_mw"]].copy()
    lagged["start_time"] = lagged["start_time"] + pd.Timedelta(days=2)
    lagged = lagged.rename(columns={"actual_mw": "naive_mw"})
    joined = scored.merge(lagged, on="start_time", how="inner").dropna(
        subset=["naive_mw"]
    )
    if joined.empty:
        return {"available": False}

    naive_err = (joined["naive_mw"] - joined["actual_mw"]).to_numpy(dtype=float)
    model_err = joined["error_mw"].to_numpy(dtype=float)
    naive_rmse = float(np.sqrt(np.mean(naive_err**2)))
    model_rmse = float(np.sqrt(np.mean(model_err**2)))
    return {
        "available": True,
        "hours": len(joined),
        "naive_rmse_mw": _f(naive_rmse),
        "naive_mae_mw": _f(np.mean(np.abs(naive_err))),
        "forecast_rmse_mw": _f(model_rmse),
        "skill_score_pct": _f(100.0 * (1 - model_rmse / naive_rmse)) if naive_rmse else None,
    }


def cover_recommendation(df: pd.DataFrame, confidences: list[float]) -> list[dict]:
    """How much extra firm power to buy, at each tolerance for being short.

    Purely empirical: the buffer at confidence *c* is the *c*-th quantile of the
    historical signed error. No distributional assumption is made, because wind
    forecast errors are visibly fat-tailed and skewed and a normal approximation
    understates exactly the tail the desk cares about.
    """
    err = df.dropna(subset=["error_mw"])["error_mw"].to_numpy(dtype=float)
    out = []
    if err.size == 0:
        return out
    for c in confidences:
        buffer_mw = float(np.quantile(err, c))
        covered = float(np.mean(err <= buffer_mw))
        # Carrying the buffer in every hour of the month, in MWh.
        out.append(
            {
                "confidence_pct": round(c * 100, 1),
                "buffer_mw": _f(buffer_mw),
                "realised_cover_pct": _f(100.0 * covered),
                "residual_short_hours": int(np.sum(err > buffer_mw)),
                "carry_cost_mwh": _f(max(buffer_mw, 0.0) * err.size),
            }
        )
    return out


def by_hour_of_day(df: pd.DataFrame, tz: str = MARKET_TZ) -> list[dict]:
    scored = df.dropna(subset=["error_mw"]).copy()
    if scored.empty:
        return []
    scored["hour"] = scored["start_time"].dt.tz_convert(tz).dt.hour
    grouped = scored.groupby("hour")
    return [
        {
            "hour": int(hour),
            "mae_mw": _f(g["abs_error_mw"].mean()),
            "bias_mw": _f(g["error_mw"].mean()),
            "p10_mw": _f(g["error_mw"].quantile(0.10)),
            "p90_mw": _f(g["error_mw"].quantile(0.90)),
            "mean_actual_mw": _f(g["actual_mw"].mean()),
            "hours": int(len(g)),
        }
        for hour, g in grouped
    ]


def by_day(df: pd.DataFrame) -> list[dict]:
    scored = df.dropna(subset=["error_mw"])
    if scored.empty:
        return []
    return [
        {
            "delivery_date": str(day),
            "publish_time": g["publish_time"].iloc[0].isoformat().replace("+00:00", "Z"),
            "mae_mw": _f(g["abs_error_mw"].mean()),
            "bias_mw": _f(g["error_mw"].mean()),
            "rmse_mw": _f(np.sqrt(np.mean(g["error_mw"].to_numpy(dtype=float) ** 2))),
            "mean_actual_mw": _f(g["actual_mw"].mean()),
            "mean_forecast_mw": _f(g["forecast_mw"].mean()),
            "net_misprocurement_mwh": _f(g["error_mw"].sum()),
            "worst_hour_error_mw": _f(
                g.loc[g["abs_error_mw"].idxmax(), "error_mw"]
            ),
            "hours": int(len(g)),
        }
        for day, g in scored.groupby("delivery_date")
    ]


def by_output_band(df: pd.DataFrame, capacity_mw: float, bands: int = 5) -> list[dict]:
    """Error conditioned on how windy it actually was.

    Wind forecast error is not homoscedastic - it is largest in the steep middle
    of the power curve and small when the fleet is becalmed or saturated. A desk
    that assumes one flat buffer across all conditions over-buys on calm days
    and is still short on volatile ones.

    Bands are quantiles of the *observed* outturn rather than fixed slices of
    nameplate capacity, so every band is populated and the comparison is not
    distorted by whatever capacity figure we assume.
    """
    del capacity_mw  # bands are data-driven; kept for signature stability
    scored = df.dropna(subset=["error_mw"]).copy()
    if scored.empty:
        return []
    try:
        scored["band"] = pd.qcut(scored["actual_mw"], q=bands, duplicates="drop")
    except ValueError:
        return []
    out = []
    for band, g in scored.groupby("band", observed=True):
        out.append(
            {
                "band_label": f"{int(band.left):,}-{int(band.right):,} MW",
                "band_from_mw": int(band.left),
                "band_to_mw": int(band.right),
                "hours": int(len(g)),
                "mae_mw": _f(g["abs_error_mw"].mean()),
                "bias_mw": _f(g["error_mw"].mean()),
                "p90_mw": _f(g["error_mw"].quantile(0.90)),
            }
        )
    return out


def rolling_bias_correction(
    df: pd.DataFrame, capacity_mw: float, lookback_days: int = 14
) -> dict:
    """What a trailing bias correction would have been worth.

    January 2026 is dominated by a one-sided lean: WINDFOR sits above metered
    outturn in the large majority of hours. Much of that gap is definitional
    rather than meteorological - FUELHH records what the fleet actually
    delivered *after* curtailment, while WINDFOR describes the wind that was
    available - but from a procurement standpoint the cause does not matter.
    A lean that persists is a lean you can subtract.

    For each delivery day D the correction is the mean signed error over the
    ``lookback_days`` delivery days ending at D-2. Not D-1: the bid for D is
    placed on the morning of D-1, when D-1's outturn does not exist yet. No
    look-ahead, and nothing that could not have been computed on the morning
    of the bid.
    """
    scored = df.dropna(subset=["error_mw"]).copy()
    if scored.empty or "delivery_date" not in scored:
        return {"available": False}

    daily = (
        scored.groupby("delivery_date")["error_mw"].mean().sort_index()
    )
    # Assumes consecutive delivery days, which build_study_frame guarantees.
    correction = daily.shift(2).rolling(lookback_days, min_periods=3).mean()
    scored["correction_mw"] = scored["delivery_date"].map(correction)
    usable = scored.dropna(subset=["correction_mw"]).copy()
    if usable.empty:
        return {"available": False}

    usable["error_mw"] = usable["error_mw"] - usable["correction_mw"]
    usable["abs_error_mw"] = usable["error_mw"].abs()
    usable["forecast_mw"] = usable["forecast_mw"] - usable["correction_mw"]

    raw = summary(
        scored.loc[usable.index].assign(
            error_mw=scored.loc[usable.index, "error_mw"],
            abs_error_mw=scored.loc[usable.index, "error_mw"].abs(),
        ),
        capacity_mw,
    )
    corrected = summary(usable, capacity_mw)
    return {
        "available": True,
        "lookback_days": lookback_days,
        "scored_hours": int(len(usable)),
        "mean_correction_mw": _f(usable["correction_mw"].mean()),
        "raw": raw,
        "corrected": corrected,
        "mae_reduction_pct": _f(
            100.0 * (1 - corrected["mae_mw"] / raw["mae_mw"]) if raw["mae_mw"] else None
        ),
        "rmse_reduction_pct": _f(
            100.0 * (1 - corrected["rmse_mw"] / raw["rmse_mw"]) if raw["rmse_mw"] else None
        ),
    }


def by_lead_time(lead_df: pd.DataFrame, bucket_hours: int = 6) -> list[dict]:
    if lead_df.empty:
        return []
    df = lead_df.copy()
    df = df.loc[(df["lead_hours"] >= 0) & (df["lead_hours"] <= 48)]
    df["bucket"] = (df["lead_hours"] // bucket_hours).astype(int) * bucket_hours
    out = []
    for bucket, g in df.groupby("bucket"):
        out.append(
            {
                "lead_from_hours": int(bucket),
                "lead_to_hours": int(bucket) + bucket_hours,
                "label": f"{int(bucket)}-{int(bucket) + bucket_hours}h",
                "hours": int(len(g)),
                "mae_mw": _f(g["abs_error_mw"].mean()),
                "rmse_mw": _f(np.sqrt(np.mean(g["error_mw"].to_numpy(dtype=float) ** 2))),
                "bias_mw": _f(g["error_mw"].mean()),
            }
        )
    return sorted(out, key=lambda r: r["lead_from_hours"])


def by_publication_run(lead_df: pd.DataFrame, tz: str = MARKET_TZ) -> list[dict]:
    """Accuracy of each daily WINDFOR run, scored only on next-day delivery.

    Answers the "is it worth waiting for the next run" question directly, in
    the units of the auction timetable.
    """
    if lead_df.empty:
        return []
    df = lead_df.copy()
    df = df.loc[(df["lead_hours"] >= 12) & (df["lead_hours"] <= 48)]
    df["run"] = df["publish_time"].dt.tz_convert("UTC").dt.strftime("%H:%M")
    # Elexon occasionally issues an unscheduled republication (January 2026 has
    # a single 12:25 run). Those have a fraction of the observations of a real
    # run and are not something a desk can plan around, so they are excluded
    # rather than shown alongside the eight scheduled runs as if comparable.
    counts = df.groupby("run")["error_mw"].size()
    scheduled = counts[counts >= 0.25 * counts.max()].index
    df = df.loc[df["run"].isin(scheduled)]
    out = []
    for run, g in df.groupby("run"):
        out.append(
            {
                "run_utc": run,
                "hours": int(len(g)),
                "mae_mw": _f(g["abs_error_mw"].mean()),
                "rmse_mw": _f(np.sqrt(np.mean(g["error_mw"].to_numpy(dtype=float) ** 2))),
                "bias_mw": _f(g["error_mw"].mean()),
            }
        )
    return sorted(out, key=lambda r: r["run_utc"])


def error_histogram(df: pd.DataFrame, bin_mw: int = 500) -> list[dict]:
    err = df.dropna(subset=["error_mw"])["error_mw"].to_numpy(dtype=float)
    if err.size == 0:
        return []
    lo = int(np.floor(err.min() / bin_mw) * bin_mw)
    hi = int(np.ceil(err.max() / bin_mw) * bin_mw)
    edges = np.arange(lo, hi + bin_mw, bin_mw)
    counts, _ = np.histogram(err, bins=edges)
    total = counts.sum() or 1
    return [
        {
            "from_mw": int(edges[i]),
            "to_mw": int(edges[i + 1]),
            "centre_mw": int((edges[i] + edges[i + 1]) / 2),
            "count": int(counts[i]),
            "share_pct": _f(100.0 * counts[i] / total),
        }
        for i in range(len(counts))
    ]
