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
- [Troubleshooting](#troubleshooting)
- [Known Limitations](#known-limitations)
- [Development](#development)
- [Contributing](#contributing)
- [License](#license)

---

## About

This integration connects to your **TP-Link Omada SDN** controller through the **Omada Open API** and exposes your network infrastructure as Home Assistant devices and entities. It supports cloud-managed and locally-hosted controllers.

With it you can:

- Monitor access points, switches, and gateways (status, CPU, memory, uptime, PoE budgets)
- Track connected clients with presence detection
- Control PoE per switch port, toggle site-wide LEDs, and block/unblock clients
- Reboot devices, trigger locate (LED flash), reconnect wireless clients, and start WLAN optimization
- Install firmware updates directly from Home Assistant
- Monitor per-client application traffic when DPI is enabled
- Automate based on any of the above

Authentication uses **OAuth 2.0 Client Credentials** with fully automatic token refresh — set it up once and forget it.

---

## Features

| Platform | What it provides |
|---|---|
| **Sensor** | Device metrics (clients, uptime, CPU, memory, model, firmware, link speed, public IP, etc.), per-band client counts for APs, client metrics (IP, RSSI, SNR, SSID, traffic, activity rates), PoE budget & per-port power, per-app traffic |
| **Binary Sensor** | Device online/offline, firmware update available, client power-save mode |
| **Device Tracker** | Presence detection for devices (APs, switches, gateways) and selected clients |
| **Switch** | PoE enable/disable per switch port, site-wide LED toggle, client network access (block/unblock) |
| **Button** | Device reboot, device locate (flash LEDs), wireless client reconnect, site-wide WLAN optimization |
| **Update** | Firmware update entity with install action |

> **Note on permissions:** PoE and LED switches are only created when the API credentials have editing rights. If your credentials are viewer-only, the integration automatically detects this during setup and skips those controls — all monitoring entities are still created.

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

After initial setup, go to **Settings → Devices & Services → TP-Link Omada Open API → Configure** to access these options:

| Option | Description |
|---|---|
| **Client selection** | Add or remove tracked clients |
| **Application selection** | Add or remove tracked DPI applications |
| **Update intervals** | Configure polling intervals for devices (default 60 s), clients (default 30 s), and app traffic (default 300 s). Range: 10 – 3600 seconds |

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


## Removing the Integration

To remove the TP-Link Omada Open API integration from Home Assistant:

1. Go to **Settings → Devices & Services** in Home Assistant.
2. Find the **TP-Link Omada Open API** integration in the list.
3. Click the integration, then click the three-dot menu (⋮) and select **Delete**.
4. Confirm the removal when prompted.

All entities and devices created by the integration will be removed. If you wish to remove configuration data and tokens, you may also delete the integration folder from `custom_components/` after removal.

For more details, see the [removal instructions rule](ha-developer-docs/core/integration-quality-scale/rules/docs-removal-instructions.md).

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

---


## Services

This integration provides the following Home Assistant service:

### `omada_open_api.debug_ssid_switches`

**Description:**
  Dumps diagnostic information about SSID switch entities for a given config entry to the Home Assistant log. Useful for troubleshooting entity creation and mapping.

**Fields:**
  - `config_entry_id` (string, required): The config entry ID of the Omada integration instance to debug. You can find this in the entity registry or by inspecting the integration in Home Assistant.

**Example YAML:**
```yaml
service: omada_open_api.debug_ssid_switches
data:
  config_entry_id: "your_config_entry_id_here"
```

See the [integration documentation](ha-developer-docs/core/integration-quality-scale/rules/docs-actions.md) for more details on service usage and troubleshooting.

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
