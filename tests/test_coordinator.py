"""Tests for Omada Open API coordinators."""

from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock

from homeassistant.util import dt as dt_util

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

from custom_components.omada_open_api.api import OmadaApiError
from custom_components.omada_open_api.coordinator import (
    OmadaAppTrafficCoordinator,
    OmadaClientCoordinator,
    OmadaSiteCoordinator,
)

from .conftest import (
    SAMPLE_DEVICE_AP,
    SAMPLE_POE_PORT_ACTIVE,
    SAMPLE_POE_PORT_INACTIVE,
    SAMPLE_POE_PORT_NOT_SUPPORTED,
    SAMPLE_POE_PORT_SWITCH_NOT_SUPPORTED,
    TEST_SITE_ID,
    TEST_SITE_NAME,
)

# ---------------------------------------------------------------------------
# OmadaSiteCoordinator
# ---------------------------------------------------------------------------


async def test_site_coordinator_fetches_devices_and_uplinks(
    hass: HomeAssistant, mock_api_client: MagicMock
) -> None:
    """Test that the site coordinator fetches devices and merges uplink info."""
    coordinator = OmadaSiteCoordinator(
        hass=hass,
        api_client=mock_api_client,
        site_id=TEST_SITE_ID,
        site_name=TEST_SITE_NAME,
    )

    await coordinator.async_refresh()
    assert coordinator.last_update_success is True

    data = coordinator.data
    assert "devices" in data
    assert len(data["devices"]) == 3

    # Verify uplink info was merged into the AP device.
    ap = data["devices"]["AA-BB-CC-DD-EE-01"]
    assert ap["name"] == "Office AP"
    assert ap["uplink_device_name"] == "Core Switch"
    assert ap["link_speed"] == 3

    # Verify gateway has no uplink (not in uplink_info fixture).
    gw = data["devices"]["AA-BB-CC-DD-EE-03"]
    assert gw["name"] == "Main Gateway"


async def test_site_coordinator_handles_uplink_failure_gracefully(
    hass: HomeAssistant, mock_api_client: MagicMock
) -> None:
    """Test that uplink info failure doesn't break the update."""
    mock_api_client.get_device_uplink_info = AsyncMock(
        side_effect=OmadaApiError("Uplink fetch failed")
    )

    coordinator = OmadaSiteCoordinator(
        hass=hass,
        api_client=mock_api_client,
        site_id=TEST_SITE_ID,
        site_name=TEST_SITE_NAME,
    )

    await coordinator.async_refresh()
    # Update should still succeed — uplink info is optional.
    assert coordinator.last_update_success is True
    assert len(coordinator.data["devices"]) == 3


async def test_site_coordinator_raises_on_device_fetch_failure(
    hass: HomeAssistant, mock_api_client: MagicMock
) -> None:
    """Test that device fetch failure raises UpdateFailed."""
    mock_api_client.get_devices = AsyncMock(
        side_effect=OmadaApiError("Connection lost")
    )

    coordinator = OmadaSiteCoordinator(
        hass=hass,
        api_client=mock_api_client,
        site_id=TEST_SITE_ID,
        site_name=TEST_SITE_NAME,
    )

    await coordinator.async_refresh()
    assert coordinator.last_update_success is False


async def test_site_coordinator_handles_device_without_mac(
    hass: HomeAssistant, mock_api_client: MagicMock
) -> None:
    """Test that devices without a MAC are skipped."""
    mock_api_client.get_devices = AsyncMock(
        return_value=[
            SAMPLE_DEVICE_AP,
            {"name": "No MAC Device", "type": "ap"},  # Missing mac
        ]
    )

    coordinator = OmadaSiteCoordinator(
        hass=hass,
        api_client=mock_api_client,
        site_id=TEST_SITE_ID,
        site_name=TEST_SITE_NAME,
    )

    await coordinator.async_refresh()
    assert coordinator.last_update_success is True
    assert len(coordinator.data["devices"]) == 1


async def test_site_coordinator_empty_device_list(
    hass: HomeAssistant, mock_api_client: MagicMock
) -> None:
    """Test that an empty device list is handled correctly."""
    mock_api_client.get_devices = AsyncMock(return_value=[])

    coordinator = OmadaSiteCoordinator(
        hass=hass,
        api_client=mock_api_client,
        site_id=TEST_SITE_ID,
        site_name=TEST_SITE_NAME,
    )

    await coordinator.async_refresh()
    assert coordinator.last_update_success is True
    assert len(coordinator.data["devices"]) == 0
    # Uplink should not be called if there are no devices.
    mock_api_client.get_device_uplink_info.assert_not_called()


