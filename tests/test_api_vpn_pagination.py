"""Tests for complete VPN status retrieval."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from custom_components.omada_open_api.api import OmadaApiClient, OmadaApiError


@pytest.mark.asyncio
async def test_vpn_s2s_stats_fetches_all_pages_without_type_filter() -> None:
    """VPN status includes every VPN protocol and page returned by Omada."""
    client = OmadaApiClient.__new__(OmadaApiClient)
    client._api_url = "https://controller.local"
    client._omada_id = "controller-id"
    client._vpn_rejected_at = {}
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


def _client(responses: list[Any]) -> OmadaApiClient:
    """Build a bare client whose requests return the given responses."""
    client = OmadaApiClient.__new__(OmadaApiClient)
    client._api_url = "https://controller.local"
    client._omada_id = "controller-id"
    client._vpn_rejected_at = {}
    client._authenticated_request = AsyncMock(side_effect=responses)
    return client


def _rows(*ids: str) -> dict[str, Any]:
    return {"result": {"totalRows": len(ids), "data": [{"id": i} for i in ids]}}


REJECTED = OmadaApiError("Invalid request parameters.", error_code=-1001)
BAD_REQUEST = OmadaApiError("HTTP 400: Bad Request", http_status=400)


@pytest.mark.asyncio
async def test_vpn_s2s_stats_queries_every_vpn_type_when_filter_required() -> None:
    """A filter-requiring controller is queried once per accepted vpnType."""
    client = _client([REJECTED, _rows("ipsec"), _rows("wireguard")])

    result = await client.get_vpn_s2s_stats("site-id")

    assert result == [{"id": "ipsec"}, {"id": "wireguard"}]
    sent = [c.kwargs["params"] for c in client._authenticated_request.await_args_list]
    assert sent == [
        {"page": 1, "pageSize": 100},
        {"page": 1, "pageSize": 100, "filters.vpnType": 2},
        {"page": 1, "pageSize": 100, "filters.vpnType": 4},
    ]


@pytest.mark.asyncio
async def test_vpn_rejected_type_is_skipped_until_retry_interval() -> None:
    """A rejected request is not repeated until the retry interval passes."""
    client = _client(
        [
            BAD_REQUEST,
            BAD_REQUEST,
            _rows("wg"),
            _rows("wg"),
            BAD_REQUEST,
            _rows("x"),
            _rows("wg"),
        ]
    )

    with patch(
        "custom_components.omada_open_api.api.time.monotonic", return_value=1000.0
    ):
        assert await client.get_vpn_s2s_stats("site-id") == [{"id": "wg"}]
        assert await client.get_vpn_s2s_stats("site-id") == [{"id": "wg"}]
    assert client._authenticated_request.await_count == 4

    with patch(
        "custom_components.omada_open_api.api.time.monotonic", return_value=4601.0
    ):
        assert await client.get_vpn_s2s_stats("site-id") == [{"id": "x"}, {"id": "wg"}]
    assert client._authenticated_request.await_count == 7


@pytest.mark.asyncio
async def test_vpn_all_types_rejected_raises_without_repeating_requests() -> None:
    """An endpoint rejecting every request raises an HTTP 400 error, cheaply."""
    client = _client([BAD_REQUEST, BAD_REQUEST, BAD_REQUEST])

    for _ in range(2):
        with pytest.raises(OmadaApiError) as err:
            await client.get_vpn_s2s_stats("site-id")
        assert err.value.http_status == 400

    assert client._authenticated_request.await_count == 3
