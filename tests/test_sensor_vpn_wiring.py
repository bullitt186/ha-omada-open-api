"""Tests for VPN entity creation wiring in sensor/binary_sensor platforms."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

from custom_components.omada_open_api.binary_sensor import OmadaVpnBinarySensor
from custom_components.omada_open_api.sensor import VPN_SENSORS, OmadaVpnSensor

from .conftest import TEST_SITE_ID, TEST_SITE_NAME

GW_MAC = "AA-BB-CC-DD-EE-03"

SAMPLE_VPN_S2S = [
    {
        "id": "t1",
        "name": "Branch Office",
        "vpnType": 2,
        "status": 1,
        "localPeerIp": "10.0.0.1",
        "remotePeerIp": "10.0.1.1",
        "uptime": 86400,
        "downBytes": 1000000,
        "upBytes": 500000,
    },
    {
        "id": "t2",
        "name": "DR Site",
        "vpnType": 2,
        "status": 0,
        "localPeerIp": "10.0.0.2",
        "remotePeerIp": "10.0.2.1",
        "uptime": 0,
        "downBytes": 0,
        "upBytes": 0,
    },
]

SAMPLE_VPN_SERVER = [
    {
        "id": "s1",
        "name": "Remote Users",
        "vpnType": 1,
        "status": 1,
        "localPeerIp": "10.0.0.3",
        "remotePeerIp": "",
        "uptime": 172800,
        "downBytes": 2000000,
        "upBytes": 1000000,
        "connectedNum": 5,
    },
]

SAMPLE_VPN_CLIENT = [
    {
        "id": "c1",
        "name": "Client Connection",
        "vpnType": 3,
        "status": 1,
        "localPeerIp": "",
        "remotePeerIp": "10.0.3.1",
        "uptime": 3600,
        "downBytes": 500000,
        "upBytes": 250000,
    },
]


def _make_entry():
    """Create a mock config entry."""
    entry = MagicMock()
    entry.entry_id = "test_entry_id"
    entry.data = {
        "host": "10.0.0.100",
        "site": "Test Site",
        "verify_ssl": False,
        "username": "admin",
        "password": "pass",
    }
    entry.options = {}
    return entry


def _make_runtime_data():
    """Create mock runtime_data with coordinator."""
    runtime_data = MagicMock()
    coordinator = MagicMock()
    coordinator.site_id = TEST_SITE_ID
    coordinator.site_name = TEST_SITE_NAME
    coordinator.data = {
        "devices": {GW_MAC: {"type": "gateway", "name": "Main Gateway"}},
        "vpn_status": {
            "s2s": SAMPLE_VPN_S2S,
            "server": SAMPLE_VPN_SERVER,
            "client": SAMPLE_VPN_CLIENT,
        },
        "site_id": TEST_SITE_ID,
        "site_name": TEST_SITE_NAME,
    }
    coordinator.api_client = MagicMock()
    runtime_data.coordinators = {TEST_SITE_ID: coordinator}
    runtime_data.client_coordinators = []
    runtime_data.site_id = TEST_SITE_ID
    runtime_data.site_name = TEST_SITE_NAME
    return runtime_data


async def test_vpn_sensor_entities_created(hass: HomeAssistant) -> None:
    """VPN sensors are created for all tunnels across all VPN types."""
    entry = _make_entry()
    entry.runtime_data = _make_runtime_data()

    from custom_components.omada_open_api.sensor import async_setup_entry

    entities: list = []

    def capture_entities(new_entities):
        entities.extend(new_entities)

    await async_setup_entry(hass, entry, capture_entities)

    vpn_entities = [e for e in entities if isinstance(e, OmadaVpnSensor)]
    assert len(vpn_entities) > 0

    # 2 S2S tunnels * 4 sensors + 1 server * 4 + 1 client * 4 = 16
    assert len(vpn_entities) == (2 + 1 + 1) * len(VPN_SENSORS)


async def test_vpn_binary_sensor_entities_created(hass: HomeAssistant) -> None:
    """VPN binary sensors are created for all tunnels across all VPN types."""
    entry = _make_entry()
    entry.runtime_data = _make_runtime_data()

    from custom_components.omada_open_api.binary_sensor import async_setup_entry

    entities: list = []

    def capture_entities(new_entities):
        entities.extend(new_entities)

    await async_setup_entry(hass, entry, capture_entities)

    vpn_entities = [e for e in entities if isinstance(e, OmadaVpnBinarySensor)]
    # 4 tunnels * 1 binary sensor each
    assert len(vpn_entities) == 4


async def test_vpn_sensors_unique_ids(hass: HomeAssistant) -> None:
    """All VPN sensors have unique IDs matching the pattern."""
    entry = _make_entry()
    entry.runtime_data = _make_runtime_data()

    from custom_components.omada_open_api.sensor import async_setup_entry

    entities: list = []

    await async_setup_entry(hass, entry, entities.extend)

    vpn_entities = [e for e in entities if isinstance(e, OmadaVpnSensor)]
    unique_ids = {e.unique_id for e in vpn_entities}
    assert len(unique_ids) == len(vpn_entities)

    # Check one specific ID
    assert f"{GW_MAC}_vpn_s2s_t1_vpn_uptime" in unique_ids


async def test_vpn_binary_sensors_unique_ids(hass: HomeAssistant) -> None:
    """All VPN binary sensors have unique IDs matching the pattern."""
    entry = _make_entry()
    entry.runtime_data = _make_runtime_data()

    from custom_components.omada_open_api.binary_sensor import async_setup_entry

    entities: list = []

    await async_setup_entry(hass, entry, entities.extend)

    vpn_entities = [e for e in entities if isinstance(e, OmadaVpnBinarySensor)]
    unique_ids = {e.unique_id for e in vpn_entities}
    assert len(unique_ids) == len(vpn_entities)

    assert f"{GW_MAC}_vpn_s2s_t1_vpn_connected" in unique_ids
