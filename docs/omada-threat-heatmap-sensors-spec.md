# Omada Threat Heatmap Sensors Specification

## Summary

Extend `ha-omada-open-api` so it exposes Omada Threat Management data as Home
Assistant sensors suitable for a generic world heatmap card.

The implementation target is backend-only: fetch, aggregate, and publish the
data. The reusable frontend card should live in a separate repository and
consume the sensor attributes described here.

The reference implementation is the POC under `poc/threat-heatmap/`:

- API probe and exporter: `poc/threat-heatmap/export_threat_heatmap.py`
- standalone renderer: `poc/threat-heatmap/index.html`

## Confirmed Source Endpoint

Use this Omada OpenAPI endpoint:

```text
GET /openapi/v1/{omadacId}/security/threat-management
```

Required query parameters:

- `siteList`: selected site ID.
- `archived`: `false` for active threat rows.
- `page`: starts at `1`.
- `pageSize`: use `100` or another safe value up to `1000`.
- `filters.startTime`: Unix timestamp in seconds.
- `filters.endTime`: Unix timestamp in seconds.
- `sorts.time`: `desc`.

The endpoint was verified against the Omada CSV export
`GlobalThreatManagement_2026-06-20-22-50_Global_1.csv`. A 30-day API query
returned exactly `667` rows, matching the CSV row count and country
distribution.

Relevant response fields:

- `time`
- `siteId`
- `siteName`
- `severity`
- `service`
- `signature`
- `category`
- `activity`
- `srcIp`
- `dstIp`
- `srcCountry`
- `dstCountry`
- `protocol`
- `srcLatitude`
- `srcLongitude`
- `dstLatitude`
- `dstLongitude`
- `classification`
- `archived`

Rows without `srcLatitude` or `srcLongitude` must be excluded from heatmap
points and counted in metadata.

## Entities to Create

Create one site-level heatmap sensor per selected site and time window:

- `sensor.<site>_threat_heatmap_daily`
- `sensor.<site>_threat_heatmap_weekly`
- `sensor.<site>_threat_heatmap_monthly`

The exact entity IDs may follow the integration's existing naming conventions,
but unique IDs must be stable and include site ID plus window:

```text
site_<site_id>_threat_heatmap_daily
site_<site_id>_threat_heatmap_weekly
site_<site_id>_threat_heatmap_monthly
```

Sensor state:

- Numeric count of raw threat rows in the window.
- `native_unit_of_measurement`: `threats`.
- `state_class`: `measurement`.

Recommended icon:

```text
mdi:map-marker-radius
```

## Time Windows

Implement fixed rolling windows:

- Daily: last `24` hours.
- Weekly: last `7` days.
- Monthly: last `30` days.

Use UTC timestamps for API parameters and metadata. Do not use calendar-local
midnight windows for v1; rolling windows are simpler, consistent, and match the
POC.

Recommended polling:

- Daily: refresh every `15` minutes.
- Weekly: refresh every `60` minutes.
- Monthly: refresh every `6` hours.

If implementation complexity is lower, all three may initially share one
coordinator with a `15` minute interval, but avoid unnecessary full 30-day
fetches every minute.

## Sensor Attribute Contract

Each sensor must expose a generic card-compatible attribute shape:

```json
{
  "source": "omada_open_api.security.threat-management",
  "site_id": "6761cac4d32f63353333586e",
  "site_name": "Calw",
  "window": "monthly",
  "window_start": 1779397184,
  "window_end": 1781989184,
  "total_rows": 667,
  "fetched_rows": 667,
  "skipped_rows": 5,
  "max": 435,
  "points": [
    {
      "lat": 35.0,
      "lon": 105.0,
      "country": "CN",
      "value": 23,
      "sample_ips": ["223.123.43.1"],
      "top_signatures": [
        ["ET EXPLOIT Apache HTTP Server 2.4.49 - Path Traversal Attempt (CVE-2021-41773) M2", 10]
      ],
      "top_activities": [["Attempted Administrator Privilege Gain", 18]],
      "severities": {"1": 22, "4": 1},
      "latest_time": 1781943373
    }
  ]
}
```

Required attributes:

- `source`
- `site_id`
- `site_name`
- `window`
- `window_start`
- `window_end`
- `total_rows`
- `fetched_rows`
- `skipped_rows`
- `max`
- `points`

