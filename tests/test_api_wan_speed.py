"""Tests for gateway WAN speed-test API access."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from custom_components.omada_open_api.api import OmadaApiClient


@pytest.mark.asyncio
async def test_get_gateway_wan_speed_test_result_unwraps_result() -> None:
    """Gateway speed-test results use the gateway-specific endpoint."""
    client = OmadaApiClient.__new__(OmadaApiClient)
    client._api_url = "https://controller.local"
    client._omada_id = "controller-id"
    client._authenticated_request = AsyncMock(
        return_value={
            "errorCode": 0,
            "result": {
                "status": 0,
                "portSpeedResults": [],
            },
        }
    )

    result = await client.get_gateway_wan_speed_test_result("site-id", "gateway-mac")

    assert result == {"status": 0, "portSpeedResults": []}
    client._authenticated_request.assert_awaited_once_with(
        "get",
        "https://controller.local/openapi/v1/controller-id/sites/site-id/"
        "gateways/gateway-mac/speedTestResult",
    )


@pytest.mark.asyncio
async def test_trigger_gateway_wan_speed_test_uses_selected_port_uuids() -> None:
    """A WAN speed test is triggered for explicit gateway ports only."""
    client = OmadaApiClient.__new__(OmadaApiClient)
    client._api_url = "https://controller.local"
    client._omada_id = "controller-id"
    client._authenticated_request = AsyncMock(return_value={"errorCode": 0})

    await client.trigger_gateway_wan_speed_test("site-id", "gateway-mac", ["port-uuid"])

    client._authenticated_request.assert_awaited_once_with(
        "post",
        "https://controller.local/openapi/v1/controller-id/sites/site-id/"
        "gateways/gateway-mac/speedTest",
        json_data={"portUuidList": ["port-uuid"]},
    )


@pytest.mark.asyncio
async def test_get_gateway_wan_speed_test_ports_returns_fusion_port_uuids() -> None:
    """Fusion's ISP dashboard supplies the UUID required to start a test."""
    client = OmadaApiClient.__new__(OmadaApiClient)
    client._api_url = "https://controller.local"
    client._omada_id = "controller-id"
    client._authenticated_request = AsyncMock(
        return_value={
            "errorCode": 0,
            "result": {
                "data": [
                    {
                        "mac": "gateway-mac",
                        "ispInfo": {
                            "ispArr": [
                                {
                                    "port": 1,
                                    "portUuid": "1_opaque-port-id",
                                    "name": "WAN1",
                                }
                            ]
                        },
                    }
                ]
            },
        }
    )

    ports = await client.get_gateway_wan_speed_test_ports("site-id", "gateway-mac")

    assert ports == [{"port": 1, "portUuid": "1_opaque-port-id", "name": "WAN1"}]
    client._authenticated_request.assert_awaited_once_with(
        "get",
        "https://controller.local/openapi/v2/controller-id/sites/site-id/"
        "dashboard/gateway/isp/load",
    )


@pytest.mark.asyncio
async def test_get_gateway_wan_speed_test_history_returns_latest_result() -> None:
    """Fusion persists completed tests in the per-port date-list endpoint."""
    client = OmadaApiClient.__new__(OmadaApiClient)
    client._api_url = "https://controller.local"
    client._omada_id = "controller-id"
    latest = {"portId": 1, "time": 1_787_258_021, "down": 940_033_152}
    client._authenticated_request = AsyncMock(
        return_value={"errorCode": 0, "result": {"data": [latest]}}
    )

    result = await client.get_gateway_wan_speed_test_history(
        "site-id", "gateway-mac", "1_opaque-port-id"
    )

    assert result == latest
    client._authenticated_request.assert_awaited_once_with(
        "post",
        "https://controller.local/openapi/v1/controller-id/sites/site-id/"
        "gateways/gateway-mac/speedTestResult/dateList",
        json_data={
            "portUuid": "1_opaque-port-id",
            "currentPage": 1,
            "currentPageSize": 1,
        },
    )
