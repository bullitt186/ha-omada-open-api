## What's New in v1.6.0

### Features

- **AP radio on/off switches** — Toggle individual Wi-Fi radio bands (2.4 GHz, 5 GHz, 5 GHz-2, 6 GHz) per access point directly from Home Assistant. Only bands supported by the AP hardware are shown. (Issue #5)
- **WLAN optimization running sensor** — Binary sensor that shows when an Omada RF planning scan is in progress. Appears under the site device as a diagnostic entity. (Issue #7)
- **RX/TX activity rate sensors for APs** — Real-time throughput sensors (MB/s) for each access point, updated every coordinator cycle (~60 seconds). (Issue #8)
- **SSID-based client filter in setup/options** — When selecting clients to track, an optional SSID filter lets you narrow the list to specific wireless networks. Wired clients are always shown. (Issue #9)
- **Configurable disconnect timeout** — Prevent false "away" events for client device trackers. Set a grace period (0–60 minutes) in Options → Device Tracker Settings before a client is marked as not home after disconnecting. (Issue #10)
- **Granular entity type toggles** — Reduce entity clutter by disabling entire categories. Options → Device Entity Settings and Options → Client Entity Settings let you turn off bandwidth sensors, diagnostic sensors, signal sensors, radio utilization sensors, block switches, and reconnect buttons independently. (Issue #11)

### Improvements

- AP radio utilization sensors (TX/RX/interference per band) are now registered as disabled-by-default diagnostic entities — enable them individually in the HA entity registry.
- HTTP 404 responses from unsupported API endpoints (e.g. RF planning on older firmware) are now logged at DEBUG level instead of ERROR, eliminating log spam on controllers that don't support every feature.
- Development environment: added `docker-compose.yml` and `make devcontainer` / `make devcontainer-down` targets for launching a local HA instance outside VS Code. `make deploy` now only targets the local devcontainer — it can never write to a remote host.

### Bug Fixes

- Fixed WLAN optimization binary sensor appearing under a new "unknown" device instead of the correct site device.
- Fixed RX/TX activity rate sensors remaining unavailable for the first 5+ minutes after startup. Rates now compute from the second coordinator poll (~60 seconds after startup).
- Fixed RX/TX activity sensors being incorrectly created for switches and gateways (which have no radio traffic counters). They are now AP-only.
