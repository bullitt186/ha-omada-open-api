# Omada Threat Heatmap POC

This POC validates the data and rendering path before adding Home Assistant
integration entities or a custom card.

## Data Source

Confirmed endpoint:

```text
GET /openapi/v1/{omadacId}/security/threat-management
```

The endpoint returns source coordinates directly:

- `srcLatitude`
- `srcLongitude`
- `srcCountry`
- `srcIp`
- `signature`
- `severity`
- `activity`
- `classification`
- `time`

The exporter aggregates rows by `(srcLatitude, srcLongitude, srcCountry)` and
writes `threat-heatmap-data.json` for the standalone page.

## Export Data

Pass credentials as shell environment variables. Do not commit credentials to
the repository.

```bash
OMADA_API_URL='https://omada.stahmer.lan:8043' \
OMADA_ID='...' \
OMADA_CLIENT_ID='...' \
OMADA_CLIENT_SECRET='...' \
python3 poc/threat-heatmap/export_threat_heatmap.py \
  --site-id 6761cac4d32f63353333586e \
  --days 30
```

The default output is:

```text
poc/threat-heatmap/threat-heatmap-data.json
```

## View the Standalone Page

The page uses `fetch()`, so serve the folder over HTTP:

```bash
cd poc/threat-heatmap
python3 -m http.server 8765
```

Then open:

```text
http://localhost:8765/
```

## Inspector Examples

The generic inspector can also probe the raw endpoint:

```bash
OMADA_API_URL='https://omada.stahmer.lan:8043' \
OMADA_ID='...' \
OMADA_CLIENT_ID='...' \
OMADA_CLIENT_SECRET='...' \
python3 scripts/omada_api_inspect.py security/threat-management \
  --max-pages 1 \
  --output raw-result \
  --param siteList=6761cac4d32f63353333586e \
  --param archived=false \
  --param filters.startTime=1780000000 \
  --param filters.endTime=1782000000 \
  --param sorts.time=desc
```

## POC Boundary

This does not add Home Assistant entities, coordinators, frontend resources, or
dashboard cards. Those decisions should happen after validating the POC output
and visual tuning.
