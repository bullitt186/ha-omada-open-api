"""Tests for VPN entity creation wiring in sensor/binary_sensor platforms."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

from custom_components.omada_open_api.binary_sensor import OmadaVpnBinarySensor
from custom_components.omada_open_api.sensor import (
    VPN_CLIENT_SENSORS,
    VPN_SENSORS,
    OmadaVpnSensor,
)

from .conftest import TEST_SITE_ID, TEST_SITE_NAME

GW_MAC = "AA-BB-CC-DD-EE-03"

# Real S2S stats payloads captured from Fusion gateway (WireGuard vpnType=4)
SAMPLE_VPN_S2S = [
    {
        "id": "1068108444",
        "vpnId": "6a5a76d6a6f5ea6278c4acbd",
        "name": "wg0",
        "port": 51820,
        "connectedNum": 1,
        "disconnectedNum": 0,
        "totalRemoteNum": 1,
    },
    {
        "id": "1068108445",
        "vpnId": "6a5a76d6a6f5ea6278c4acbe",
        "name": "wg1",
        "port": 51821,
        "connectedNum": 0,
        "disconnectedNum": 2,
        "totalRemoteNum": 2,
    },
]

# Server/client VPN stats — unverified (Fusion returns empty data for these)
# Using best-guess fields; sensors should handle missing fields gracefully.
SAMPLE_VPN_SERVER = [
    {
        "id": "s1",
        "vpnId": "s1",
        "name": "Remote Users",
        "vpnType": 1,
        "connectedNum": 5,
        "disconnectedNum": 1,
        "totalRemoteNum": 6,
    },
]

SAMPLE_VPN_CLIENT = [
    {
        "id": "c1",
        "vpnId": "c1",
        "name": "Client Connection",
        "vpnType": 3,
        "connectedNum": 1,
        "disconnectedNum": 0,
        "totalRemoteNum": 1,
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

    # S2S and server tunnels expose peer counts; clients expose own traffic.
    assert len(vpn_entities) == (2 + 1) * len(VPN_SENSORS) + len(VPN_CLIENT_SENSORS)


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
    """All VPN sensors have unique IDs matching the pattern using vpnId."""
    entry = _make_entry()
    entry.runtime_data = _make_runtime_data()

    from custom_components.omada_open_api.sensor import async_setup_entry

    entities: list = []

    await async_setup_entry(hass, entry, entities.extend)

    vpn_entities = [e for e in entities if isinstance(e, OmadaVpnSensor)]
    unique_ids = {e.unique_id for e in vpn_entities}
    assert len(unique_ids) == len(vpn_entities)

    # Check one specific ID using vpnId anchor
    assert (
        f"{GW_MAC}_vpn_s2s_6a5a76d6a6f5ea6278c4acbd_vpn_connected_peers" in unique_ids
    )


async def test_vpn_binary_sensors_unique_ids(hass: HomeAssistant) -> None:
    """All VPN binary sensors have unique IDs matching the pattern using vpnId."""
    entry = _make_entry()
    entry.runtime_data = _make_runtime_data()

    from custom_components.omada_open_api.binary_sensor import async_setup_entry

    entities: list = []

    await async_setup_entry(hass, entry, entities.extend)

    vpn_entities = [e for e in entities if isinstance(e, OmadaVpnBinarySensor)]
    unique_ids = {e.unique_id for e in vpn_entities}
    assert len(unique_ids) == len(vpn_entities)

    assert f"{GW_MAC}_vpn_s2s_6a5a76d6a6f5ea6278c4acbd_vpn_connected" in unique_ids


async def test_vpn_binary_sensors_are_added_after_tunnel_discovery(
    hass: HomeAssistant,
) -> None:
    """A new tunnel creates binary sensors even when its gateway is known."""
    entry = _make_entry()
    runtime_data = _make_runtime_data()
    coordinator = runtime_data.coordinators[TEST_SITE_ID]
    coordinator.data["vpn_status"] = {"s2s": [], "server": [], "client": []}
    listeners: list = []
    coordinator.async_add_listener.side_effect = lambda listener: (
        listeners.append(listener) or (lambda: None)
    )
    entry.runtime_data = runtime_data
    entities: list = []

    from custom_components.omada_open_api.binary_sensor import async_setup_entry

    await async_setup_entry(hass, entry, entities.extend)
    coordinator.data["vpn_status"] = {
        "s2s": [SAMPLE_VPN_S2S[0]],
        "server": [],
        "client": [],
    }

    listeners[0]()

    assert len([e for e in entities if isinstance(e, OmadaVpnBinarySensor)]) == 1
