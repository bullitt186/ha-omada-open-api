"""Tests for WAN speed test API methods."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from custom_components.omada_open_api.api import OmadaApiClient


def _make_client() -> OmadaApiClient:
    """Create a minimal API client with required attributes."""
    client = OmadaApiClient.__new__(OmadaApiClient)
    client._api_url = "https://controller.local"
    client._omada_id = "test-omada-id"
    client._authenticated_request = AsyncMock(return_value={})
    return client


@pytest.mark.asyncio
async def test_get_wan_speed_test_stats() -> None:
    """get_wan_speed_test_stats calls the correct endpoint."""
    client = _make_client()
    client._authenticated_request = AsyncMock(return_value={"id": 1, "status": 1})

    result = await client.get_wan_speed_test_stats("site1")

    assert result == {"id": 1, "status": 1}
    client._authenticated_request.assert_called_once_with(
        "get",
        "https://controller.local/openapi/v1/test-omada-id/sites/site1/statistics/speedTest",
    )


@pytest.mark.asyncio
async def test_trigger_wan_speed_test() -> None:
    """trigger_wan_speed_test calls the correct endpoint."""
    client = _make_client()
    client._authenticated_request = AsyncMock(return_value={"success": True})

    result = await client.trigger_wan_speed_test("site1", wan_id="wan1")

    assert result == {"success": True}
    client._authenticated_request.assert_called_once_with(
        "post",
        "https://controller.local/openapi/v1/test-omada-id/sites/site1/statistics/speedTest",
        json_data={"id": "wan1"},
    )


@pytest.mark.asyncio
async def test_trigger_wan_speed_test_no_wan_id() -> None:
    """trigger_wan_speed_test without wan_id sends empty payload."""
    client = _make_client()
    client._authenticated_request = AsyncMock(return_value={"success": True})

    await client.trigger_wan_speed_test("site1")

    client._authenticated_request.assert_called_once_with(
        "post",
        "https://controller.local/openapi/v1/test-omada-id/sites/site1/statistics/speedTest",
        json_data={},
    )
