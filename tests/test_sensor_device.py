"""Tests for OmadaDeviceSensor entity - Step 2 enrichment."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

from custom_components.omada_open_api.const import DOMAIN
from custom_components.omada_open_api.coordinator import OmadaSiteCoordinator
from custom_components.omada_open_api.devices import process_device
from custom_components.omada_open_api.sensor import (
    AP_BAND_CLIENT_SENSORS,
    DEVICE_SENSORS,
    OmadaDeviceSensor,
)

from .conftest import (
    SAMPLE_DEVICE_AP,
    SAMPLE_DEVICE_GATEWAY,
    SAMPLE_DEVICE_SWITCH,
    TEST_SITE_ID,
    TEST_SITE_NAME,
)

AP_MAC = "AA-BB-CC-DD-EE-01"
SWITCH_MAC = "AA-BB-CC-DD-EE-02"
GATEWAY_MAC = "AA-BB-CC-DD-EE-03"


def _build_coordinator_data(
    devices: dict[str, dict] | None = None,
) -> dict:
    """Build coordinator data dict with devices."""
    return {
        "devices": devices or {},
        "poe_ports": {},
        "poe_budget": {},
        "site_id": TEST_SITE_ID,
        "site_name": TEST_SITE_NAME,
    }


def _create_device_sensor(
    hass: HomeAssistant,
    device_mac: str,
    devices: dict[str, dict],
    description_key: str,
    sensor_list: tuple = DEVICE_SENSORS,
) -> OmadaDeviceSensor:
    """Create an OmadaDeviceSensor with a mock coordinator."""
    coordinator = OmadaSiteCoordinator(
        hass=hass,
        api_client=MagicMock(),
        site_id=TEST_SITE_ID,
        site_name=TEST_SITE_NAME,
    )
    coordinator.data = _build_coordinator_data(devices)

    description = next(d for d in sensor_list if d.key == description_key)

    return OmadaDeviceSensor(
        coordinator=coordinator,
        description=description,
        device_mac=device_mac,
    )


# ---------------------------------------------------------------------------
# Existing sensor value checks
# ---------------------------------------------------------------------------


async def test_client_num_sensor(hass: HomeAssistant) -> None:
    """Test client_num sensor returns count."""
    data = process_device(SAMPLE_DEVICE_AP)
    sensor = _create_device_sensor(hass, AP_MAC, {AP_MAC: data}, "client_num")
    assert sensor.native_value == 12


async def test_uptime_sensor_string(hass: HomeAssistant) -> None:
    """Test uptime sensor parses string format."""
    data = process_device(SAMPLE_DEVICE_AP)
    sensor = _create_device_sensor(hass, AP_MAC, {AP_MAC: data}, "uptime")
    # "2day(s) 5h 30m 10s" = 2*86400 + 5*3600 + 30*60 + 10 = 192610
    assert sensor.native_value == 192610


async def test_uptime_sensor_int(hass: HomeAssistant) -> None:
    """Test uptime sensor accepts integer directly."""
    data = process_device(SAMPLE_DEVICE_SWITCH)
    sensor = _create_device_sensor(hass, SWITCH_MAC, {SWITCH_MAC: data}, "uptime")
    assert sensor.native_value == 90000


async def test_cpu_util_sensor(hass: HomeAssistant) -> None:
    """Test CPU utilization sensor."""
    data = process_device(SAMPLE_DEVICE_AP)
    sensor = _create_device_sensor(hass, AP_MAC, {AP_MAC: data}, "cpu_util")
    assert sensor.native_value == 15


async def test_mem_util_sensor(hass: HomeAssistant) -> None:
    """Test memory utilization sensor."""
    data = process_device(SAMPLE_DEVICE_SWITCH)
    sensor = _create_device_sensor(hass, SWITCH_MAC, {SWITCH_MAC: data}, "mem_util")
    assert sensor.native_value == 30


async def test_firmware_version_sensor(hass: HomeAssistant) -> None:
    """Test firmware version sensor."""
    data = process_device(SAMPLE_DEVICE_GATEWAY)
    sensor = _create_device_sensor(
        hass, GATEWAY_MAC, {GATEWAY_MAC: data}, "firmware_version"
    )
    assert sensor.native_value == "3.0.0"


async def test_model_sensor(hass: HomeAssistant) -> None:
    """Test model sensor."""
    data = process_device(SAMPLE_DEVICE_AP)
    sensor = _create_device_sensor(hass, AP_MAC, {AP_MAC: data}, "model")
    assert sensor.native_value == "EAP660 HD"


async def test_device_type_sensor(hass: HomeAssistant) -> None:
    """Test device type sensor."""
    data = process_device(SAMPLE_DEVICE_SWITCH)
    sensor = _create_device_sensor(hass, SWITCH_MAC, {SWITCH_MAC: data}, "device_type")
    assert sensor.native_value == "switch"


async def test_public_ip_sensor(hass: HomeAssistant) -> None:
    """Test public IP sensor for gateway."""
    data = process_device(SAMPLE_DEVICE_GATEWAY)
    sensor = _create_device_sensor(hass, GATEWAY_MAC, {GATEWAY_MAC: data}, "public_ip")
    assert sensor.native_value == "1.2.3.4"


async def test_public_ip_unavailable_for_ap(hass: HomeAssistant) -> None:
    """Test public IP unavailable for AP (no public IP)."""
    data = process_device(SAMPLE_DEVICE_AP)
    sensor = _create_device_sensor(hass, AP_MAC, {AP_MAC: data}, "public_ip")
    assert sensor.available is False


# ---------------------------------------------------------------------------
# Detail status sensor (new in Step 2)
# ---------------------------------------------------------------------------


async def test_detail_status_connected(hass: HomeAssistant) -> None:
    """Test detail_status returns human-readable string."""
    ap = dict(SAMPLE_DEVICE_AP)
    ap["detailStatus"] = 14
    data = process_device(ap)
    sensor = _create_device_sensor(hass, AP_MAC, {AP_MAC: data}, "detail_status")
    assert sensor.native_value == "Connected"


async def test_detail_status_disconnected(hass: HomeAssistant) -> None:
    """Test detail_status for disconnected device."""
    ap = dict(SAMPLE_DEVICE_AP)
    ap["detailStatus"] = 0
    data = process_device(ap)
    sensor = _create_device_sensor(hass, AP_MAC, {AP_MAC: data}, "detail_status")
    assert sensor.native_value == "Disconnected"


async def test_detail_status_upgrading(hass: HomeAssistant) -> None:
    """Test detail_status for upgrading device."""
    ap = dict(SAMPLE_DEVICE_AP)
    ap["detailStatus"] = 12
    data = process_device(ap)
    sensor = _create_device_sensor(hass, AP_MAC, {AP_MAC: data}, "detail_status")
    assert sensor.native_value == "Upgrading"


async def test_detail_status_heartbeat_missed(hass: HomeAssistant) -> None:
    """Test detail_status for heartbeat missed."""
    sw = dict(SAMPLE_DEVICE_SWITCH)
    sw["detailStatus"] = 30
    data = process_device(sw)
    sensor = _create_device_sensor(
        hass, SWITCH_MAC, {SWITCH_MAC: data}, "detail_status"
    )
    assert sensor.native_value == "Heartbeat Missed"


async def test_detail_status_unknown_code(hass: HomeAssistant) -> None:
    """Test detail_status with unknown code."""
    ap = dict(SAMPLE_DEVICE_AP)
    ap["detailStatus"] = 999
    data = process_device(ap)
    sensor = _create_device_sensor(hass, AP_MAC, {AP_MAC: data}, "detail_status")
    assert sensor.native_value == "Unknown (999)"


async def test_detail_status_unavailable_when_none(hass: HomeAssistant) -> None:
    """Test detail_status unavailable when not in data."""
    data = process_device(SAMPLE_DEVICE_AP)
    sensor = _create_device_sensor(hass, AP_MAC, {AP_MAC: data}, "detail_status")
    assert sensor.available is False


# ---------------------------------------------------------------------------
# Per-band client count sensors (AP-only, new in Step 2)
# ---------------------------------------------------------------------------


def _ap_data_with_bands() -> dict:
    """Return AP device data with per-band client counts."""
    data = process_device(SAMPLE_DEVICE_AP)
    data["client_num_2g"] = 5
    data["client_num_5g"] = 7
    data["client_num_5g2"] = 0
    data["client_num_6g"] = 3
    return data


async def test_clients_2g_sensor(hass: HomeAssistant) -> None:
    """Test 2.4 GHz client count sensor."""
    data = _ap_data_with_bands()
    sensor = _create_device_sensor(
        hass, AP_MAC, {AP_MAC: data}, "clients_2g", AP_BAND_CLIENT_SENSORS
    )
    assert sensor.native_value == 5


async def test_clients_5g_sensor(hass: HomeAssistant) -> None:
    """Test 5 GHz client count sensor."""
    data = _ap_data_with_bands()
    sensor = _create_device_sensor(
        hass, AP_MAC, {AP_MAC: data}, "clients_5g", AP_BAND_CLIENT_SENSORS
    )
    assert sensor.native_value == 7


async def test_clients_5g2_sensor(hass: HomeAssistant) -> None:
    """Test 5 GHz-2 client count sensor."""
    data = _ap_data_with_bands()
    sensor = _create_device_sensor(
        hass, AP_MAC, {AP_MAC: data}, "clients_5g2", AP_BAND_CLIENT_SENSORS
    )
    assert sensor.native_value == 0


async def test_clients_6g_sensor(hass: HomeAssistant) -> None:
    """Test 6 GHz client count sensor."""
    data = _ap_data_with_bands()
    sensor = _create_device_sensor(
        hass, AP_MAC, {AP_MAC: data}, "clients_6g", AP_BAND_CLIENT_SENSORS
    )
    assert sensor.native_value == 3


async def test_band_sensor_unavailable_without_data(hass: HomeAssistant) -> None:
    """Test per-band sensor unavailable when data not populated."""
    data = process_device(SAMPLE_DEVICE_AP)
    # No client_num_2g key in data
    sensor = _create_device_sensor(
        hass, AP_MAC, {AP_MAC: data}, "clients_2g", AP_BAND_CLIENT_SENSORS
    )
    assert sensor.available is False


# ---------------------------------------------------------------------------
# Identity and device_info
# ---------------------------------------------------------------------------


async def test_device_sensor_unique_id(hass: HomeAssistant) -> None:
    """Test unique_id format for device sensor."""
    data = process_device(SAMPLE_DEVICE_AP)
    sensor = _create_device_sensor(hass, AP_MAC, {AP_MAC: data}, "cpu_util")
    assert sensor.unique_id == f"{AP_MAC}_cpu_util"


async def test_device_sensor_device_info_ap(hass: HomeAssistant) -> None:
    """Test device_info for AP."""
    data = process_device(SAMPLE_DEVICE_AP)
    sensor = _create_device_sensor(hass, AP_MAC, {AP_MAC: data}, "client_num")
    device_info = sensor._attr_device_info  # noqa: SLF001
    assert (DOMAIN, AP_MAC) in device_info["identifiers"]
    assert device_info["name"] == "Office AP"
    assert device_info["manufacturer"] == "TP-Link"
    assert device_info["model"] == "EAP660 HD"


async def test_device_sensor_device_info_gateway(hass: HomeAssistant) -> None:
    """Test device_info for gateway has no via_device."""
    data = process_device(SAMPLE_DEVICE_GATEWAY)
    sensor = _create_device_sensor(hass, GATEWAY_MAC, {GATEWAY_MAC: data}, "client_num")
    device_info = sensor._attr_device_info  # noqa: SLF001
    assert "via_device" not in device_info


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


async def test_device_sensor_missing_device_data(hass: HomeAssistant) -> None:
    """Test sensor returns None when device not in coordinator data."""
    data = process_device(SAMPLE_DEVICE_AP)
    sensor = _create_device_sensor(hass, AP_MAC, {AP_MAC: data}, "cpu_util")
    sensor.coordinator.data = _build_coordinator_data({})
    assert sensor.native_value is None
    assert sensor.available is False


async def test_device_sensor_coordinator_failure(hass: HomeAssistant) -> None:
    """Test sensor unavailable when coordinator update fails."""
    data = process_device(SAMPLE_DEVICE_AP)
    sensor = _create_device_sensor(hass, AP_MAC, {AP_MAC: data}, "cpu_util")
    sensor.coordinator.last_update_success = False
    assert sensor.available is False
