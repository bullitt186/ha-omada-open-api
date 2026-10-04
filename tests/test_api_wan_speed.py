"""Tests for gateway WAN speed-test API access."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from custom_components.omada_open_api.api import OmadaApiClient, OmadaApiError


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
async def test_get_gateway_wan_speed_test_ports_returns_empty_on_404() -> None:
    """A non-Fusion controller lacks the ISP dashboard endpoint (HTTP 404).

    Standard (non-Fusion) Omada Software Controllers don't expose
    `dashboard/gateway/isp/load`. The lookup should degrade to "no Fusion
    ports" instead of propagating, so the WAN speed-test coordinator can
    still return the working v1 `speedTestResult` data. See GH #68.
    """
    client = OmadaApiClient.__new__(OmadaApiClient)
    client._api_url = "https://controller.local"
    client._omada_id = "controller-id"
    client._authenticated_request = AsyncMock(
        side_effect=OmadaApiError("HTTP 404: Not Found", http_status=404)
    )

    ports = await client.get_gateway_wan_speed_test_ports("site-id", "gateway-mac")

    assert ports == []


@pytest.mark.asyncio
async def test_get_gateway_wan_speed_test_ports_returns_empty_on_unsupported_path() -> (
    None
):
    """A controller rejecting the ISP dashboard path with -1600 has no ports.

    Some non-Fusion controllers answer HTTP 200 with errorCode -1600
    ("Unsupported request path") instead of HTTP 404. See GH #64 and #68.
    """
    client = OmadaApiClient.__new__(OmadaApiClient)
    client._api_url = "https://controller.local"
    client._omada_id = "controller-id"
    client._authenticated_request = AsyncMock(
        side_effect=OmadaApiError(
            "API error -1600: Unsupported request path.", error_code=-1600
        )
    )

    ports = await client.get_gateway_wan_speed_test_ports("site-id", "gateway-mac")

    assert ports == []


@pytest.mark.asyncio
async def test_get_gateway_wan_speed_test_ports_reraises_other_errors() -> None:
    """A non-404 failure on the ISP dashboard endpoint still propagates."""
    client = OmadaApiClient.__new__(OmadaApiClient)
    client._api_url = "https://controller.local"
    client._omada_id = "controller-id"
    client._authenticated_request = AsyncMock(
        side_effect=OmadaApiError("HTTP 500: Internal Server Error", http_status=500)
    )

    with pytest.raises(OmadaApiError):
        await client.get_gateway_wan_speed_test_ports("site-id", "gateway-mac")


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
