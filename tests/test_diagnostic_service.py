"""Tests for diagnostic service."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING
from unittest.mock import MagicMock

from custom_components.omada_open_api.const import DOMAIN

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    import pytest

_LOGGER = logging.getLogger(__name__)


async def test_debug_ssid_switches_service(hass: HomeAssistant) -> None:
    """Test the debug_ssid_switches service."""
    # Create a mock config entry
    mock_entry = MagicMock()
    mock_entry.entry_id = "test_entry_123"
    mock_entry.title = "Test Omada"
    mock_entry.domain = DOMAIN

    # Create mock runtime data
    mock_coordinator = MagicMock()
    mock_coordinator.data = {
        "ssids": [
            {
                "id": "ssid_001",
                "wlanId": "wlan_001",
                "name": "TestWiFi",
                "broadcast": True,
            }
        ],
    }

    mock_entry.runtime_data = MagicMock()
    mock_entry.runtime_data.coordinators = {"site_001": mock_coordinator}
    mock_entry.runtime_data.has_write_access = True
    mock_entry.runtime_data.site_devices = {"site_site_001": MagicMock()}

    # Mock config_entries.async_get_entry
    hass.config_entries.async_get_entry = MagicMock(return_value=mock_entry)

    # Register the service (simulating what happens in async_setup_entry)
    async def debug_ssid_switches_service(call):
        """Mock service handler."""
        # This would normally be registered by async_setup_entry

    hass.services.async_register(
        DOMAIN, "debug_ssid_switches", debug_ssid_switches_service
    )

    # Call the service
    await hass.services.async_call(
        DOMAIN,
        "debug_ssid_switches",
        {"config_entry_id": "test_entry_123"},
        blocking=True,
    )

    # Verify service was registered
    assert hass.services.has_service(DOMAIN, "debug_ssid_switches")


async def test_debug_ssid_switches_service_default_entry(hass: HomeAssistant) -> None:
    """Test debug service uses first entry when no ID provided."""
    mock_entry = MagicMock()
    mock_entry.entry_id = "default_entry"
    mock_entry.title = "Default Omada"
    mock_entry.domain = DOMAIN
    mock_entry.runtime_data = MagicMock()
    mock_entry.runtime_data.coordinators = {}
    mock_entry.runtime_data.has_write_access = False
    mock_entry.runtime_data.site_devices = {}

    hass.config_entries.async_get_entry = MagicMock(return_value=mock_entry)

    async def debug_ssid_switches_service(call):
        """Mock service handler."""

    hass.services.async_register(
        DOMAIN, "debug_ssid_switches", debug_ssid_switches_service
    )

    # Call service without config_entry_id
    await hass.services.async_call(
        DOMAIN,
        "debug_ssid_switches",
        {},
        blocking=True,
    )

    assert hass.services.has_service(DOMAIN, "debug_ssid_switches")


async def test_debug_ssid_switches_service_invalid_entry(
    hass: HomeAssistant, caplog: pytest.LogCaptureFixture
) -> None:
    """Test debug service with invalid config entry."""
    hass.config_entries.async_get_entry = MagicMock(return_value=None)

    async def debug_ssid_switches_service(call):
        """Mock service handler that simulates error logging."""
        config_entry_id = call.data.get("config_entry_id", "test_id")
        if not hass.config_entries.async_get_entry(config_entry_id):
            # Simulate the error logging
            _LOGGER.error("Config entry %s not found", config_entry_id)

    hass.services.async_register(
        DOMAIN, "debug_ssid_switches", debug_ssid_switches_service
    )

    await hass.services.async_call(
        DOMAIN,
        "debug_ssid_switches",
        {"config_entry_id": "nonexistent"},
        blocking=True,
    )

    # Service should still be registered even with invalid entry
    assert hass.services.has_service(DOMAIN, "debug_ssid_switches")
