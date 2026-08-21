"""Tests for VPN status fetching in OmadaSiteCoordinator."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

from custom_components.omada_open_api.api import OmadaApiError
from custom_components.omada_open_api.coordinator import OmadaSiteCoordinator

from .conftest import TEST_SITE_ID, TEST_SITE_NAME

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

SAMPLE_VPN_SERVER = {
    "id": "srv_1",
    "name": "WireGuard Server",
    "vpnType": 4,
    "status": 1,
    "connectedNum": 3,
    "disconnectedNum": 1,
}

SAMPLE_VPN_CLIENT = {
    "id": "cli_1",
    "name": "Remote Worker",
    "vpnType": 4,
    "status": 1,
    "remotePeerIp": "203.0.113.50",
    "uptime": 3600,
}


async def test_site_coordinator_fetches_vpn_status(
    hass: HomeAssistant, mock_api_client: MagicMock
) -> None:
    """Test site coordinator fetches VPN status for gateways."""
    mock_api_client.get_vpn_s2s_stats = AsyncMock(return_value=[SAMPLE_VPN_S2S_TUNNEL])
    mock_api_client.get_vpn_server_stats = AsyncMock(return_value=[SAMPLE_VPN_SERVER])
    mock_api_client.get_vpn_client_stats = AsyncMock(return_value=[SAMPLE_VPN_CLIENT])

    coordinator = OmadaSiteCoordinator(
        hass=hass,
        api_client=mock_api_client,
        site_id=TEST_SITE_ID,
        site_name=TEST_SITE_NAME,
    )

    await coordinator.async_refresh()
    assert coordinator.last_update_success is True

    vpn = coordinator.data.get("vpn_status", {})
    assert "s2s" in vpn
    assert "server" in vpn
    assert "client" in vpn
    assert len(vpn["s2s"]) == 1
    assert vpn["s2s"][0]["name"] == "Branch Office"
    assert len(vpn["server"]) == 1
    assert vpn["server"][0]["name"] == "WireGuard Server"
    assert len(vpn["client"]) == 1
    assert vpn["client"][0]["name"] == "Remote Worker"


async def test_site_coordinator_vpn_status_empty(
    hass: HomeAssistant, mock_api_client: MagicMock
) -> None:
    """Test VPN status returns empty lists when no tunnels exist."""
    mock_api_client.get_vpn_s2s_stats = AsyncMock(return_value=[])
    mock_api_client.get_vpn_server_stats = AsyncMock(return_value=[])
    mock_api_client.get_vpn_client_stats = AsyncMock(return_value=[])

    coordinator = OmadaSiteCoordinator(
        hass=hass,
        api_client=mock_api_client,
        site_id=TEST_SITE_ID,
        site_name=TEST_SITE_NAME,
    )

    await coordinator.async_refresh()
    assert coordinator.last_update_success is True

    vpn = coordinator.data.get("vpn_status", {})
    assert vpn["s2s"] == []
    assert vpn["server"] == []
    assert vpn["client"] == []


async def test_site_coordinator_skips_vpn_requests_when_disabled(
    hass: HomeAssistant, mock_api_client: MagicMock
) -> None:
    """VPN endpoints are not polled when VPN monitoring is disabled."""
    mock_api_client.get_vpn_s2s_stats = AsyncMock()
    mock_api_client.get_vpn_server_stats = AsyncMock()
    mock_api_client.get_vpn_client_stats = AsyncMock()

    coordinator = OmadaSiteCoordinator(
        hass=hass,
        api_client=mock_api_client,
        site_id=TEST_SITE_ID,
        site_name=TEST_SITE_NAME,
        enable_vpn_status=False,
    )

    await coordinator.async_refresh()

    assert coordinator.data["vpn_status"] == {}
    mock_api_client.get_vpn_s2s_stats.assert_not_awaited()
    mock_api_client.get_vpn_server_stats.assert_not_awaited()
    mock_api_client.get_vpn_client_stats.assert_not_awaited()


async def test_site_coordinator_vpn_status_failure_graceful(
    hass: HomeAssistant, mock_api_client: MagicMock
) -> None:
    """Test VPN status failure doesn't break the coordinator update."""
    mock_api_client.get_vpn_s2s_stats = AsyncMock(
        side_effect=OmadaApiError("VPN fetch failed")
    )
    mock_api_client.get_vpn_server_stats = AsyncMock(return_value=[])
    mock_api_client.get_vpn_client_stats = AsyncMock(return_value=[])

    coordinator = OmadaSiteCoordinator(
        hass=hass,
        api_client=mock_api_client,
        site_id=TEST_SITE_ID,
        site_name=TEST_SITE_NAME,
    )

    await coordinator.async_refresh()
    assert coordinator.last_update_success is True

    vpn = coordinator.data.get("vpn_status", {})
    # S2S fetch failed, so it should be empty.
    assert vpn["s2s"] == []
    # Other types should still work.
    assert vpn["server"] == []
    assert vpn["client"] == []


