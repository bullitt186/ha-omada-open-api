"""Tests for IP address and temperature sensors."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock

from custom_components.omada_open_api.coordinator import OmadaSiteCoordinator
from custom_components.omada_open_api.sensor import DEVICE_SENSORS, OmadaDeviceSensor

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant


def _create_device_sensor(
    hass: HomeAssistant,
    device_mac: str,
    devices_data: dict,
    sensor_key: str,
) -> OmadaDeviceSensor:
    """Helper to create a device sensor for testing."""
    # Create mock API client
    mock_api_client = MagicMock()
    mock_api_client.api_url = "https://test.example.com"

    coordinator = MagicMock(spec=OmadaSiteCoordinator)
    coordinator.hass = hass
    coordinator.site_id = "site_001"
    coordinator.site_name = "Test Site"
    coordinator.api_client = mock_api_client
    coordinator.data = {
        "devices": devices_data,
        "site_id": "site_001",
        "site_name": "Test Site",
    }
    coordinator.last_update_success = True

    sensor_desc = next(desc for desc in DEVICE_SENSORS if desc.key == sensor_key)

    return OmadaDeviceSensor(
        coordinator=coordinator,
        device_mac=device_mac,
        description=sensor_desc,
    )


def _processed_ap() -> dict:
    """Return processed AP device data."""
    return {
        "mac": "AA-BB-CC-DD-EE-01",
        "name": "Office AP",
        "model": "EAP225",
        "type": "ap",
        "ip": "192.168.1.10",
        "status": "connected",
    }


def _processed_gateway() -> dict:
    """Return processed gateway device data."""
    return {
        "mac": "AA-BB-CC-DD-EE-02",
        "name": "Main Gateway",
        "model": "ER605",
        "type": "gateway",
        "ip": "192.168.1.1",
        "temperature": 42,
        "status": "connected",
    }


def _processed_switch() -> dict:
    """Return processed switch device data."""
    return {
        "mac": "AA-BB-CC-DD-EE-03",
        "name": "Main Switch",
        "model": "SG2008P",
        "type": "switch",
        "ip": "192.168.1.2",
        "status": "connected",
    }


# ---------------------------------------------------------------------------
# Device IP Address Sensor Tests
# ---------------------------------------------------------------------------


async def test_device_ip_sensor_ap(hass: HomeAssistant) -> None:
    """Test device IP sensor returns IP for AP."""
    ap_mac = "AA-BB-CC-DD-EE-01"
    sensor = _create_device_sensor(
        hass,
        ap_mac,
        {ap_mac: _processed_ap()},
        "device_ip",
    )
    assert sensor.native_value == "192.168.1.10"
    assert sensor.available is True


async def test_device_ip_sensor_gateway(hass: HomeAssistant) -> None:
    """Test device IP sensor returns IP for gateway."""
    gateway_mac = "AA-BB-CC-DD-EE-02"
    sensor = _create_device_sensor(
        hass,
        gateway_mac,
        {gateway_mac: _processed_gateway()},
        "device_ip",
    )
    assert sensor.native_value == "192.168.1.1"
    assert sensor.available is True


async def test_device_ip_sensor_switch(hass: HomeAssistant) -> None:
    """Test device IP sensor returns IP for switch."""
    switch_mac = "AA-BB-CC-DD-EE-03"
    sensor = _create_device_sensor(
        hass,
        switch_mac,
        {switch_mac: _processed_switch()},
        "device_ip",
    )
    assert sensor.native_value == "192.168.1.2"
    assert sensor.available is True


async def test_device_ip_sensor_unavailable_when_missing(
    hass: HomeAssistant,
) -> None:
    """Test device IP sensor unavailable when IP is missing."""
    device_mac = "AA-BB-CC-DD-EE-01"
    device_data = _processed_ap()
    device_data["ip"] = None
    sensor = _create_device_sensor(
        hass,
        device_mac,
        {device_mac: device_data},
        "device_ip",
    )
    assert sensor.available is False


# ---------------------------------------------------------------------------
# Temperature Sensor Tests
# ---------------------------------------------------------------------------


async def test_temperature_sensor_gateway(hass: HomeAssistant) -> None:
    """Test temperature sensor returns temp for gateway."""
    gateway_mac = "AA-BB-CC-DD-EE-02"
    sensor = _create_device_sensor(
        hass,
        gateway_mac,
        {gateway_mac: _processed_gateway()},
        "temperature",
    )
    assert sensor.native_value == 42
    assert sensor.available is True


async def test_temperature_sensor_unavailable_when_missing(
    hass: HomeAssistant,
) -> None:
    """Test temperature sensor unavailable when temp is None."""
    gateway_mac = "AA-BB-CC-DD-EE-02"
    device_data = _processed_gateway()
    device_data["temperature"] = None
    sensor = _create_device_sensor(
        hass,
        gateway_mac,
        {gateway_mac: device_data},
        "temperature",
    )
    assert sensor.available is False


async def test_temperature_sensor_not_created_for_ap(hass: HomeAssistant) -> None:
    """Test temperature sensor is not applicable for AP devices."""
    temp_sensor = next(desc for desc in DEVICE_SENSORS if desc.key == "temperature")
    # Verify it's only applicable to gateways
    assert temp_sensor.applicable_types == ("gateway",)
