"""Tests for Omada update entities (firmware)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

from homeassistant.exceptions import HomeAssistantError

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
    firmware_info: dict[str, dict[str, Any]] | None = None,
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
        "firmware_info": firmware_info or {},
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
    firmware_info: dict[str, dict[str, Any]] | None = None,
) -> OmadaDeviceUpdateEntity:
    """Create an OmadaDeviceUpdateEntity."""
    if devices is None:
        devices = {device_mac: SAMPLE_DEVICE_AP}
    coordinator = _build_coordinator(hass, devices, firmware_info)
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
    assert entity.translation_key == "firmware"


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


async def test_update_latest_version_from_coordinator(hass: HomeAssistant) -> None:
    """Test latest_version is read from coordinator firmware_info."""
    firmware_info = {
        AP_MAC: {
            "curFwVer": "1.0.0",
            "lastFwVer": "1.1.0",
            "fwReleaseLog": "Bug fixes",
        }
    }
    entity = _create_update_entity(hass, firmware_info=firmware_info)
    assert entity.latest_version == "1.1.0"


async def test_update_latest_version_fallback(hass: HomeAssistant) -> None:
    """Test latest_version falls back to installed when no firmware_info."""
    entity = _create_update_entity(hass)
    # No firmware_info provided, should fall back to installed_version.
    assert entity.latest_version == entity.installed_version


async def test_update_release_summary(hass: HomeAssistant) -> None:
    """Test release_summary is read from coordinator firmware_info."""
    firmware_info = {
        AP_MAC: {
            "curFwVer": "1.0.0",
            "lastFwVer": "1.1.0",
            "fwReleaseLog": "Bug fixes",
        }
    }
    entity = _create_update_entity(hass, firmware_info=firmware_info)
    assert entity.release_summary == "Bug fixes"


async def test_update_release_summary_none(hass: HomeAssistant) -> None:
    """Test release_summary is None when no firmware_info."""
    entity = _create_update_entity(hass)
    assert entity.release_summary is None


async def test_update_install(hass: HomeAssistant) -> None:
    """Test installing firmware calls the API and activates fast polling."""
    entity = _create_update_entity(hass)
    with patch.object(
        entity.coordinator, "async_request_refresh", new=AsyncMock()
    ) as mock_refresh:
        await entity.async_install(version=None, backup=False)
    entity.coordinator.api_client.start_online_upgrade.assert_called_once_with(
        TEST_SITE_ID, AP_MAC
    )
    # Fast polling should be activated immediately after install.
    assert entity.coordinator._upgrade_active is True  # noqa: SLF001
    mock_refresh.assert_awaited_once()


async def test_update_install_error(hass: HomeAssistant) -> None:
    """Test install raises HomeAssistantError on API error."""
    entity = _create_update_entity(hass)
    entity.coordinator.api_client.start_online_upgrade.side_effect = OmadaApiError(
        "fail"
    )
    with pytest.raises(HomeAssistantError):
        await entity.async_install(version=None, backup=False)


async def test_update_device_info(hass: HomeAssistant) -> None:
    """Test update entity device info includes sw_version."""
    entity = _create_update_entity(hass)
    info = entity.device_info
    assert info is not None
    assert info["identifiers"] == {(DOMAIN, AP_MAC)}
    assert info["sw_version"] == SAMPLE_DEVICE_AP["firmwareVersion"]


async def test_update_device_info_sw_version_updates(hass: HomeAssistant) -> None:
    """Test sw_version updates when coordinator data changes after upgrade."""
    entity = _create_update_entity(hass)
    assert entity.device_info["sw_version"] == SAMPLE_DEVICE_AP["firmwareVersion"]

    # Simulate firmware upgrade completing — coordinator data now has new version.
    updated_device = {**SAMPLE_DEVICE_AP, "firmwareVersion": "99.0.0"}
    entity.coordinator.data["devices"][AP_MAC] = process_device(updated_device)

    assert entity.device_info["sw_version"] == "99.0.0"


async def test_update_in_progress_upgrading(hass: HomeAssistant) -> None:
    """Test in_progress is True when device detailStatus is 12 (Upgrading)."""
    device = {**SAMPLE_DEVICE_AP, "detailStatus": 12}
    entity = _create_update_entity(hass, devices={AP_MAC: device})
    assert entity.in_progress is True


async def test_update_in_progress_rebooting(hass: HomeAssistant) -> None:
    """Test in_progress is True when device detailStatus is 13 (Rebooting)."""
    device = {**SAMPLE_DEVICE_AP, "detailStatus": 13}
    entity = _create_update_entity(hass, devices={AP_MAC: device})
    assert entity.in_progress is True


async def test_update_not_in_progress(hass: HomeAssistant) -> None:
    """Test in_progress is False when device is in normal state."""
    entity = _create_update_entity(hass)
    assert entity.in_progress is False


async def test_update_not_in_progress_missing_device(hass: HomeAssistant) -> None:
    """Test in_progress is False when device is missing."""
    entity = _create_update_entity(hass)
    entity.coordinator.data["devices"] = {}
    assert entity.in_progress is False


async def test_update_release_notes_full_text(hass: HomeAssistant) -> None:
    """Test async_release_notes returns full text from firmware_info."""
    long_notes = (
        "Version Info:\n"
        "1.Minimum FW Version for Update: 1.3.1\n"
        "2.This firmware upgrade is irreversible.\n"
        "Bug fixed:\n"
        "1.Fixed a memory leak issue."
    )
    firmware_info = {
        AP_MAC: {
            "curFwVer": "1.0.0",
            "lastFwVer": "1.1.0",
            "fwReleaseLog": long_notes,
        }
    }
    entity = _create_update_entity(hass, firmware_info=firmware_info)
    result = await entity.async_release_notes()
    # Newlines should be converted to markdown line breaks (two trailing spaces).
    expected = long_notes.replace("\n", "  \n")
    assert result == expected


async def test_update_release_notes_none(hass: HomeAssistant) -> None:
    """Test async_release_notes returns None when no firmware_info."""
    entity = _create_update_entity(hass)
    result = await entity.async_release_notes()
    assert result is None