async def test_site_coordinator_fetches_poe_ports(
    hass: HomeAssistant, mock_api_client: MagicMock
) -> None:
    """Test that site coordinator fetches and filters PoE port data."""
    mock_api_client.get_switch_ports_poe = AsyncMock(
        return_value=[
            SAMPLE_POE_PORT_ACTIVE,
            SAMPLE_POE_PORT_INACTIVE,
            SAMPLE_POE_PORT_NOT_SUPPORTED,
            SAMPLE_POE_PORT_SWITCH_NOT_SUPPORTED,
        ]
    )

    coordinator = OmadaSiteCoordinator(
        hass=hass,
        api_client=mock_api_client,
        site_id=TEST_SITE_ID,
        site_name=TEST_SITE_NAME,
    )

    await coordinator.async_refresh()
    assert coordinator.last_update_success is True

    poe_ports = coordinator.data["poe_ports"]
    # Only ports with supportPoe=True AND switchSupportPoe=1 should be included.
    # Port 3 (supportPoe=False) and switch-not-supported port should be excluded.
    assert len(poe_ports) == 2

    key_active = "AA-BB-CC-DD-EE-02_1"
    assert key_active in poe_ports
    assert poe_ports[key_active]["power"] == 12.5
    assert poe_ports[key_active]["poe_enabled"] is True
    assert poe_ports[key_active]["switch_name"] == "Core Switch"
    assert poe_ports[key_active]["port_name"] == "Port 1"
    assert poe_ports[key_active]["voltage"] == 53.2
    assert poe_ports[key_active]["current"] == 235.0
    assert poe_ports[key_active]["pd_class"] == "Class 4"
    assert poe_ports[key_active]["poe_display_type"] == 4

    key_inactive = "AA-BB-CC-DD-EE-02_2"
    assert key_inactive in poe_ports
    assert poe_ports[key_inactive]["power"] == 0.0
    assert poe_ports[key_inactive]["poe_enabled"] is False


async def test_site_coordinator_poe_failure_graceful(
    hass: HomeAssistant, mock_api_client: MagicMock
) -> None:
    """Test that PoE fetch failure doesn't break the update."""
    mock_api_client.get_switch_ports_poe = AsyncMock(
        side_effect=OmadaApiError("PoE endpoint unavailable")
    )

    coordinator = OmadaSiteCoordinator(
        hass=hass,
        api_client=mock_api_client,
        site_id=TEST_SITE_ID,
        site_name=TEST_SITE_NAME,
    )

    await coordinator.async_refresh()
    assert coordinator.last_update_success is True
    # PoE ports should be empty dict, not missing.
    assert coordinator.data["poe_ports"] == {}
    # Devices should still be present.
    assert len(coordinator.data["devices"]) == 3


async def test_site_coordinator_poe_empty_response(
    hass: HomeAssistant, mock_api_client: MagicMock
) -> None:
    """Test that empty PoE response results in empty poe_ports dict."""
    mock_api_client.get_switch_ports_poe = AsyncMock(return_value=[])

    coordinator = OmadaSiteCoordinator(
        hass=hass,
        api_client=mock_api_client,
        site_id=TEST_SITE_ID,
        site_name=TEST_SITE_NAME,
    )

    await coordinator.async_refresh()
    assert coordinator.last_update_success is True
    assert coordinator.data["poe_ports"] == {}


# ---------------------------------------------------------------------------
# OmadaClientCoordinator
# ---------------------------------------------------------------------------


async def test_client_coordinator_filters_selected_clients(
    hass: HomeAssistant, mock_api_client: MagicMock
) -> None:
    """Test that only selected clients are returned."""
    coordinator = OmadaClientCoordinator(
        hass=hass,
        api_client=mock_api_client,
        site_id=TEST_SITE_ID,
        site_name=TEST_SITE_NAME,
        selected_client_macs=["11-22-33-44-55-AA"],
    )

    await coordinator.async_refresh()
    assert coordinator.last_update_success is True

    data = coordinator.data
    assert "11-22-33-44-55-AA" in data
    assert "11-22-33-44-55-BB" not in data
    assert data["11-22-33-44-55-AA"]["name"] == "Phone"


async def test_client_coordinator_handles_all_selected(
    hass: HomeAssistant, mock_api_client: MagicMock
) -> None:
    """Test with all clients selected."""
    coordinator = OmadaClientCoordinator(
        hass=hass,
        api_client=mock_api_client,
        site_id=TEST_SITE_ID,
        site_name=TEST_SITE_NAME,
        selected_client_macs=["11-22-33-44-55-AA", "11-22-33-44-55-BB"],
    )

    await coordinator.async_refresh()
    assert coordinator.last_update_success is True
    assert len(coordinator.data) == 2


async def test_client_coordinator_selected_client_not_online(
    hass: HomeAssistant, mock_api_client: MagicMock
) -> None:
    """Test that missing (offline) selected clients are simply absent from data."""
    mock_api_client.get_clients = AsyncMock(
        return_value={"data": [], "totalRows": 0, "currentPage": 1}
    )

    coordinator = OmadaClientCoordinator(
        hass=hass,
        api_client=mock_api_client,
        site_id=TEST_SITE_ID,
        site_name=TEST_SITE_NAME,
        selected_client_macs=["11-22-33-44-55-AA"],
    )

    await coordinator.async_refresh()
    assert coordinator.last_update_success is True
    assert len(coordinator.data) == 0


