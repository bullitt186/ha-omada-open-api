"""Tests for VPN per-peer sensor and binary sensor entities.

Fixtures use real per-peer stats payloads captured from the Fusion gateway
API:
  GET /openapi/v1/{oid}/sites/{sid}/setting/vpn/stats/s2s/{tunnelId}/peer

Real fields: id, vpnId, name, remoteIp, downPkts, downBytes, upPkts,
upBytes, loginTime, port, status (0=disconnected, 1=connected).
"""

from __future__ import annotations

import datetime as dt
from typing import TYPE_CHECKING
from unittest.mock import MagicMock

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

from custom_components.omada_open_api.binary_sensor import (
    VPN_PEER_BINARY_SENSORS,
    OmadaVpnPeerBinarySensor,
)
from custom_components.omada_open_api.const import DOMAIN
from custom_components.omada_open_api.coordinator import OmadaSiteCoordinator
from custom_components.omada_open_api.sensor import VPN_PEER_SENSORS, OmadaVpnPeerSensor

from .conftest import TEST_SITE_ID, TEST_SITE_NAME

GW_MAC = "AA-BB-CC-DD-EE-03"

# Real per-peer stats payload captured from Fusion gateway (WireGuard vpnType=4)
SAMPLE_VPN_PEER_CONNECTED = {
    "id": "755282459",
    "vpnId": "6a86c79cad12260d2cd2e05f",
    "name": "bordenaus_server",
    "remoteIp": "192.168.0.2",
    "downPkts": 1279,
    "downBytes": 184940,
    "upPkts": 1243,
    "upBytes": 114404,
    "loginTime": 1787226476000,
    "port": 49384,
    "status": 1,  # 0=disconnected, 1=connected
}

SAMPLE_VPN_PEER_DISCONNECTED = {
    "id": "755282460",
    "vpnId": "6a86c79da0c4220d6e2e05f0",
    "name": "backup_server",
    "remoteIp": "192.168.0.3",
    "downPkts": 0,
    "downBytes": 0,
    "upPkts": 0,
    "upBytes": 0,
    "loginTime": 0,
    "port": 0,
    "status": 0,
}

SAMPLE_S2S_TUNNEL = {
    "id": "1068108444",  # Stats row ID (used to fetch peers)
    "vpnId": "6a5a76d6a6f5ea6278c4acbd",  # Stable config ID (entity anchor)
    "name": "wg0",
    "port": 51820,
    "connectedNum": 1,
    "disconnectedNum": 1,
    "totalRemoteNum": 2,
    "peers": [SAMPLE_VPN_PEER_CONNECTED, SAMPLE_VPN_PEER_DISCONNECTED],
}


def _build_vpn_coordinator_data(
    s2s: list[dict] | None = None,
) -> dict:
    return {
        "devices": {GW_MAC: {"type": "gateway", "name": "Main Gateway"}},
        "vpn_status": {
            "s2s": s2s or [],
            "server": [],
            "client": [],
        },
        "site_id": TEST_SITE_ID,
        "site_name": TEST_SITE_NAME,
    }


def _make_coordinator(hass: HomeAssistant, data: dict) -> OmadaSiteCoordinator:
    coord = OmadaSiteCoordinator(
        hass=hass,
        api_client=MagicMock(),
        site_id=TEST_SITE_ID,
        site_name=TEST_SITE_NAME,
    )
    coord.data = data
    return coord


# ---------------------------------------------------------------------------
# Per-peer sensor descriptions
# ---------------------------------------------------------------------------


def test_vpn_peer_sensor_description_keys() -> None:
    """VPN_PEER_SENSORS contains expected keys matching real peer fields."""
    keys = {d.key for d in VPN_PEER_SENSORS}
    assert "vpn_peer_bytes_received" in keys
    assert "vpn_peer_bytes_sent" in keys
    assert "vpn_peer_packets_received" in keys
    assert "vpn_peer_packets_sent" in keys
    assert "vpn_peer_remote_ip" in keys
    assert "vpn_peer_connected_since" in keys


