"""Tests for SSID switches."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock

from custom_components.omada_open_api.api import OmadaApiError
from custom_components.omada_open_api.const import DOMAIN
from custom_components.omada_open_api.coordinator import OmadaSiteCoordinator
from custom_components.omada_open_api.switch import OmadaSsidSwitch

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant


def _create_ssid_switch(
    hass: HomeAssistant,
    ssid_data: dict,
    coordinator_data: dict | None = None,
) -> OmadaSsidSwitch:
    """Helper to create an SSID switch for testing."""
    mock_api_client = MagicMock()
    mock_api_client.api_url = "https://test.example.com"
    mock_api_client.get_ssid_detail = AsyncMock(
        return_value={
            "ssidId": ssid_data.get("ssidId"),
            "wlanId": ssid_data.get("wlanId"),
            "name": ssid_data.get("ssidName"),
            "ssidName": ssid_data.get("ssidName"),
            "broadcast": ssid_data.get("broadcast", True),
            "band": 7,
            "vlanEnable": False,
            "security": {"mode": "wpa2-personal"},
            "enable11r": False,
            "guestNetEnable": False,
            "pmfMode": "disabled",
            "mloEnable": False,
        }
    )
    mock_api_client.update_ssid_basic_config = AsyncMock()

    coordinator = MagicMock(spec=OmadaSiteCoordinator)
    coordinator.hass = hass
    coordinator.site_id = "site_001"
    coordinator.site_name = "Test Site"
    coordinator.api_client = mock_api_client
    coordinator.data = coordinator_data or {
        "ssids": [ssid_data],
        "site_id": "site_001",
        "site_name": "Test Site",
    }
    coordinator.last_update_success = True
    coordinator.async_request_refresh = AsyncMock()

    return OmadaSsidSwitch(
        coordinator=coordinator,
        site_device_id="site_site_001",
        ssid_data=ssid_data,
    )


async def test_ssid_switch_unique_id(hass: HomeAssistant) -> None:
    """Test SSID switch has correct unique ID."""
    ssid_data = {
        "ssidId": "ssid_001",
        "wlanId": "wlan_001",
        "ssidName": "HomeWiFi",
        "broadcast": True,
    }
    switch = _create_ssid_switch(hass, ssid_data)
    assert switch.unique_id == "omada_open_api_site_001_ssid_ssid_001"


async def test_ssid_switch_device_info(hass: HomeAssistant) -> None:
    """Test SSID switch links to Site device."""
    ssid_data = {
        "ssidId": "ssid_001",
        "wlanId": "wlan_001",
        "ssidName": "HomeWiFi",
        "broadcast": True,
    }
    switch = _create_ssid_switch(hass, ssid_data)
    device_info = switch.device_info
    assert (DOMAIN, "site_site_001") in device_info.get("identifiers", set())


async def test_ssid_switch_is_on_when_broadcast_enabled(hass: HomeAssistant) -> None:
    """Test SSID switch reports on when broadcast is enabled."""
    ssid_data = {
        "ssidId": "ssid_001",
        "wlanId": "wlan_001",
        "ssidName": "HomeWiFi",
        "broadcast": True,
    }
    switch = _create_ssid_switch(hass, ssid_data)
    assert switch.is_on is True


async def test_ssid_switch_is_off_when_broadcast_disabled(hass: HomeAssistant) -> None:
    """Test SSID switch reports off when broadcast is disabled."""
    ssid_data = {
        "ssidId": "ssid_001",
        "wlanId": "wlan_001",
        "ssidName": "HomeWiFi",
        "broadcast": False,
    }
    switch = _create_ssid_switch(hass, ssid_data)
    assert switch.is_on is False


async def test_ssid_switch_icon_on(hass: HomeAssistant) -> None:
    """Test SSID switch shows wifi icon when on."""
    ssid_data = {
        "ssidId": "ssid_001",
        "wlanId": "wlan_001",
        "ssidName": "HomeWiFi",
        "broadcast": True,
    }
    switch = _create_ssid_switch(hass, ssid_data)
    assert switch.icon == "mdi:wifi"


async def test_ssid_switch_icon_off(hass: HomeAssistant) -> None:
    """Test SSID switch shows wifi-off icon when off."""
    ssid_data = {
        "ssidId": "ssid_001",
        "wlanId": "wlan_001",
        "ssidName": "HomeWiFi",
        "broadcast": False,
    }
    switch = _create_ssid_switch(hass, ssid_data)
    assert switch.icon == "mdi:wifi-off"


async def test_ssid_switch_turn_on(hass: HomeAssistant) -> None:
    """Test turning on SSID switch enables broadcast."""
    ssid_data = {
        "ssidId": "ssid_001",
        "wlanId": "wlan_001",
        "ssidName": "HomeWiFi",
        "broadcast": False,
    }
    switch = _create_ssid_switch(hass, ssid_data)

    await switch.async_turn_on()

    # Verify update_ssid_basic_config was called with complete config
    switch.coordinator.api_client.update_ssid_basic_config.assert_called_once()
    call_args = switch.coordinator.api_client.update_ssid_basic_config.call_args
    assert call_args[0][0] == "site_001"  # site_id
    assert call_args[0][1] == "wlan_001"  # wlan_id
    assert call_args[0][2] == "ssid_001"  # ssid_id
    config = call_args[0][3]
    assert config["broadcast"] is True
    # Verify all required fields are preserved
    assert config["vlanEnable"] is False
    assert config["security"]["mode"] == "wpa2-personal"
    assert config["enable11r"] is False
    assert config["guestNetEnable"] is False
    assert config["pmfMode"] == "disabled"
    assert config["mloEnable"] is False

    assert switch.is_on is True


async def test_ssid_switch_turn_off(hass: HomeAssistant) -> None:
    """Test turning off SSID switch disables broadcast."""
    ssid_data = {
        "ssidId": "ssid_001",
        "wlanId": "wlan_001",
        "ssidName": "HomeWiFi",
        "broadcast": True,
    }
    switch = _create_ssid_switch(hass, ssid_data)

    await switch.async_turn_off()

    # Verify update_ssid_basic_config was called with complete config
    switch.coordinator.api_client.update_ssid_basic_config.assert_called_once()
    call_args = switch.coordinator.api_client.update_ssid_basic_config.call_args
    assert call_args[0][0] == "site_001"  # site_id
    assert call_args[0][1] == "wlan_001"  # wlan_id
    assert call_args[0][2] == "ssid_001"  # ssid_id
    config = call_args[0][3]
    assert config["broadcast"] is False
    # Verify all required fields are preserved
    assert config["vlanEnable"] is False
    assert config["security"]["mode"] == "wpa2-personal"
    assert config["enable11r"] is False
    assert config["guestNetEnable"] is False
    assert config["pmfMode"] == "disabled"
    assert config["mloEnable"] is False

    assert switch.is_on is False


async def test_ssid_switch_turn_on_permission_error(hass: HomeAssistant) -> None:
    """Test turning on SSID with permission error handles gracefully."""
    ssid_data = {
        "ssidId": "ssid_001",
        "wlanId": "wlan_001",
        "ssidName": "HomeWiFi",
        "broadcast": False,
    }
    switch = _create_ssid_switch(hass, ssid_data)
    switch.coordinator.api_client.update_ssid_basic_config = AsyncMock(
        side_effect=OmadaApiError("Permission denied", error_code=-1007)
    )

    # Should not raise, just log warning
    await switch.async_turn_on()

    # State should not change on error
    assert switch.is_on is False


async def test_ssid_switch_turn_off_api_error(hass: HomeAssistant) -> None:
    """Test turning off SSID with API error handles gracefully."""
    ssid_data = {
        "ssidId": "ssid_001",
        "wlanId": "wlan_001",
        "ssidName": "HomeWiFi",
        "broadcast": True,
    }
    switch = _create_ssid_switch(hass, ssid_data)
    switch.coordinator.api_client.update_ssid_basic_config = AsyncMock(
        side_effect=OmadaApiError("API Error")
    )

    # Should not raise, just log exception
    await switch.async_turn_off()

    # State should not change on error
    assert switch.is_on is True


async def test_ssid_switch_async_update(hass: HomeAssistant) -> None:
    """Test SSID switch updates state from coordinator data."""
    ssid_data = {
        "ssidId": "ssid_001",
        "wlanId": "wlan_001",
        "ssidName": "HomeWiFi",
        "broadcast": True,
    }
    switch = _create_ssid_switch(hass, ssid_data)

    # Change coordinator data
    switch.coordinator.data = {
        "ssids": [
            {
                "ssidId": "ssid_001",
                "wlanId": "wlan_001",
                "ssidName": "HomeWiFi",
                "broadcast": False,  # Changed to False
            }
        ],
        "site_id": "site_001",
        "site_name": "Test Site",
    }

    await switch.async_update()

    # State should reflect coordinator data
    assert switch.is_on is False


async def test_ssid_switch_available(hass: HomeAssistant) -> None:
    """Test SSID switch availability based on coordinator."""
    ssid_data = {
        "ssidId": "ssid_001",
        "wlanId": "wlan_001",
        "ssidName": "HomeWiFi",
        "broadcast": True,
    }
    switch = _create_ssid_switch(hass, ssid_data)

    switch.coordinator.last_update_success = True
    assert switch.available is True

    switch.coordinator.last_update_success = False
    assert switch.available is False
