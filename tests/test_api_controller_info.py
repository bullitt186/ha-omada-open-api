"""Tests for the unauthenticated controller info lookup (GET /api/info)."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import aiohttp
import pytest

from custom_components.omada_open_api.api import (
    OmadaApiClient,
    OmadaApiError,
    async_get_controller_id,
)
from custom_components.omada_open_api.const import DEFAULT_TIMEOUT


def _session(status: int = 200, payload: Any = None) -> MagicMock:
    response = MagicMock(status=status)
    response.json = AsyncMock(return_value=payload)
    session = MagicMock()
    session.get.return_value.__aenter__ = AsyncMock(return_value=response)
    session.get.return_value.__aexit__ = AsyncMock(return_value=False)
    return session


@pytest.mark.asyncio
async def test_returns_omadac_id_from_info_endpoint() -> None:
    """The ID comes from result.omadacId of GET {url}/api/info."""
    session = _session(payload={"errorCode": 0, "result": {"omadacId": "cid-1"}})

    assert await async_get_controller_id(session, "https://192.168.1.1/") == "cid-1"

    call = session.get.call_args
    assert call.args == ("https://192.168.1.1/api/info",)
    assert call.kwargs["timeout"].total == DEFAULT_TIMEOUT
    response = await session.get.return_value.__aenter__()
    response.json.assert_awaited_with(content_type=None)


@pytest.mark.asyncio
async def test_http_error_keeps_status() -> None:
    """A non-200 answer raises with its HTTP status."""
    with pytest.raises(OmadaApiError) as err:
        await async_get_controller_id(_session(status=502), "https://gw")

    assert err.value.http_status == 502
    assert err.value.error_code is None


@pytest.mark.asyncio
async def test_error_code_is_kept() -> None:
    """An Omada error code in the answer is kept on the raised error."""
    session = _session(payload={"errorCode": -1, "msg": "denied"})

    with pytest.raises(OmadaApiError) as err:
        await async_get_controller_id(session, "https://gw")

    assert err.value.error_code == -1
    assert "denied" in str(err.value)


@pytest.mark.parametrize(
    "payload",
    [
        {"errorCode": 0},
        {"errorCode": 0, "result": None},
        {"errorCode": 0, "result": {}},
    ],
)
@pytest.mark.asyncio
async def test_missing_controller_id_raises(payload: dict[str, Any]) -> None:
    """An answer without omadacId raises without status or error code."""
    with pytest.raises(OmadaApiError) as err:
        await async_get_controller_id(_session(payload=payload), "https://gw")

    assert err.value.http_status is None
    assert err.value.error_code is None


@pytest.mark.asyncio
async def test_connection_error_is_wrapped_with_cause() -> None:
    """Connection errors keep the aiohttp error as cause for classification."""
    refused = aiohttp.ClientConnectionError("Connection refused")
    session = MagicMock()
    session.get.return_value.__aenter__ = AsyncMock(side_effect=refused)
    session.get.return_value.__aexit__ = AsyncMock(return_value=False)

    with pytest.raises(OmadaApiError) as err:
        await async_get_controller_id(session, "https://gw")

    assert err.value.__cause__ is refused


@pytest.mark.asyncio
async def test_from_auth_uses_the_given_auth_session_and_ids() -> None:
    """A client built from an auth strategy requests through it."""
    auth = MagicMock()
    auth.ensure_valid_session = AsyncMock()
    auth.decorate_request = MagicMock(
        side_effect=lambda headers: headers.update({"Csrf-Token": "csrf"})
    )
    session = _session(payload={"errorCode": 0, "result": {"data": [], "totalRows": 0}})

    client = OmadaApiClient.from_auth(session, auth, "https://gw/", "cid-1")

    assert client.auth is auth
    assert client.session is session
    assert client.api_url == "https://gw"
    assert await client.get_sites() == []
    assert session.get.call_args.args == ("https://gw/openapi/v1/cid-1/sites",)
    assert session.get.call_args.kwargs["headers"]["Csrf-Token"] == "csrf"
