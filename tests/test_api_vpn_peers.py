"""Tests for VPN per-peer and per-client stats API methods."""

from __future__ import annotations

import datetime as dt
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.omada_open_api.api import OmadaApiClient
from custom_components.omada_open_api.const import (
    CONF_ACCESS_TOKEN,
    CONF_API_URL,
    CONF_CLIENT_ID,
    CONF_CLIENT_SECRET,
    CONF_OMADA_ID,
    CONF_REFRESH_TOKEN,
    CONF_TOKEN_EXPIRES_AT,
)

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

SAMPLE_PEER_RESPONSE = {
    "errorCode": 0,
    "msg": "Success.",
    "result": {
        "totalRows": 1,
        "data": [
            {
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
                "status": 1,
            }
        ],
        "supportWireguardStatus": True,
    },
}


@pytest.fixture
def mock_config_entry():
    """Create a mock config entry for testing."""
    entry = MagicMock()
    entry.data = {
        CONF_API_URL: "https://test-controller.example.com",
        CONF_OMADA_ID: "test_omada_id",
        CONF_CLIENT_ID: "test_client_id",
        CONF_CLIENT_SECRET: "test_client_secret",
        CONF_ACCESS_TOKEN: "test_access_token",
        CONF_REFRESH_TOKEN: "test_refresh_token",
        CONF_TOKEN_EXPIRES_AT: (
            dt.datetime.now(dt.UTC) + dt.timedelta(hours=1)
        ).isoformat(),
    }
    entry.entry_id = "test_entry_id"
    return entry


def _make_client(mock_config_entry) -> OmadaApiClient:
    """Create an OmadaApiClient with a mocked session."""
    return OmadaApiClient(
        session=MagicMock(),
        token_update_callback=AsyncMock(),
        api_url=mock_config_entry.data[CONF_API_URL],
        omada_id=mock_config_entry.data[CONF_OMADA_ID],
        client_id=mock_config_entry.data[CONF_CLIENT_ID],
        client_secret=mock_config_entry.data[CONF_CLIENT_SECRET],
        access_token=mock_config_entry.data[CONF_ACCESS_TOKEN],
        refresh_token=mock_config_entry.data[CONF_REFRESH_TOKEN],
        token_expires_at=dt.datetime.now(dt.UTC) + dt.timedelta(hours=1),
    )


async def test_get_vpn_s2s_peers(hass: HomeAssistant, mock_config_entry) -> None:
    """Test get_vpn_s2s_peers returns per-peer stats for an S2S tunnel."""
    with patch.object(
        OmadaApiClient,
        "_authenticated_request",
        new_callable=AsyncMock,
        return_value=SAMPLE_PEER_RESPONSE,
    ) as mock_req:
        api_client = _make_client(mock_config_entry)
        result = await api_client.get_vpn_s2s_peers("site_001", "tunnel_1")

    assert result == SAMPLE_PEER_RESPONSE["result"]["data"]
    mock_req.assert_called_once()
    call_url = mock_req.call_args[0][1]
    assert "/setting/vpn/stats/s2s/tunnel_1/peer" in call_url
    assert "site_001" in call_url
    call_params = mock_req.call_args[1]["params"]
    assert call_params["page"] == 1
    assert call_params["pageSize"] == 100


async def test_get_vpn_s2s_peers_fetches_all_pages(
    hass: HomeAssistant, mock_config_entry
) -> None:
    """S2S peer discovery includes peers beyond the first API page."""
    first_page = [{"id": str(index)} for index in range(100)]
    with patch.object(
        OmadaApiClient,
        "_authenticated_request",
        new_callable=AsyncMock,
        side_effect=[
            {"result": {"totalRows": 101, "data": first_page}},
            {"result": {"totalRows": 101, "data": [{"id": "100"}]}},
        ],
    ) as mock_req:
        api_client = _make_client(mock_config_entry)
        result = await api_client.get_vpn_s2s_peers("site_001", "tunnel_1")

    assert result == [*first_page, {"id": "100"}]
    assert mock_req.await_count == 2
    assert mock_req.await_args_list[1].kwargs["params"] == {"page": 2, "pageSize": 100}


async def test_get_vpn_server_clients(hass: HomeAssistant, mock_config_entry) -> None:
    """Test get_vpn_server_clients returns per-client stats for a server."""
    with patch.object(
        OmadaApiClient,
        "_authenticated_request",
        new_callable=AsyncMock,
        return_value=SAMPLE_PEER_RESPONSE,
    ) as mock_req:
        api_client = _make_client(mock_config_entry)
        result = await api_client.get_vpn_server_clients("site_001", "srv_1")

    assert result == SAMPLE_PEER_RESPONSE["result"]["data"]
    mock_req.assert_called_once()
    call_url = mock_req.call_args[0][1]
    assert "/setting/vpn/stats/server/srv_1/client" in call_url
    assert "site_001" in call_url
    call_params = mock_req.call_args[1]["params"]
    assert call_params["page"] == 1
    assert call_params["pageSize"] == 100


async def test_get_vpn_s2s_peers_empty(hass: HomeAssistant, mock_config_entry) -> None:
    """Test get_vpn_s2s_peers returns an empty list when no peers exist."""
    with patch.object(
        OmadaApiClient,
        "_authenticated_request",
        new_callable=AsyncMock,
        return_value={"errorCode": 0, "result": {"totalRows": 0, "data": []}},
    ) as mock_req:
        api_client = _make_client(mock_config_entry)
        result = await api_client.get_vpn_s2s_peers("site_001", "tunnel_1")

    assert result == []
    mock_req.assert_called_once()
