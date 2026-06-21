# TP-Link Omada Open API Integration for Home Assistant

<p align="center">
  <img src="assets/logo@2x.png" alt="TP-Link Omada Open API" width="256">
</p>

[![HACS Custom](https://img.shields.io/badge/HACS-Custom-41BDF5.svg?style=for-the-badge)](https://github.com/hacs/integration)
[![GitHub Release](https://img.shields.io/github/release/bullitt186/ha-omada-open-api.svg?style=for-the-badge)](https://github.com/bullitt186/ha-omada-open-api/releases)
[![License](https://img.shields.io/github/license/bullitt186/ha-omada-open-api.svg?style=for-the-badge)](LICENSE)

**Monitor and control your TP-Link Omada SDN infrastructure directly from Home Assistant.**

[![My Home Assistant](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=omada_open_api)

---

## Disclaimer

> This integration is under active development and has been heavily developed with AI assistance. The maintainer cannot guarantee long-term support. Use at your own risk and always test in a non-production environment first. Contributions and feedback are welcome!

---

## Table of Contents

- [About](#about)
- [Features](#features)
- [Installation](#installation)
- [Configuration](#configuration)
- [Entities](#entities)
- [Automation Examples](#automation-examples)
- [Options](#options)
- [Supported Devices](#supported-devices)
- [Data Update](#data-update)
- [Use Cases](#use-cases)
- [Diagnostics](#diagnostics)
- [Removing the Integration](#removing-the-integration)
- [Troubleshooting](#troubleshooting)
- [Services](#services)
- [Reporting Issues](#reporting-issues)
- [Known Limitations](#known-limitations)
- [Development](#development)
- [Contributing](#contributing)
- [License](#license)

---

## About

Connects to your **TP-Link Omada SDN** controller (cloud or local) through the **Omada Open API** and exposes your infrastructure, clients, and security data as Home Assistant entities — monitoring, control, and automation triggers included. See [Features](#features) for the full breakdown.

Authentication uses **OAuth 2.0 Client Credentials** with fully automatic token refresh — set it up once and forget it.

---

## Features

Not every feature works on every setup — some need specific hardware:

| Feature | Platform(s) | Requires |
|---|---|---|
| Device status, CPU/memory, uptime, IP, firmware update/install | Sensor, Binary Sensor, Device Tracker, Button, Update | Any AP, switch, or gateway (install needs write access) |
| Wired client count, uplink device/port, link speed | Sensor | Device with confirmed wired ports (gateways always qualify) |
| Wireless client count, per-band stats, radio utilization, SSID & radio-band switches | Sensor, Switch | Access Point (per-band sensors disabled by default; switches need write access) |
| Temperature, public IP, WAN rate/total/latency/loss, WAN status | Sensor, Binary Sensor | Gateway |
| Application (DPI) traffic | Sensor | Gateway with DPI enabled, plus clients/apps selected in Options |
| PoE budget/used/remaining, per-port power & switch | Sensor, Switch | PoE-capable switch (switch needs write access) |
| Site-wide LED toggle, WLAN optimization | Switch, Button, Binary Sensor | Any site (needs write access) |
| Threat heatmap (rolling hourly/daily/weekly/monthly) | Sensor | Controller with the Omada Threat Management API — not on the free cloud tier (see below); can be disabled in Options |
| Client sensors, presence, block/unblock, reconnect | Sensor, Binary Sensor, Device Tracker, Switch, Button | Selected client (RSSI/SNR/power-save are wireless-only; block/unblock and reconnect need write access) |

> **World heatmap card:** Threat heatmap sensors feed the companion [`ha-world-heatmap-card`](https://github.com/bullitt186/ha-world-heatmap-card), a generic Lovelace card for any sensor exposing this attribute shape. This integration is backend-only — install the card separately to visualize the data.

> **Free cloud accounts won't work.** Omada Cloud/Central **Essentials** has no Open API support — confirmed by TP-Link support. Cloud mode needs the paid **Standard** tier or higher; otherwise use **Local** with a self-hosted controller. See [Authentication Errors](#authentication-errors) for the resulting error.

> **OC200 controllers don't support Open API**, regardless of licensing — a hardware limitation. Use a different hardware controller (e.g. OC300) or the free Software Controller instead.

> **Permissions:** Control entities (PoE/LED/SSID/radio-band switches, firmware install) need write-access credentials. Viewer-only credentials still get all monitoring entities; controls are detected and skipped automatically.

---

## Installation

### HACS (Recommended)

1. Open **HACS → Integrations → ⋮ → Custom repositories**
2. Add `https://github.com/bullitt186/ha-omada-open-api` as **Integration**
3. Search for **TP-Link Omada Open API**, click **Download**, then restart Home Assistant
4. Go to **Settings → Devices & Services → Add Integration** and search for **TP-Link Omada Open API**

[![My Home Assistant](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=omada_open_api)

### Manual

1. Download the [latest release](https://github.com/bullitt186/ha-omada-open-api/releases) and copy the `omada_open_api` folder into your `custom_components/` directory
2. Restart Home Assistant
3. Add the integration via **Settings → Devices & Services**

---

## Configuration

### Obtaining API Credentials

1. Log in to the [TP-Link Omada Cloud Portal](https://omada.tplinkcloud.com)
2. Go to **Settings → Platform Integration → OpenAPI** (or your controller's equivalent)
3. Create an application to obtain your **Client ID**, **Client Secret**, and note your **Omada ID** (controller ID)

### Setup Flow

The integration guides you through a multi-step configuration:

1. **Controller type** — Cloud or local
2. **Region** (cloud) or **API URL** (local)
3. **Credentials** — Omada ID, Client ID, Client Secret
4. **Sites** — Select one or more sites to monitor
5. **Clients** *(optional)* — Select clients for presence detection and detailed monitoring
6. **Applications** *(optional)* — Select DPI-tracked applications for per-client traffic sensors (requires DPI enabled on your gateway)

### Installation Parameters

The following parameters are required during the initial setup flow:

| Parameter | Step | Required | Description |
|---|---|---|---|
| **Controller Type** | 1 – Controller type | Yes | `Cloud` (TP-Link cloud-hosted) or `Local` (self-hosted controller). Determines the API endpoint used. |
| **Region** | 2 – Region *(cloud only)* | Yes (cloud) | Cloud region where your controller is deployed: **United States**, **Europe**, or **Asia Pacific (Singapore)**. Sets the API base URL automatically. |
| **Controller URL** | 2 – Local URL *(local only)* | Yes (local) | Full URL of your self-hosted controller, including protocol and port (e.g., `https://192.168.1.100:8043`). |
| **Omada ID** | 3 – Credentials | Yes | The MSP ID or Customer ID from your Open API application. Found in **Settings → Platform Integration → Open API** in the Omada controller. |
| **Client ID** | 3 – Credentials | Yes | OAuth2 Client ID from your Open API application. Generated when creating a new application in the controller. |
| **Client Secret** | 3 – Credentials | Yes | OAuth2 Client Secret from your Open API application. Shown once when the application is created — copy and store it securely. |
| **Sites** | 4 – Site selection | Yes | One or more Omada sites to monitor. All devices and clients under the selected sites become available as Home Assistant entities. |
| **Clients** | 5 – Client selection | No | Network clients to track for presence detection and per-client metrics. Can be modified later via Options. Limited to the first 200 clients in the UI. |
| **Applications** | 6 – Application selection | No | DPI-tracked applications for per-client traffic monitoring (upload/download sensors). Requires DPI enabled on the gateway. Can be modified later via Options. |

**Network requirements:**
- Cloud: outbound HTTPS (443) to TP-Link cloud
- Local: network access to your controller's API port

---

## Entities

### Per Device (AP, Switch, Gateway)

| Entity | Example | Description |
|---|---|---|
| Sensor | `sensor.office_ap_connected_clients` | Connected client count |
| Sensor | `sensor.office_ap_uptime` | Uptime as a timestamp |
| Sensor | `sensor.office_ap_cpu_utilization` | CPU usage (%) |
| Sensor | `sensor.office_ap_memory_utilization` | Memory usage (%) |
| Sensor | `sensor.office_ap_clients_2_4_ghz` | 2.4 GHz clients (APs only) |
| Sensor | `sensor.office_ap_clients_5_ghz` | 5 GHz clients (APs only) |
| Sensor | `sensor.main_switch_poe_power_used` | PoE power draw (W) |
| Sensor | `sensor.main_switch_poe_power_budget` | PoE power budget (W) |
| Sensor | `sensor.main_switch_poe_power_remaining` | PoE remaining (%) |
| Sensor | `sensor.main_switch_port_3_poe_power` | Per-port PoE power (W) |
| Binary Sensor | `binary_sensor.office_ap_status` | Online / offline |
| Binary Sensor | `binary_sensor.office_ap_firmware_update_available` | Firmware update needed |
| Device Tracker | `device_tracker.office_ap` | Device presence (home/away) |
| Switch | `switch.main_switch_port_3_poe` | PoE on/off per port |
| Switch | `switch.home_led` | Site-wide LED on/off |
| Button | `button.office_ap_reboot` | Reboot device |
| Button | `button.office_ap_locate` | Flash LEDs / beep to locate |
| Button | `button.home_wlan_optimization` | Start WLAN optimization |
| Update | `update.office_ap_firmware` | Firmware with install action |

### Per Client

| Entity | Example | Description |
|---|---|---|
| Sensor | `sensor.johns_iphone_ip_address` | Current IP |
| Sensor | `sensor.johns_iphone_rssi` | Signal strength (dBm) |
| Sensor | `sensor.johns_iphone_snr` | Signal-to-noise ratio (dB) |
| Sensor | `sensor.johns_iphone_ssid` | Connected network |
| Sensor | `sensor.johns_iphone_connected_to` | Connected AP / switch |
| Sensor | `sensor.johns_iphone_downloaded` | Total downloaded (MB) |
| Sensor | `sensor.johns_iphone_uploaded` | Total uploaded (MB) |
| Sensor | `sensor.johns_iphone_rx_activity` | RX rate (MB/s) |
| Sensor | `sensor.johns_iphone_tx_activity` | TX rate (MB/s) |
| Sensor | `sensor.johns_iphone_uptime` | Client uptime |
| Binary Sensor | `binary_sensor.johns_iphone_power_save` | Power-save mode (wireless) |
| Device Tracker | `device_tracker.johns_iphone` | Presence detection |
| Switch | `switch.johns_iphone_network_access` | Block / unblock client |
| Button | `button.johns_iphone_reconnect` | Reconnect wireless client |

### Per Client + Application (DPI)

| Entity | Example | Description |
|---|---|---|
| Sensor | `sensor.johns_iphone_youtube_download` | App download traffic (auto-scaled) |
| Sensor | `sensor.johns_iphone_youtube_upload` | App upload traffic (auto-scaled) |

Application traffic sensors auto-scale their unit (B, KB, MB, GB, TB) and reset daily at midnight.

### Per Site — Threat Heatmap

| Entity | Example | Description |
|---|---|---|
| Sensor | `sensor.office_site_threat_heatmap_hourly` | Threat count, rolling last 60 minutes |
| Sensor | `sensor.office_site_threat_heatmap_daily` | Threat count, rolling last 24 hours |
| Sensor | `sensor.office_site_threat_heatmap_weekly` | Threat count, rolling last 7 days |
| Sensor | `sensor.office_site_threat_heatmap_monthly` | Threat count, rolling last 30 days |

One set of four per selected site. State is the raw threat count for a rolling window (relative to "now", never calendar-aligned). Attributes carry `source`, `site_id`, `site_name`, `window`, `window_start`/`window_end`, `total_rows`, `fetched_rows`, `skipped_rows`, `max`, and a `points` array (`lat`, `lon`, `country`, `value`, sample IPs, top signatures/activities, severities) — the shape [`ha-world-heatmap-card`](https://github.com/bullitt186/ha-world-heatmap-card) consumes. Disable under **Options → Site Entity Settings**; unsupported controllers just leave the sensors `unavailable`.

---

## Automation Examples

### Alert When an AP Goes Offline

```yaml
automation:
  - alias: "AP offline alert"
    trigger:
      - platform: state
        entity_id: binary_sensor.living_room_ap_status
        to: "off"
    action:
      - action: notify.mobile_app
        data:
          title: "Network Alert"
          message: "Living Room AP is offline!"
```

### Presence-Based Welcome Home

```yaml
automation:
  - alias: "Welcome home"
    trigger:
      - platform: state
        entity_id: device_tracker.johns_iphone
        to: "home"
    action:
      - action: light.turn_on
        target:
          entity_id: light.entrance
```

### High CPU Alert

```yaml
automation:
  - alias: "High CPU on switch"
    trigger:
      - platform: numeric_state
        entity_id: sensor.main_switch_cpu_utilization
        above: 80
        for: "00:05:00"
    action:
      - action: persistent_notification.create
        data:
          title: "Performance Alert"
          message: "Main switch CPU above 80% for 5 minutes"
```

### Disable PoE at Night

```yaml
automation:
  - alias: "Disable PoE on port 5 at night"
    trigger:
      - platform: time
        at: "23:00:00"
    action:
      - action: switch.turn_off
        target:
          entity_id: switch.main_switch_port_5_poe
```

---

## Options

After initial setup, go to **Settings → Devices & Services → TP-Link Omada Open API → Configure** to access a menu with the following configuration options:

### Client Selection

Add or remove tracked network clients. Select clients that should have device tracker entities and per-client sensors (IP, RSSI, SNR, traffic, etc.) created in Home Assistant.

| Parameter | Type | Description |
|---|---|---|
| **Clients to Track** | Multi-select | List of network clients discovered on your Omada network. Select one or more to create entities. Deselecting a client removes its entities and device. Limited to 200 clients in the UI. |

### Application Selection

Add or remove tracked DPI applications for per-client traffic monitoring. Each selected application creates upload and download sensors for every tracked client.

| Parameter | Type | Description |
|---|---|---|
| **Applications to Track** | Multi-select | List of DPI-tracked applications discovered on your network. Requires DPI (Deep Packet Inspection) to be enabled on your gateway. Traffic data resets daily at midnight. |

### Update Intervals

Configure how frequently each data type is polled from the Omada controller. Lower values give more responsive updates but increase API load.

| Parameter | Default | Range | Description |
|---|---|---|---|
| **Device polling interval** | 60 s | 10 – 3600 s | How often infrastructure device data (APs, switches, gateways) is refreshed. Affects status, CPU, memory, uptime, PoE, and firmware sensors. |
| **Client polling interval** | 30 s | 10 – 3600 s | How often client data is refreshed. Affects device trackers, RSSI, SNR, traffic, and activity rate sensors. |
| **Application traffic polling interval** | 300 s | 10 – 3600 s | How often per-client application traffic data is refreshed. Higher values recommended since DPI data updates less frequently on the controller. |

### Site Entity Settings

| Parameter | Default | Description |
|---|---|---|
| **Threat heatmap sensors** | Enabled | Enables/disables the four threat heatmap sensors (hourly/daily/weekly/monthly) per site. Disable if your controller doesn't support the Omada Threat Management endpoint. |

---

## Supported Devices

All TP-Link Omada SDN devices accessible via the Open API are supported:

- **Controllers**: OC200, OC300, software controllers, cloud-managed controllers
- **Access Points**: EAP series (WiFi 5/6/6E/7, indoor & outdoor)
- **Switches**: JetStream and Smart Managed switches (PoE and non-PoE)
- **Gateways**: ER and SafeStream series
- **Clients**: Any device connected to the Omada network (wireless and wired)

Device availability depends on your controller's firmware version and API access level.

---

## Data Update

The integration uses Home Assistant's **DataUpdateCoordinator** pattern to fetch data efficiently from the Omada Open API. Three separate coordinators handle different data types, each with its own polling interval:

| Coordinator | Default Interval | Data Fetched |
|---|---|---|
| **Device Coordinator** | 60 s | Infrastructure devices (APs, switches, gateways), SSIDs, PoE budgets, AP band stats, gateway temperature, uplink info, AP SSID overrides |
| **Client Coordinator** | 30 s | Connected clients (IP, MAC, RSSI, SNR, traffic, activity rates), device tracker state |
| **App Traffic Coordinator** | 300 s | Per-client application traffic (upload/download) from DPI data, queried from midnight to now, resets daily |

### Polling Architecture

- **One coordinator per site** — each selected site gets its own set of coordinators
- **Hierarchical fetch** — device data merges supplementary info (uplink, band stats, temperature, PoE) in a single update cycle
- **Token management** — OAuth2 tokens refresh automatically 5 minutes before expiry; expired refresh tokens trigger full re-authentication using client credentials
- **Error recovery** — transient API failures raise `UpdateFailed`, triggering HA's automatic back-off and retry. Authentication errors raise `ConfigEntryAuthFailed`, prompting a reauth flow

All polling intervals are configurable via **Options → Update Intervals** (range: 10–3600 s).

---

## Use Cases

- **Network dashboard** — device status, client counts, CPU/memory, PoE budgets at a glance
- **Presence detection** — trigger lights/locks/thermostat from device trackers
- **PoE scheduling** — power cameras/APs/phones down at night, back up in the morning
- **Firmware management** — get notified and install updates from HA
- **Bandwidth alerts** — flag a client or app exceeding a traffic threshold
- **Guest network automation** — toggle SSID broadcast by time, presence, or switch
- **Infrastructure health** — alert on sustained high CPU/memory for proactive maintenance

---

## Diagnostics

**Settings → Devices & Services → TP-Link Omada Open API → ⋮ → Download diagnostics** produces a JSON file with config data, coordinator summaries (device/client counts, tracked apps), write-access status, and site device info. Tokens, secrets, MAC addresses, and IPs are redacted automatically.

---

## Removing the Integration

**Settings → Devices & Services → TP-Link Omada Open API → ⋮ → Delete**, then confirm. This removes all entities and devices it created. To also clear config data/tokens, delete the `custom_components/omada_open_api` folder afterward.

---
## Troubleshooting

### Integration Not Loading

1. Check Home Assistant logs at **Settings → System → Logs**
2. Verify `custom_components/omada_open_api/manifest.json` exists
3. Restart Home Assistant after installation

### Authentication Errors

1. Double-check Client ID, Client Secret, and Omada ID — no extra spaces
2. Verify region (cloud) or API URL (local) is correct
3. Ensure outbound HTTPS is not blocked by a firewall
4. Use **Settings → Devices & Services → TP-Link Omada Open API → Reauthenticate** to re-enter credentials

> **"Controller ID not exist" (error -7131)?** Re-copying the Omada ID won't help — the free Essentials tier has no Open API at all (see [Features](#features)). Upgrade to Standard, or switch to **Local** with a self-hosted controller.

### No Entities Created

1. Verify you selected at least one site during setup
2. Check that devices and clients exist in your Omada Controller
3. Check logs for coordinator update errors

### Missing Application Traffic Sensors

1. Enable **DPI** on your gateway: Omada Controller → Gateway → Settings → DPI
2. Verify applications were selected during setup (or add them via Options → Application selection)
3. Application data resets daily at midnight

### Entities Showing "Unavailable"

1. Confirm the device is online in the Omada Controller
2. Check logs for API errors
3. Try increasing the polling interval via Options if you hit rate limits

### Token Errors

Token refresh is fully automatic. If you see persistent token errors in logs, use the **Reauthenticate** flow to obtain fresh credentials.

### Reconfiguring the Integration

To change the controller type, API URL, credentials, or selected sites without deleting and re-adding the integration, use **Settings → Devices & Services → TP-Link Omada Open API → ⋮ → Reconfigure**. The reconfigure flow walks through the same steps as initial setup and preserves your options (clients, applications, intervals).

### Repair Notifications

The integration may create repair notifications under **Settings → Repairs**:

- **Read-only API credentials** — Your API application has viewer-only permissions. Device controls (PoE, LED, reboot) are unavailable. Update the application permissions in your Omada controller.
- **No gateway for DPI tracking** — You selected applications for traffic tracking but no gateway was found. DPI requires an Omada gateway in your network.

---


## Services

### `omada_open_api.debug_ssid_switches`

Dumps SSID switch entity diagnostics for a config entry to the HA log — useful when entities aren't created as expected.

```yaml
service: omada_open_api.debug_ssid_switches
data:
  config_entry_id: "your_config_entry_id_here"  # from the entity registry
```

---

## Reporting Issues

Use our [issue templates](https://github.com/bullitt186/ha-omada-open-api/issues/new/choose): [Bug Report](https://github.com/bullitt186/ha-omada-open-api/issues/new?template=bug_report.yml) (fill all required fields) or [Feature Request](https://github.com/bullitt186/ha-omada-open-api/issues/new?template=feature_request.yml) (describe the problem, not just the fix). For general questions, use the [Community forum](https://community.home-assistant.io/) instead.

Before reporting a bug, gather:

1. Debug logs — **⋮ → Enable debug logging**, reproduce the issue, then **Settings → System → Logs** (strip tokens/secrets)
2. Diagnostics — **⋮ → Download diagnostics**
3. Your environment — HA version, install type, integration version, Omada Controller version, cloud or local

---
## Known Limitations

- **Cloud dependency**: Cloud controllers require internet connectivity
- **DPI required**: Application traffic monitoring needs DPI enabled on the gateway
- **Local controller**: Requires Open API enabled (not available on all firmware versions)
- **API rate limits**: Respected automatically; rarely an issue with default polling intervals
- **Viewer-only credentials**: PoE and LED switches are not created; all monitoring entities still work

---

## Development

This project uses VS Code devcontainers for a consistent development environment.

### Prerequisites

- Docker ([Desktop](https://docs.docker.com/desktop/) or [Engine](https://docs.docker.com/engine/install/))
- [Visual Studio Code](https://code.visualstudio.com/) with the [Dev Containers](https://marketplace.visualstudio.com/items?itemName=ms-vscode-remote.remote-containers) extension

### Getting Started

```bash
git clone https://github.com/bullitt186/ha-omada-open-api.git
cd ha-omada-open-api
# Open in VS Code → Reopen in Container
# Dev HA instance at http://localhost:8123
```

### Code Quality

Pre-commit hooks enforce **Ruff** (lint + format), **Pylint**, **Mypy**, and **pytest with a coverage gate** on every commit.

```bash
ruff check custom_components/ && ruff format --check custom_components/
mypy custom_components/omada_open_api/
pytest tests/ -v
pytest tests/ --cov=custom_components.omada_open_api --cov-report=html
```

---

## Contributing

Contributions are welcome — bug reports, feature requests, pull requests, documentation, and testing with different Omada setups.

1. Fork the repository
2. Create a feature branch
3. Make changes and add tests
4. Ensure all checks pass (`pytest`, `ruff`, `mypy`, `pylint`)
5. Open a pull request

---

## License

This project is licensed under the **MIT License** — see [LICENSE](LICENSE) for details.

**Acknowledgments**: Home Assistant community, TP-Link for the Omada Open API, HACS for custom component distribution.

---

[![GitHub stars](https://img.shields.io/github/stars/bullitt186/ha-omada-open-api.svg?style=social)](https://github.com/bullitt186/ha-omada-open-api/stargazers)
[![GitHub forks](https://img.shields.io/github/forks/bullitt186/ha-omada-open-api.svg?style=social)](https://github.com/bullitt186/ha-omada-open-api/network)
