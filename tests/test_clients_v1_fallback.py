"""Tests for the v1 clients fallback on controllers without the v2 endpoint.

Software controllers such as 5.15 answer the v2 POST clients endpoint with
HTTP 404 rather than errorCode -1600, but still list clients via the v1 GET.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import pytest

from custom_components.omada_open_api.api import OmadaApiClient, OmadaApiError
from custom_components.omada_open_api.config_flow import OmadaConfigFlow

V2_URL = "https://controller.local/openapi/v2/controller-id/sites/site-id/clients"
V1_URL = "https://controller.local/openapi/v1/controller-id/sites/site-id/clients"


def _api_client(side_effect: list[Any]) -> OmadaApiClient:
    client = OmadaApiClient.__new__(OmadaApiClient)
    client._api_url = "https://controller.local"
    client._omada_id = "controller-id"
    client._use_v1_clients = False
    client._authenticated_request = AsyncMock(side_effect=side_effect)
    return client


@pytest.mark.asyncio
async def test_get_clients_falls_back_to_v1_on_http_404() -> None:
    """A 404 from the v2 endpoint switches to the v1 GET for good."""
    v1_result = {"totalRows": 1, "currentPage": 1, "data": [{"mac": "AA"}]}
    client = _api_client(
        [
            OmadaApiError("HTTP 404: Not Found", http_status=404),
            {"errorCode": 0, "result": v1_result},
            {"errorCode": 0, "result": v1_result},
        ]
    )

    assert await client.get_clients("site-id") == v1_result
    assert client._use_v1_clients is True
    assert await client.get_clients("site-id") == v1_result

    calls = client._authenticated_request.await_args_list
    assert calls[0].args == ("post", V2_URL)
    assert calls[1].args == ("get", V1_URL)
    assert calls[2].args == ("get", V1_URL)


@pytest.mark.asyncio
async def test_get_clients_reraises_other_http_errors() -> None:
    """A non-404 failure of the v2 endpoint still propagates."""
    client = _api_client(
        [OmadaApiError("HTTP 500: Internal Server Error", http_status=500)]
    )

    with pytest.raises(OmadaApiError):
        await client.get_clients("site-id")
    assert client._use_v1_clients is False


@pytest.mark.asyncio
async def test_get_all_clients_falls_back_to_v1_on_http_404() -> None:
    """The client picker lists clients via v1 when v2 is missing (HTTP 404)."""
    clients = [{"mac": "AA"}, {"mac": "BB"}]
    client = _api_client(
        [
            OmadaApiError("HTTP 404: Not Found", http_status=404),
            {"errorCode": 0, "result": {"totalRows": 2, "data": clients}},
        ]
    )

    assert await client.get_all_clients("site-id") == clients

    calls = client._authenticated_request.await_args_list
    assert calls[0].args == ("post", V2_URL)
    assert calls[0].kwargs["json_data"] == {
        "page": 1,
        "pageSize": 200,
        "scope": 0,
        "filters": {},
    }
    assert calls[1].args == ("get", V1_URL)
    assert calls[1].kwargs["params"] == {"page": 1, "pageSize": 200}


@pytest.mark.asyncio
async def test_get_all_clients_falls_back_to_v1_on_error_code_1600() -> None:
    """Fusion firmware rejects the v2 endpoint with errorCode -1600."""
    clients = [{"mac": "AA"}]
    client = _api_client(
        [
            OmadaApiError("API error -1600: Unsupported", error_code=-1600),
            {"errorCode": 0, "result": {"totalRows": 1, "data": clients}},
        ]
    )

    assert await client.get_all_clients("site-id") == clients
    assert client._authenticated_request.await_args_list[1].args == ("get", V1_URL)


@pytest.mark.asyncio
async def test_get_all_clients_reads_every_page() -> None:
    """Every page up to totalRows is requested with the given scope."""
    page_1 = [{"mac": f"A{i}"} for i in range(200)]
    page_2 = [{"mac": f"B{i}"} for i in range(50)]
    client = _api_client(
        [
            {"errorCode": 0, "result": {"totalRows": 250, "data": page_1}},
            {"errorCode": 0, "result": {"totalRows": 250, "data": page_2}},
        ]
    )

    assert await client.get_all_clients("site-id", scope=2) == page_1 + page_2

    bodies = [
        c.kwargs["json_data"] for c in client._authenticated_request.await_args_list
    ]
    assert bodies == [
        {"page": 1, "pageSize": 200, "scope": 2, "filters": {}},
        {"page": 2, "pageSize": 200, "scope": 2, "filters": {}},
    ]


@pytest.mark.asyncio
async def test_flow_clients_empty_when_v1_also_missing() -> None:
    """No clients endpoint at all skips client selection instead of failing."""
    flow = OmadaConfigFlow()
    flow._api_client = _api_client(
        [
            OmadaApiError("HTTP 404: Not Found", http_status=404),
            OmadaApiError("HTTP 404: Not Found", http_status=404),
        ]
    )

    assert await flow._get_clients("site-id") == []


@pytest.mark.asyncio
async def test_flow_clients_reraise_other_errors() -> None:
    """Other failures reach the step, which reports them."""
    flow = OmadaConfigFlow()
    flow._api_client = _api_client([OmadaApiError("HTTP 500", http_status=500)])

    with pytest.raises(OmadaApiError):
        await flow._get_clients("site-id")
