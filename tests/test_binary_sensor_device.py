"""Tests for OmadaDeviceBinarySensor - need_upgrade (Step 2)."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

from custom_components.omada_open_api.binary_sensor import (
    DEVICE_BINARY_SENSORS,
    OmadaDeviceBinarySensor,
)
from custom_components.omada_open_api.const import DOMAIN
from custom_components.omada_open_api.coordinator import OmadaSiteCoordinator
from custom_components.omada_open_api.devices import process_device

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


def _build_coordinator_data(devices: dict[str, dict] | None = None) -> dict:
    """Build coordinator data dict."""
    return {
        "devices": devices or {},
        "poe_ports": {},
        "poe_budget": {},
        "site_id": TEST_SITE_ID,
        "site_name": TEST_SITE_NAME,
    }


def _create_device_binary_sensor(
    hass: HomeAssistant,
    device_mac: str,
    devices: dict[str, dict],
    description_key: str,
) -> OmadaDeviceBinarySensor:
    """Create an OmadaDeviceBinarySensor with mock coordinator."""
    coordinator = OmadaSiteCoordinator(
        hass=hass,
        api_client=MagicMock(),
        site_id=TEST_SITE_ID,
        site_name=TEST_SITE_NAME,
    )
    coordinator.data = _build_coordinator_data(devices)

    description = next(d for d in DEVICE_BINARY_SENSORS if d.key == description_key)

    return OmadaDeviceBinarySensor(
        coordinator=coordinator,
        description=description,
        device_mac=device_mac,
    )


# ---------------------------------------------------------------------------
# Existing device binary sensors
# ---------------------------------------------------------------------------


async def test_status_online(hass: HomeAssistant) -> None:
    """Test status binary sensor shows online."""
    ap = dict(SAMPLE_DEVICE_AP)
    ap["status"] = 1
    data = process_device(ap)
    sensor = _create_device_binary_sensor(hass, AP_MAC, {AP_MAC: data}, "status")
    assert sensor.is_on is True


async def test_status_offline(hass: HomeAssistant) -> None:
    """Test status binary sensor shows offline."""
    ap = dict(SAMPLE_DEVICE_AP)
    ap["status"] = 0
    data = process_device(ap)
    sensor = _create_device_binary_sensor(hass, AP_MAC, {AP_MAC: data}, "status")
    assert sensor.is_on is False


# ---------------------------------------------------------------------------
# need_upgrade binary sensor (new in Step 2)
# ---------------------------------------------------------------------------


async def test_need_upgrade_true(hass: HomeAssistant) -> None:
    """Test need_upgrade returns True when upgrade available."""
    ap = dict(SAMPLE_DEVICE_AP)
    ap["needUpgrade"] = True
    data = process_device(ap)
    sensor = _create_device_binary_sensor(hass, AP_MAC, {AP_MAC: data}, "need_upgrade")
    assert sensor.is_on is True


async def test_need_upgrade_false(hass: HomeAssistant) -> None:
    """Test need_upgrade returns False when no upgrade."""
    ap = dict(SAMPLE_DEVICE_AP)
    ap["needUpgrade"] = False
    data = process_device(ap)
    sensor = _create_device_binary_sensor(hass, AP_MAC, {AP_MAC: data}, "need_upgrade")
    assert sensor.is_on is False


async def test_need_upgrade_missing_defaults_false(hass: HomeAssistant) -> None:
    """Test need_upgrade defaults to False when key missing."""
    data = process_device(SAMPLE_DEVICE_AP)
    sensor = _create_device_binary_sensor(hass, AP_MAC, {AP_MAC: data}, "need_upgrade")
    assert sensor.is_on is False


async def test_need_upgrade_switch(hass: HomeAssistant) -> None:
    """Test need_upgrade works for switch device."""
    sw = dict(SAMPLE_DEVICE_SWITCH)
    sw["needUpgrade"] = True
    data = process_device(sw)
    sensor = _create_device_binary_sensor(
        hass, SWITCH_MAC, {SWITCH_MAC: data}, "need_upgrade"
    )
    assert sensor.is_on is True


async def test_need_upgrade_gateway(hass: HomeAssistant) -> None:
    """Test need_upgrade works for gateway device."""
    gw = dict(SAMPLE_DEVICE_GATEWAY)
    gw["needUpgrade"] = False
    data = process_device(gw)
    sensor = _create_device_binary_sensor(
        hass, GATEWAY_MAC, {GATEWAY_MAC: data}, "need_upgrade"
    )
    assert sensor.is_on is False


# ---------------------------------------------------------------------------
# Identity and device_info
# ---------------------------------------------------------------------------


async def test_unique_id(hass: HomeAssistant) -> None:
    """Test unique_id format."""
    data = process_device(SAMPLE_DEVICE_SWITCH)
    sensor = _create_device_binary_sensor(
        hass, SWITCH_MAC, {SWITCH_MAC: data}, "status"
    )
    assert sensor.unique_id == f"{SWITCH_MAC}_status"


async def test_device_info(hass: HomeAssistant) -> None:
    """Test device_info structure."""
    data = process_device(SAMPLE_DEVICE_SWITCH)
    sensor = _create_device_binary_sensor(
        hass, SWITCH_MAC, {SWITCH_MAC: data}, "need_upgrade"
    )
    device_info = sensor._attr_device_info  # noqa: SLF001
    assert (DOMAIN, SWITCH_MAC) in device_info["identifiers"]
    assert device_info["name"] == "Core Switch"


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


async def test_binary_sensor_missing_device(hass: HomeAssistant) -> None:
    """Test binary sensor when device removed from coordinator."""
    data = process_device(SAMPLE_DEVICE_AP)
    sensor = _create_device_binary_sensor(hass, AP_MAC, {AP_MAC: data}, "need_upgrade")
    sensor.coordinator.data = _build_coordinator_data({})
    assert sensor.is_on is False
    assert sensor.available is False


async def test_binary_sensor_coordinator_failure(hass: HomeAssistant) -> None:
    """Test unavailable when coordinator update fails."""
    data = process_device(SAMPLE_DEVICE_AP)
    sensor = _create_device_binary_sensor(hass, AP_MAC, {AP_MAC: data}, "status")
    sensor.coordinator.last_update_success = False
    assert sensor.available is False
