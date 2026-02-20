"""Tests for OmadaClientBinarySensor entity."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

from custom_components.omada_open_api.binary_sensor import (
    CLIENT_BINARY_SENSORS,
    OmadaClientBinarySensor,
)
from custom_components.omada_open_api.clients import process_client
from custom_components.omada_open_api.const import DOMAIN
from custom_components.omada_open_api.coordinator import OmadaClientCoordinator

from .conftest import (
    SAMPLE_CLIENT_WIRED,
    SAMPLE_CLIENT_WIRELESS,
    TEST_SITE_ID,
    TEST_SITE_NAME,
)

WIRELESS_MAC = "11-22-33-44-55-AA"
WIRED_MAC = "11-22-33-44-55-BB"


def _processed_wireless() -> dict:
    """Return processed wireless client data."""
    return process_client(SAMPLE_CLIENT_WIRELESS)


def _processed_wired() -> dict:
    """Return processed wired client data."""
    return process_client(SAMPLE_CLIENT_WIRED)


def _create_client_binary_sensor(
    hass: HomeAssistant,
    client_mac: str,
    clients: dict[str, dict],
    description_key: str,
) -> OmadaClientBinarySensor:
    """Create an OmadaClientBinarySensor with a mock coordinator."""
    coordinator = OmadaClientCoordinator(
        hass=hass,
        api_client=MagicMock(),
        site_id=TEST_SITE_ID,
        site_name=TEST_SITE_NAME,
        selected_client_macs=list(clients.keys()),
    )
    coordinator.data = clients

    description = next(d for d in CLIENT_BINARY_SENSORS if d.key == description_key)

    return OmadaClientBinarySensor(
        coordinator=coordinator,
        description=description,
        client_mac=client_mac,
    )


# ---------------------------------------------------------------------------
# Initialization & identity
# ---------------------------------------------------------------------------


async def test_client_binary_sensor_unique_id(hass: HomeAssistant) -> None:
    """Test unique_id format for client binary sensor."""
    sensor = _create_client_binary_sensor(
        hass,
        WIRELESS_MAC,
        {WIRELESS_MAC: _processed_wireless()},
        "power_save",
    )
    assert sensor.unique_id == f"{WIRELESS_MAC}_power_save"


async def test_client_binary_sensor_device_info(hass: HomeAssistant) -> None:
    """Test device_info links to client device."""
    sensor = _create_client_binary_sensor(
        hass,
        WIRELESS_MAC,
        {WIRELESS_MAC: _processed_wireless()},
        "power_save",
    )
    device_info = sensor._attr_device_info  # noqa: SLF001
    assert (DOMAIN, WIRELESS_MAC) in device_info["identifiers"]


# ---------------------------------------------------------------------------
# Power save - is_on
# ---------------------------------------------------------------------------


async def test_power_save_on(hass: HomeAssistant) -> None:
    """Test power_save returns True when enabled."""
    sensor = _create_client_binary_sensor(
        hass,
        WIRELESS_MAC,
        {WIRELESS_MAC: _processed_wireless()},
        "power_save",
    )
    # SAMPLE_CLIENT_WIRELESS has powerSave: True
    assert sensor.is_on is True


async def test_power_save_off(hass: HomeAssistant) -> None:
    """Test power_save returns False when disabled."""
    data = _processed_wireless()
    data["power_save"] = False
    sensor = _create_client_binary_sensor(
        hass,
        WIRELESS_MAC,
        {WIRELESS_MAC: data},
        "power_save",
    )
    assert sensor.is_on is False


# ---------------------------------------------------------------------------
# Availability
# ---------------------------------------------------------------------------


async def test_power_save_available_wireless(hass: HomeAssistant) -> None:
    """Test power_save available for wireless client."""
    sensor = _create_client_binary_sensor(
        hass,
        WIRELESS_MAC,
        {WIRELESS_MAC: _processed_wireless()},
        "power_save",
    )
    assert sensor.available is True


async def test_power_save_unavailable_wired(hass: HomeAssistant) -> None:
    """Test power_save unavailable for wired client."""
    sensor = _create_client_binary_sensor(
        hass,
        WIRED_MAC,
        {WIRED_MAC: _processed_wired()},
        "power_save",
    )
    assert sensor.available is False


async def test_power_save_unavailable_missing_client(hass: HomeAssistant) -> None:
    """Test power_save unavailable when client disappears."""
    sensor = _create_client_binary_sensor(
        hass,
        WIRELESS_MAC,
        {WIRELESS_MAC: _processed_wireless()},
        "power_save",
    )
    sensor.coordinator.data = {}
    assert sensor.available is False
    assert sensor.is_on is False


async def test_power_save_unavailable_coordinator_failure(
    hass: HomeAssistant,
) -> None:
    """Test power_save unavailable when coordinator fails."""
    sensor = _create_client_binary_sensor(
        hass,
        WIRELESS_MAC,
        {WIRELESS_MAC: _processed_wireless()},
        "power_save",
    )
    sensor.coordinator.last_update_success = False
    assert sensor.available is False