def test_vpn_peer_sensor_value_fns() -> None:
    """Per-peer value_fn extracts the correct fields from a peer dict."""
    fns = {d.key: d for d in VPN_PEER_SENSORS}
    assert fns["vpn_peer_bytes_received"].value_fn(SAMPLE_VPN_PEER_CONNECTED) == 184940
    assert fns["vpn_peer_bytes_received"].value_fn(SAMPLE_VPN_PEER_DISCONNECTED) == 0
    assert fns["vpn_peer_bytes_sent"].value_fn(SAMPLE_VPN_PEER_CONNECTED) == 114404
    assert fns["vpn_peer_packets_received"].value_fn(SAMPLE_VPN_PEER_CONNECTED) == 1279
    assert fns["vpn_peer_packets_sent"].value_fn(SAMPLE_VPN_PEER_CONNECTED) == 1243
    assert fns["vpn_peer_remote_ip"].value_fn(SAMPLE_VPN_PEER_CONNECTED) == (
        "192.168.0.2"
    )
    assert fns["vpn_peer_connected_since"].value_fn(
        SAMPLE_VPN_PEER_CONNECTED
    ) == dt.datetime.fromtimestamp(1787226476, tz=dt.UTC)


def test_vpn_peer_sensors_are_diagnostic() -> None:
    """All per-peer sensors are disabled-by-default diagnostics."""
    for desc in VPN_PEER_SENSORS:
        assert desc.translation_key == desc.key
        assert desc.entity_category == "diagnostic"
        assert desc.entity_registry_enabled_default is False


# ---------------------------------------------------------------------------
# OmadaVpnPeerSensor entity
# ---------------------------------------------------------------------------


async def test_vpn_peer_sensor_native_value(hass: HomeAssistant) -> None:
    """Per-peer sensor returns correct native_value from coordinator data."""
    data = _build_vpn_coordinator_data(s2s=[SAMPLE_S2S_TUNNEL])
    coord = _make_coordinator(hass, data)

    desc = next(d for d in VPN_PEER_SENSORS if d.key == "vpn_peer_bytes_received")
    sensor = OmadaVpnPeerSensor(
        coordinator=coord,
        description=desc,
        gateway_mac=GW_MAC,
        vpn_type="s2s",
        tunnel_id="6a5a76d6a6f5ea6278c4acbd",  # vpnId
        tunnel_name="wg0",
        peer_id="755282459",
        peer_name="bordenaus_server",
    )

    assert sensor.native_value == 184940


async def test_vpn_peer_sensor_matches_a_numeric_api_peer_id(
    hass: HomeAssistant,
) -> None:
    """Entities use string IDs even when Omada returns a numeric peer ID."""
    numeric_peer = {**SAMPLE_VPN_PEER_CONNECTED, "id": 755282459}
    tunnel = {**SAMPLE_S2S_TUNNEL, "peers": [numeric_peer]}
    coord = _make_coordinator(hass, _build_vpn_coordinator_data(s2s=[tunnel]))
    desc = next(d for d in VPN_PEER_SENSORS if d.key == "vpn_peer_bytes_received")
    sensor = OmadaVpnPeerSensor(
        coordinator=coord,
        description=desc,
        gateway_mac=GW_MAC,
        vpn_type="s2s",
        tunnel_id="6a5a76d6a6f5ea6278c4acbd",
        tunnel_name="wg0",
        peer_id="755282459",
        peer_name="bordenaus_server",
    )

    assert sensor.native_value == 184940
    assert sensor.available is True


async def test_vpn_peer_sensor_native_value_missing_peer(
    hass: HomeAssistant,
) -> None:
    """VPN peer sensor returns None when the tunnel/peer is not present."""
    coord = _make_coordinator(hass, _build_vpn_coordinator_data(s2s=[]))

    desc = next(d for d in VPN_PEER_SENSORS if d.key == "vpn_peer_remote_ip")
    sensor = OmadaVpnPeerSensor(
        coordinator=coord,
        description=desc,
        gateway_mac=GW_MAC,
        vpn_type="s2s",
        tunnel_id="deadbeefdeadbeefdeadbeef",
        tunnel_name="wg0",
        peer_id="999999999",
        peer_name="ghost",
    )

    assert sensor.native_value is None
    assert sensor.available is False


