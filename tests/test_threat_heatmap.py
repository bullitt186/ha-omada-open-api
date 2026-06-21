"""Tests for threat heatmap aggregation and window calculations."""

from __future__ import annotations

import datetime as dt

from custom_components.omada_open_api.threat_heatmap import (
    aggregate_threat_points,
    compute_window,
)

ROW_US_1 = {
    "time": 100,
    "srcLatitude": 38.0,
    "srcLongitude": -97.0,
    "srcCountry": "US",
    "srcIp": "1.1.1.1",
    "signature": "ET EXPLOIT Foo",
    "activity": "Attempted Administrator Privilege Gain",
    "severity": 1,
}
ROW_US_2 = {
    "time": 200,
    "srcLatitude": 38.0,
    "srcLongitude": -97.0,
    "srcCountry": "US",
    "srcIp": "1.1.1.2",
    "signature": "ET EXPLOIT Foo",
    "activity": "Attempted Administrator Privilege Gain",
    "severity": 4,
}
ROW_CN_1 = {
    "time": 150,
    "srcLatitude": 35.0,
    "srcLongitude": 105.0,
    "srcCountry": "CN",
    "srcIp": "2.2.2.2",
    "signature": "ET SCAN Bar",
    "activity": "Network Scan",
    "severity": 2,
}
ROW_NO_COORDS = {
    "time": 50,
    "srcLatitude": None,
    "srcLongitude": None,
    "srcCountry": "DE",
}


def test_aggregate_groups_by_lat_lon_country() -> None:
    """Rows sharing (lat, lon, country) aggregate into one point."""
    points, skipped = aggregate_threat_points([ROW_US_1, ROW_US_2, ROW_CN_1])

    assert skipped == 0
    us_point = next(p for p in points if p["country"] == "US")
    assert us_point["lat"] == 38.0
    assert us_point["lon"] == -97.0
    assert us_point["value"] == 2


def test_aggregate_skips_rows_without_coordinates() -> None:
    """Rows missing srcLatitude/srcLongitude are excluded and counted."""
    points, skipped = aggregate_threat_points([ROW_US_1, ROW_NO_COORDS])

    assert skipped == 1
    assert len(points) == 1


def test_aggregate_sorts_points_by_descending_value() -> None:
    """Points are sorted by value, highest first."""
    points, _ = aggregate_threat_points([ROW_US_1, ROW_US_2, ROW_CN_1])

    assert [p["country"] for p in points] == ["US", "CN"]
    assert points[0]["value"] >= points[1]["value"]


def test_aggregate_point_fields() -> None:
    """Each point carries sample_ips, top_signatures/activities, severities, latest_time."""
    points, _ = aggregate_threat_points([ROW_US_1, ROW_US_2])

    point = points[0]
    assert point["sample_ips"] == ["1.1.1.1", "1.1.1.2"]
    assert point["top_signatures"] == [("ET EXPLOIT Foo", 2)]
    assert point["top_activities"] == [("Attempted Administrator Privilege Gain", 2)]
    assert point["severities"] == {"1": 1, "4": 1}
    assert point["latest_time"] == 200


def test_aggregate_caps_sample_ips_at_limit() -> None:
    """sample_ips stops growing once it reaches the 5-IP cap."""
    rows = [
        {
            "time": i,
            "srcLatitude": 38.0,
            "srcLongitude": -97.0,
            "srcCountry": "US",
            "srcIp": f"1.1.1.{i}",
        }
        for i in range(8)
    ]
    points, _ = aggregate_threat_points(rows)

    assert len(points[0]["sample_ips"]) == 5


def test_aggregate_empty_rows_returns_no_points() -> None:
    """No rows produces an empty point list and zero skipped."""
    points, skipped = aggregate_threat_points([])

    assert points == []
    assert skipped == 0


def test_compute_window_hourly() -> None:
    """Hourly window spans the last 60 minutes."""
    now = dt.datetime(2026, 6, 20, 12, 0, 0, tzinfo=dt.UTC)
    start, end = compute_window("hourly", now=now)

    assert end == int(now.timestamp())
    assert start == end - 3600


def test_compute_window_daily() -> None:
    """Daily window spans the last 24 hours."""
    now = dt.datetime(2026, 6, 20, 12, 0, 0, tzinfo=dt.UTC)
    start, end = compute_window("daily", now=now)

    assert end == int(now.timestamp())
    assert start == end - 86400


def test_compute_window_weekly() -> None:
    """Weekly window spans the last 7 days."""
    now = dt.datetime(2026, 6, 20, 12, 0, 0, tzinfo=dt.UTC)
    start, end = compute_window("weekly", now=now)

    assert end == int(now.timestamp())
    assert start == end - 7 * 86400


def test_compute_window_monthly() -> None:
    """Monthly window spans the last 30 days."""
    now = dt.datetime(2026, 6, 20, 12, 0, 0, tzinfo=dt.UTC)
    start, end = compute_window("monthly", now=now)

    assert end == int(now.timestamp())
    assert start == end - 30 * 86400
