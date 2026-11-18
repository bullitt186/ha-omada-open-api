"""Tests for paginated Open API list endpoints (sites and devices).

The Omada Open API pages list endpoints with ``page`` (starting at 1) and
``pageSize`` (1-1000) and reports the overall row count as ``totalRows``.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import pytest

from custom_components.omada_open_api.api import OmadaApiClient, OmadaApiError

API_URL = "https://controller.local"
OMADA_ID = "controller-id"
SITES_URL = f"{API_URL}/openapi/v1/{OMADA_ID}/sites"
DEVICES_URL = f"{API_URL}/openapi/v1/{OMADA_ID}/sites/site-1/devices"


def _client(responses: list[Any]) -> OmadaApiClient:
    """Build a bare client whose requests return the given responses."""
    client = OmadaApiClient.__new__(OmadaApiClient)
    client._api_url = API_URL
    client._omada_id = OMADA_ID
    client._authenticated_request = AsyncMock(side_effect=responses)
    return client


def _page(prefix: str, start: int, count: int, total: int) -> dict[str, Any]:
    """Return one Open API list response with ``count`` rows."""
    return {
        "errorCode": 0,
        "result": {
            "totalRows": total,
            "currentPage": start // 100 + 1,
            "currentSize": count,
            "data": [{"id": f"{prefix}-{i}"} for i in range(start, start + count)],
        },
    }


def _requests(client: OmadaApiClient) -> list[tuple[str, str, dict[str, Any]]]:
    """Return (method, url, params) of every request the client sent."""
    mock = client._authenticated_request
    assert isinstance(mock, AsyncMock)
    return [(c.args[0], c.args[1], c.kwargs["params"]) for c in mock.await_args_list]


@pytest.mark.asyncio
async def test_get_sites_returns_rows_of_every_page() -> None:
    """A controller with more sites than one page holds returns all of them."""
    client = _client([_page("site", 0, 100, 150), _page("site", 100, 50, 150)])

    sites = await client.get_sites()

    assert [site["id"] for site in sites] == [f"site-{i}" for i in range(150)]
    assert _requests(client) == [
        ("get", SITES_URL, {"page": 1, "pageSize": 100}),
        ("get", SITES_URL, {"page": 2, "pageSize": 100}),
    ]


@pytest.mark.asyncio
async def test_get_devices_returns_rows_of_every_page() -> None:
    """A site with more than 100 devices returns every device."""
    client = _client(
        [
            _page("dev", 0, 100, 201),
            _page("dev", 100, 100, 201),
            _page("dev", 200, 1, 201),
        ]
    )

    devices = await client.get_devices("site-1")

    assert [device["id"] for device in devices] == [f"dev-{i}" for i in range(201)]
    assert _requests(client) == [
        ("get", DEVICES_URL, {"page": 1, "pageSize": 100}),
        ("get", DEVICES_URL, {"page": 2, "pageSize": 100}),
        ("get", DEVICES_URL, {"page": 3, "pageSize": 100}),
    ]


@pytest.mark.asyncio
async def test_get_devices_stops_when_total_rows_reached_on_full_page() -> None:
    """No further page is requested once totalRows rows were received."""
    client = _client([_page("dev", 0, 100, 200), _page("dev", 100, 100, 200)])

    devices = await client.get_devices("site-1")

    assert len(devices) == 200
    assert [params["page"] for _, _, params in _requests(client)] == [1, 2]


@pytest.mark.asyncio
async def test_get_sites_single_page_sends_one_request() -> None:
    """A result that fits one page needs exactly one request."""
    client = _client([_page("site", 0, 3, 3)])

    sites = await client.get_sites()

    assert [site["id"] for site in sites] == ["site-0", "site-1", "site-2"]
    assert _requests(client) == [("get", SITES_URL, {"page": 1, "pageSize": 100})]


@pytest.mark.asyncio
async def test_get_devices_empty_site_returns_empty_list() -> None:
    """A site without devices returns an empty list after one request."""
    client = _client([_page("dev", 0, 0, 0)])

    assert await client.get_devices("site-1") == []
    assert len(_requests(client)) == 1


@pytest.mark.asyncio
async def test_short_page_ends_paging_even_if_total_rows_is_larger() -> None:
    """A page shorter than pageSize is the last one, whatever totalRows says."""
    client = _client([_page("site", 0, 40, 500)])

    sites = await client.get_sites()

    assert len(sites) == 40
    assert len(_requests(client)) == 1


@pytest.mark.asyncio
async def test_error_on_a_later_page_is_raised() -> None:
    """A failing page fails the call instead of returning a truncated list."""
    client = _client(
        [_page("dev", 0, 100, 150), OmadaApiError("HTTP 500: boom", http_status=500)]
    )

    with pytest.raises(OmadaApiError) as err:
        await client.get_devices("site-1")

    assert err.value.http_status == 500
