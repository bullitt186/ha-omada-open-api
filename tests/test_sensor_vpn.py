"""Tests for VPN sensor and binary sensor entities."""

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

SAMPLE_VPN_S2S_TUNNEL = {
    "id": "tunnel_1",
    "name": "Branch Office",
    "vpnType": 2,
    "status": 1,
    "localPeerIp": "10.0.0.1",
    "remotePeerIp": "10.0.1.1",
    "uptime": 86400,
    "downBytes": 1000000,
    "upBytes": 500000,
}

SAMPLE_VPN_DISCONNECTED = {
    "id": "tunnel_2",
    "name": "Disaster Recovery",
    "vpnType": 2,
    "status": 0,
    "localPeerIp": "10.0.0.2",
    "remotePeerIp": "10.0.2.1",
    "uptime": 0,
    "downBytes": 0,
    "upBytes": 0,
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
    """VPN_SENSORS contains expected sensor keys."""
    keys = {d.key for d in VPN_SENSORS}
    assert "vpn_uptime" in keys
    assert "vpn_download" in keys
    assert "vpn_upload" in keys
    assert "vpn_remote_peer" in keys


def test_vpn_sensor_uptime_value_fn() -> None:
    """vpn_uptime value_fn extracts uptime from tunnel data."""
    desc = next(d for d in VPN_SENSORS if d.key == "vpn_uptime")
    assert desc.value_fn(SAMPLE_VPN_S2S_TUNNEL) == 86400


def test_vpn_sensor_download_value_fn() -> None:
    """vpn_download value_fn extracts downBytes from tunnel data."""
    desc = next(d for d in VPN_SENSORS if d.key == "vpn_download")
    assert desc.value_fn(SAMPLE_VPN_S2S_TUNNEL) == 1000000


def test_vpn_sensor_upload_value_fn() -> None:
    """vpn_upload value_fn extracts upBytes from tunnel data."""
    desc = next(d for d in VPN_SENSORS if d.key == "vpn_upload")
    assert desc.value_fn(SAMPLE_VPN_S2S_TUNNEL) == 500000


def test_vpn_sensor_remote_peer_value_fn() -> None:
    """vpn_remote_peer value_fn extracts remotePeerIp."""
    desc = next(d for d in VPN_SENSORS if d.key == "vpn_remote_peer")
    assert desc.value_fn(SAMPLE_VPN_S2S_TUNNEL) == "10.0.1.1"


# ---------------------------------------------------------------------------
# VPN binary sensor descriptions
# ---------------------------------------------------------------------------


def test_vpn_binary_sensor_description_keys() -> None:
    """VPN_BINARY_SENSORS contains expected binary sensor keys."""
    keys = {d.key for d in VPN_BINARY_SENSORS}
    assert "vpn_connected" in keys


def test_vpn_binary_sensor_connected_value_fn() -> None:
    """vpn_connected value_fn maps status==1 to True."""
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

    desc = next(d for d in VPN_SENSORS if d.key == "vpn_uptime")
    sensor = OmadaVpnSensor(
        coordinator=coord,
        description=desc,
        gateway_mac=GW_MAC,
        vpn_type="s2s",
        tunnel_id="tunnel_1",
        tunnel_name="Branch Office",
    )

    assert sensor.native_value == 86400


async def test_vpn_sensor_available(hass: HomeAssistant) -> None:
    """VPN sensor is available when tunnel data exists."""
    data = _build_vpn_coordinator_data(s2s=[SAMPLE_VPN_S2S_TUNNEL])
    coord = _make_coordinator(hass, data)

    desc = next(d for d in VPN_SENSORS if d.key == "vpn_uptime")
    sensor = OmadaVpnSensor(
        coordinator=coord,
        description=desc,
        gateway_mac=GW_MAC,
        vpn_type="s2s",
        tunnel_id="tunnel_1",
        tunnel_name="Branch Office",
    )

    assert sensor.available is True


async def test_vpn_sensor_unavailable_when_missing(hass: HomeAssistant) -> None:
    """VPN sensor is unavailable when tunnel data is missing."""
    data = _build_vpn_coordinator_data(s2s=[])
    coord = _make_coordinator(hass, data)

    desc = next(d for d in VPN_SENSORS if d.key == "vpn_uptime")
    sensor = OmadaVpnSensor(
        coordinator=coord,
        description=desc,
        gateway_mac=GW_MAC,
        vpn_type="s2s",
        tunnel_id="tunnel_1",
        tunnel_name="Branch Office",
    )

    assert sensor.available is False


def test_vpn_sensor_unique_id() -> None:
    """VPN sensor unique_id follows the expected pattern."""
    coord = MagicMock()
    coord.data = _build_vpn_coordinator_data(s2s=[SAMPLE_VPN_S2S_TUNNEL])

    desc = next(d for d in VPN_SENSORS if d.key == "vpn_uptime")
    sensor = OmadaVpnSensor(
        coordinator=coord,
        description=desc,
        gateway_mac=GW_MAC,
        vpn_type="s2s",
        tunnel_id="tunnel_1",
        tunnel_name="Branch Office",
    )

    assert sensor.unique_id == f"{GW_MAC}_vpn_s2s_tunnel_1_vpn_uptime"


def test_vpn_sensor_device_info() -> None:
    """VPN sensor links to the gateway device."""
    coord = MagicMock()
    coord.data = _build_vpn_coordinator_data(s2s=[SAMPLE_VPN_S2S_TUNNEL])

    desc = next(d for d in VPN_SENSORS if d.key == "vpn_uptime")
    sensor = OmadaVpnSensor(
        coordinator=coord,
        description=desc,
        gateway_mac=GW_MAC,
        vpn_type="s2s",
        tunnel_id="tunnel_1",
        tunnel_name="Branch Office",
    )

    assert (DOMAIN, GW_MAC) in sensor.device_info["identifiers"]


def test_vpn_sensor_translation_key() -> None:
    """VPN sensor uses translation_key, not hardcoded name."""
    coord = MagicMock()
    coord.data = _build_vpn_coordinator_data(s2s=[SAMPLE_VPN_S2S_TUNNEL])

    desc = next(d for d in VPN_SENSORS if d.key == "vpn_uptime")
    sensor = OmadaVpnSensor(
        coordinator=coord,
        description=desc,
        gateway_mac=GW_MAC,
        vpn_type="s2s",
        tunnel_id="tunnel_1",
        tunnel_name="Branch Office",
    )

    assert sensor.translation_key == "vpn_uptime"
    assert sensor.translation_placeholders == {"tunnel_name": "Branch Office"}


# ---------------------------------------------------------------------------
# OmadaVpnBinarySensor entity
# ---------------------------------------------------------------------------


async def test_vpn_binary_sensor_is_on(
    hass: HomeAssistant,
) -> None:
    """VPN binary sensor returns True when tunnel is connected."""
    data = _build_vpn_coordinator_data(s2s=[SAMPLE_VPN_S2S_TUNNEL])
    coord = _make_coordinator(hass, data)

    desc = next(d for d in VPN_BINARY_SENSORS if d.key == "vpn_connected")
    sensor = OmadaVpnBinarySensor(
        coordinator=coord,
        description=desc,
        gateway_mac=GW_MAC,
        vpn_type="s2s",
        tunnel_id="tunnel_1",
        tunnel_name="Branch Office",
    )

    assert sensor.is_on is True


async def test_vpn_binary_sensor_is_off(
    hass: HomeAssistant,
) -> None:
    """VPN binary sensor returns False when tunnel is disconnected."""
    data = _build_vpn_coordinator_data(s2s=[SAMPLE_VPN_DISCONNECTED])
    coord = _make_coordinator(hass, data)

    desc = next(d for d in VPN_BINARY_SENSORS if d.key == "vpn_connected")
    sensor = OmadaVpnBinarySensor(
        coordinator=coord,
        description=desc,
        gateway_mac=GW_MAC,
        vpn_type="s2s",
        tunnel_id="tunnel_2",
        tunnel_name="Disaster Recovery",
    )

    assert sensor.is_on is False


def test_vpn_binary_sensor_unique_id() -> None:
    """VPN binary sensor unique_id follows the expected pattern."""
    coord = MagicMock()
    coord.data = _build_vpn_coordinator_data(s2s=[SAMPLE_VPN_S2S_TUNNEL])

    desc = next(d for d in VPN_BINARY_SENSORS if d.key == "vpn_connected")
    sensor = OmadaVpnBinarySensor(
        coordinator=coord,
        description=desc,
        gateway_mac=GW_MAC,
        vpn_type="s2s",
        tunnel_id="tunnel_1",
        tunnel_name="Branch Office",
    )

    assert sensor.unique_id == f"{GW_MAC}_vpn_s2s_tunnel_1_vpn_connected"


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
        tunnel_id="tunnel_1",
        tunnel_name="Branch Office",
    )

    assert (DOMAIN, GW_MAC) in sensor.device_info["identifiers"]
