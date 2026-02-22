"""Tests for OmadaWanBinarySensor entity."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

from custom_components.omada_open_api.binary_sensor import (
    WAN_PORT_BINARY_SENSORS,
    OmadaWanBinarySensor,
)
from custom_components.omada_open_api.const import DOMAIN
from custom_components.omada_open_api.coordinator import OmadaSiteCoordinator

from .conftest import SAMPLE_WAN_PORT_1, SAMPLE_WAN_PORT_2, TEST_SITE_ID, TEST_SITE_NAME

GATEWAY_MAC = "AA-BB-CC-DD-EE-03"


def _build_coordinator_data(
    wan_status: dict[str, list[dict]] | None = None,
) -> dict:
    """Build coordinator data with WAN status."""
    return {
        "devices": {},
        "poe_ports": {},
        "poe_budget": {},
        "site_id": TEST_SITE_ID,
        "site_name": TEST_SITE_NAME,
        "wan_status": wan_status or {},
    }


def _create_wan_binary_sensor(
    hass: HomeAssistant,
    wan_status: dict[str, list[dict]],
    description_key: str,
    gateway_mac: str = GATEWAY_MAC,
    port_index: int = 0,
    port_name: str = "WAN1",
) -> OmadaWanBinarySensor:
    """Create an OmadaWanBinarySensor with a mock coordinator."""
    coordinator = OmadaSiteCoordinator(
        hass=hass,
        api_client=MagicMock(),
        site_id=TEST_SITE_ID,
        site_name=TEST_SITE_NAME,
    )
    coordinator.data = _build_coordinator_data(wan_status)

    description = next(d for d in WAN_PORT_BINARY_SENSORS if d.key == description_key)

    return OmadaWanBinarySensor(
        coordinator=coordinator,
        description=description,
        gateway_mac=gateway_mac,
        port_index=port_index,
        port_name=port_name,
    )


# ---------------------------------------------------------------------------
# wan_connected binary sensor
# ---------------------------------------------------------------------------


async def test_wan_connected_online(hass: HomeAssistant) -> None:
    """Test WAN connected binary sensor is ON when status==1."""
    sensor = _create_wan_binary_sensor(
        hass,
        {GATEWAY_MAC: [SAMPLE_WAN_PORT_1]},
        "wan_connected",
    )
    assert sensor.is_on is True


async def test_wan_connected_offline(hass: HomeAssistant) -> None:
    """Test WAN connected binary sensor is OFF when status==0."""
    sensor = _create_wan_binary_sensor(
        hass,
        {GATEWAY_MAC: [SAMPLE_WAN_PORT_2]},
        "wan_connected",
    )
    assert sensor.is_on is False


# ---------------------------------------------------------------------------
# wan_internet binary sensor
# ---------------------------------------------------------------------------


async def test_wan_internet_online(hass: HomeAssistant) -> None:
    """Test WAN internet binary sensor is ON when internetState==1."""
    sensor = _create_wan_binary_sensor(
        hass,
        {GATEWAY_MAC: [SAMPLE_WAN_PORT_1]},
        "wan_internet",
    )
    assert sensor.is_on is True


async def test_wan_internet_offline(hass: HomeAssistant) -> None:
    """Test WAN internet binary sensor is OFF when internetState==0."""
    sensor = _create_wan_binary_sensor(
        hass,
        {GATEWAY_MAC: [SAMPLE_WAN_PORT_2]},
        "wan_internet",
    )
    assert sensor.is_on is False


# ---------------------------------------------------------------------------
# Unique ID and device info
# ---------------------------------------------------------------------------


async def test_unique_id_format(hass: HomeAssistant) -> None:
    """Test unique_id includes gateway MAC, port index, and key."""
    sensor = _create_wan_binary_sensor(
        hass,
        {GATEWAY_MAC: [SAMPLE_WAN_PORT_1]},
        "wan_connected",
        port_index=0,
    )
    assert sensor.unique_id == f"{GATEWAY_MAC}_wan0_wan_connected"


async def test_unique_id_second_port(hass: HomeAssistant) -> None:
    """Test unique_id for second WAN port binary sensor."""
    sensor = _create_wan_binary_sensor(
        hass,
        {GATEWAY_MAC: [SAMPLE_WAN_PORT_1, SAMPLE_WAN_PORT_2]},
        "wan_internet",
        port_index=1,
        port_name="WAN2",
    )
    assert sensor.unique_id == f"{GATEWAY_MAC}_wan1_wan_internet"


async def test_device_info_links_to_gateway(hass: HomeAssistant) -> None:
    """Test device_info links binary sensor to the gateway device."""
    sensor = _create_wan_binary_sensor(
        hass,
        {GATEWAY_MAC: [SAMPLE_WAN_PORT_1]},
        "wan_connected",
    )
    device_info = sensor._attr_device_info  # noqa: SLF001
    assert (DOMAIN, GATEWAY_MAC) in device_info["identifiers"]


async def test_translation_placeholders(hass: HomeAssistant) -> None:
    """Test translation placeholders contain port_name."""
    sensor = _create_wan_binary_sensor(
        hass,
        {GATEWAY_MAC: [SAMPLE_WAN_PORT_1]},
        "wan_connected",
        port_name="WAN1",
    )
    placeholders = sensor._attr_translation_placeholders  # noqa: SLF001
    assert placeholders == {"port_name": "WAN1"}


# ---------------------------------------------------------------------------
# Availability edge cases
# ---------------------------------------------------------------------------


async def test_unavailable_no_gateway(hass: HomeAssistant) -> None:
    """Test binary sensor unavailable when gateway not in data."""
    sensor = _create_wan_binary_sensor(
        hass,
        {},
        "wan_connected",
    )
    assert sensor.available is False


async def test_unavailable_port_index_out_of_range(
    hass: HomeAssistant,
) -> None:
    """Test binary sensor unavailable when port_index exceeds list."""
    sensor = _create_wan_binary_sensor(
        hass,
        {GATEWAY_MAC: [SAMPLE_WAN_PORT_1]},
        "wan_connected",
        port_index=5,
    )
    assert sensor.available is False


async def test_is_on_false_when_no_port_data(hass: HomeAssistant) -> None:
    """Test is_on returns False when port data missing."""
    sensor = _create_wan_binary_sensor(
        hass,
        {},
        "wan_connected",
    )
    assert sensor.is_on is False


async def test_unavailable_coordinator_failure(hass: HomeAssistant) -> None:
    """Test binary sensor unavailable when coordinator fails."""
    sensor = _create_wan_binary_sensor(
        hass,
        {GATEWAY_MAC: [SAMPLE_WAN_PORT_1]},
        "wan_connected",
    )
    sensor.coordinator.last_update_success = False
    assert sensor.available is False
