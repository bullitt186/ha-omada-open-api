"""Tests for the gateway WAN speed-test coordinator."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

from custom_components.omada_open_api.coordinator import OmadaWanSpeedTestCoordinator

from .conftest import TEST_SITE_ID


async def test_wan_speed_test_coordinator_fetches_one_gateway(
    hass: HomeAssistant, mock_api_client: MagicMock
) -> None:
    """A gateway coordinator fetches the latest persisted result per port."""
    gateway_mac = "AA-BB-CC-DD-EE-03"
    ports = [{"port": 1, "portUuid": "1_opaque-port-id", "name": "WAN1"}]
    mock_api_client.get_gateway_wan_speed_test_ports = AsyncMock(return_value=ports)
    latest = {"portId": 1, "down": 987_000_000}
    mock_api_client.get_gateway_wan_speed_test_history = AsyncMock(return_value=latest)
    mock_api_client.get_gateway_wan_speed_test_result = AsyncMock(
        return_value={"portSpeedResults": [{"portId": 1, "status": 2}]}
    )

    coordinator = OmadaWanSpeedTestCoordinator(
        hass, mock_api_client, TEST_SITE_ID, gateway_mac
    )

    await coordinator.async_refresh()

    assert coordinator.last_update_success is True
    assert coordinator.data == {
        "ports": ports,
        "portSpeedResults": [latest],
        "activePortResults": [{"portId": 1, "status": 2}],
    }
    mock_api_client.get_gateway_wan_speed_test_ports.assert_awaited_once_with(
        TEST_SITE_ID, gateway_mac
    )
    mock_api_client.get_gateway_wan_speed_test_history.assert_awaited_once_with(
        TEST_SITE_ID, gateway_mac, "1_opaque-port-id"
    )
    mock_api_client.get_gateway_wan_speed_test_result.assert_awaited_once_with(
        TEST_SITE_ID, gateway_mac
    )
