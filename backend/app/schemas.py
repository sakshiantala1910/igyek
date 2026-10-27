"""Response models. These double as the API contract the frontend types mirror."""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class HourRow(BaseModel):
    start_time: str
    local_time: str
    forecast_mw: float | None = None
    actual_mw: float | None = None
    error_mw: float | None = None
    lead_hours: float | None = None
    band_low_mw: float | None = Field(
        default=None, description="Lower edge of the empirical uncertainty band"
    )
    band_high_mw: float | None = None


class DayResponse(BaseModel):
    delivery_date: str
    deadline_local: str
    deadline_utc: str
    vintage_publish_time: str | None
    vintage_age_minutes: float | None
    forecast_horizon_hours: float | None
    band_method: str
    band_confidence_pct: float
    hours: list[HourRow]
    summary: dict[str, Any]
    cover: list[dict[str, Any]]


class AccuracyResponse(BaseModel):
    window: dict[str, Any]
    summary: dict[str, Any]
    persistence: dict[str, Any]
    bias_correction: dict[str, Any]
    cover: list[dict[str, Any]]
    histogram: list[dict[str, Any]]
    by_hour_of_day: list[dict[str, Any]]
    by_day: list[dict[str, Any]]
    by_output_band: list[dict[str, Any]]


class LeadTimeResponse(BaseModel):
    window: dict[str, Any]
    by_lead_time: list[dict[str, Any]]
    by_publication_run: list[dict[str, Any]]
