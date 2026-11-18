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


def _requests(client: OmadaApiClient) -> list[tuple[str, str, dict[str, Any] | None]]:
    """Return (method, url, params) of every request the client sent."""
    mock = client._authenticated_request
    assert isinstance(mock, AsyncMock)
    return [
        (c.args[0], c.args[1], c.kwargs.get("params")) for c in mock.await_args_list
    ]


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


@pytest.mark.asyncio
async def test_response_without_result_counts_as_empty_list() -> None:
    """A success response without a result object yields no rows."""
    client = _client([{"errorCode": 0}])

    assert await client.get_sites() == []


@pytest.mark.asyncio
async def test_result_without_data_counts_as_empty_page() -> None:
    """A result without a data list yields no rows."""
    client = _client([{"errorCode": 0, "result": {"totalRows": 0}}])

    assert await client.get_devices("site-1") == []


@pytest.mark.asyncio
async def test_result_without_total_rows_returns_the_received_page() -> None:
    """Without totalRows the received full page is all that is known."""
    page = _page("site", 0, 100, 0)
    del page["result"]["totalRows"]
    client = _client([page])

    sites = await client.get_sites()

    assert len(sites) == 100
    assert len(_requests(client)) == 1


@pytest.mark.asyncio
async def test_threat_management_pages_with_the_requested_page_size() -> None:
    """The caller's page_size is sent as pageSize and ends paging."""
    url = f"{API_URL}/openapi/v1/{OMADA_ID}/security/threat-management"
    client = _client([_page("t", 0, 50, 60), _page("t", 50, 10, 60)])

    rows = await client.get_threat_management(
        site_id="site-1", start_time=10, end_time=20, page_size=50
    )

    assert len(rows) == 60
    filters = {
        "siteList": "site-1",
        "archived": "false",
        "filters.startTime": 10,
        "filters.endTime": 20,
        "sorts.time": "desc",
    }
    assert _requests(client) == [
        ("get", url, {"page": 1, "pageSize": 50, **filters}),
        ("get", url, {"page": 2, "pageSize": 50, **filters}),
    ]


@pytest.mark.asyncio
async def test_site_ssids_skip_wlans_without_id_and_keep_ssid_name() -> None:
    """WLAN groups without an ID are skipped; an existing ssidName is kept."""
    ssids_url = (
        f"{API_URL}/openapi/v1/{OMADA_ID}/sites/site-1/wireless-network/wlans/w2/ssids"
    )
    client = _client(
        [
            {
                "errorCode": 0,
                "result": [{"name": "Broken"}, {"wlanId": "w2", "name": "Main"}],
            },
            {
                "errorCode": 0,
                "result": {
                    "totalRows": 2,
                    "data": [
                        {"ssidId": "s1", "name": "Home"},
                        {"ssidId": "s2", "name": "raw", "ssidName": "Guest"},
                    ],
                },
            },
        ]
    )

    ssids = await client.get_site_ssids_comprehensive("site-1")

    assert ssids == [
        {
            "ssidId": "s1",
            "name": "Home",
            "ssidName": "Home",
            "wlanId": "w2",
            "wlanName": "Main",
        },
        {
            "ssidId": "s2",
            "name": "raw",
            "ssidName": "Guest",
            "wlanId": "w2",
            "wlanName": "Main",
        },
    ]
    assert _requests(client)[1] == ("get", ssids_url, {"page": 1, "pageSize": 100})
