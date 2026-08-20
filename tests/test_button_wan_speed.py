"""Tests for the gateway WAN speed-test button."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.omada_open_api.button import OmadaWanSpeedTestButton


@pytest.mark.asyncio
async def test_wan_speed_test_button_triggers_selected_port_and_refreshes() -> None:
    """Pressing the button targets one WAN port and refreshes its result."""
    coordinator = MagicMock()
    coordinator.site_id = "site-id"
    coordinator.gateway_mac = "gateway-mac"
    coordinator.api_client.trigger_gateway_wan_speed_test = AsyncMock()
    coordinator.async_request_refresh = AsyncMock()

    button = OmadaWanSpeedTestButton(
        coordinator=coordinator,
        gateway_mac="gateway-mac",
        port_id="1",
        port_uuid="1_opaque-port-id",
        port_name="WAN1",
    )

    await button.async_press()

    coordinator.api_client.trigger_gateway_wan_speed_test.assert_awaited_once_with(
        "site-id", "gateway-mac", ["1_opaque-port-id"]
    )
    coordinator.async_request_refresh.assert_awaited_once()


async def test_wan_speed_test_button_is_created_without_a_cached_result(
    hass,
) -> None:
    """Known WAN ports expose their test button before the first result exists."""
    from custom_components.omada_open_api.button import async_setup_entry

    gateway_mac = "AA-BB-CC-DD-EE-03"
    site_coordinator = MagicMock()
    site_coordinator.site_id = "site-id"
    site_coordinator.data = {
        "devices": {gateway_mac: {"type": "gateway"}},
        "wan_status": {gateway_mac: [{"portName": "WAN1"}]},
    }
    site_coordinator.async_add_listener.return_value = lambda: None
    speed_coordinator = MagicMock()
    speed_coordinator.data = {
        "portSpeedResults": [],
        "ports": [{"port": 1, "portUuid": "1_opaque-port-id", "name": "WAN1"}],
    }
    entry = MagicMock()
    entry.runtime_data.coordinators = {"site-id": site_coordinator}
    entry.runtime_data.client_coordinators = []
    entry.runtime_data.wan_speed_test_coordinators = {
        ("site-id", gateway_mac): speed_coordinator
    }
    entities = []

    await async_setup_entry(hass, entry, entities.extend)

    button = next(
        entity for entity in entities if isinstance(entity, OmadaWanSpeedTestButton)
    )
    assert button.unique_id == f"{gateway_mac}_1_wan_speed_test"
