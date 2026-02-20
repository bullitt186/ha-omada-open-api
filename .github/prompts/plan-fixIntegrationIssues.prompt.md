## Plan: Fix 7 Integration Issues

**TL;DR**: Fix a mix of data display issues, a critical runtime_data key mismatch (`site_coordinators` vs `coordinators`), an update entity initialization gap, and a permissions error in PoE control. The `site_coordinators` mismatch (Issue 6) is the highest-priority bug — it silently prevents LED switches, device reboot/locate buttons, WLAN optimization buttons, and device trackers from being created.

**Steps**

### 1. Device type abbreviation mapping (Issue 1)
- In [sensor.py](custom_components/omada_open_api/sensor.py#L148-L153), the `device_type` sensor's `value_fn` does `device.get("type")` which returns raw API abbreviations (`"ap"`, `"gateway"`, `"switch"`).
- Add a `DEVICE_TYPE_LABELS` mapping dict in [sensor.py](custom_components/omada_open_api/sensor.py) (e.g., `{"ap": "Access Point", "gateway": "Gateway", "switch": "Switch", "olt": "OLT"}`).
- Update the `value_fn` to look up the label: `lambda device: DEVICE_TYPE_LABELS.get(device.get("type", ""), device.get("type"))`.

### 2. Update entity shows "Unknown" until first poll (Issues 2 & 3)
- In [update.py](custom_components/omada_open_api/update.py#L88-L90), `latest_version` returns `self._latest_version` which is `None` until `async_update()` runs. HA renders `None` as "Unknown".
- Fix the `latest_version` property to fall back to `installed_version` when `_latest_version` is still `None`:
  ```
  return self._latest_version if self._latest_version is not None else self.installed_version
  ```
- This way, on initial load before firmware check completes, `latest_version == installed_version` (meaning "up to date" display rather than "Unknown").

### 3. Uptime auto-scaling (Issue 4)
- Both [device uptime](custom_components/omada_open_api/sensor.py#L94-L100) and [client uptime](custom_components/omada_open_api/sensor.py#L383-L389) use `SensorDeviceClass.DURATION` with `UnitOfTime.SECONDS`. HA's frontend **should** auto-format this with `SensorDeviceClass.DURATION`, but the user sees raw seconds.
- Change approach: convert uptime to a **timestamp** sensor using `SensorDeviceClass.TIMESTAMP`. Calculate `now - uptime_seconds` to produce a "last boot" datetime. HA natively displays this as a relative time ("5 days ago").
- Alternatively, keep `DURATION` but switch `native_unit_of_measurement` to `UnitOfTime.DAYS` and convert seconds to fractional days in `value_fn`. HA's duration class auto-scales days.
- **Recommended**: Use `SensorDeviceClass.TIMESTAMP` with `value_fn` returning an ISO datetime string of the boot time. This is the standard HA pattern for uptime (used by many integrations).

### 4. TX Activity availability (Issue 5)
- In [sensor.py](custom_components/omada_open_api/sensor.py#L344-L357), the `tx_activity` sensor's `available_fn` returns `False` when `upload_activity` is `None`.
- The API may omit `uploadActivity` for wired or idle clients. The `process_client` in [clients.py](custom_components/omada_open_api/clients.py#L68) maps it correctly.
- Fix: change `available_fn` to always return `True` for active clients, and have `value_fn` default to `0` when `upload_activity` is `None`:
  ```
  value_fn=lambda client: round((client.get("upload_activity") or 0) / 1_000_000, 2)
  available_fn=lambda client: client.get("active", False)
  ```
- Apply the same pattern to `rx_activity` (`activity` field) for consistency.

### 5. Fix `site_coordinators` key mismatch (Issue 6 — **CRITICAL**)
- `__init__.py` stores `"coordinators"` (a `dict[str, OmadaSiteCoordinator]`) in [runtime_data](custom_components/omada_open_api/__init__.py#L228-L233).
- But [button.py](custom_components/omada_open_api/button.py#L36), [switch.py](custom_components/omada_open_api/switch.py#L55), and [device_tracker.py](custom_components/omada_open_api/device_tracker.py#L39) all read `data.get("site_coordinators", [])` — a key that **never exists**.
- Result: LED switches, device reboot/locate buttons, WLAN optimization buttons, and device trackers for infrastructure devices are **silently never created**. This also explains the excessive entity_registry logging — many entities register device_info on every poll because the entity count is much larger than expected relative to actual entities created.
- Fix: In all three platform files, change `data.get("site_coordinators", [])` to `list(data.get("coordinators", {}).values())` to match the actual runtime_data structure.

### 6. PoE switch permissions error (Issue 7)
- Error `-1007: The current user does not have permissions` when calling `set_port_profile_override`.
- Per the OpenAPI spec, this endpoint requires **"Site Device Manager Modify"** permission. The user's API client likely lacks this permission.
- This is a **configuration issue**, not a code bug. However, the integration should:
  1. Log a more helpful error message indicating the permission requirement.
  2. Consider catching this specific error code and raising a `HomeAssistantError` with a user-friendly message.
- In [switch.py](custom_components/omada_open_api/switch.py#L155-L175), improve the `_set_poe` error handler to check for `-1007` and log a specific message about required permissions.
- In [api.py](custom_components/omada_open_api/api.py#L193), consider exposing the error code in `OmadaApiError` so callers can differentiate permission errors from other failures.

### 7. Update tests for all changes
- Update [test_sensor_device.py](tests/test_sensor_device.py) for device_type mapping and uptime format change.
- Update [test_update.py](tests/test_update.py) for `latest_version` fallback behavior.
- Update client sensor tests for TX/RX activity availability changes.
- Update [test_switch.py](tests/test_switch.py) for PoE error handling improvements.
- Update [test_button.py](tests/test_button.py) to use `coordinators` key instead of `site_coordinators` in any integration-level tests.
- Ensure all tests pass and coverage threshold is maintained.

**Verification**
1. `pytest tests/ -v --tb=short` — all tests pass
2. `ruff check && ruff format --check` — no lint issues
3. `mypy custom_components/omada_open_api/` — no new type errors
4. Start HA (`hass -c config`), check logs for zero omada-specific errors/warnings
5. Verify in HA UI: device type shows "Access Point", update entity shows version (not "Unknown"), uptime shows human-readable time, TX Activity shows 0 instead of unavailable
6. Verify LED switch, reboot/locate buttons, device trackers now appear in HA entities

**Decisions**
- Issue 4 (uptime): Use `SensorDeviceClass.TIMESTAMP` (boot time) — this is the HA-standard approach and gives the best frontend display ("5 days ago")
- Issue 5 (TX Activity): Default to `0` for active clients instead of marking unavailable — users expect to see a value
- Issue 6 (key mismatch): Fix in platform files rather than `__init__.py` — the `"coordinators"` dict structure is used correctly by sensor.py, update.py, and PoE switches already
- Issue 7 (PoE permissions): Improve error messages in code but note this is primarily a user configuration issue (API client permissions)
