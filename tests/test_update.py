"""Tests for Omada update entities (firmware)."""

from __future__ import annotations

import datetime as dt
from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

from homeassistant.exceptions import HomeAssistantError
from homeassistant.util import dt as dt_util

from custom_components.omada_open_api.api import OmadaApiError
from custom_components.omada_open_api.const import DOMAIN
from custom_components.omada_open_api.coordinator import OmadaSiteCoordinator
from custom_components.omada_open_api.devices import process_device
from custom_components.omada_open_api.update import (
    INSTALL_FLAG_TIMEOUT,
    OmadaDeviceUpdateEntity,
    async_setup_entry,
)

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


@pytest.mark.parametrize("expected_lingering_timers", [True])
async def test_setup_entry_no_new_devices_on_second_callback(
    hass: HomeAssistant,
) -> None:
    """Test _async_check_new_devices returns early when no new MACs found."""
    coordinator = _build_coordinator(hass, devices={AP_MAC: SAMPLE_DEVICE_AP})

    entry = MagicMock()
    entry.runtime_data.coordinators = {"site1": coordinator}
    # Collect unload callbacks registered via entry.async_on_unload.
    unload_callbacks: list[Any] = []
    entry.async_on_unload.side_effect = unload_callbacks.append

    added_entities: list[Any] = []
    mock_add_entities = MagicMock(side_effect=added_entities.extend)

    await async_setup_entry(hass, entry, mock_add_entities)

    # First call adds 1 entity for the AP.
    assert len(added_entities) == 1

    # Trigger the listener callback again — same devices, no new MACs.
    coordinator.async_update_listeners()
    # No additional entities should have been added.
    assert len(added_entities) == 1

    # Run unload callbacks to cancel the coordinator's refresh-interval timer
    # and avoid a lingering handle in the HA test harness's verify_cleanup check.
    for cb in unload_callbacks:
        cb()


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


async def test_update_latest_version_ignores_absent_upgrade_flag(
    hass: HomeAssistant,
) -> None:
    """Test latest_version reports newer firmware with no upgrade-flag field at all."""
    device = {k: v for k, v in SAMPLE_DEVICE_AP.items() if k != "needUpgrade"}
    firmware_info = {
        AP_MAC: {
            "curFwVer": "1.0.0",
            "lastFwVer": "1.1.0",
            "fwReleaseLog": "Bug fixes",
        }
    }
    entity = _create_update_entity(
        hass, devices={AP_MAC: device}, firmware_info=firmware_info
    )
    # latest_version must come purely from firmware_info, regardless of
    # whether the device carries any upgrade-flag field.
    assert entity.latest_version == "1.1.0"


async def test_update_latest_version_device_missing(hass: HomeAssistant) -> None:
    """Test latest_version returns installed_version when device is missing."""
    entity = _create_update_entity(hass)
    entity.coordinator.data["devices"] = {}
    assert entity.latest_version is None


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


async def test_install_sets_in_progress_immediately(hass: HomeAssistant) -> None:
    """Test that in_progress is True right after async_install succeeds."""
    entity = _create_update_entity(hass)
    # Device is in normal state (detailStatus != 12/13) before install.
    assert entity.in_progress is False

    with patch.object(entity.coordinator, "async_request_refresh", new=AsyncMock()):
        await entity.async_install(version=None, backup=False)

    # Flag should be set immediately — no coordinator poll needed.
    assert entity._is_installing is True  # noqa: SLF001
    assert entity.in_progress is True


async def test_install_writes_ha_state_immediately(hass: HomeAssistant) -> None:
    """Test that async_install calls async_write_ha_state when hass is set."""
    entity = _create_update_entity(hass)
    entity.hass = hass

    with (
        patch.object(entity.coordinator, "async_request_refresh", new=AsyncMock()),
        patch.object(entity, "async_write_ha_state") as mock_write,
    ):
        await entity.async_install(version=None, backup=False)

    mock_write.assert_called_once()
    assert entity._is_installing is True  # noqa: SLF001


async def test_install_error_does_not_set_in_progress(hass: HomeAssistant) -> None:
    """Test that _is_installing stays False when the API call fails."""
    entity = _create_update_entity(hass)
    entity.coordinator.api_client.start_online_upgrade.side_effect = OmadaApiError(
        "fail"
    )
    with pytest.raises(HomeAssistantError):
        await entity.async_install(version=None, backup=False)

    assert entity._is_installing is False  # noqa: SLF001
    assert entity.in_progress is False


async def test_in_progress_cleared_when_coordinator_updates(
    hass: HomeAssistant,
) -> None:
    """Test _is_installing clears on coordinator update when status is upgrading."""
    device = {**SAMPLE_DEVICE_AP, "detailStatus": 12}
    entity = _create_update_entity(hass, devices={AP_MAC: device})

    # Simulate the optimistic flag being set after install.
    entity._is_installing = True  # noqa: SLF001

    # Simulate a coordinator update callback (mock write_ha_state — entity not registered).
    with patch.object(entity, "async_write_ha_state"):
        entity._handle_coordinator_update()  # noqa: SLF001

    # Flag should be cleared; in_progress still True from coordinator data.
    assert entity._is_installing is False  # noqa: SLF001
    assert entity.in_progress is True


async def test_in_progress_flag_persists_until_controller_confirms(
    hass: HomeAssistant,
) -> None:
    """Test _is_installing persists when controller hasn't acknowledged upgrade."""
    entity = _create_update_entity(hass)

    # Simulate: install was called, flag is set with a recent timestamp.
    entity._is_installing = True  # noqa: SLF001
    entity._install_started_at = dt_util.utcnow()  # noqa: SLF001

    # Coordinator polls but device is still in normal state (not yet upgrading).
    with patch.object(entity, "async_write_ha_state"):
        entity._handle_coordinator_update()  # noqa: SLF001

    # Flag must persist — controller hasn't confirmed yet.
    assert entity._is_installing is True  # noqa: SLF001
    assert entity.in_progress is True


async def test_in_progress_cleared_on_timeout(
    hass: HomeAssistant,
) -> None:
    """Test _is_installing clears after safety timeout if controller never confirms."""
    entity = _create_update_entity(hass)

    # Simulate: install was called long ago (past timeout).
    entity._is_installing = True  # noqa: SLF001
    entity._install_started_at = (  # noqa: SLF001
        dt_util.utcnow() - dt.timedelta(seconds=INSTALL_FLAG_TIMEOUT + 10)
    )

    # Coordinator polls — device is in normal state and timeout has elapsed.
    with patch.object(entity, "async_write_ha_state"):
        entity._handle_coordinator_update()  # noqa: SLF001

    # Flag should be cleared due to timeout.
    assert entity._is_installing is False  # noqa: SLF001
    assert entity.in_progress is False
