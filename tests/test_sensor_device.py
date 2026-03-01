"""Tests for OmadaDeviceSensor entity - Step 2 enrichment."""

from __future__ import annotations

import datetime as _dt
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
    """Test client_num sensor returns count from connected_clients list."""
    data = process_device(SAMPLE_DEVICE_AP)
    # The sensor now uses len(connected_clients), not raw client_num.
    data["connected_clients"] = [
        {
            "name": f"Client {i}",
            "mac": f"CC:CC:CC:CC:00:{i:02X}",
            "ip": f"10.0.0.{i}",
            "wireless": True,
        }
        for i in range(12)
    ]
    sensor = _create_device_sensor(hass, AP_MAC, {AP_MAC: data}, "client_num")
    assert sensor.native_value == 12


async def test_uptime_sensor_string(hass: HomeAssistant) -> None:
    """Test uptime sensor returns datetime (boot time)."""
    data = process_device(SAMPLE_DEVICE_AP)
    sensor = _create_device_sensor(hass, AP_MAC, {AP_MAC: data}, "uptime")
    value = sensor.native_value
    assert isinstance(value, _dt.datetime)
    assert value.tzinfo is not None


async def test_uptime_sensor_int(hass: HomeAssistant) -> None:
    """Test uptime sensor returns datetime for integer uptime."""
    data = process_device(SAMPLE_DEVICE_SWITCH)
    sensor = _create_device_sensor(hass, SWITCH_MAC, {SWITCH_MAC: data}, "uptime")
    value = sensor.native_value
    assert isinstance(value, _dt.datetime)
    assert value.tzinfo is not None


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


async def test_device_type_sensor(hass: HomeAssistant) -> None:
    """Test device type sensor returns human-readable label."""
    data = process_device(SAMPLE_DEVICE_SWITCH)
    sensor = _create_device_sensor(hass, SWITCH_MAC, {SWITCH_MAC: data}, "device_type")
    assert sensor.native_value == "Switch"


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
    ap = dict(SAMPLE_DEVICE_AP)
    del ap["detailStatus"]
    data = process_device(ap)
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
    sensor = _create_device_sensor(
        hass, GATEWAY_MAC, {GATEWAY_MAC: data}, "device_type"
    )
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


# ---------------------------------------------------------------------------
# Device type label mapping
# ---------------------------------------------------------------------------


async def test_device_type_sensor_ap(hass: HomeAssistant) -> None:
    """Test device type sensor returns 'Access Point' for ap type."""
    data = process_device(SAMPLE_DEVICE_AP)
    sensor = _create_device_sensor(hass, AP_MAC, {AP_MAC: data}, "device_type")
    assert sensor.native_value == "Access Point"


async def test_device_type_sensor_gateway(hass: HomeAssistant) -> None:
    """Test device type sensor returns 'Gateway' for gateway type."""
    data = process_device(SAMPLE_DEVICE_GATEWAY)
    sensor = _create_device_sensor(
        hass, GATEWAY_MAC, {GATEWAY_MAC: data}, "device_type"
    )
    assert sensor.native_value == "Gateway"


async def test_device_type_sensor_unknown_type(hass: HomeAssistant) -> None:
    """Test device type sensor falls back to raw value for unknown type."""
    data = process_device(SAMPLE_DEVICE_AP)
    data["type"] = "router"
    sensor = _create_device_sensor(hass, AP_MAC, {AP_MAC: data}, "device_type")
    assert sensor.native_value == "router"


# ---------------------------------------------------------------------------
# Uptime as boot-time timestamp
# ---------------------------------------------------------------------------


async def test_uptime_unavailable_when_none(hass: HomeAssistant) -> None:
    """Test uptime sensor unavailable when uptime is None."""
    data = process_device(SAMPLE_DEVICE_AP)
    data["uptime"] = None
    sensor = _create_device_sensor(hass, AP_MAC, {AP_MAC: data}, "uptime")
    assert sensor.available is False


# ---------------------------------------------------------------------------
# Client list attributes on device sensors
# ---------------------------------------------------------------------------

_SAMPLE_CONNECTED_CLIENTS: list[dict] = [
    {
        "name": "Laptop",
        "mac": "CC:00:00:00:00:01",
        "ip": "10.0.0.1",
        "wireless": True,
        "radio_id": 1,
    },
    {
        "name": "Phone",
        "mac": "CC:00:00:00:00:02",
        "ip": "10.0.0.2",
        "wireless": True,
        "radio_id": 0,
    },
    {
        "name": "Printer",
        "mac": "CC:00:00:00:00:03",
        "ip": "10.0.0.3",
        "wireless": False,
    },
]


