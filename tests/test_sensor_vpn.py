"""Tests for VPN sensor and binary sensor entities.

Fixtures use real S2S stats payloads captured from the Fusion gateway API:
  GET /openapi/v1/.../setting/vpn/stats/s2s?filters.vpnType=4

Real fields: id, vpnId, name, port, connectedNum, disconnectedNum, totalRemoteNum
(see WP0 schema capture in PR #27 description).

NOTE: Server/client VPN stats row schemas are unverified — the Fusion gateway
only supports WireGuard S2S mode; server/client endpoints return empty data.
Server/client fixtures below use best-guess fields; sensors should handle
missing fields gracefully via .get() with defaults.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

from custom_components.omada_open_api.binary_sensor import (
    VPN_BINARY_SENSORS,
    OmadaVpnBinarySensor,
)
from custom_components.omada_open_api.const import DOMAIN
from custom_components.omada_open_api.coordinator import OmadaSiteCoordinator
from custom_components.omada_open_api.sensor import VPN_SENSORS, OmadaVpnSensor

from .conftest import TEST_SITE_ID, TEST_SITE_NAME

GW_MAC = "AA-BB-CC-DD-EE-03"

# Real S2S stats payload captured from Fusion gateway (WireGuard vpnType=4)
# API: GET /openapi/v1/{oid}/sites/{sid}/setting/vpn/stats/s2s?filters.vpnType=4
# Verified stable across 30-second polling gap (WP0 schema capture).
SAMPLE_VPN_S2S_TUNNEL = {
    "id": "1068108444",                       # stats row ID (stable)
    "vpnId": "6a5a76d6a6f5ea6278c4acbd",      # VPN config ID (stable, used as anchor)
    "name": "wg0",
    "port": 51820,
    "connectedNum": 1,                        # connected remote peers
    "disconnectedNum": 0,                     # disconnected remote peers
    "totalRemoteNum": 1,                      # total configured remote peers
}

SAMPLE_VPN_DISCONNECTED = {
    "id": "1068108445",
    "vpnId": "6a5a76d6a6f5ea6278c4acbe",
    "name": "wg1",
    "port": 51821,
    "connectedNum": 0,
    "disconnectedNum": 2,
    "totalRemoteNum": 2,
}


def _build_vpn_coordinator_data(
    s2s: list[dict] | None = None,
    server: list[dict] | None = None,
    client: list[dict] | None = None,
) -> dict:
    return {
        "devices": {GW_MAC: {"type": "gateway", "name": "Main Gateway"}},
        "vpn_status": {
            "s2s": s2s or [],
            "server": server or [],
            "client": client or [],
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
# VPN sensor descriptions
# ---------------------------------------------------------------------------


def test_vpn_sensor_description_keys() -> None:
    """VPN_SENSORS contains expected sensor keys matching real S2S stats fields."""
    keys = {d.key for d in VPN_SENSORS}
    assert "vpn_connected_peers" in keys
    assert "vpn_disconnected_peers" in keys
    assert "vpn_total_remote_peers" in keys
    assert "vpn_listen_port" in keys


def test_vpn_sensor_connected_peers_value_fn() -> None:
    """vpn_connected_peers value_fn extracts connectedNum from tunnel data."""
    desc = next(d for d in VPN_SENSORS if d.key == "vpn_connected_peers")
    assert desc.value_fn(SAMPLE_VPN_S2S_TUNNEL) == 1
    assert desc.value_fn(SAMPLE_VPN_DISCONNECTED) == 0


def test_vpn_sensor_disconnected_peers_value_fn() -> None:
    """vpn_disconnected_peers value_fn extracts disconnectedNum."""
    desc = next(d for d in VPN_SENSORS if d.key == "vpn_disconnected_peers")
    assert desc.value_fn(SAMPLE_VPN_S2S_TUNNEL) == 0
    assert desc.value_fn(SAMPLE_VPN_DISCONNECTED) == 2


def test_vpn_sensor_total_remote_peers_value_fn() -> None:
    """vpn_total_remote_peers value_fn extracts totalRemoteNum."""
    desc = next(d for d in VPN_SENSORS if d.key == "vpn_total_remote_peers")
    assert desc.value_fn(SAMPLE_VPN_S2S_TUNNEL) == 1
    assert desc.value_fn(SAMPLE_VPN_DISCONNECTED) == 2


def test_vpn_sensor_listen_port_value_fn() -> None:
    """vpn_listen_port value_fn extracts port."""
    desc = next(d for d in VPN_SENSORS if d.key == "vpn_listen_port")
    assert desc.value_fn(SAMPLE_VPN_S2S_TUNNEL) == 51820
    assert desc.value_fn(SAMPLE_VPN_DISCONNECTED) == 51821


# ---------------------------------------------------------------------------
# VPN binary sensor descriptions
# ---------------------------------------------------------------------------


def test_vpn_binary_sensor_description_keys() -> None:
    """VPN_BINARY_SENSORS contains expected binary sensor keys."""
    keys = {d.key for d in VPN_BINARY_SENSORS}
    assert "vpn_connected" in keys


def test_vpn_binary_sensor_connected_value_fn() -> None:
    """vpn_connected value_fn maps connectedNum > 0 to True."""
    desc = next(d for d in VPN_BINARY_SENSORS if d.key == "vpn_connected")
    assert desc.value_fn(SAMPLE_VPN_S2S_TUNNEL) is True
    assert desc.value_fn(SAMPLE_VPN_DISCONNECTED) is False


# ---------------------------------------------------------------------------
# OmadaVpnSensor entity
# ---------------------------------------------------------------------------


async def test_vpn_sensor_native_value(
    hass: HomeAssistant,
) -> None:
    """VPN sensor returns correct native_value from coordinator data."""
    data = _build_vpn_coordinator_data(s2s=[SAMPLE_VPN_S2S_TUNNEL])
    coord = _make_coordinator(hass, data)

    desc = next(d for d in VPN_SENSORS if d.key == "vpn_connected_peers")
    sensor = OmadaVpnSensor(
        coordinator=coord,
        description=desc,
        gateway_mac=GW_MAC,
        vpn_type="s2s",
        tunnel_id="6a5a76d6a6f5ea6278c4acbd",  # vpnId, not stats row id
        tunnel_name="wg0",
    )

    assert sensor.native_value == 1


async def test_vpn_sensor_available(hass: HomeAssistant) -> None:
    """VPN sensor is available when tunnel data exists."""
    data = _build_vpn_coordinator_data(s2s=[SAMPLE_VPN_S2S_TUNNEL])
    coord = _make_coordinator(hass, data)

    desc = next(d for d in VPN_SENSORS if d.key == "vpn_connected_peers")
    sensor = OmadaVpnSensor(
        coordinator=coord,
        description=desc,
        gateway_mac=GW_MAC,
        vpn_type="s2s",
        tunnel_id="6a5a76d6a6f5ea6278c4acbd",  # vpnId
        tunnel_name="wg0",
    )

    assert sensor.available is True


async def test_vpn_sensor_unavailable_when_missing(hass: HomeAssistant) -> None:
    """VPN sensor is unavailable when tunnel data is missing."""
    data = _build_vpn_coordinator_data(s2s=[])
    coord = _make_coordinator(hass, data)

    desc = next(d for d in VPN_SENSORS if d.key == "vpn_connected_peers")
    sensor = OmadaVpnSensor(
        coordinator=coord,
        description=desc,
        gateway_mac=GW_MAC,
        vpn_type="s2s",
        tunnel_id="6a5a76d6a6f5ea6278c4acbd",  # vpnId
        tunnel_name="wg0",
    )

    assert sensor.available is False


def test_vpn_sensor_unique_id() -> None:
    """VPN sensor unique_id follows the expected pattern using vpnId."""
    coord = MagicMock()
    coord.data = _build_vpn_coordinator_data(s2s=[SAMPLE_VPN_S2S_TUNNEL])

    desc = next(d for d in VPN_SENSORS if d.key == "vpn_connected_peers")
    sensor = OmadaVpnSensor(
        coordinator=coord,
        description=desc,
        gateway_mac=GW_MAC,
        vpn_type="s2s",
        tunnel_id="6a5a76d6a6f5ea6278c4acbd",  # vpnId
        tunnel_name="wg0",
    )

    assert sensor.unique_id == (
        f"{GW_MAC}_vpn_s2s_6a5a76d6a6f5ea6278c4acbd_vpn_connected_peers"
    )


def test_vpn_sensor_device_info() -> None:
    """VPN sensor links to the gateway device."""
    coord = MagicMock()
    coord.data = _build_vpn_coordinator_data(s2s=[SAMPLE_VPN_S2S_TUNNEL])

    desc = next(d for d in VPN_SENSORS if d.key == "vpn_connected_peers")
    sensor = OmadaVpnSensor(
        coordinator=coord,
        description=desc,
        gateway_mac=GW_MAC,
        vpn_type="s2s",
        tunnel_id="6a5a76d6a6f5ea6278c4acbd",
        tunnel_name="wg0",
    )

    assert (DOMAIN, GW_MAC) in sensor.device_info["identifiers"]


def test_vpn_sensor_translation_key() -> None:
    """VPN sensor uses translation_key, not hardcoded name."""
    coord = MagicMock()
    coord.data = _build_vpn_coordinator_data(s2s=[SAMPLE_VPN_S2S_TUNNEL])

    desc = next(d for d in VPN_SENSORS if d.key == "vpn_connected_peers")
    sensor = OmadaVpnSensor(
        coordinator=coord,
        description=desc,
        gateway_mac=GW_MAC,
        vpn_type="s2s",
        tunnel_id="6a5a76d6a6f5ea6278c4acbd",
        tunnel_name="wg0",
    )

    assert sensor.translation_key == "vpn_connected_peers"
    assert sensor.translation_placeholders == {"tunnel_name": "wg0"}


# ---------------------------------------------------------------------------
# OmadaVpnBinarySensor entity
# ---------------------------------------------------------------------------


async def test_vpn_binary_sensor_is_on(
    hass: HomeAssistant,
) -> None:
    """VPN binary sensor returns True when tunnel has connected peers."""
    data = _build_vpn_coordinator_data(s2s=[SAMPLE_VPN_S2S_TUNNEL])
    coord = _make_coordinator(hass, data)

    desc = next(d for d in VPN_BINARY_SENSORS if d.key == "vpn_connected")
    sensor = OmadaVpnBinarySensor(
        coordinator=coord,
        description=desc,
        gateway_mac=GW_MAC,
        vpn_type="s2s",
        tunnel_id="6a5a76d6a6f5ea6278c4acbd",  # vpnId
        tunnel_name="wg0",
    )

    assert sensor.is_on is True


async def test_vpn_binary_sensor_is_off(
    hass: HomeAssistant,
) -> None:
    """VPN binary sensor returns False when tunnel has no connected peers."""
    data = _build_vpn_coordinator_data(s2s=[SAMPLE_VPN_DISCONNECTED])
    coord = _make_coordinator(hass, data)

    desc = next(d for d in VPN_BINARY_SENSORS if d.key == "vpn_connected")
    sensor = OmadaVpnBinarySensor(
        coordinator=coord,
        description=desc,
        gateway_mac=GW_MAC,
        vpn_type="s2s",
        tunnel_id="6a5a76d6a6f5ea6278c4acbe",  # vpnId
        tunnel_name="wg1",
    )

    assert sensor.is_on is False


def test_vpn_binary_sensor_unique_id() -> None:
    """VPN binary sensor unique_id follows the expected pattern using vpnId."""
    coord = MagicMock()
    coord.data = _build_vpn_coordinator_data(s2s=[SAMPLE_VPN_S2S_TUNNEL])

    desc = next(d for d in VPN_BINARY_SENSORS if d.key == "vpn_connected")
    sensor = OmadaVpnBinarySensor(
        coordinator=coord,
        description=desc,
        gateway_mac=GW_MAC,
        vpn_type="s2s",
        tunnel_id="6a5a76d6a6f5ea6278c4acbd",  # vpnId
        tunnel_name="wg0",
    )

    assert sensor.unique_id == (
        f"{GW_MAC}_vpn_s2s_6a5a76d6a6f5ea6278c4acbd_vpn_connected"
    )


def test_vpn_binary_sensor_device_info() -> None:
    """VPN binary sensor links to the gateway device."""
    coord = MagicMock()
    coord.data = _build_vpn_coordinator_data(s2s=[SAMPLE_VPN_S2S_TUNNEL])

    desc = next(d for d in VPN_BINARY_SENSORS if d.key == "vpn_connected")
    sensor = OmadaVpnBinarySensor(
        coordinator=coord,
        description=desc,
        gateway_mac=GW_MAC,
        vpn_type="s2s",
        tunnel_id="6a5a76d6a6f5ea6278c4acbd",
        tunnel_name="wg0",
    )

    assert (DOMAIN, GW_MAC) in sensor.device_info["identifiers"]
