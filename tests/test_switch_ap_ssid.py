"""Tests for Omada per-AP SSID switch entities."""

from __future__ import annotations

from unittest.mock import AsyncMock

from homeassistant.exceptions import HomeAssistantError
import pytest

from custom_components.omada_open_api.api import OmadaApiError
from custom_components.omada_open_api.const import DOMAIN
from custom_components.omada_open_api.switch import OmadaApSsidSwitch
from tests.conftest import TEST_SITE_ID, TEST_SITE_NAME

# Sample AP SSID override data
SAMPLE_AP_SSID_OVERRIDE = {
    "ssidId": "ssid_001",
    "ssidEntryId": 1,
    "ssidName": "Corporate WiFi",
    "ssidEnable": True,
    "overrideSsidEnable": True,
}

SAMPLE_AP_MAC = "AA-BB-CC-DD-EE-01"
SAMPLE_AP_NAME = "Office AP"


@pytest.fixture
def mock_coordinator(mock_api_client):
    """Create a mock coordinator."""
    coordinator = AsyncMock()
    coordinator.site_id = TEST_SITE_ID
    coordinator.site_name = TEST_SITE_NAME
    coordinator.api_client = mock_api_client
    coordinator.last_update_success = True
    coordinator.data = {
        "ap_ssid_overrides": {
            SAMPLE_AP_MAC: {
                "ssidOverrides": [SAMPLE_AP_SSID_OVERRIDE],
            }
        }
    }
    return coordinator


async def test_ap_ssid_switch_unique_id(mock_coordinator):
    """Test AP SSID switch unique ID."""
    switch = OmadaApSsidSwitch(
        mock_coordinator,
        SAMPLE_AP_MAC,
        SAMPLE_AP_NAME,
        SAMPLE_AP_SSID_OVERRIDE,
    )
    assert switch.unique_id == f"omada_open_api_{SAMPLE_AP_MAC}_ssid_ssid_001"


async def test_ap_ssid_switch_name(mock_coordinator):
    """Test AP SSID switch name."""
    switch = OmadaApSsidSwitch(
        mock_coordinator,
        SAMPLE_AP_MAC,
        SAMPLE_AP_NAME,
        SAMPLE_AP_SSID_OVERRIDE,
    )
    assert switch.translation_key == "ap_ssid"
    assert switch.translation_placeholders == {"ssid_name": "Corporate WiFi"}


async def test_ap_ssid_switch_device_info(mock_coordinator):
    """Test AP SSID switch links to AP device."""
    switch = OmadaApSsidSwitch(
        mock_coordinator,
        SAMPLE_AP_MAC,
        SAMPLE_AP_NAME,
        SAMPLE_AP_SSID_OVERRIDE,
    )
    device_info = switch.device_info
    assert device_info["identifiers"] == {(DOMAIN, SAMPLE_AP_MAC)}


async def test_ap_ssid_switch_is_on_when_enabled(mock_coordinator):
    """Test AP SSID switch is_on when SSID is enabled."""
    switch = OmadaApSsidSwitch(
        mock_coordinator,
        SAMPLE_AP_MAC,
        SAMPLE_AP_NAME,
        SAMPLE_AP_SSID_OVERRIDE,
    )
    assert switch.is_on is True


async def test_ap_ssid_switch_is_off_when_disabled(mock_coordinator):
    """Test AP SSID switch is_on when SSID is disabled."""
    disabled_ssid = SAMPLE_AP_SSID_OVERRIDE.copy()
    disabled_ssid["ssidEnable"] = False

    switch = OmadaApSsidSwitch(
        mock_coordinator,
        SAMPLE_AP_MAC,
        SAMPLE_AP_NAME,
        disabled_ssid,
    )
    assert switch.is_on is False


async def test_ap_ssid_switch_icon_on(mock_coordinator):
    """Test AP SSID switch icon when on."""
    switch = OmadaApSsidSwitch(
        mock_coordinator,
        SAMPLE_AP_MAC,
        SAMPLE_AP_NAME,
        SAMPLE_AP_SSID_OVERRIDE,
    )
    assert switch.icon == "mdi:wifi"


async def test_ap_ssid_switch_icon_off(mock_coordinator):
    """Test AP SSID switch icon when off."""
    disabled_ssid = SAMPLE_AP_SSID_OVERRIDE.copy()
    disabled_ssid["ssidEnable"] = False

    switch = OmadaApSsidSwitch(
        mock_coordinator,
        SAMPLE_AP_MAC,
        SAMPLE_AP_NAME,
        disabled_ssid,
    )
    assert switch.icon == "mdi:wifi-off"


async def test_ap_ssid_switch_available(mock_coordinator):
    """Test AP SSID switch availability."""
    switch = OmadaApSsidSwitch(
        mock_coordinator,
        SAMPLE_AP_MAC,
        SAMPLE_AP_NAME,
        SAMPLE_AP_SSID_OVERRIDE,
    )
    assert switch.available is True