async def test_client_coordinator_api_failure(
    hass: HomeAssistant, mock_api_client: MagicMock
) -> None:
    """Test that API failure raises UpdateFailed."""
    mock_api_client.get_clients = AsyncMock(
        side_effect=OmadaApiError("API unreachable")
    )

    coordinator = OmadaClientCoordinator(
        hass=hass,
        api_client=mock_api_client,
        site_id=TEST_SITE_ID,
        site_name=TEST_SITE_NAME,
        selected_client_macs=["11-22-33-44-55-AA"],
    )

    await coordinator.async_refresh()
    assert coordinator.last_update_success is False


# ---------------------------------------------------------------------------
# OmadaAppTrafficCoordinator
# ---------------------------------------------------------------------------


async def test_app_traffic_coordinator_fetches_data(
    hass: HomeAssistant, mock_api_client: MagicMock
) -> None:
    """Test that app traffic coordinator fetches and filters data."""
    mock_api_client.get_client_app_traffic = AsyncMock(
        return_value=[
            {
                "applicationId": 100,
                "applicationName": "Netflix",
                "upload": 1024,
                "download": 2048,
                "traffic": 3072,
            },
            {
                "applicationId": 200,
                "applicationName": "YouTube",
                "upload": 512,
                "download": 1024,
                "traffic": 1536,
            },
            {
                "applicationId": 999,
                "applicationName": "Unselected App",
                "upload": 0,
                "download": 0,
                "traffic": 0,
            },
        ]
    )

    coordinator = OmadaAppTrafficCoordinator(
        hass=hass,
        api_client=mock_api_client,
        site_id=TEST_SITE_ID,
        site_name=TEST_SITE_NAME,
        selected_client_macs=["11-22-33-44-55-AA"],
        selected_app_ids=["100", "200"],
    )

    await coordinator.async_refresh()
    assert coordinator.last_update_success is True

    data = coordinator.data
    assert "11-22-33-44-55-AA" in data
    client_apps = data["11-22-33-44-55-AA"]
    assert "100" in client_apps
    assert "200" in client_apps
    assert "999" not in client_apps  # Not selected
    assert client_apps["100"]["download"] == 2048


async def test_app_traffic_coordinator_per_client_error_resilience(
    hass: HomeAssistant, mock_api_client: MagicMock
) -> None:
    """Test that one client failing doesn't affect others."""
    call_count = 0

    async def _side_effect(site_id, mac, start, end):
        nonlocal call_count
        call_count += 1
        if mac == "11-22-33-44-55-AA":
            raise OmadaApiError("Timeout for this client")
        return [
            {
                "applicationId": 100,
                "applicationName": "Netflix",
                "upload": 100,
                "download": 200,
                "traffic": 300,
            },
        ]

    mock_api_client.get_client_app_traffic = AsyncMock(side_effect=_side_effect)

    coordinator = OmadaAppTrafficCoordinator(
        hass=hass,
        api_client=mock_api_client,
        site_id=TEST_SITE_ID,
        site_name=TEST_SITE_NAME,
        selected_client_macs=["11-22-33-44-55-AA", "11-22-33-44-55-BB"],
        selected_app_ids=["100"],
    )

    await coordinator.async_refresh()
    assert coordinator.last_update_success is True

    # First client failed, second succeeded.
    data = coordinator.data
    assert "11-22-33-44-55-AA" not in data
    assert "11-22-33-44-55-BB" in data


async def test_app_traffic_coordinator_midnight_reset(
    hass: HomeAssistant, mock_api_client: MagicMock, freezer
) -> None:
    """Test that the coordinator resets its tracking at midnight."""
    mock_api_client.get_client_app_traffic = AsyncMock(return_value=[])

    coordinator = OmadaAppTrafficCoordinator(
        hass=hass,
        api_client=mock_api_client,
        site_id=TEST_SITE_ID,
        site_name=TEST_SITE_NAME,
        selected_client_macs=["11-22-33-44-55-AA"],
        selected_app_ids=["100"],
    )

    # First fetch sets _last_reset.
    await coordinator.async_refresh()
    assert coordinator._last_reset is not None  # noqa: SLF001
    first_reset = coordinator._last_reset  # noqa: SLF001

    # Advance time by 1 day.
    freezer.move_to(dt_util.now() + timedelta(days=1, hours=1))

    await coordinator.async_refresh()
    second_reset = coordinator._last_reset  # noqa: SLF001
    assert second_reset > first_reset


async def test_app_traffic_coordinator_no_selected_apps_returns_empty(
    hass: HomeAssistant, mock_api_client: MagicMock
) -> None:
    """Test coordinator with no apps returns empty data for each client."""
    mock_api_client.get_client_app_traffic = AsyncMock(
        return_value=[
            {
                "applicationId": 100,
                "applicationName": "Netflix",
                "upload": 1024,
                "download": 2048,
                "traffic": 3072,
            },
        ]
    )

    coordinator = OmadaAppTrafficCoordinator(
        hass=hass,
        api_client=mock_api_client,
        site_id=TEST_SITE_ID,
        site_name=TEST_SITE_NAME,
        selected_client_macs=["11-22-33-44-55-AA"],
        selected_app_ids=[],  # No apps selected
    )

    await coordinator.async_refresh()
    assert coordinator.last_update_success is True
    # No matching apps → client not in data.
    assert len(coordinator.data) == 0
