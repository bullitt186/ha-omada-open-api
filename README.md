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
- [Use Cases](#use-cases)
- [Options](#options)
- [Supported Devices](#supported-devices)
- [Known Limitations](#known-limitations)
- [Removing the Integration](#removing-the-integration)
- [Getting Help & Contributing](#getting-help--contributing)
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

> **Free cloud accounts won't work.** Omada Cloud/Central **Essentials** has no Open API support — confirmed by TP-Link support. Cloud mode needs the paid **Standard** tier or higher; otherwise use **Local** with a self-hosted controller. See [TROUBLESHOOTING.md](TROUBLESHOOTING.md#authentication-errors) for the resulting error.

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
| **Controller Type** | 1 – Controller type | Yes | `Cloud` (TP-Link cloud-hosted), `Local` (self-hosted controller), or `Fusion Gateway` (built-in controller). Determines the authentication method and API endpoint used. |
| **Region** | 2 – Region *(cloud only)* | Yes (cloud) | Cloud region where your controller is deployed: **United States**, **Europe**, or **Asia Pacific (Singapore)**. Sets the API base URL automatically. |
| **Controller URL** | 2 – Local URL *(local/fusion)* | Yes (local/fusion) | Full URL of your controller, including protocol and port (e.g., `https://192.168.1.100:8043` for local, `https://192.168.1.1` for Fusion). |
| **Username** | 2 – Fusion credentials *(fusion only)* | Yes (fusion) | Web interface login username for the Fusion Gateway. |
| **Password** | 2 – Fusion credentials *(fusion only)* | Yes (fusion) | Web interface login password for the Fusion Gateway. |
| **Omada ID** | 3 – Credentials *(local/cloud)* | Yes (local/cloud) | The MSP ID or Customer ID from your Open API application. Found in **Settings → Platform Integration → Open API** in the Omada controller. |
| **Client ID** | 3 – Credentials *(local/cloud)* | Yes (local/cloud) | OAuth2 Client ID from your Open API application. Generated when creating a new application in the controller. |
| **Client Secret** | 3 – Credentials *(local/cloud)* | Yes (local/cloud) | OAuth2 Client Secret from your Open API application. Shown once when the application is created — copy and store it securely. |
| **Sites** | 4 – Site selection | Yes | One or more Omada sites to monitor. Fusion gateways with a single site are auto-selected. All devices and clients under the selected sites become available as Home Assistant entities. |
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

## Use Cases

- **Network dashboard** — device status, client counts, CPU/memory, PoE budgets at a glance
- **Presence detection** — trigger lights/locks/thermostat from device trackers
- **PoE scheduling** — power cameras/APs/phones down at night, back up in the morning
- **Firmware management** — get notified and install updates from HA
- **Bandwidth alerts** — flag a client or app exceeding a traffic threshold
- **Guest network automation** — toggle SSID broadcast by time, presence, or switch
- **Infrastructure health** — alert on sustained high CPU/memory for proactive maintenance

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
- **Fusion Gateways**: TP-Link Omada Fusion series (built-in controller, no separate hardware controller required)
- **Access Points**: EAP series (WiFi 5/6/6E/7, indoor & outdoor)
- **Switches**: JetStream and Smart Managed switches (PoE and non-PoE)
- **Gateways**: ER and SafeStream series
- **Clients**: Any device connected to the Omada network (wireless and wired)

> **Fusion + Traditional side by side**: You can add both a Fusion Gateway and a traditional Omada controller in the same Home Assistant instance — each as its own integration entry with independent authentication and polling.

Device availability depends on your controller's firmware version and API access level. See [Features](#features) for the OC200 and free-cloud-tier limitations.

---

## Known Limitations

- **Cloud dependency**: Cloud controllers require internet connectivity
- **DPI required**: Application traffic monitoring needs DPI enabled on the gateway
- **Local controller**: Requires Open API enabled (not available on all firmware versions)
- **Fusion Gateway**: Single-site only; no Open API app creation UI (uses web-session auth instead)
- **API rate limits**: Respected automatically; rarely an issue with default polling intervals
- **Viewer-only credentials**: PoE and LED switches are not created; all monitoring entities still work

---

## Removing the Integration

**Settings → Devices & Services → TP-Link Omada Open API → ⋮ → Delete**, then confirm. This removes all entities and devices it created. To also clear config data/tokens, delete the `custom_components/omada_open_api` folder afterward.

---

## Getting Help & Contributing

Something not working? See [TROUBLESHOOTING.md](TROUBLESHOOTING.md). Want to contribute code, report a bug, or request a feature? See [CONTRIBUTING.md](CONTRIBUTING.md).

---

## License

This project is licensed under the **MIT License** — see [LICENSE](LICENSE) for details.

**Acknowledgments**: Home Assistant community, TP-Link for the Omada Open API, HACS for custom component distribution.

---

[![GitHub stars](https://img.shields.io/github/stars/bullitt186/ha-omada-open-api.svg?style=social)](https://github.com/bullitt186/ha-omada-open-api/stargazers)
[![GitHub forks](https://img.shields.io/github/forks/bullitt186/ha-omada-open-api.svg?style=social)](https://github.com/bullitt186/ha-omada-open-api/network)