async def test_client_num_attrs(hass: HomeAssistant) -> None:
    """Test client_num sensor has clients attribute list."""
    data = process_device(SAMPLE_DEVICE_AP)
    data["connected_clients"] = _SAMPLE_CONNECTED_CLIENTS
    sensor = _create_device_sensor(hass, AP_MAC, {AP_MAC: data}, "client_num")
    attrs = sensor.extra_state_attributes
    assert attrs is not None
    assert len(attrs["clients"]) == 3
    assert attrs["clients"][0]["name"] == "Laptop"


async def test_wired_clients_sensor(hass: HomeAssistant) -> None:
    """Test wired_clients sensor returns only wired count."""
    data = process_device(SAMPLE_DEVICE_SWITCH)
    data["connected_clients"] = _SAMPLE_CONNECTED_CLIENTS
    sensor = _create_device_sensor(
        hass, SWITCH_MAC, {SWITCH_MAC: data}, "wired_clients"
    )
    assert sensor.native_value == 1


async def test_wired_clients_attrs(hass: HomeAssistant) -> None:
    """Test wired_clients sensor has only wired clients in attribute."""
    data = process_device(SAMPLE_DEVICE_SWITCH)
    data["connected_clients"] = _SAMPLE_CONNECTED_CLIENTS
    sensor = _create_device_sensor(
        hass, SWITCH_MAC, {SWITCH_MAC: data}, "wired_clients"
    )
    attrs = sensor.extra_state_attributes
    assert attrs is not None
    assert len(attrs["clients"]) == 1
    assert attrs["clients"][0]["name"] == "Printer"


async def test_wireless_clients_sensor(hass: HomeAssistant) -> None:
    """Test wireless_clients sensor returns only wireless count."""
    data = process_device(SAMPLE_DEVICE_AP)
    data["connected_clients"] = _SAMPLE_CONNECTED_CLIENTS
    sensor = _create_device_sensor(hass, AP_MAC, {AP_MAC: data}, "wireless_clients")
    assert sensor.native_value == 2


async def test_wireless_clients_attrs(hass: HomeAssistant) -> None:
    """Test wireless_clients sensor has only wireless clients in attribute."""
    data = process_device(SAMPLE_DEVICE_AP)
    data["connected_clients"] = _SAMPLE_CONNECTED_CLIENTS
    sensor = _create_device_sensor(hass, AP_MAC, {AP_MAC: data}, "wireless_clients")
    attrs = sensor.extra_state_attributes
    assert attrs is not None
    assert len(attrs["clients"]) == 2
    assert {c["name"] for c in attrs["clients"]} == {"Laptop", "Phone"}


async def test_client_num_empty_list(hass: HomeAssistant) -> None:
    """Test client_num returns 0 when connected_clients is empty."""
    data = process_device(SAMPLE_DEVICE_SWITCH)
    data["connected_clients"] = []
    sensor = _create_device_sensor(hass, SWITCH_MAC, {SWITCH_MAC: data}, "client_num")
    assert sensor.native_value == 0


async def test_device_sensor_no_attrs_when_fn_none(hass: HomeAssistant) -> None:
    """Test sensors without attrs_fn return None for extra_state_attributes."""
    data = process_device(SAMPLE_DEVICE_AP)
    sensor = _create_device_sensor(hass, AP_MAC, {AP_MAC: data}, "cpu_util")
    assert sensor.extra_state_attributes is None


# ---------------------------------------------------------------------------
# Per-band client list attributes
# ---------------------------------------------------------------------------


async def test_band_2g_client_attrs(hass: HomeAssistant) -> None:
    """Test 2.4 GHz sensor attrs contain only radio_id=0 clients."""
    data = _ap_data_with_bands()
    data["connected_clients"] = _SAMPLE_CONNECTED_CLIENTS
    sensor = _create_device_sensor(
        hass, AP_MAC, {AP_MAC: data}, "clients_2g", AP_BAND_CLIENT_SENSORS
    )
    attrs = sensor.extra_state_attributes
    assert attrs is not None
    assert len(attrs["clients"]) == 1
    assert attrs["clients"][0]["name"] == "Phone"


async def test_band_5g_client_attrs(hass: HomeAssistant) -> None:
    """Test 5 GHz sensor attrs contain only radio_id=1 clients."""
    data = _ap_data_with_bands()
    data["connected_clients"] = _SAMPLE_CONNECTED_CLIENTS
    sensor = _create_device_sensor(
        hass, AP_MAC, {AP_MAC: data}, "clients_5g", AP_BAND_CLIENT_SENSORS
    )
    attrs = sensor.extra_state_attributes
    assert attrs is not None
    assert len(attrs["clients"]) == 1
    assert attrs["clients"][0]["name"] == "Laptop"
