"""Tests for the v1 clients fallback on controllers without the v2 endpoint.

Software controllers such as 5.15 answer the v2 POST clients endpoint with
HTTP 404 rather than errorCode -1600, but still list clients via the v1 GET.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.omada_open_api.api import OmadaApiClient, OmadaApiError
from custom_components.omada_open_api.config_flow import _fetch_all_clients

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


def _response(status: int, payload: dict[str, Any] | None = None) -> MagicMock:
    response = MagicMock()
    response.status = status
    response.text = AsyncMock(return_value="Not Found")
    response.json = AsyncMock(return_value=payload)
    response.raise_for_status = MagicMock()
    return response


def _session(post_response: MagicMock, get_response: MagicMock) -> MagicMock:
    session = MagicMock()
    session.post.return_value.__aenter__ = AsyncMock(return_value=post_response)
    session.post.return_value.__aexit__ = AsyncMock(return_value=False)
    session.get.return_value.__aenter__ = AsyncMock(return_value=get_response)
    session.get.return_value.__aexit__ = AsyncMock(return_value=False)
    return session


@pytest.mark.asyncio
async def test_fetch_all_clients_falls_back_to_v1_on_http_404() -> None:
    """The client picker lists clients via v1 when v2 is missing."""
    clients = [{"mac": "AA"}, {"mac": "BB"}]
    session = _session(
        _response(404),
        _response(
            200, {"errorCode": 0, "result": {"totalRows": 2, "data": clients}}
        ),
    )

    result = await _fetch_all_clients(session, V2_URL, {}, "site-id")

    assert result == clients
    assert session.get.call_args.args == (V1_URL,)
    assert session.get.call_args.kwargs["params"] == {"page": 1, "pageSize": 200}


@pytest.mark.asyncio
async def test_fetch_all_clients_empty_when_v1_also_missing() -> None:
    """No clients endpoint at all skips client selection instead of failing."""
    session = _session(_response(404), _response(404))

    assert await _fetch_all_clients(session, V2_URL, {}, "site-id") == []
