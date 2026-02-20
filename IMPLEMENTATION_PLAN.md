# Implementation Plan: Feature Parity with ha-omada

> This file tracks the implementation plan for achieving feature parity between
> `bullitt186/ha-omada-open-api` (Open API / cloud) and `zachcheatham/ha-omada` (local API).
>
> **Branch**: `feature/ha-omada-parity`
> **Baseline**: 199 tests, 72% coverage, 4 platforms (sensor, binary_sensor, device_tracker, switch)

---

## Completed Steps

### Step 1: Enrich Client Sensors ✅ (commit 36569ed)
- 7 new client sensors: downloaded, uploaded, rx_activity, tx_activity, rssi, snr, client_uptime
- 1 new client binary sensor: power_save (wireless only)
- 37 new tests, coverage 64% → 66%

### Step 2: Enrich Device Data ✅ (commit 6dea28f)
- `get_device_client_stats()` API method for per-band client counts
- 4 AP-only sensors: clients_2g, clients_5g, clients_5g2, clients_6g
- `detail_status` sensor with human-readable status mapping (DETAIL_STATUS_MAP)
- `need_upgrade` binary sensor for firmware update detection
- Coordinator refactored: extracted `_merge_uplink_info()`, `_merge_band_client_stats()`
- 42 new tests, coverage 66% → 68%

### Step 3: Device Tracker Platform ✅ (commit a37c7b7)
- `OmadaClientTracker` entity using ScannerEntity + CoordinatorEntity
- Tracks client presence across network (wireless + wired)
- Extra attributes: ip, ssid, connected_to, wireless flag
- Dynamic entity creation/removal via coordinator listener
- 19 new tests, coverage 68% → 70%

### Step 4: PoE Switch Control ✅ (commit f78cb6c)
- `OmadaPoeSwitch` entity in switch.py
- `set_port_profile_override()` and `set_port_poe_mode()` API methods
- Extra state attributes: port, port_name, power, voltage, current
- Platform.SWITCH registered
- 26 new tests (17 switch + 5 API + 4 coordinator), coverage 70% → 71%

### Step 5: Granular Options Flow ✅ (commit 4fa0d27)
- Configurable scan intervals (device, client, app traffic) via options flow
- New constants: CONF_DEVICE_SCAN_INTERVAL, CONF_CLIENT_SCAN_INTERVAL, CONF_APP_SCAN_INTERVAL
- Coordinators accept custom update_interval
- Options flow menu with "Update Intervals" step
- 8 new tests, coverage 71% → 72%

---

## Remaining Steps

### Step 6: Device Tracker for Devices
**Status**: 🔄 IN PROGRESS

**Goal**: Track AP/switch/gateway online status as device_tracker entities (matching ha-omada).

**Files to modify**:
- `custom_components/omada_open_api/device_tracker.py` — Add `OmadaDeviceTracker` class
- `tests/test_device_tracker.py` — Add device tracker tests

**Implementation details**:
- New entity class `OmadaDeviceTracker` using `ScannerEntity` + `CoordinatorEntity[OmadaSiteCoordinator]`
- `is_connected` based on `status_category == 1` (connected states)
- `mac_address` from device MAC
- Extra attributes: type, model, firmware_version, ip, detail_status
- Uses existing `OmadaSiteCoordinator` data — no new API calls needed
- Add alongside existing client tracker entities in `async_setup_entry()`

**Test plan**: ~10 tests (AP online/offline, switch online/offline, attributes, unique_id, device_info)

---

### Step 7: Button Platform (reboot, reconnect, WLAN optimization)
**Status**: ⬜ PENDING

**Goal**: Add button entities for device reboot, client reconnect, and WLAN optimization.

**Files to create/modify**:
- `custom_components/omada_open_api/button.py` — New platform file
- `custom_components/omada_open_api/api.py` — Add 3 API methods
- `custom_components/omada_open_api/__init__.py` — Register Platform.BUTTON
- `tests/test_button.py` — New test file