async def test_ap_ssid_switch_unavailable(mock_coordinator):
    """Test AP SSID switch unavailable when coordinator fails."""
    mock_coordinator.last_update_success = False
    switch = OmadaApSsidSwitch(
        mock_coordinator,
        SAMPLE_AP_MAC,
        SAMPLE_AP_NAME,
        SAMPLE_AP_SSID_OVERRIDE,
    )
    assert switch.available is False


async def test_ap_ssid_switch_async_update(mock_coordinator):
    """Test AP SSID switch async_update refreshes from coordinator."""
    switch = OmadaApSsidSwitch(
        mock_coordinator,
        SAMPLE_AP_MAC,
        SAMPLE_AP_NAME,
        SAMPLE_AP_SSID_OVERRIDE,
    )

    # Initially enabled
    assert switch.is_on is True

    # Update coordinator data to show disabled
    updated_override = SAMPLE_AP_SSID_OVERRIDE.copy()
    updated_override["ssidEnable"] = False
    mock_coordinator.data = {
        "ap_ssid_overrides": {
            SAMPLE_AP_MAC: {
                "ssidOverrides": [updated_override],
            }
        }
    }

    # Call async_update
    await switch.async_update()

    # Should now be disabled
    assert switch.is_on is False


async def test_ap_ssid_switch_turn_on(mock_coordinator, mock_api_client):
    """Test turning on AP SSID switch."""
    switch = OmadaApSsidSwitch(
        mock_coordinator,
        SAMPLE_AP_MAC,
        SAMPLE_AP_NAME,
        SAMPLE_AP_SSID_OVERRIDE,
    )

    await switch.async_turn_on()

    mock_api_client.update_ap_ssid_override.assert_called_once_with(
        TEST_SITE_ID,
        SAMPLE_AP_MAC,
        1,  # ssidEntryId
        "Corporate WiFi",  # ssidName
        ssid_enable=True,
    )
    mock_coordinator.async_request_refresh.assert_called_once()


async def test_ap_ssid_switch_turn_off(mock_coordinator, mock_api_client):
    """Test turning off AP SSID switch."""
    switch = OmadaApSsidSwitch(
        mock_coordinator,
        SAMPLE_AP_MAC,
        SAMPLE_AP_NAME,
        SAMPLE_AP_SSID_OVERRIDE,
    )

    await switch.async_turn_off()

    mock_api_client.update_ap_ssid_override.assert_called_once_with(
        TEST_SITE_ID,
        SAMPLE_AP_MAC,
        1,  # ssidEntryId
        "Corporate WiFi",  # ssidName
        ssid_enable=False,
    )
    mock_coordinator.async_request_refresh.assert_called_once()


async def test_ap_ssid_switch_turn_on_permission_error(
    mock_coordinator, mock_api_client
):
    """Test AP SSID switch raises HomeAssistantError on permission error."""
    mock_api_client.update_ap_ssid_override = AsyncMock(
        side_effect=OmadaApiError("Permission denied", error_code=-1005)
    )

    switch = OmadaApSsidSwitch(
        mock_coordinator,
        SAMPLE_AP_MAC,
        SAMPLE_AP_NAME,
        SAMPLE_AP_SSID_OVERRIDE,
    )

    with pytest.raises(HomeAssistantError, match="Permission denied"):
        await switch.async_turn_on()


async def test_ap_ssid_switch_turn_off_permission_error(
    mock_coordinator, mock_api_client
):
    """Test AP SSID switch raises HomeAssistantError on permission error turn off."""
    mock_api_client.update_ap_ssid_override = AsyncMock(
        side_effect=OmadaApiError("Permission denied", error_code=-1007)
    )

    switch = OmadaApSsidSwitch(
        mock_coordinator,
        SAMPLE_AP_MAC,
        SAMPLE_AP_NAME,
        SAMPLE_AP_SSID_OVERRIDE,
    )

    with pytest.raises(HomeAssistantError, match="Permission denied"):
        await switch.async_turn_off()


async def test_ap_ssid_switch_turn_on_api_error(mock_coordinator, mock_api_client):
    """Test AP SSID switch raises HomeAssistantError on API error."""
    mock_api_client.update_ap_ssid_override = AsyncMock(
        side_effect=OmadaApiError("Unexpected error", error_code=-9999)
    )

    switch = OmadaApSsidSwitch(
        mock_coordinator,
        SAMPLE_AP_MAC,
        SAMPLE_AP_NAME,
        SAMPLE_AP_SSID_OVERRIDE,
    )

    with pytest.raises(HomeAssistantError):
        await switch.async_turn_on()


async def test_ap_ssid_switch_turn_off_api_error(mock_coordinator, mock_api_client):
    """Test AP SSID switch raises HomeAssistantError on API error turn off."""
    mock_api_client.update_ap_ssid_override = AsyncMock(
        side_effect=OmadaApiError("Unexpected error", error_code=-9999)
    )

    switch = OmadaApSsidSwitch(
        mock_coordinator,
        SAMPLE_AP_MAC,
        SAMPLE_AP_NAME,
        SAMPLE_AP_SSID_OVERRIDE,
    )

    with pytest.raises(HomeAssistantError):
        await switch.async_turn_off()
