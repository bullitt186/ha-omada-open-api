# Plan: Fix 8 Live-Testing Issues

## Issue 1 — Connected Clients = 0 for APs

**Root cause**: `_merge_band_client_stats()` in `coordinator.py` merges per-band counts (`client_num_2g`, `client_num_5g`, etc.) but never merges the total `clientNum` from the AP stats into `devices[mac]["client_num"]`.

**Fix** (`coordinator.py`): In `_merge_band_client_stats()`, add:
```python
devices[mac]["client_num"] = stat.get("clientNum", 0)
```
alongside the existing per-band merges.

---

## Issue 2 — Redundant Firmware Sensors

**Problem**: `need_upgrade` binary sensor and `firmware_version` sensor are redundant now that the `update` platform entity exists (shows firmware version, update availability, and triggers upgrades).

**Fix**:
- **sensor.py**: Remove `firmware_version` entry from `DEVICE_SENSORS`
- **binary_sensor.py**: Remove `need_upgrade` entry from `DEVICE_BINARY_SENSORS`

---

## Issue 3 — Public IP Sensor on Non-Gateway Devices

**Problem**: `public_ip` sensor is created for all device types, but only gateways have a WAN public IP. APs and switches show `None`.

**Fix** (`sensor.py`): Restrict `public_ip` to gateway devices only via `applicable_types=("gateway",)`.

---

## Issue 4 — Connected Clients Sensor on Non-WiFi Devices

**Problem**: `client_num` sensor is created for all device types, but only APs report meaningful connected WiFi client counts. Switches show pass-through clients (misleading), gateways show 0.

**Fix** (`sensor.py`): Restrict `client_num` to AP devices only via `applicable_types=("ap",)`.

---

## Issue 5 — Uplink Sensors on Gateways

**Problem**: `uplink_device`, `uplink_port`, and `link_speed` sensors are created for gateways, but gateways are the top of the network hierarchy — they have no uplink device.

**Fix** (`sensor.py`): Restrict these three sensors to APs and switches only via `applicable_types=("ap", "switch")`.

---

## Issue 6 — Model Sensor Redundant with Device Info

**Problem**: `model` sensor duplicates the model already shown in the HA device info card (set via `DeviceInfo.model`).

**Fix** (`sensor.py`): Remove `model` entry from `DEVICE_SENSORS`.

---

## Issue 7 — Confusing 5 GHz Band Naming

**Problem**: `"Clients 5 GHz"` and `"Clients 5 GHz-2"` naming is asymmetric and confusing. Users don't know which radio is which.

**Fix** (`sensor.py`): Rename `"Clients 5 GHz"` → `"Clients 5 GHz-1"` in `AP_BAND_CLIENT_SENSORS` for symmetry with `"Clients 5 GHz-2"`.

---

## Issue 8 — Device Tracker Always Shows "Away"

**Root cause**: `is_connected` in `device_tracker.py` checks `device.get("status_category")`, but the API never returns a `statusCategory` field — it returns `status` (0 = Disconnected, 1 = Connected). The `devices.py` processor stores `device.get("statusCategory")` which is always `None`, so `is_connected` is always `False`.

**Fix** (`device_tracker.py`): Change `is_connected` to use `device.get("status")`:
```python
@property
def is_connected(self) -> bool:
    device = self.coordinator.data.get(self._device_mac, {})
    return device.get("status") == _STATUS_CONNECTED
```
Update the constant from `_STATUS_CATEGORY_CONNECTED` to `_STATUS_CONNECTED = 1`.

---

## Implementation Steps

### Step 1 — Add `applicable_types` filtering to sensor descriptions

Add an optional `applicable_types: tuple[str, ...] | None = None` field to `OmadaSensorEntityDescription`. In `async_setup_entry`, skip entity creation when the device type is not in `applicable_types` (if set).

### Step 2 — Apply all sensor.py changes

- Remove `model` and `firmware_version` from `DEVICE_SENSORS`
- Set `applicable_types=("ap",)` on `client_num`
- Set `applicable_types=("gateway",)` on `public_ip`
- Set `applicable_types=("ap", "switch")` on `uplink_device`, `uplink_port`, `link_speed`
- Rename `"Clients 5 GHz"` → `"Clients 5 GHz-1"` in `AP_BAND_CLIENT_SENSORS`

### Step 3 — Remove `need_upgrade` from binary_sensor.py

### Step 4 — Fix device tracker `is_connected`

### Step 5 — Fix coordinator `_merge_band_client_stats()`

### Step 6 — Update tests

- Remove tests for deleted sensors (`model`, `firmware_version`, `need_upgrade`)
- Update device tracker tests to use `status` instead of `status_category`
- Add tests for `applicable_types` filtering (AP-only, gateway-only, etc.)
- Update 5 GHz sensor name assertions

### Step 7 — Verify

```bash
pytest tests/ -v
ruff check custom_components/
ruff format --check custom_components/
```

Commit and push.
