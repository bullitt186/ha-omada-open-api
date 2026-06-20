#!/usr/bin/env python3
"""Export Omada Threat Management rows as simpleheat-ready point data."""

from __future__ import annotations

import argparse
import asyncio
from collections import Counter, defaultdict
import datetime as dt
import json
import os
from pathlib import Path
import sys
from typing import Any

import aiohttp

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT = Path(__file__).with_name("threat-heatmap-data.json")


def _load_dotenv() -> None:
    """Load repo-root .env values without overriding the current shell."""
    env_path = REPO_ROOT / ".env"
    if not env_path.exists():
        return
    for raw_line in env_path.read_text().splitlines():
        line = raw_line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip())


async def _get_token(
    session: aiohttp.ClientSession,
    api_url: str,
    omada_id: str,
    client_id: str,
    client_secret: str,
) -> str:
    """Fetch an Omada OpenAPI access token."""
    async with session.post(
        f"{api_url}/openapi/authorize/token",
        params={"grant_type": "client_credentials"},
        json={
            "omadacId": omada_id,
            "client_id": client_id,
            "client_secret": client_secret,
        },
        ssl=False,
    ) as response:
        data = await response.json()
    if data.get("errorCode") != 0:
        raise RuntimeError(f"Token request failed: {data}")
    return str(data["result"]["accessToken"])


