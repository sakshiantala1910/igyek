"""Integration tests against the committed snapshot.

These run on the real January 2026 data, so they double as a guard on the data
itself: if a future snapshot rebuild loses days or changes resolution, these
fail rather than quietly shifting every headline number.
"""
import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


@pytest.fixture(scope="module")
def accuracy():
    resp = client.get("/api/accuracy")
    assert resp.status_code == 200
    return resp.json()


def test_health():
    assert client.get("/api/health").json() == {"status": "ok"}


def test_meta_describes_the_study_window():
    meta = client.get("/api/meta").json()
    assert meta["decision_window"] == {"from": "2026-01-01", "to": "2026-01-31"}
    assert meta["delivery_window"] == {"from": "2026-01-02", "to": "2026-02-01"}
    # Eight scheduled WINDFOR runs a day.
    assert "07:30" in meta["windfor_runs_utc"]


def test_accuracy_scores_every_hour_of_every_delivery_day(accuracy):
    # 31 decisions -> 31 delivery days -> 744 hours, with none dropped.
    assert accuracy["window"]["scored_hours"] == 744
    assert accuracy["summary"]["days"] == 31


def test_accuracy_reports_the_january_over_forecast_lean(accuracy):
    """Regression guard on the headline finding."""
    s = accuracy["summary"]
    assert s["bias_mw"] > 1000, "January 2026 WINDFOR runs materially high"
    assert s["share_hours_short_pct"] > 75


def test_bias_correction_beats_the_raw_forecast(accuracy):
    bc = accuracy["bias_correction"]
    assert bc["available"] is True
    assert bc["corrected"]["mae_mw"] < bc["raw"]["mae_mw"]
    assert abs(bc["corrected"]["bias_mw"]) < abs(bc["raw"]["bias_mw"])


def test_forecast_beats_persistence(accuracy):
    assert accuracy["persistence"]["skill_score_pct"] > 0


def test_cover_table_is_monotonic(accuracy):
    buffers = [row["buffer_mw"] for row in accuracy["cover"]]
    assert buffers == sorted(buffers)


def test_day_uses_a_vintage_published_before_gate_closure():
    day = client.get("/api/day", params={"date": "2026-01-15"}).json()
    assert day["vintage_publish_time"] == "2026-01-14T07:30:00Z"
    assert day["vintage_age_minutes"] == 120.0
    assert len(day["hours"]) == 24


def test_day_band_brackets_most_outturns():
    day = client.get(
        "/api/day", params={"date": "2026-01-20", "confidence": 0.8}
    ).json()
    inside = [
        h
        for h in day["hours"]
        if h["actual_mw"] is not None
        and h["band_low_mw"] <= h["actual_mw"] <= h["band_high_mw"]
    ]
    assert len(inside) >= len(day["hours"]) // 2


def test_day_rejects_a_malformed_deadline():
    resp = client.get("/api/day", params={"date": "2026-01-15", "deadline": "half nine"})
    assert resp.status_code == 422


def test_day_404s_outside_the_snapshot():
    assert client.get("/api/day", params={"date": "2024-01-15"}).status_code == 404


def test_accuracy_rejects_an_inverted_window():
    resp = client.get("/api/accuracy", params={"from": "2026-01-20", "to": "2026-01-10"})
    assert resp.status_code == 422


def test_leadtime_error_grows_with_horizon():
    lead = client.get("/api/leadtime").json()
    buckets = lead["by_lead_time"]
    assert buckets[0]["mae_mw"] < buckets[-1]["mae_mw"]


def test_publication_runs_exclude_unscheduled_republications():
    """A one-off 12:25 run with a handful of points is not a comparable run."""
    runs = client.get("/api/leadtime").json()["by_publication_run"]
    assert [r["run_utc"] for r in runs] == [
        "02:30",
        "04:30",
        "07:30",
        "09:30",
        "11:30",
        "15:30",
        "18:30",
        "22:30",
    ]
