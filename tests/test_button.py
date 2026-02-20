"""Tests for Omada button platform."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock, MagicMock

import pytest

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

from custom_components.omada_open_api.api import OmadaApiError
from custom_components.omada_open_api.button import (
    OmadaClientReconnectButton,
    OmadaDeviceRebootButton,
    OmadaWlanOptimizationButton,
)
from custom_components.omada_open_api.clients import process_client
from custom_components.omada_open_api.coordinator import (
    OmadaClientCoordinator,
    OmadaSiteCoordinator,
)
from custom_components.omada_open_api.devices import process_device

from .conftest import (
    SAMPLE_CLIENT_WIRELESS,
    SAMPLE_DEVICE_AP,
    SAMPLE_DEVICE_GATEWAY,
    SAMPLE_DEVICE_SWITCH,
    TEST_SITE_ID,
    TEST_SITE_NAME,
)

AP_MAC = "AA-BB-CC-DD-EE-01"
SWITCH_MAC = "AA-BB-CC-DD-EE-02"
GATEWAY_MAC = "AA-BB-CC-DD-EE-03"
WIRELESS_MAC = "11-22-33-44-55-AA"
WIRED_MAC = "11-22-33-44-55-BB"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_site_coordinator(
    hass: HomeAssistant,
    devices: dict[str, dict[str, Any]] | None = None,
) -> OmadaSiteCoordinator:
    """Create a site coordinator with mock device data."""
    coordinator = OmadaSiteCoordinator(
        hass=hass,
        api_client=MagicMock(),
        site_id=TEST_SITE_ID,
        site_name=TEST_SITE_NAME,
    )
    coordinator.data = {
        "devices": devices or {},
        "poe_budget": {},
        "poe_ports": {},
        "site_id": TEST_SITE_ID,
        "site_name": TEST_SITE_NAME,
    }
    # Make api_client methods async.
    coordinator.api_client.reboot_device = AsyncMock()
    coordinator.api_client.start_wlan_optimization = AsyncMock()
    return coordinator


def _build_client_coordinator(
    hass: HomeAssistant,
    clients: dict[str, dict[str, Any]] | None = None,
) -> OmadaClientCoordinator:
    """Create a client coordinator with mock data."""
    coordinator = OmadaClientCoordinator(
        hass=hass,
        api_client=MagicMock(),
        site_id=TEST_SITE_ID,
        site_name=TEST_SITE_NAME,
        selected_client_macs=[WIRELESS_MAC, WIRED_MAC],
    )
    coordinator.data = clients or {}
    coordinator.api_client.reconnect_client = AsyncMock()
    return coordinator


# ===========================================================================
# OmadaDeviceRebootButton tests
# ===========================================================================


async def test_reboot_button_unique_id(hass: HomeAssistant) -> None:
    """Test reboot button unique ID format."""
    data = process_device(SAMPLE_DEVICE_AP)
    coordinator = _build_site_coordinator(hass, {AP_MAC: data})
    button = OmadaDeviceRebootButton(coordinator, AP_MAC)
    assert button.unique_id == f"omada_open_api_{AP_MAC}_reboot"


async def test_reboot_button_name(hass: HomeAssistant) -> None:
    """Test reboot button name includes device name."""
    data = process_device(SAMPLE_DEVICE_AP)
    coordinator = _build_site_coordinator(hass, {AP_MAC: data})
    button = OmadaDeviceRebootButton(coordinator, AP_MAC)
    assert button.name == "Office AP Reboot"


async def test_reboot_button_device_info(hass: HomeAssistant) -> None:
    """Test reboot button links to correct device."""
    data = process_device(SAMPLE_DEVICE_AP)
    coordinator = _build_site_coordinator(hass, {AP_MAC: data})
    button = OmadaDeviceRebootButton(coordinator, AP_MAC)
    info = button.device_info
    assert info is not None
    assert info["identifiers"] == {("omada_open_api", AP_MAC)}


async def test_reboot_button_device_info_missing(hass: HomeAssistant) -> None:
    """Test reboot button device info when device missing."""
    coordinator = _build_site_coordinator(hass, {})
    button = OmadaDeviceRebootButton(coordinator, AP_MAC)
    assert button.device_info is None


async def test_reboot_button_available(hass: HomeAssistant) -> None:
    """Test reboot button available when device exists."""
    data = process_device(SAMPLE_DEVICE_AP)
    coordinator = _build_site_coordinator(hass, {AP_MAC: data})
    button = OmadaDeviceRebootButton(coordinator, AP_MAC)
    assert button.available is True


async def test_reboot_button_unavailable_missing(hass: HomeAssistant) -> None:
    """Test reboot button unavailable when device missing."""
    coordinator = _build_site_coordinator(hass, {})
    button = OmadaDeviceRebootButton(coordinator, AP_MAC)
    assert button.available is False


async def test_reboot_button_unavailable_coordinator_failure(
    hass: HomeAssistant,
) -> None:
    """Test reboot button unavailable on coordinator failure."""
    data = process_device(SAMPLE_DEVICE_AP)
    coordinator = _build_site_coordinator(hass, {AP_MAC: data})
    button = OmadaDeviceRebootButton(coordinator, AP_MAC)
    coordinator.last_update_success = False
    assert button.available is False


async def test_reboot_button_press(hass: HomeAssistant) -> None:
    """Test pressing the reboot button calls the API."""
    data = process_device(SAMPLE_DEVICE_AP)
    coordinator = _build_site_coordinator(hass, {AP_MAC: data})
    button = OmadaDeviceRebootButton(coordinator, AP_MAC)
    await button.async_press()
    coordinator.api_client.reboot_device.assert_called_once_with(TEST_SITE_ID, AP_MAC)


async def test_reboot_button_press_api_error(hass: HomeAssistant) -> None:
    """Test reboot button re-raises API errors."""
    data = process_device(SAMPLE_DEVICE_AP)
    coordinator = _build_site_coordinator(hass, {AP_MAC: data})
    button = OmadaDeviceRebootButton(coordinator, AP_MAC)
    coordinator.api_client.reboot_device.side_effect = OmadaApiError("fail")
    with pytest.raises(OmadaApiError):
        await button.async_press()


async def test_reboot_button_switch(hass: HomeAssistant) -> None:
    """Test reboot button works for a switch device."""
    data = process_device(SAMPLE_DEVICE_SWITCH)
    coordinator = _build_site_coordinator(hass, {SWITCH_MAC: data})
    button = OmadaDeviceRebootButton(coordinator, SWITCH_MAC)
    assert button.name == "Core Switch Reboot"
    await button.async_press()
    coordinator.api_client.reboot_device.assert_called_once_with(
        TEST_SITE_ID, SWITCH_MAC
    )


async def test_reboot_button_gateway(hass: HomeAssistant) -> None:
    """Test reboot button works for a gateway device."""
    data = process_device(SAMPLE_DEVICE_GATEWAY)
    coordinator = _build_site_coordinator(hass, {GATEWAY_MAC: data})
    button = OmadaDeviceRebootButton(coordinator, GATEWAY_MAC)
    assert button.name == "Main Gateway Reboot"


# ===========================================================================
# OmadaClientReconnectButton tests
# ===========================================================================


async def test_reconnect_button_unique_id(hass: HomeAssistant) -> None:
    """Test reconnect button unique ID format."""
    data = process_client(SAMPLE_CLIENT_WIRELESS)
    coordinator = _build_client_coordinator(hass, {WIRELESS_MAC: data})
    button = OmadaClientReconnectButton(coordinator, WIRELESS_MAC)
    assert button.unique_id == f"omada_open_api_{WIRELESS_MAC}_reconnect"


async def test_reconnect_button_name(hass: HomeAssistant) -> None:
    """Test reconnect button name includes client name."""
    data = process_client(SAMPLE_CLIENT_WIRELESS)
    coordinator = _build_client_coordinator(hass, {WIRELESS_MAC: data})
    button = OmadaClientReconnectButton(coordinator, WIRELESS_MAC)
    assert button.name == "Phone Reconnect"


async def test_reconnect_button_available(hass: HomeAssistant) -> None:
    """Test reconnect button available when client is active."""
    data = process_client(SAMPLE_CLIENT_WIRELESS)
    coordinator = _build_client_coordinator(hass, {WIRELESS_MAC: data})
    button = OmadaClientReconnectButton(coordinator, WIRELESS_MAC)
    assert button.available is True


async def test_reconnect_button_unavailable_inactive(
    hass: HomeAssistant,
) -> None:
    """Test reconnect button unavailable when client inactive."""
    raw = dict(SAMPLE_CLIENT_WIRELESS)
    raw["active"] = False
    data = process_client(raw)
    coordinator = _build_client_coordinator(hass, {WIRELESS_MAC: data})
    button = OmadaClientReconnectButton(coordinator, WIRELESS_MAC)
    assert button.available is False


async def test_reconnect_button_unavailable_missing(
    hass: HomeAssistant,
) -> None:
    """Test reconnect button unavailable when client missing."""
    coordinator = _build_client_coordinator(hass, {})
    button = OmadaClientReconnectButton(coordinator, WIRELESS_MAC)
    assert button.available is False


async def test_reconnect_button_press(hass: HomeAssistant) -> None:
    """Test pressing the reconnect button calls the API."""
    data = process_client(SAMPLE_CLIENT_WIRELESS)
    coordinator = _build_client_coordinator(hass, {WIRELESS_MAC: data})
    button = OmadaClientReconnectButton(coordinator, WIRELESS_MAC)
    await button.async_press()
    coordinator.api_client.reconnect_client.assert_called_once_with(
        TEST_SITE_ID, WIRELESS_MAC
    )


async def test_reconnect_button_press_api_error(hass: HomeAssistant) -> None:
    """Test reconnect button re-raises API errors."""
    data = process_client(SAMPLE_CLIENT_WIRELESS)
    coordinator = _build_client_coordinator(hass, {WIRELESS_MAC: data})
    button = OmadaClientReconnectButton(coordinator, WIRELESS_MAC)
    coordinator.api_client.reconnect_client.side_effect = OmadaApiError("fail")
    with pytest.raises(OmadaApiError):
        await button.async_press()


async def test_reconnect_button_device_info(hass: HomeAssistant) -> None:
    """Test reconnect button device info."""
    data = process_client(SAMPLE_CLIENT_WIRELESS)
    coordinator = _build_client_coordinator(hass, {WIRELESS_MAC: data})
    button = OmadaClientReconnectButton(coordinator, WIRELESS_MAC)
    info = button.device_info
    assert info is not None
    assert info["identifiers"] == {("omada_open_api", f"client_{WIRELESS_MAC}")}


# ===========================================================================
# OmadaWlanOptimizationButton tests
# ===========================================================================


async def test_wlan_button_unique_id(hass: HomeAssistant) -> None:
    """Test WLAN optimization button unique ID."""
    coordinator = _build_site_coordinator(hass)
    button = OmadaWlanOptimizationButton(coordinator)
    assert button.unique_id == f"omada_open_api_{TEST_SITE_ID}_wlan_optimization"


async def test_wlan_button_name(hass: HomeAssistant) -> None:
    """Test WLAN optimization button name."""
    coordinator = _build_site_coordinator(hass)
    button = OmadaWlanOptimizationButton(coordinator)
    assert button.name == f"{TEST_SITE_NAME} WLAN Optimization"


async def test_wlan_button_available(hass: HomeAssistant) -> None:
    """Test WLAN optimization button available."""
    coordinator = _build_site_coordinator(hass)
    button = OmadaWlanOptimizationButton(coordinator)
    assert button.available is True


async def test_wlan_button_unavailable(hass: HomeAssistant) -> None:
    """Test WLAN optimization button unavailable on coordinator failure."""
    coordinator = _build_site_coordinator(hass)
    coordinator.last_update_success = False
    button = OmadaWlanOptimizationButton(coordinator)
    assert button.available is False


async def test_wlan_button_press(hass: HomeAssistant) -> None:
    """Test pressing the WLAN optimization button calls the API."""
    coordinator = _build_site_coordinator(hass)
    button = OmadaWlanOptimizationButton(coordinator)
    await button.async_press()
    coordinator.api_client.start_wlan_optimization.assert_called_once_with(TEST_SITE_ID)


async def test_wlan_button_press_api_error(hass: HomeAssistant) -> None:
    """Test WLAN optimization button re-raises API errors."""
    coordinator = _build_site_coordinator(hass)
    button = OmadaWlanOptimizationButton(coordinator)
    coordinator.api_client.start_wlan_optimization.side_effect = OmadaApiError("fail")
    with pytest.raises(OmadaApiError):
        await button.async_press()