async def _get_json(
    session: aiohttp.ClientSession,
    url: str,
    access_token: str,
    params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """GET JSON from an authenticated Omada endpoint."""
    async with session.get(
        url,
        headers={"Authorization": f"AccessToken={access_token}"},
        params=params,
        ssl=False,
    ) as response:
        data = await response.json()
    if data.get("errorCode") != 0:
        raise RuntimeError(f"API request failed: {data}")
    return data


async def _get_first_site(
    session: aiohttp.ClientSession,
    api_url: str,
    omada_id: str,
    access_token: str,
) -> str:
    """Return the first site ID from the controller."""
    data = await _get_json(
        session,
        f"{api_url}/openapi/v1/{omada_id}/sites",
        access_token,
        {"page": 1, "pageSize": 100},
    )
    sites = data.get("result", {}).get("data", [])
    if not sites:
        raise RuntimeError("No Omada sites returned by the API.")
    return str(sites[0]["siteId"])


async def _fetch_threats(
    session: aiohttp.ClientSession,
    api_url: str,
    omada_id: str,
    access_token: str,
    *,
    archived: bool,
    end_time: int,
    page_size: int,
    site_id: str,
    start_time: int,
) -> tuple[list[dict[str, Any]], int]:
    """Fetch all threat-management rows for the requested window."""
    rows: list[dict[str, Any]] = []
    page = 1
    total_rows = 0
    while True:
        params: dict[str, Any] = {
            "siteList": site_id,
            "archived": str(archived).lower(),
            "page": page,
            "pageSize": page_size,
            "filters.startTime": start_time,
            "filters.endTime": end_time,
            "sorts.time": "desc",
        }
        data = await _get_json(
            session,
            f"{api_url}/openapi/v1/{omada_id}/security/threat-management",
            access_token,
            params,
        )
        result = data.get("result", {})
        batch = result.get("data", [])
        total_rows = int(result.get("totalRows", 0))
        rows.extend(batch)
        print(  # noqa: T201
            f"Fetched page {page}: {len(batch)} rows "
            f"(total {total_rows}, fetched {len(rows)})",
            file=sys.stderr,
        )
        if len(rows) >= total_rows or len(batch) < page_size:
            break
        page += 1
    return rows, total_rows


def _aggregate_points(
    rows: list[dict[str, Any]],
    *,
    sample_ip_limit: int,
    top_signature_limit: int,
) -> list[dict[str, Any]]:
    """Aggregate threat rows by source coordinate and country."""
    grouped: dict[tuple[float, float, str], list[dict[str, Any]]] = defaultdict(list)
    skipped = 0
    for row in rows:
        lat = row.get("srcLatitude")
        lon = row.get("srcLongitude")
        country = row.get("srcCountry") or "--"
        if lat is None or lon is None:
            skipped += 1
            continue
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
            if len(sample_ips) >= sample_ip_limit:
                break

        points.append(
            {
                "lat": lat,
                "lon": lon,
                "country": country,
                "value": len(items),
                "sample_ips": sample_ips,
                "top_signatures": signatures.most_common(top_signature_limit),
                "top_activities": activities.most_common(5),
                "severities": dict(severities),
                "latest_time": max(int(item.get("time") or 0) for item in items),
            }
        )

    points.sort(key=lambda point: int(point["value"]), reverse=True)
    if skipped:
        print(f"Skipped {skipped} rows without source coordinates.", file=sys.stderr)  # noqa: T201
    return points


async def _async_main(args: argparse.Namespace) -> None:
    """Run the export."""
    _load_dotenv()

    api_url = os.environ.get("OMADA_API_URL", "").rstrip("/")
    omada_id = os.environ.get("OMADA_ID", "")
    client_id = os.environ.get("OMADA_CLIENT_ID", "")
    client_secret = os.environ.get("OMADA_CLIENT_SECRET", "")
    access_token = os.environ.get("OMADA_ACCESS_TOKEN", "")

    if not api_url or not omada_id:
        raise SystemExit("OMADA_API_URL and OMADA_ID must be set.")
    if not access_token and (not client_id or not client_secret):
        raise SystemExit(
            "Set OMADA_ACCESS_TOKEN or both OMADA_CLIENT_ID and OMADA_CLIENT_SECRET."
        )

    now = dt.datetime.now(dt.UTC)
    end_time = int(args.end.timestamp()) if args.end else int(now.timestamp())
    start_time = (
        int(args.start.timestamp())
        if args.start
        else int((now - dt.timedelta(days=args.days)).timestamp())
    )

    async with aiohttp.ClientSession() as session:
        if not access_token:
            print("Fetching access token...", file=sys.stderr)  # noqa: T201
            access_token = await _get_token(
                session,
                api_url,
                omada_id,
                client_id,
                client_secret,
            )

        site_id = args.site_id or await _get_first_site(
            session,
            api_url,
            omada_id,
            access_token,
        )
        rows, total_rows = await _fetch_threats(
            session,
            api_url,
            omada_id,
            access_token,
            archived=args.archived,
            end_time=end_time,
            page_size=args.page_size,
            site_id=site_id,
            start_time=start_time,
        )

    points = _aggregate_points(
        rows,
        sample_ip_limit=args.sample_ip_limit,
        top_signature_limit=args.top_signature_limit,
    )
    payload = {
        "source": "omada_open_api.security.threat-management",
        "site_id": site_id,
        "window_start": start_time,
        "window_end": end_time,
        "total_rows": total_rows,
        "fetched_rows": len(rows),
        "max": max((int(point["value"]) for point in points), default=0),
        "points": points,
    }

    output_path = Path(args.output)
    await asyncio.to_thread(output_path.parent.mkdir, parents=True, exist_ok=True)
    await asyncio.to_thread(
        output_path.write_text, json.dumps(payload, indent=2) + "\n"
    )
    print(  # noqa: T201
        f"Wrote {len(points)} heatmap points from {len(rows)} rows to {output_path}",
        file=sys.stderr,
    )


def _parse_datetime(value: str) -> dt.datetime:
    """Parse an ISO timestamp or YYYY-MM-DD date as UTC."""
    try:
        parsed = dt.datetime.fromisoformat(value)
    except ValueError as err:
        raise argparse.ArgumentTypeError(str(err)) from err
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=dt.UTC)
    return parsed.astimezone(dt.UTC)


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--site-id", help="Omada site ID. Defaults to the first site.")
    parser.add_argument("--days", type=int, default=30, help="Lookback window in days.")
    parser.add_argument("--start", type=_parse_datetime, help="UTC start timestamp.")
    parser.add_argument("--end", type=_parse_datetime, help="UTC end timestamp.")
    parser.add_argument(
        "--archived",
        action="store_true",
        help="Query archived threats instead of active threats.",
    )
    parser.add_argument("--page-size", type=int, default=100)
    parser.add_argument("--sample-ip-limit", type=int, default=5)
    parser.add_argument("--top-signature-limit", type=int, default=5)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args()

    if args.days < 1:
        raise SystemExit("--days must be at least 1.")
    if args.page_size < 1 or args.page_size > 1000:
        raise SystemExit("--page-size must be between 1 and 1000.")

    asyncio.run(_async_main(args))


if __name__ == "__main__":
    main()
