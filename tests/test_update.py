"""Tests for Omada update entities (firmware)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock, MagicMock, patch

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

from custom_components.omada_open_api.api import OmadaApiError
from custom_components.omada_open_api.const import DOMAIN
from custom_components.omada_open_api.coordinator import OmadaSiteCoordinator
from custom_components.omada_open_api.devices import process_device
from custom_components.omada_open_api.update import OmadaDeviceUpdateEntity

from .conftest import SAMPLE_DEVICE_AP, TEST_SITE_ID, TEST_SITE_NAME

AP_MAC = SAMPLE_DEVICE_AP["mac"]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_coordinator(
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
    processed = {}
    if devices:
        for mac, raw in devices.items():
            processed[mac] = process_device(raw)
    coordinator.data = {
        "devices": processed,
        "poe_budget": {},
        "poe_ports": {},
        "site_id": TEST_SITE_ID,
        "site_name": TEST_SITE_NAME,
    }
    coordinator.api_client.get_firmware_info = AsyncMock(
        return_value={
            "curFwVer": "1.0.0",
            "lastFwVer": "1.1.0",
            "fwReleaseLog": "Bug fixes",
        }
    )
    coordinator.api_client.start_online_upgrade = AsyncMock(return_value={})
    return coordinator


def _create_update_entity(
    hass: HomeAssistant,
    device_mac: str = AP_MAC,
    devices: dict[str, dict[str, Any]] | None = None,
) -> OmadaDeviceUpdateEntity:
    """Create an OmadaDeviceUpdateEntity."""
    if devices is None:
        devices = {device_mac: SAMPLE_DEVICE_AP}
    coordinator = _build_coordinator(hass, devices)
    return OmadaDeviceUpdateEntity(coordinator=coordinator, device_mac=device_mac)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


async def test_update_unique_id(hass: HomeAssistant) -> None:
    """Test update entity unique ID format."""
    entity = _create_update_entity(hass)
    assert entity.unique_id == f"omada_open_api_{AP_MAC}_firmware"


async def test_update_name(hass: HomeAssistant) -> None:
    """Test update entity name includes device name."""
    entity = _create_update_entity(hass)
    assert "Firmware" in entity.name


async def test_update_installed_version(hass: HomeAssistant) -> None:
    """Test installed version comes from device data."""
    entity = _create_update_entity(hass)
    assert entity.installed_version is not None


async def test_update_installed_version_missing(hass: HomeAssistant) -> None:
    """Test installed version returns None when device missing."""
    entity = _create_update_entity(hass)
    entity.coordinator.data["devices"] = {}
    assert entity.installed_version is None


async def test_update_available(hass: HomeAssistant) -> None:
    """Test entity available when device exists."""
    entity = _create_update_entity(hass)
    assert entity.available is True


async def test_update_unavailable_missing_device(hass: HomeAssistant) -> None:
    """Test entity unavailable when device is missing."""
    entity = _create_update_entity(hass)
    entity.coordinator.data["devices"] = {}
    assert entity.available is False


async def test_update_unavailable_coordinator_failure(hass: HomeAssistant) -> None:
    """Test entity unavailable on coordinator failure."""
    entity = _create_update_entity(hass)
    entity.coordinator.last_update_success = False
    assert entity.available is False


async def test_update_latest_version_after_update(hass: HomeAssistant) -> None:
    """Test latest_version is populated after async_update."""
    entity = _create_update_entity(hass)
    assert entity.latest_version is None

    await entity.async_update()
    assert entity.latest_version == "1.1.0"


async def test_update_release_summary(hass: HomeAssistant) -> None:
    """Test release_summary is populated after async_update."""
    entity = _create_update_entity(hass)
    await entity.async_update()
    assert entity.release_summary == "Bug fixes"


async def test_update_firmware_check_error(hass: HomeAssistant) -> None:
    """Test graceful handling of firmware check errors."""
    entity = _create_update_entity(hass)
    entity.coordinator.api_client.get_firmware_info.side_effect = OmadaApiError("fail")
    await entity.async_update()
    # Falls back to installed version.
    assert entity.latest_version == entity.installed_version


async def test_update_install(hass: HomeAssistant) -> None:
    """Test installing firmware calls the API."""
    entity = _create_update_entity(hass)
    with patch.object(
        entity.coordinator, "async_request_refresh", new=AsyncMock()
    ) as mock_refresh:
        await entity.async_install(version=None, backup=False)
    entity.coordinator.api_client.start_online_upgrade.assert_called_once_with(
        TEST_SITE_ID, AP_MAC
    )
    mock_refresh.assert_awaited_once()


async def test_update_install_error(hass: HomeAssistant) -> None:
    """Test install handles API error gracefully."""
    entity = _create_update_entity(hass)
    entity.coordinator.api_client.start_online_upgrade.side_effect = OmadaApiError(
        "fail"
    )
    # Should not raise.
    await entity.async_install(version=None, backup=False)


async def test_update_device_info(hass: HomeAssistant) -> None:
    """Test update entity device info."""
    entity = _create_update_entity(hass)
    info = entity.device_info
    assert info is not None
    assert info["identifiers"] == {(DOMAIN, AP_MAC)}
