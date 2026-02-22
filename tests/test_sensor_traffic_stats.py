"""Tests for OmadaDeviceTrafficSensor entity."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

from custom_components.omada_open_api.const import DOMAIN
from custom_components.omada_open_api.coordinator import (
    OmadaDeviceStatsCoordinator,
    OmadaSiteCoordinator,
)
from custom_components.omada_open_api.sensor import (
    DEVICE_TRAFFIC_SENSORS,
    OmadaDeviceTrafficSensor,
)

from .conftest import TEST_SITE_ID, TEST_SITE_NAME

AP_MAC = "AA-BB-CC-DD-EE-01"
SWITCH_MAC = "AA-BB-CC-DD-EE-02"
GATEWAY_MAC = "AA-BB-CC-DD-EE-03"


def _create_device_traffic_sensor(
    hass: HomeAssistant,
    stats: dict[str, dict],
    description_key: str,
    device_mac: str = AP_MAC,
) -> OmadaDeviceTrafficSensor:
    """Create an OmadaDeviceTrafficSensor with mock coordinator."""
    site_coordinator = OmadaSiteCoordinator(
        hass=hass,
        api_client=MagicMock(),
        site_id=TEST_SITE_ID,
        site_name=TEST_SITE_NAME,
    )
    coordinator = OmadaDeviceStatsCoordinator(
        hass=hass,
        api_client=MagicMock(),
        site_coordinator=site_coordinator,
    )
    coordinator.data = stats

    description = next(d for d in DEVICE_TRAFFIC_SENSORS if d.key == description_key)

    return OmadaDeviceTrafficSensor(
        coordinator=coordinator,
        description=description,
        device_mac=device_mac,
    )


# ---------------------------------------------------------------------------
# Daily download / upload value tests
# ---------------------------------------------------------------------------


async def test_daily_download(hass: HomeAssistant) -> None:
    """Test daily download sensor returns daily_rx bytes."""
    sensor = _create_device_traffic_sensor(
        hass,
        {AP_MAC: {"daily_rx": 1_200_000_000, "daily_tx": 500_000_000}},
        "daily_download",
    )
    assert sensor.native_value == 1_200.0


async def test_daily_upload(hass: HomeAssistant) -> None:
    """Test daily upload sensor returns daily_tx in MB."""
    sensor = _create_device_traffic_sensor(
        hass,
        {AP_MAC: {"daily_rx": 1_200_000_000, "daily_tx": 500_000_000}},
        "daily_upload",
    )
    assert sensor.native_value == 500.0


async def test_daily_download_zero(hass: HomeAssistant) -> None:
    """Test daily download returns 0 when no traffic."""
    sensor = _create_device_traffic_sensor(
        hass,
        {AP_MAC: {"daily_rx": 0, "daily_tx": 0}},
        "daily_download",
    )
    assert sensor.native_value == 0.0


# ---------------------------------------------------------------------------
# Different device types
# ---------------------------------------------------------------------------


async def test_daily_download_switch(hass: HomeAssistant) -> None:
    """Test daily download for a switch device."""
    sensor = _create_device_traffic_sensor(
        hass,
        {SWITCH_MAC: {"daily_rx": 5_000_000_000, "daily_tx": 2_000_000_000}},
        "daily_download",
        device_mac=SWITCH_MAC,
    )
    assert sensor.native_value == 5_000.0


async def test_daily_upload_gateway(hass: HomeAssistant) -> None:
    """Test daily upload for a gateway device."""
    sensor = _create_device_traffic_sensor(
        hass,
        {GATEWAY_MAC: {"daily_rx": 10_000_000_000, "daily_tx": 8_000_000_000}},
        "daily_upload",
        device_mac=GATEWAY_MAC,
    )
    assert sensor.native_value == 8_000.0


# ---------------------------------------------------------------------------
# Unique ID and device info
# ---------------------------------------------------------------------------


async def test_unique_id_format(hass: HomeAssistant) -> None:
    """Test unique_id format for device traffic sensor."""
    sensor = _create_device_traffic_sensor(
        hass,
        {AP_MAC: {"daily_rx": 0, "daily_tx": 0}},
        "daily_download",
    )
    assert sensor.unique_id == f"{AP_MAC}_daily_download"


async def test_device_info(hass: HomeAssistant) -> None:
    """Test device_info links sensor to the infrastructure device."""
    sensor = _create_device_traffic_sensor(
        hass,
        {SWITCH_MAC: {"daily_rx": 0, "daily_tx": 0}},
        "daily_upload",
        device_mac=SWITCH_MAC,
    )
    device_info = sensor._attr_device_info  # noqa: SLF001
    assert (DOMAIN, SWITCH_MAC) in device_info["identifiers"]


# ---------------------------------------------------------------------------
# Availability edge cases
# ---------------------------------------------------------------------------


async def test_available_with_data(hass: HomeAssistant) -> None:
    """Test sensor is available when device data exists."""
    sensor = _create_device_traffic_sensor(
        hass,
        {AP_MAC: {"daily_rx": 100, "daily_tx": 50}},
        "daily_download",
    )
    assert sensor.available is True


async def test_unavailable_no_device(hass: HomeAssistant) -> None:
    """Test sensor unavailable when device not in stats data."""
    sensor = _create_device_traffic_sensor(
        hass,
        {},  # Empty stats
        "daily_download",
    )
    assert sensor.available is False


async def test_native_value_none_no_device(hass: HomeAssistant) -> None:
    """Test native_value is None when device not in data."""
    sensor = _create_device_traffic_sensor(
        hass,
        {},
        "daily_upload",
    )
    assert sensor.native_value is None


async def test_unavailable_missing_field(hass: HomeAssistant) -> None:
    """Test sensor unavailable when daily_rx field is None."""
    sensor = _create_device_traffic_sensor(
        hass,
        {AP_MAC: {"daily_tx": 100}},  # Missing daily_rx
        "daily_download",
    )
    assert sensor.available is False


async def test_unavailable_coordinator_failure(hass: HomeAssistant) -> None:
    """Test sensor unavailable when coordinator last_update_success is False."""
    sensor = _create_device_traffic_sensor(
        hass,
        {AP_MAC: {"daily_rx": 100, "daily_tx": 50}},
        "daily_download",
    )
    sensor.coordinator.last_update_success = False
    assert sensor.available is False
