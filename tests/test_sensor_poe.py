"""Tests for OmadaPoeSensor entity."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

from custom_components.omada_open_api.const import DOMAIN
from custom_components.omada_open_api.coordinator import OmadaSiteCoordinator
from custom_components.omada_open_api.sensor import POE_DISPLAY_TYPES, OmadaPoeSensor

from .conftest import TEST_SITE_ID, TEST_SITE_NAME


def _build_poe_coordinator_data(
    poe_ports: dict | None = None,
) -> dict:
    """Build coordinator data dict with PoE ports."""
    return {
        "devices": {},
        "poe_ports": poe_ports or {},
        "site_id": TEST_SITE_ID,
        "site_name": TEST_SITE_NAME,
    }


SAMPLE_PORT_DATA = {
    "switch_mac": "AA-BB-CC-DD-EE-02",
    "switch_name": "Core Switch",
    "port": 1,
    "port_name": "Port 1",
    "poe_enabled": True,
    "power": 12.5,
    "voltage": 53.2,
    "current": 235.0,
    "poe_status": 1.0,
    "pd_class": "Class 4",
    "poe_display_type": 4,
    "connected_status": 0,
}

SAMPLE_PORT_DATA_DISABLED = {
    "switch_mac": "AA-BB-CC-DD-EE-02",
    "switch_name": "Core Switch",
    "port": 2,
    "port_name": "Port 2",
    "poe_enabled": False,
    "power": 0.0,
    "voltage": 0.0,
    "current": 0.0,
    "poe_status": 0.0,
    "pd_class": "",
    "poe_display_type": 4,
    "connected_status": 1,
}


def _create_poe_sensor(
    hass: HomeAssistant,
    port_key: str,
    poe_ports: dict,
) -> OmadaPoeSensor:
    """Create an OmadaPoeSensor with a mock coordinator."""
    coordinator = OmadaSiteCoordinator(
        hass=hass,
        api_client=MagicMock(),
        site_id=TEST_SITE_ID,
        site_name=TEST_SITE_NAME,
    )
    coordinator.data = _build_poe_coordinator_data(poe_ports)

    return OmadaPoeSensor(coordinator=coordinator, port_key=port_key)


# ---------------------------------------------------------------------------
# Initialization & identity
# ---------------------------------------------------------------------------


async def test_poe_sensor_unique_id(hass: HomeAssistant) -> None:
    """Test unique_id format for PoE sensor."""
    sensor = _create_poe_sensor(
        hass,
        "AA-BB-CC-DD-EE-02_1",
        {"AA-BB-CC-DD-EE-02_1": SAMPLE_PORT_DATA},
    )

    assert sensor.unique_id == "AA-BB-CC-DD-EE-02_port1_poe_power"


async def test_poe_sensor_name(hass: HomeAssistant) -> None:
    """Test sensor name includes port name."""
    sensor = _create_poe_sensor(
        hass,
        "AA-BB-CC-DD-EE-02_1",
        {"AA-BB-CC-DD-EE-02_1": SAMPLE_PORT_DATA},
    )

    assert sensor.name == "Port 1 PoE power"


async def test_poe_sensor_device_info(hass: HomeAssistant) -> None:
    """Test device_info links to parent switch."""
    sensor = _create_poe_sensor(
        hass,
        "AA-BB-CC-DD-EE-02_1",
        {"AA-BB-CC-DD-EE-02_1": SAMPLE_PORT_DATA},
    )

    assert sensor.device_info is not None
    assert (DOMAIN, "AA-BB-CC-DD-EE-02") in sensor.device_info["identifiers"]


# ---------------------------------------------------------------------------
# State values
# ---------------------------------------------------------------------------


async def test_poe_sensor_native_value_returns_power(hass: HomeAssistant) -> None:
    """Test native_value returns power in watts."""
    sensor = _create_poe_sensor(
        hass,
        "AA-BB-CC-DD-EE-02_1",
        {"AA-BB-CC-DD-EE-02_1": SAMPLE_PORT_DATA},
    )

    assert sensor.native_value == 12.5


async def test_poe_sensor_native_value_disabled_port(hass: HomeAssistant) -> None:
    """Test native_value for a disabled PoE port returns 0.0."""
    sensor = _create_poe_sensor(
        hass,
        "AA-BB-CC-DD-EE-02_2",
        {"AA-BB-CC-DD-EE-02_2": SAMPLE_PORT_DATA_DISABLED},
    )

    assert sensor.native_value == 0.0


async def test_poe_sensor_native_value_missing_port_data(
    hass: HomeAssistant,
) -> None:
    """Test native_value returns None when port data is missing."""
    sensor = _create_poe_sensor(
        hass,
        "AA-BB-CC-DD-EE-02_1",
        {"AA-BB-CC-DD-EE-02_1": SAMPLE_PORT_DATA},
    )

    # Simulate port disappearing from coordinator data.
    sensor.coordinator.data = _build_poe_coordinator_data({})

    assert sensor.native_value is None


# ---------------------------------------------------------------------------
# Extra attributes
# ---------------------------------------------------------------------------


async def test_poe_sensor_extra_attributes(hass: HomeAssistant) -> None:
    """Test extra_state_attributes contains all expected fields."""
    sensor = _create_poe_sensor(
        hass,
        "AA-BB-CC-DD-EE-02_1",
        {"AA-BB-CC-DD-EE-02_1": SAMPLE_PORT_DATA},
    )

    attrs = sensor.extra_state_attributes
    assert attrs["port"] == 1
    assert attrs["port_name"] == "Port 1"
    assert attrs["poe_enabled"] is True
    assert attrs["voltage"] == 53.2
    assert attrs["current"] == 235.0
    assert attrs["pd_class"] == "Class 4"
    assert attrs["poe_standard"] == "PoE+ (30W)"


async def test_poe_sensor_extra_attributes_no_pd_class(
    hass: HomeAssistant,
) -> None:
    """Test extra_state_attributes omits pd_class when empty."""
    sensor = _create_poe_sensor(
        hass,
        "AA-BB-CC-DD-EE-02_2",
        {"AA-BB-CC-DD-EE-02_2": SAMPLE_PORT_DATA_DISABLED},
    )

    attrs = sensor.extra_state_attributes
    assert "pd_class" not in attrs


async def test_poe_sensor_extra_attributes_missing_data(
    hass: HomeAssistant,
) -> None:
    """Test extra_state_attributes returns empty dict when port data missing."""
    sensor = _create_poe_sensor(
        hass,
        "AA-BB-CC-DD-EE-02_1",
        {"AA-BB-CC-DD-EE-02_1": SAMPLE_PORT_DATA},
    )

    sensor.coordinator.data = _build_poe_coordinator_data({})

    assert sensor.extra_state_attributes == {}


# ---------------------------------------------------------------------------
# Availability
# ---------------------------------------------------------------------------


async def test_poe_sensor_available_when_data_present(hass: HomeAssistant) -> None:
    """Test sensor is available when coordinator succeeds and port data exists."""
    sensor = _create_poe_sensor(
        hass,
        "AA-BB-CC-DD-EE-02_1",
        {"AA-BB-CC-DD-EE-02_1": SAMPLE_PORT_DATA},
    )

    # Simulate successful update.
    sensor.coordinator.last_update_success = True
    assert sensor.available is True


async def test_poe_sensor_unavailable_when_update_failed(
    hass: HomeAssistant,
) -> None:
    """Test sensor is unavailable when coordinator update fails."""
    sensor = _create_poe_sensor(
        hass,
        "AA-BB-CC-DD-EE-02_1",
        {"AA-BB-CC-DD-EE-02_1": SAMPLE_PORT_DATA},
    )

    sensor.coordinator.last_update_success = False
    assert sensor.available is False


async def test_poe_sensor_unavailable_when_port_data_gone(
    hass: HomeAssistant,
) -> None:
    """Test sensor is unavailable when port disappears from data."""
    sensor = _create_poe_sensor(
        hass,
        "AA-BB-CC-DD-EE-02_1",
        {"AA-BB-CC-DD-EE-02_1": SAMPLE_PORT_DATA},
    )

    sensor.coordinator.last_update_success = True
    sensor.coordinator.data = _build_poe_coordinator_data({})
    assert sensor.available is False


# ---------------------------------------------------------------------------
# POE_DISPLAY_TYPES mapping
# ---------------------------------------------------------------------------


async def test_poe_display_types_mapping(hass: HomeAssistant) -> None:
    """Test all POE_DISPLAY_TYPES values are present."""
    assert POE_DISPLAY_TYPES[-1] == "Not Supported"
    assert POE_DISPLAY_TYPES[0] == "PoE"
    assert POE_DISPLAY_TYPES[4] == "PoE+ (30W)"
    assert POE_DISPLAY_TYPES[8] == "PoE++ (90W)"
    assert POE_DISPLAY_TYPES[9] == "PoE++ (100W)"
    assert len(POE_DISPLAY_TYPES) == 11


async def test_poe_sensor_unknown_display_type(hass: HomeAssistant) -> None:
    """Test that an unknown poe_display_type maps to 'Unknown'."""
    port_data = {**SAMPLE_PORT_DATA, "poe_display_type": 99}
    sensor = _create_poe_sensor(
        hass,
        "AA-BB-CC-DD-EE-02_1",
        {"AA-BB-CC-DD-EE-02_1": port_data},
    )

    attrs = sensor.extra_state_attributes
    assert attrs["poe_standard"] == "Unknown"
