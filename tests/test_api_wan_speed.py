"""Tests for WAN speed test API methods."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from custom_components.omada_open_api.api import OmadaApiClient


@pytest.mark.asyncio
async def test_get_wan_speed_test_stats() -> None:
    """get_wan_speed_test_stats calls the correct endpoint."""
    client = OmadaApiClient.__new__(OmadaApiClient)
    client._authenticated_request = AsyncMock(return_value={"id": 1, "status": 1})

    result = await client.get_wan_speed_test_stats("site1")

    assert result == {"id": 1, "status": 1}
    client._authenticated_request.assert_called_once_with(
        "get",
        "sites/site1/statistics/speedTest",
    )


@pytest.mark.asyncio
async def test_trigger_wan_speed_test() -> None:
    """trigger_wan_speed_test calls the correct endpoint."""
    client = OmadaApiClient.__new__(OmadaApiClient)
    client._authenticated_request = AsyncMock(return_value={"success": True})

    result = await client.trigger_wan_speed_test("site1", wan_id="wan1")

    assert result == {"success": True}
    client._authenticated_request.assert_called_once_with(
        "post",
        "sites/site1/statistics/speedTest",
        json_data={"id": "wan1"},
    )


@pytest.mark.asyncio
async def test_trigger_wan_speed_test_no_wan_id() -> None:
    """trigger_wan_speed_test without wan_id sends empty payload."""
    client = OmadaApiClient.__new__(OmadaApiClient)
    client._authenticated_request = AsyncMock(return_value={"success": True})

    await client.trigger_wan_speed_test("site1")

    client._authenticated_request.assert_called_once_with(
        "post",
        "sites/site1/statistics/speedTest",
        json_data={},
    )
