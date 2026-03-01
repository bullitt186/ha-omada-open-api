"""Tests for OmadaSiteSensor entity - site-level aggregation sensors."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from unittest.mock import MagicMock

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

from custom_components.omada_open_api.const import DOMAIN
from custom_components.omada_open_api.coordinator import OmadaSiteCoordinator
from custom_components.omada_open_api.sensor import SITE_SENSORS, OmadaSiteSensor

from .conftest import TEST_SITE_ID, TEST_SITE_NAME

# Sample client data for testing
SAMPLE_CLIENTS: list[dict[str, Any]] = [
    {"name": "Laptop", "mac": "CC:00:00:00:00:01", "ip": "10.0.0.1", "wireless": True},
    {"name": "Phone", "mac": "CC:00:00:00:00:02", "ip": "10.0.0.2", "wireless": True},
    {
        "name": "Printer",
        "mac": "CC:00:00:00:00:03",
        "ip": "10.0.0.3",
        "wireless": False,
    },
    {
        "name": "Desktop",
        "mac": "CC:00:00:00:00:04",
        "ip": "10.0.0.4",
        "wireless": False,
    },
    {"name": "Tablet", "mac": "CC:00:00:00:00:05", "ip": "10.0.0.5", "wireless": True},
]

SAMPLE_POE_BUDGET: dict[str, dict[str, Any]] = {
    "AA-BB-CC-DD-EE-02": {
        "total_power": 250.0,
        "total_power_used": 45.3,
        "total_percent_used": 18.1,
    },
    "AA-BB-CC-DD-EE-04": {
        "total_power": 370.0,
        "total_power_used": 112.7,
        "total_percent_used": 30.5,
    },
}


def _build_site_data(
    all_clients: list[dict[str, Any]] | None = None,
    poe_budget: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build coordinator data dict with site-level data."""
    return {
        "devices": {},
        "poe_ports": {},
        "poe_budget": poe_budget or {},
        "ssids": [],
        "ap_ssid_overrides": {},
        "wan_status": {},
        "all_clients": all_clients or [],
        "site_id": TEST_SITE_ID,
        "site_name": TEST_SITE_NAME,
    }


def _create_site_sensor(
    hass: HomeAssistant,
    data: dict[str, Any],
    description_key: str,
) -> OmadaSiteSensor:
    """Create an OmadaSiteSensor with a mock coordinator."""
    coordinator = OmadaSiteCoordinator(
        hass=hass,
        api_client=MagicMock(),
        site_id=TEST_SITE_ID,
        site_name=TEST_SITE_NAME,
    )
    coordinator.data = data

    description = next(d for d in SITE_SENSORS if d.key == description_key)

    return OmadaSiteSensor(
        coordinator=coordinator,
        description=description,
    )


# ---------------------------------------------------------------------------
# Total clients
# ---------------------------------------------------------------------------


async def test_site_total_clients(hass: HomeAssistant) -> None:
    """Test site total clients returns count of all clients."""
    data = _build_site_data(all_clients=SAMPLE_CLIENTS)
    sensor = _create_site_sensor(hass, data, "site_total_clients")
    assert sensor.native_value == 5


async def test_site_total_clients_attrs(hass: HomeAssistant) -> None:
    """Test site total clients has client list attribute."""
    data = _build_site_data(all_clients=SAMPLE_CLIENTS)
    sensor = _create_site_sensor(hass, data, "site_total_clients")
    attrs = sensor.extra_state_attributes
    assert attrs is not None
    assert len(attrs["clients"]) == 5
    names = {c["name"] for c in attrs["clients"]}
    assert "Laptop" in names
    assert "Desktop" in names


async def test_site_total_clients_empty(hass: HomeAssistant) -> None:
    """Test site total clients returns 0 when no clients."""
    data = _build_site_data(all_clients=[])
    sensor = _create_site_sensor(hass, data, "site_total_clients")
    assert sensor.native_value == 0


# ---------------------------------------------------------------------------
# Wired clients
# ---------------------------------------------------------------------------


async def test_site_wired_clients(hass: HomeAssistant) -> None:
    """Test site wired clients returns only wired count."""
    data = _build_site_data(all_clients=SAMPLE_CLIENTS)
    sensor = _create_site_sensor(hass, data, "site_wired_clients")
    assert sensor.native_value == 2