Required point fields:

- `lat`
- `lon`
- `country`
- `value`

Optional point fields:

- `sample_ips`
- `top_signatures`
- `top_activities`
- `severities`
- `latest_time`

Keep `points` sorted by descending `value`.

## Aggregation Rules

Aggregate raw threat rows by:

```text
(srcLatitude, srcLongitude, srcCountry)
```

For each group:

- `lat`: `srcLatitude`
- `lon`: `srcLongitude`
- `country`: `srcCountry` or `"--"`
- `value`: number of rows in the group
- `sample_ips`: first unique source IPs, max `5`
- `top_signatures`: top `5` signatures with counts
- `top_activities`: top `5` activities with counts
- `severities`: counts keyed by Omada severity number as a string
- `latest_time`: max `time`

`max` is the maximum point `value`, or `0` when there are no points.

Known verified examples from the POC monthly data:

- `US`: `lat=38.0`, `lon=-97.0`, `value=435`
- `CN`: `lat=35.0`, `lon=105.0`, `value=23`
- `GB`: `lat=54.0`, `lon=-2.0`, `value=66`
- `DE`: `lat=51.0`, `lon=9.0`, `value=25`

## Coordinator and API Client Changes

Add an API client method:

```python
async def get_threat_management(
    self,
    *,
    site_id: str,
    start_time: int,
    end_time: int,
    archived: bool = False,
    page_size: int = 100,
) -> list[dict[str, Any]]:
```

Implementation notes:

- Fetch all pages until `len(rows) >= totalRows` or the page returns fewer than
  `pageSize` rows.
- Use the existing authenticated request helper.
- Treat `404` or unsupported endpoint errors as unavailable data for the
  coordinator, not as integration setup failure.

Add one coordinator or coordinator family for threat heatmap windows. It should:

- be per site,
- know the rolling window duration,
- call the API method,
- aggregate points,
- expose a compact data dictionary consumed by sensor entities.

## Configuration and Options

Add an integration option to enable/disable threat heatmap sensors. Default:
enabled if the endpoint works during setup or first update; otherwise entities
may remain unavailable.

Optional v1 configuration:

- `enable_threat_heatmap_sensors`: boolean, default `true`.
- `threat_heatmap_daily_interval`: default `900` seconds.
- `threat_heatmap_weekly_interval`: default `3600` seconds.
- `threat_heatmap_monthly_interval`: default `21600` seconds.

If adding UI options is too large for the first implementation, hard-code the
windows and intervals but keep constants named so options can be added later.

## Availability and Error Handling

Sensors should be unavailable when:

- the endpoint returns an authorization error,
- the endpoint is unsupported,
- the API call fails and there is no previous data.

If a refresh fails after prior successful data:

- keep the last data in coordinator state if that matches existing integration
  patterns,
- mark availability according to Home Assistant coordinator behavior,
- log concise diagnostics without dumping full threat rows.

Do not include credentials or tokens in diagnostics.

## Tests

Add focused unit tests for:

- API pagination of `security/threat-management`.
- Aggregation by `(srcLatitude, srcLongitude, srcCountry)`.
- Skipping rows without coordinates.
- `max`, `total_rows`, `fetched_rows`, `skipped_rows`, and sorted points.
- Daily, weekly, and monthly window timestamp calculations.
- Sensor state equals raw total threat row count.
- Sensor attributes match the contract consumed by the custom card.
- Endpoint error handling leaves sensors unavailable or data empty as intended.

Use fixture rows based on the POC shape; do not include live IPs from the local
network in committed tests unless anonymized.

## Acceptance Criteria

- The monthly sensor can reproduce the POC shape generated by
  `poc/threat-heatmap/export_threat_heatmap.py`.
- The generic custom card can render each of the three sensors without Omada
  specific code.
- Daily, weekly, and monthly entities are created for each selected site.
- No new frontend/dashboard resources are registered by this integration.
- Generated attributes remain small enough for Home Assistant state attributes
  in typical home deployments. If very large installations produce too many
  points, cap points by descending value with a clear metadata field such as
  `truncated_points: true`.

## Out of Scope for v1

- ACL log ingestion.
- Syslog listener.
- MaxMind or other GeoIP enrichment.
- Direct support for Omada `security/threat-map`, which returned empty data in
  the live POC.
- Frontend custom card implementation inside this repository.