async def test_fetch_vpn_status_includes_peers(
    hass: HomeAssistant, mock_api_client: MagicMock
) -> None:
    """Test S2S and server tunnels with connected peers get per-peer data."""
    s2s_tunnel = {**SAMPLE_VPN_S2S_TUNNEL, "connectedNum": 1}
    mock_api_client.get_vpn_s2s_stats = AsyncMock(return_value=[s2s_tunnel])
    mock_api_client.get_vpn_server_stats = AsyncMock(return_value=[SAMPLE_VPN_SERVER])
    mock_api_client.get_vpn_client_stats = AsyncMock(return_value=[])
    mock_api_client.get_vpn_s2s_peers = AsyncMock(
        return_value=[{"name": "peer_a", "remoteIp": "192.168.0.2"}]
    )
    mock_api_client.get_vpn_server_clients = AsyncMock(
        return_value=[{"name": "client_a"}]
    )

    coordinator = OmadaSiteCoordinator(
        hass=hass,
        api_client=mock_api_client,
        site_id=TEST_SITE_ID,
        site_name=TEST_SITE_NAME,
    )

    await coordinator.async_refresh()
    assert coordinator.last_update_success is True

    vpn = coordinator.data.get("vpn_status", {})
    assert vpn["s2s"][0]["peers"] == [{"name": "peer_a", "remoteIp": "192.168.0.2"}]
    assert vpn["server"][0]["peers"] == [{"name": "client_a"}]
    mock_api_client.get_vpn_s2s_peers.assert_called_once_with(TEST_SITE_ID, "tunnel_1")
    mock_api_client.get_vpn_server_clients.assert_called_once_with(
        TEST_SITE_ID, "srv_1"
    )


async def test_fetch_vpn_status_includes_disconnected_s2s_peers(
    hass: HomeAssistant, mock_api_client: MagicMock
) -> None:
    """Configured peers remain discoverable while all peers are disconnected."""
    tunnel = {**SAMPLE_VPN_S2S_TUNNEL, "connectedNum": 0}
    mock_api_client.get_vpn_s2s_stats = AsyncMock(return_value=[tunnel])
    mock_api_client.get_vpn_server_stats = AsyncMock(return_value=[])
    mock_api_client.get_vpn_client_stats = AsyncMock(return_value=[])
    mock_api_client.get_vpn_s2s_peers = AsyncMock(
        return_value=[{"id": "peer-1", "name": "Remote site", "status": 0}]
    )

    coordinator = OmadaSiteCoordinator(
        hass=hass,
        api_client=mock_api_client,
        site_id=TEST_SITE_ID,
        site_name=TEST_SITE_NAME,
    )

    await coordinator.async_refresh()

    assert coordinator.data["vpn_status"]["s2s"][0]["peers"] == [
        {"id": "peer-1", "name": "Remote site", "status": 0}
    ]
