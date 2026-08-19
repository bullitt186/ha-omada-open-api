"""Aggregation and rolling-window helpers for Omada threat heatmap sensors."""

from __future__ import annotations

from collections import Counter, defaultdict
import datetime as dt
from typing import Any

SAMPLE_IP_LIMIT = 5
TOP_SIGNATURE_LIMIT = 5
TOP_ACTIVITY_LIMIT = 5

# Rolling window lengths in seconds (named per the spec: v1 hard-codes these).
WINDOW_SECONDS: dict[str, int] = {
    "hourly": 3600,
    "daily": 86400,
    "weekly": 7 * 86400,
    "monthly": 30 * 86400,
}


def compute_window(window: str, *, now: dt.datetime | None = None) -> tuple[int, int]:
    """Compute the (start, end) Unix timestamps for a rolling window.

    Args:
        window: One of "hourly", "daily", "weekly", "monthly"
        now: Reference time (defaults to current UTC time)

    Returns:
        Tuple of (window_start, window_end) Unix timestamps in seconds

    """
    if now is None:
        now = dt.datetime.now(dt.UTC)
    end = int(now.timestamp())
    return end - WINDOW_SECONDS[window], end


def aggregate_threat_points(
    rows: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], int]:
    """Aggregate raw threat rows into heatmap points.

    Groups rows by (srcLatitude, srcLongitude, srcCountry). Rows missing
    source coordinates are excluded and counted as skipped.

    Args:
        rows: Raw threat-management row dictionaries

    Returns:
        Tuple of (points sorted by descending value, skipped_rows count)

    """
    grouped: dict[tuple[float, float, str], list[dict[str, Any]]] = defaultdict(list)
    skipped = 0

    for row in rows:
        lat = row.get("srcLatitude")
        lon = row.get("srcLongitude")
        if lat is None or lon is None:
            skipped += 1
            continue
        country = row.get("srcCountry") or "--"
        grouped[(float(lat), float(lon), str(country))].append(row)

    points: list[dict[str, Any]] = []
    for (lat, lon, country), items in grouped.items():
        signatures = Counter(str(item.get("signature") or "") for item in items)
        activities = Counter(str(item.get("activity") or "") for item in items)
        severities = Counter(str(item.get("severity")) for item in items)

        sample_ips: list[str] = []
        for item in items:
            src_ip = str(item.get("srcIp") or "")
            if src_ip and src_ip not in sample_ips:
                sample_ips.append(src_ip)
            if len(sample_ips) >= SAMPLE_IP_LIMIT:
                break

        points.append(
            {
                "lat": lat,
                "lon": lon,
                "country": country,
                "value": len(items),
                "sample_ips": sample_ips,
                "top_signatures": signatures.most_common(TOP_SIGNATURE_LIMIT),
                "top_activities": activities.most_common(TOP_ACTIVITY_LIMIT),
                "severities": dict(severities),
                "latest_time": max(int(item.get("time") or 0) for item in items),
            }
        )

    points.sort(key=lambda point: int(point["value"]), reverse=True)
    return points, skipped