async def test_site_wired_clients_attrs(hass: HomeAssistant) -> None:
    """Test site wired clients has only wired clients in attribute."""
    data = _build_site_data(all_clients=SAMPLE_CLIENTS)
    sensor = _create_site_sensor(hass, data, "site_wired_clients")
    attrs = sensor.extra_state_attributes
    assert attrs is not None
    assert len(attrs["clients"]) == 2
    names = {c["name"] for c in attrs["clients"]}
    assert names == {"Printer", "Desktop"}


# ---------------------------------------------------------------------------
# Wireless clients
# ---------------------------------------------------------------------------


async def test_site_wireless_clients(hass: HomeAssistant) -> None:
    """Test site wireless clients returns only wireless count."""
    data = _build_site_data(all_clients=SAMPLE_CLIENTS)
    sensor = _create_site_sensor(hass, data, "site_wireless_clients")
    assert sensor.native_value == 3


async def test_site_wireless_clients_attrs(hass: HomeAssistant) -> None:
    """Test site wireless clients has only wireless clients in attribute."""
    data = _build_site_data(all_clients=SAMPLE_CLIENTS)
    sensor = _create_site_sensor(hass, data, "site_wireless_clients")
    attrs = sensor.extra_state_attributes
    assert attrs is not None
    assert len(attrs["clients"]) == 3
    names = {c["name"] for c in attrs["clients"]}
    assert names == {"Laptop", "Phone", "Tablet"}


# ---------------------------------------------------------------------------
# PoE consumption
# ---------------------------------------------------------------------------


async def test_site_poe_consumption(hass: HomeAssistant) -> None:
    """Test site PoE consumption sums across all switches."""
    data = _build_site_data(poe_budget=SAMPLE_POE_BUDGET)
    sensor = _create_site_sensor(hass, data, "site_poe_consumption")
    # 45.3 + 112.7 = 158.0
    assert sensor.native_value == 158.0


async def test_site_poe_consumption_no_switches(hass: HomeAssistant) -> None:
    """Test site PoE consumption is 0 when no switches."""
    data = _build_site_data(poe_budget={})
    sensor = _create_site_sensor(hass, data, "site_poe_consumption")
    assert sensor.native_value == 0.0


async def test_site_poe_consumption_no_attrs(hass: HomeAssistant) -> None:
    """Test PoE consumption sensor has no client list attribute."""
    data = _build_site_data(poe_budget=SAMPLE_POE_BUDGET)
    sensor = _create_site_sensor(hass, data, "site_poe_consumption")
    assert sensor.extra_state_attributes is None


# ---------------------------------------------------------------------------
# Identity and device_info
# ---------------------------------------------------------------------------


async def test_site_sensor_unique_id(hass: HomeAssistant) -> None:
    """Test unique_id format for site sensor."""
    data = _build_site_data()
    sensor = _create_site_sensor(hass, data, "site_total_clients")
    assert sensor.unique_id == f"site_{TEST_SITE_ID}_site_total_clients"


async def test_site_sensor_device_info(hass: HomeAssistant) -> None:
    """Test device_info uses site device identifier."""
    data = _build_site_data()
    sensor = _create_site_sensor(hass, data, "site_total_clients")
    device_info = sensor._attr_device_info  # noqa: SLF001
    assert (DOMAIN, f"site_{TEST_SITE_ID}") in device_info["identifiers"]


# ---------------------------------------------------------------------------
# Availability
# ---------------------------------------------------------------------------


async def test_site_sensor_available(hass: HomeAssistant) -> None:
    """Test site sensor available when coordinator succeeds."""
    data = _build_site_data(all_clients=SAMPLE_CLIENTS)
    sensor = _create_site_sensor(hass, data, "site_total_clients")
    assert sensor.available is True


async def test_site_sensor_unavailable_coordinator_failure(
    hass: HomeAssistant,
) -> None:
    """Test site sensor unavailable when coordinator fails."""
    data = _build_site_data(all_clients=SAMPLE_CLIENTS)
    sensor = _create_site_sensor(hass, data, "site_total_clients")
    sensor.coordinator.last_update_success = False
    assert sensor.available is False