def test_vpn_peer_sensor_unique_id() -> None:
    """VPN peer sensor unique_id follows the expected pattern."""
    coord = MagicMock()
    coord.data = _build_vpn_coordinator_data(s2s=[SAMPLE_S2S_TUNNEL])

    desc = next(d for d in VPN_PEER_SENSORS if d.key == "vpn_peer_bytes_received")
    sensor = OmadaVpnPeerSensor(
        coordinator=coord,
        description=desc,
        gateway_mac=GW_MAC,
        vpn_type="s2s",
        tunnel_id="6a5a76d6a6f5ea6278c4acbd",  # vpnId
        tunnel_name="wg0",
        peer_id="755282459",
        peer_name="bordenaus_server",
    )

    assert sensor.unique_id == (
        f"{GW_MAC}_vpn_peer_s2s_6a5a76d6a6f5ea6278c4acbd_755282459_"
        "vpn_peer_bytes_received"
    )


def test_vpn_peer_sensor_translation_key_and_placeholders() -> None:
    """VPN peer sensor uses translation_key with peer and tunnel placeholders."""
    coord = MagicMock()
    coord.data = _build_vpn_coordinator_data(s2s=[SAMPLE_S2S_TUNNEL])

    desc = next(d for d in VPN_PEER_SENSORS if d.key == "vpn_peer_remote_ip")
    sensor = OmadaVpnPeerSensor(
        coordinator=coord,
        description=desc,
        gateway_mac=GW_MAC,
        vpn_type="s2s",
        tunnel_id="6a5a76d6a6f5ea5903c4acbd",
        tunnel_name="wg0",
        peer_id="755282473",
        peer_name="bordenaus_server",
    )

    assert sensor.translation_key == "vpn_peer_remote_ip"
    assert sensor.translation_placeholders == {
        "peer_name": "bordenaus_server",
        "tunnel_name": "wg0",
    }


def test_vpn_peer_sensor_device_info() -> None:
    """VPN peer sensor links to the gateway device."""
    coord = MagicMock()
    coord.data = _build_vpn_coordinator_data(s2s=[SAMPLE_S2S_TUNNEL])

    desc = next(d for d in VPN_PEER_SENSORS if d.key == "vpn_peer_remote_ip")
    sensor = OmadaVpnPeerSensor(
        coordinator=coord,
        description=desc,
        gateway_mac=GW_MAC,
        vpn_type="s2s",
        tunnel_id="6a5a86d6a6f5ea5903c4acbd",
        tunnel_name="wg0",
        peer_id="755282473",
        peer_name="bordenaus_server",
    )

    assert (DOMAIN, GW_MAC) in sensor.device_info["identifiers"]


# ---------------------------------------------------------------------------
# Per-peer binary sensor
# ---------------------------------------------------------------------------


def test_vpn_peer_binary_sensor_description_keys() -> None:
    """VPN_PEER_BINARY_SENSORS contains the expected binary sensor key."""
    keys = {d.key for d in VPN_PEER_BINARY_SENSORS}
    assert "vpn_peer_connected" in keys


def test_vpn_peer_binary_sensor_value_fn() -> None:
    """vpn_peer_connected value_fn maps status 1/0 to True/False."""
    desc = next(d for d in VPN_PEER_BINARY_SENSORS if d.key == "vpn_peer_connected")
    assert desc.value_fn(SAMPLE_VPN_PEER_CONNECTED) is True
    assert desc.value_fn(SAMPLE_VPN_PEER_DISCONNECTED) is False
    assert desc.value_fn({}) is False  # Missing status defaults to disconnected


async def test_vpn_peer_binary_sensor_is_on(hass: HomeAssistant) -> None:
    """Peer binary sensor is on when the peer status is 1."""
    coord = _make_coordinator(
        hass, _build_vpn_coordinator_data(s2s=[SAMPLE_S2S_TUNNEL])
    )

    desc = next(d for d in VPN_PEER_BINARY_SENSORS if d.key == "vpn_peer_connected")
    sensor = OmadaVpnPeerBinarySensor(
        coordinator=coord,
        description=desc,
        gateway_mac=GW_MAC,
        vpn_type="s2s",
        tunnel_id="6a5a76d6a6f5ea6278c4acbd",
        tunnel_name="wg0",
        peer_id="755282459",
        peer_name="bordenaus_server",
    )

    assert sensor.is_on is True


