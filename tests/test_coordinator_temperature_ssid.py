"""Tests for coordinator temperature and SSID fetching."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock

from custom_components.omada_open_api.api import OmadaApiError
from custom_components.omada_open_api.coordinator import OmadaSiteCoordinator

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant


async def test_merge_gateway_temperature_success(hass: HomeAssistant) -> None:
    """Test merging gateway temperature data."""
    mock_api_client = MagicMock()
    mock_api_client.get_gateway_info = AsyncMock(
        return_value={"mac": "AA:BB:CC:DD:EE:FF", "temp": 45}
    )

    devices = {
        "AA:BB:CC:DD:EE:FF": {
            "mac": "AA:BB:CC:DD:EE:FF",
            "type": "gateway",
            "name": "Gateway 1",
        }
    }

    coordinator = OmadaSiteCoordinator(
        hass=hass,
        api_client=mock_api_client,
        site_id="site_001",
        site_name="Test Site",
    )

    # Call the private method
    await coordinator._merge_gateway_temperature(devices)  # noqa: SLF001

    # Verify temperature was merged
    assert devices["AA:BB:CC:DD:EE:FF"].get("temperature") == 45
    mock_api_client.get_gateway_info.assert_called_once_with(
        "site_001", "AA:BB:CC:DD:EE:FF"
    )


async def test_merge_gateway_temperature_api_error(hass: HomeAssistant) -> None:
    """Test merging gateway temperature handles API errors."""
    mock_api_client = MagicMock()
    mock_api_client.get_gateway_info = AsyncMock(side_effect=OmadaApiError("API Error"))

    devices = {
        "AA:BB:CC:DD:EE:FF": {
            "mac": "AA:BB:CC:DD:EE:FF",
            "type": "gateway",
            "name": "Gateway 1",
        }
    }

    coordinator = OmadaSiteCoordinator(
        hass=hass,
        api_client=mock_api_client,
        site_id="site_001",
        site_name="Test Site",
    )

    # Should not raise, just log warning
    await coordinator._merge_gateway_temperature(devices)  # noqa: SLF001

    # Temperature should not be added on error
    assert "temperature" not in devices["AA:BB:CC:DD:EE:FF"]


async def test_merge_gateway_temperature_skips_non_gateways(
    hass: HomeAssistant,
) -> None:
    """Test merging gateway temperature skips non-gateway devices."""
    mock_api_client = MagicMock()
    mock_api_client.get_gateway_info = AsyncMock()

    devices = {
        "AA:BB:CC:DD:EE:FF": {
            "mac": "AA:BB:CC:DD:EE:FF",
            "type": "ap",
            "name": "Access Point 1",
        }
    }

    coordinator = OmadaSiteCoordinator(
        hass=hass,
        api_client=mock_api_client,
        site_id="site_001",
        site_name="Test Site",
    )

    await coordinator._merge_gateway_temperature(devices)  # noqa: SLF001

    # Should not call get_gateway_info for non-gateways
    mock_api_client.get_gateway_info.assert_not_called()
    assert "temperature" not in devices["AA:BB:CC:DD:EE:FF"]


async def test_fetch_site_ssids_success(hass: HomeAssistant) -> None:
    """Test fetching site SSIDs successfully."""
    mock_api_client = MagicMock()
    mock_api_client.get_site_ssids_comprehensive = AsyncMock(
        return_value=[
            {"ssidId": "ssid_001", "ssidName": "HomeWiFi", "broadcast": True},
            {"ssidId": "ssid_002", "ssidName": "GuestWiFi", "broadcast": False},
        ]
    )

    coordinator = OmadaSiteCoordinator(
        hass=hass,
        api_client=mock_api_client,
        site_id="site_001",
        site_name="Test Site",
    )

    ssids = await coordinator._fetch_site_ssids()  # noqa: SLF001

    assert len(ssids) == 2
    assert ssids[0]["ssidName"] == "HomeWiFi"
    assert ssids[1]["ssidName"] == "GuestWiFi"
    mock_api_client.get_site_ssids_comprehensive.assert_called_once_with("site_001")


async def test_fetch_site_ssids_api_error(hass: HomeAssistant) -> None:
    """Test fetching site SSIDs handles API errors gracefully."""
    mock_api_client = MagicMock()
    mock_api_client.get_site_ssids_comprehensive = AsyncMock(
        side_effect=OmadaApiError("API Error")
    )

    coordinator = OmadaSiteCoordinator(
        hass=hass,
        api_client=mock_api_client,
        site_id="site_001",
        site_name="Test Site",
    )

    ssids = await coordinator._fetch_site_ssids()  # noqa: SLF001

    # Should return empty list on error
    assert ssids == []