**New API methods**:
- `reboot_device(site_id, device_mac)` — POST `.../devices/{deviceMac}/reboot`
- `reconnect_client(site_id, client_mac)` — POST `.../clients/{clientMac}/reconnect`
- `start_wlan_optimization(site_id)` — POST `.../cmd/rfPlanning/rrmOptimization`

**Entity classes**:
- `OmadaDeviceRebootButton` — per device (AP, switch, gateway), uses OmadaSiteCoordinator
- `OmadaClientReconnectButton` — per wireless client, uses OmadaClientCoordinator
- `OmadaWlanOptimizationButton` — per site (one button)

---

### Step 8: Client Block/Unblock Switch
**Status**: ⬜ PENDING

**Goal**: Add switch entity to block/unblock clients from network access.

**Files to modify**:
- `custom_components/omada_open_api/switch.py` — Add `OmadaClientBlockSwitch`
- `custom_components/omada_open_api/api.py` — Add 2 API methods
- `tests/test_switch.py` — Add block switch tests

**New API methods**:
- `block_client(site_id, client_mac)` — POST `.../clients/{clientMac}/block`
- `unblock_client(site_id, client_mac)` — POST `.../clients/{clientMac}/unblock`

**Implementation details**:
- `is_on = NOT blocked` (inverted logic, matching ha-omada)
- Uses `OmadaClientCoordinator`

---

### Step 9: SSID Enable/Disable Switch
**Status**: ⬜ PENDING

**Goal**: Add switch entities to enable/disable SSIDs (site-wide, not per-AP).

**Files to modify**:
- `custom_components/omada_open_api/switch.py` — Add `OmadaSsidSwitch`
- `custom_components/omada_open_api/api.py` — Add 3 API methods
- `custom_components/omada_open_api/coordinator.py` — Fetch SSIDs during site update

**New API methods**:
- `get_wlans(site_id)` — GET `.../wireless-network/wlans`
- `get_ssids(site_id, wlan_id)` — GET `.../wireless-network/wlans/{wlanId}/ssids`
- `set_ssid_enabled(site_id, wlan_id, ssid_id, enabled)` — PATCH `.../ssids/{ssidId}/update-basic-config`

**Note**: Site-wide toggle only (Open API limitation — no per-AP overrides).

---

### Step 10: Update Platform (Firmware)
**Status**: ⬜ PENDING

**Goal**: Add update entities showing firmware version and allowing upgrades.

**Files to create/modify**:
- `custom_components/omada_open_api/update.py` — New platform file
- `custom_components/omada_open_api/api.py` — Add 2 API methods
- `custom_components/omada_open_api/__init__.py` — Register Platform.UPDATE

**New API methods**:
- `get_firmware_info(site_id, device_mac)` — GET firmware upgrade info
- `start_firmware_upgrade(site_id, device_macs)` — POST `.../multi-devices/start-rolling-upgrade`

---

### Step 11: Device Bandwidth & Radio Utilization Sensors
**Status**: ⬜ PENDING

**Goal**: Add device-level traffic sensors and AP radio utilization sensors.

**New sensors**: device_downloaded, device_uploaded, device_rx_activity, device_tx_activity,
tx_util_2g/5g/6g, rx_util_2g/5g/6g, interference_2g/5g/6g, guest_num, user_num

---

### Step 12: LED Control & Device Locate (Bonus)
**Status**: ⬜ PENDING

**Goal**: Bonus features not in ha-omada but available via Open API.

**New API methods**:
- `get_led_setting(site_id)` / `set_led_setting(site_id, enabled)` — GET/PUT `.../led`
- `locate_device(site_id, device_mac)` — POST `.../devices/{deviceMac}/locate`

---

## Features NOT Implementable via Open API

| Feature | Reason |
|---------|--------|
| AP radio toggle (2.4/5/6 GHz) | No AP radio enable/disable endpoint in Open API |
| Per-AP SSID override | Open API only supports site-wide SSID enable/disable |
| WLAN optimization binary sensor | No endpoint to check RF planning execution status |
