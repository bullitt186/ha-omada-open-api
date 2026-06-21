## What's New in v1.7.0

### Features

- Added threat heatmap sensors: for each selected site, the integration now creates `sensor.<site>_threat_heatmap_hourly`, `..._daily`, `..._weekly`, and `..._monthly` entities backed by the Omada Threat Management API. Each sensor's state is the raw threat count for a rolling time window (always relative to "now," never calendar-aligned), with attributes exposing aggregated points (location, country, severity, top signatures/activities) suitable for mapping.
- These sensors are designed to pair with the new [`ha-world-heatmap-card`](https://github.com/bullitt186/ha-world-heatmap-card) — a standalone Lovelace card that renders the heatmap on a world map. Install it separately; this integration only provides the backend sensors and registers no dashboard resources.
- Added a **Site Entity Settings** option to enable/disable the threat heatmap sensors per config entry (enabled by default). Controllers that don't support the Threat Management endpoint leave the sensors `unavailable` instead of blocking setup.
