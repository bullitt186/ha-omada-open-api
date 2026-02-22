"""Tests for OmadaWanSensor entity."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

from custom_components.omada_open_api.const import DOMAIN, WAN_SPEED_MAP
from custom_components.omada_open_api.coordinator import OmadaSiteCoordinator
from custom_components.omada_open_api.sensor import (
    WAN_PORT_SENSORS,
    OmadaWanSensor,
    _build_wan_sensors,
)

from .conftest import SAMPLE_WAN_PORT_1, SAMPLE_WAN_PORT_2, TEST_SITE_ID, TEST_SITE_NAME

GATEWAY_MAC = "AA-BB-CC-DD-EE-03"


def _build_coordinator_data(
    wan_status: dict[str, list[dict]] | None = None,
) -> dict:
    """Build coordinator data dict with WAN status."""
    return {
        "devices": {},
        "poe_ports": {},
        "poe_budget": {},
        "site_id": TEST_SITE_ID,
        "site_name": TEST_SITE_NAME,
        "wan_status": wan_status or {},
    }


def _create_wan_sensor(
    hass: HomeAssistant,
    wan_status: dict[str, list[dict]],
    description_key: str,
    gateway_mac: str = GATEWAY_MAC,
    port_index: int = 0,
    port_name: str = "WAN1",
) -> OmadaWanSensor:
    """Create an OmadaWanSensor with a mock coordinator."""
    coordinator = OmadaSiteCoordinator(
        hass=hass,
        api_client=MagicMock(),
        site_id=TEST_SITE_ID,
        site_name=TEST_SITE_NAME,
    )
    coordinator.data = _build_coordinator_data(wan_status)

    description = next(d for d in WAN_PORT_SENSORS if d.key == description_key)

    return OmadaWanSensor(
        coordinator=coordinator,
        description=description,
        gateway_mac=gateway_mac,
        port_index=port_index,
        port_name=port_name,
    )


# ---------------------------------------------------------------------------
# WAN download / upload rate sensors
# ---------------------------------------------------------------------------


async def test_wan_download_rate(hass: HomeAssistant) -> None:
    """Test WAN download rate sensor returns rxRate."""
    sensor = _create_wan_sensor(
        hass,
        {GATEWAY_MAC: [SAMPLE_WAN_PORT_1]},
        "wan_download_rate",
    )
    assert sensor.native_value == 1250.5


async def test_wan_upload_rate(hass: HomeAssistant) -> None:
    """Test WAN upload rate sensor returns txRate."""
    sensor = _create_wan_sensor(
        hass,
        {GATEWAY_MAC: [SAMPLE_WAN_PORT_1]},
        "wan_upload_rate",
    )
    assert sensor.native_value == 340.2


async def test_wan_download_rate_disconnected(hass: HomeAssistant) -> None:
    """Test WAN download rate on disconnected port."""
    sensor = _create_wan_sensor(
        hass,
        {GATEWAY_MAC: [SAMPLE_WAN_PORT_2]},
        "wan_download_rate",
    )
    assert sensor.native_value == 0


# ---------------------------------------------------------------------------
# WAN download / upload total sensors
# ---------------------------------------------------------------------------


async def test_wan_download_total(hass: HomeAssistant) -> None:
    """Test WAN download total sensor returns rx bytes."""
    sensor = _create_wan_sensor(
        hass,
        {GATEWAY_MAC: [SAMPLE_WAN_PORT_1]},
        "wan_download_total",
    )
    assert sensor.native_value == 15_000.0


async def test_wan_upload_total(hass: HomeAssistant) -> None:
    """Test WAN upload total sensor returns tx in MB."""
    sensor = _create_wan_sensor(
        hass,
        {GATEWAY_MAC: [SAMPLE_WAN_PORT_1]},
        "wan_upload_total",
    )
    assert sensor.native_value == 3_000.0


# ---------------------------------------------------------------------------
# WAN latency and packet loss
# ---------------------------------------------------------------------------


async def test_wan_latency(hass: HomeAssistant) -> None:
    """Test WAN latency sensor returns latency in ms."""
    sensor = _create_wan_sensor(
        hass,
        {GATEWAY_MAC: [SAMPLE_WAN_PORT_1]},
        "wan_latency",
    )
    assert sensor.native_value == 12


async def test_wan_latency_disconnected_unavailable(hass: HomeAssistant) -> None:
    """Test WAN latency sensor unavailable when port is disconnected."""
    sensor = _create_wan_sensor(
        hass,
        {GATEWAY_MAC: [SAMPLE_WAN_PORT_2]},
        "wan_latency",
    )
    assert sensor.available is False


async def test_wan_packet_loss(hass: HomeAssistant) -> None:
    """Test WAN packet loss sensor returns loss percentage."""
    sensor = _create_wan_sensor(
        hass,
        {GATEWAY_MAC: [SAMPLE_WAN_PORT_1]},
        "wan_packet_loss",
    )
    assert sensor.native_value == 0.1


async def test_wan_packet_loss_disconnected_unavailable(
    hass: HomeAssistant,
) -> None:
    """Test WAN packet loss unavailable when port disconnected."""
    sensor = _create_wan_sensor(
        hass,
        {GATEWAY_MAC: [SAMPLE_WAN_PORT_2]},
        "wan_packet_loss",
    )
    assert sensor.available is False


# ---------------------------------------------------------------------------
# WAN IP address and link speed
# ---------------------------------------------------------------------------


async def test_wan_ip_address(hass: HomeAssistant) -> None:
    """Test WAN IP address sensor returns the IP."""
    sensor = _create_wan_sensor(
        hass,
        {GATEWAY_MAC: [SAMPLE_WAN_PORT_1]},
        "wan_ip_address",
    )
    assert sensor.native_value == "203.0.113.10"


async def test_wan_ip_address_empty_unavailable(hass: HomeAssistant) -> None:
    """Test WAN IP address unavailable when IP is empty."""
    sensor = _create_wan_sensor(
        hass,
        {GATEWAY_MAC: [SAMPLE_WAN_PORT_2]},
        "wan_ip_address",
    )
    assert sensor.available is False


async def test_wan_link_speed(hass: HomeAssistant) -> None:
    """Test WAN link speed returns mapped Mbps value."""
    sensor = _create_wan_sensor(
        hass,
        {GATEWAY_MAC: [SAMPLE_WAN_PORT_1]},
        "wan_link_speed",
    )
    # speed=3 → 1000 Mbps via WAN_SPEED_MAP
    assert sensor.native_value == WAN_SPEED_MAP[3]
    assert sensor.native_value == 1000


async def test_wan_link_speed_100mbps(hass: HomeAssistant) -> None:
    """Test WAN link speed for 100 Mbps port."""
    sensor = _create_wan_sensor(
        hass,
        {GATEWAY_MAC: [SAMPLE_WAN_PORT_2]},
        "wan_link_speed",
    )
    # speed=2 → 100 Mbps
    assert sensor.native_value == WAN_SPEED_MAP[2]
    assert sensor.native_value == 100


# ---------------------------------------------------------------------------
# Multiple WAN ports (port_index)
# ---------------------------------------------------------------------------


async def test_second_wan_port(hass: HomeAssistant) -> None:
    """Test sensor for the second WAN port (port_index=1)."""
    sensor = _create_wan_sensor(
        hass,
        {GATEWAY_MAC: [SAMPLE_WAN_PORT_1, SAMPLE_WAN_PORT_2]},
        "wan_download_rate",
        port_index=1,
        port_name="WAN2",
    )
    assert sensor.native_value == 0


# ---------------------------------------------------------------------------
# Unique ID and device info
# ---------------------------------------------------------------------------


async def test_unique_id_format(hass: HomeAssistant) -> None:
    """Test unique_id includes gateway MAC, port index, and key."""
    sensor = _create_wan_sensor(
        hass,
        {GATEWAY_MAC: [SAMPLE_WAN_PORT_1]},
        "wan_download_rate",
        port_index=0,
    )
    assert sensor.unique_id == f"{GATEWAY_MAC}_wan0_wan_download_rate"


async def test_unique_id_second_port(hass: HomeAssistant) -> None:
    """Test unique_id for second WAN port."""
    sensor = _create_wan_sensor(
        hass,
        {GATEWAY_MAC: [SAMPLE_WAN_PORT_1, SAMPLE_WAN_PORT_2]},
        "wan_upload_rate",
        port_index=1,
        port_name="WAN2",
    )
    assert sensor.unique_id == f"{GATEWAY_MAC}_wan1_wan_upload_rate"


async def test_device_info_links_to_gateway(hass: HomeAssistant) -> None:
    """Test device_info links sensor to the gateway device."""
    sensor = _create_wan_sensor(
        hass,
        {GATEWAY_MAC: [SAMPLE_WAN_PORT_1]},
        "wan_download_rate",
    )
    device_info = sensor._attr_device_info  # noqa: SLF001
    assert (DOMAIN, GATEWAY_MAC) in device_info["identifiers"]


async def test_translation_placeholders(hass: HomeAssistant) -> None:
    """Test translation placeholders contain port_name."""
    sensor = _create_wan_sensor(
        hass,
        {GATEWAY_MAC: [SAMPLE_WAN_PORT_1]},
        "wan_latency",
        port_name="WAN1",
    )
    placeholders = sensor._attr_translation_placeholders  # noqa: SLF001
    assert placeholders == {"port_name": "WAN1"}


# ---------------------------------------------------------------------------
# Availability edge cases
# ---------------------------------------------------------------------------


async def test_wan_sensor_unavailable_no_gateway(hass: HomeAssistant) -> None:
    """Test sensor unavailable when gateway not in WAN status data."""
    sensor = _create_wan_sensor(
        hass,
        {},  # Empty WAN status
        "wan_download_rate",
    )
    assert sensor.available is False


async def test_wan_sensor_unavailable_port_index_out_of_range(
    hass: HomeAssistant,
) -> None:
    """Test sensor unavailable when port_index exceeds port list."""
    sensor = _create_wan_sensor(
        hass,
        {GATEWAY_MAC: [SAMPLE_WAN_PORT_1]},
        "wan_download_rate",
        port_index=5,
    )
    assert sensor.available is False


async def test_wan_sensor_none_when_no_port_data(hass: HomeAssistant) -> None:
    """Test native_value is None when port data missing."""
    sensor = _create_wan_sensor(
        hass,
        {},
        "wan_download_rate",
    )
    assert sensor.native_value is None


async def test_wan_sensor_unavailable_coordinator_failure(
    hass: HomeAssistant,
) -> None:
    """Test sensor unavailable when coordinator last_update_success is False."""
    sensor = _create_wan_sensor(
        hass,
        {GATEWAY_MAC: [SAMPLE_WAN_PORT_1]},
        "wan_download_rate",
    )
    sensor.coordinator.last_update_success = False
    assert sensor.available is False


# ---------------------------------------------------------------------------
# _build_wan_sensors helper
# ---------------------------------------------------------------------------


async def test_build_wan_sensors_creates_all_descriptions(
    hass: HomeAssistant,
) -> None:
    """Test _build_wan_sensors creates a sensor for each description per port."""
    coordinator = OmadaSiteCoordinator(
        hass=hass,
        api_client=MagicMock(),
        site_id=TEST_SITE_ID,
        site_name=TEST_SITE_NAME,
    )
    wan_status = {GATEWAY_MAC: [SAMPLE_WAN_PORT_1]}
    known: set[str] = set()

    entities = _build_wan_sensors(coordinator, wan_status, known)
    assert len(entities) == len(WAN_PORT_SENSORS)
    assert f"{GATEWAY_MAC}_wan_0" in known


async def test_build_wan_sensors_skips_already_known(
    hass: HomeAssistant,
) -> None:
    """Test _build_wan_sensors skips already-known WAN port keys."""
    coordinator = OmadaSiteCoordinator(
        hass=hass,
        api_client=MagicMock(),
        site_id=TEST_SITE_ID,
        site_name=TEST_SITE_NAME,
    )
    wan_status = {GATEWAY_MAC: [SAMPLE_WAN_PORT_1]}
    known: set[str] = {f"{GATEWAY_MAC}_wan_0"}

    entities = _build_wan_sensors(coordinator, wan_status, known)
    assert entities == []


async def test_build_wan_sensors_multiple_ports(
    hass: HomeAssistant,
) -> None:
    """Test _build_wan_sensors handles multiple WAN ports."""
    coordinator = OmadaSiteCoordinator(
        hass=hass,
        api_client=MagicMock(),
        site_id=TEST_SITE_ID,
        site_name=TEST_SITE_NAME,
    )
    wan_status = {GATEWAY_MAC: [SAMPLE_WAN_PORT_1, SAMPLE_WAN_PORT_2]}
    known: set[str] = set()

    entities = _build_wan_sensors(coordinator, wan_status, known)
    assert len(entities) == len(WAN_PORT_SENSORS) * 2


async def test_build_wan_sensors_empty_wan_status(
    hass: HomeAssistant,
) -> None:
    """Test _build_wan_sensors returns empty list for empty wan_status."""
    coordinator = OmadaSiteCoordinator(
        hass=hass,
        api_client=MagicMock(),
        site_id=TEST_SITE_ID,
        site_name=TEST_SITE_NAME,
    )
    entities = _build_wan_sensors(coordinator, {}, set())
    assert entities == []