async def test_vpn_peer_binary_sensor_is_off(hass: HomeAssistant) -> None:
    """Peer binary sensor is off when the peer status is 0."""
    coord = _make_coordinator(
        hass, _build_vpn_coordinator_data(s2s=[SAMPLE_S2S_TUNNEL])
    )

    desc = next(d for d in VPN_PEER_BINARY_SENSORS if d.key == "vpn_peer_connected")
    sensor = OmadaVpnPeerBinarySensor(
        coordinator=coord,
        description=desc,
        gateway_mac=GW_MAC,
        vpn_type="s2s",
        tunnel_id="6a5a76d6a6f5ea6278c4acbd",
        tunnel_name="wg0",
        peer_id="755282460",
        peer_name="backup_server",
    )

    assert sensor.is_on is False


def test_vpn_peer_binary_sensor_unique_id() -> None:
    """Peer binary sensor unique_id follows the expected pattern."""
    coord = MagicMock()
    coord.data = _build_vpn_coordinator_data(s2s=[SAMPLE_S2S_TUNNEL])

    desc = next(d for d in VPN_PEER_BINARY_SENSORS if d.key == "vpn_peer_connected")
    sensor = OmadaVpnPeerBinarySensor(
        coordinator=coord,
        description=desc,
        gateway_mac=GW_MAC,
        vpn_type="s2s",
        tunnel_id="6a5a96d6a6f5ea5903c4acbd",
        tunnel_name="wg0",
        peer_id="755282459",
        peer_name="bordenaus_server",
    )

    assert sensor.unique_id == (
        f"{GW_MAC}_vpn_peer_s2s_6a5a96d6a6f5ea5903c4acbd_755282459_vpn_peer_connected"
    )


# ---------------------------------------------------------------------------
# Builder functions
# ---------------------------------------------------------------------------


def test_build_vpn_peer_sensors_entities() -> None:
    """_build_vpn_peer_sensors creates one sensor per peer per description."""
    from custom_components.omada_open_api.sensor import _build_vpn_peer_sensors

    entities = _build_vpn_peer_sensors(
        coordinator=MagicMock(),
        devices={GW_MAC: {"type": "gateway"}},
        vpn_status={"s2s": [SAMPLE_S2S_TUNNEL], "server": [], "client": []},
        known_vpn_peer_keys=set(),
    )

    # 2 peers * 5 descriptions
    assert len(entities) == 2 * len(VPN_PEER_SENSORS)


def test_build_vpn_peer_sensors_skips_tunnels_without_peers() -> None:
    """Builder creates no entities for tunnels without a 'peers' list."""
    from custom_components.omada_open_api.sensor import _build_vpn_peer_sensors

    tunnel_no_peers = {k: v for k, v in SAMPLE_S2S_TUNNEL.items() if k != "peers"}
    entities = _build_vpn_peer_sensors(
        coordinator=MagicMock(),
        devices={GW_MAC: {"type": "gateway"}},
        vpn_status={"s2s": [tunnel_no_peers], "server": [], "client": []},
        known_vpn_peer_keys=set(),
    )
    assert entities == []


def test_build_vpn_peer_binary_sensors_entities() -> None:
    """_build_vpn_peer_binary_sensors creates one entity per peer."""
    from custom_components.omada_open_api.binary_sensor import (
        _build_vpn_peer_binary_sensors,
    )

    entities = _build_vpn_peer_binary_sensors(
        coordinator=MagicMock(),
        devices={GW_MAC: {"type": "gateway"}},
        vpn_status={"s2s": [SAMPLE_S2S_TUNNEL], "server": [], "client": []},
        known_vpn_peer_keys=set(),
    )

    # 2 peers * 1 description
    assert len(entities) == 2 * len(VPN_PEER_BINARY_SENSORS)
