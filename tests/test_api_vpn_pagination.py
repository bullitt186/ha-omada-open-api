"""Tests for complete VPN status retrieval."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from custom_components.omada_open_api.api import OmadaApiClient, OmadaApiError


@pytest.mark.asyncio
async def test_vpn_s2s_stats_fetches_all_pages_without_type_filter() -> None:
    """VPN status includes every VPN protocol and page returned by Omada."""
    client = OmadaApiClient.__new__(OmadaApiClient)
    client._api_url = "https://controller.local"
    client._omada_id = "controller-id"
    client._authenticated_request = AsyncMock(
        side_effect=[
            {
                "result": {
                    "totalRows": 101,
                    "data": [{"id": f"row-{index}"} for index in range(100)],
                }
            },
            {"result": {"totalRows": 101, "data": [{"id": "second"}]}},
        ]
    )

    result = await client.get_vpn_s2s_stats("site-id")

    assert result[0] == {"id": "row-0"}
    assert result[-1] == {"id": "second"}
    assert len(result) == 101
    assert client._authenticated_request.await_args_list[0].kwargs["params"] == {
        "page": 1,
        "pageSize": 100,
    }
    assert client._authenticated_request.await_args_list[1].kwargs["params"] == {
        "page": 2,
        "pageSize": 100,
    }


@pytest.mark.asyncio
async def test_vpn_s2s_stats_falls_back_for_fusion_filter_requirement() -> None:
    """Fusion retries WireGuard filtering only after rejecting an unfiltered request."""
    client = OmadaApiClient.__new__(OmadaApiClient)
    client._api_url = "https://controller.local"
    client._omada_id = "controller-id"
    client._authenticated_request = AsyncMock(
        side_effect=[
            OmadaApiError("Invalid request parameters.", error_code=-1001),
            {"result": {"totalRows": 1, "data": [{"id": "wireguard"}]}},
        ]
    )

    result = await client.get_vpn_s2s_stats("site-id")

    assert result == [{"id": "wireguard"}]
    assert client._authenticated_request.await_args_list[0].kwargs["params"] == {
        "page": 1,
        "pageSize": 100,
    }
    assert client._authenticated_request.await_args_list[1].kwargs["params"] == {
        "page": 1,
        "pageSize": 100,
        "filters.vpnType": 4,
    }
