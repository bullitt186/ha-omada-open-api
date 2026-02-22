"""Tests for Omada Open API integration setup and teardown."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock, MagicMock, patch

from homeassistant.config_entries import ConfigEntryState
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import (
    device_registry as dr,
    entity_registry as er,
    issue_registry as ir,
)
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.omada_open_api import (
    _cleanup_devices,
    _cleanup_entities,
    _migrate_data_to_options,
    async_remove_config_entry_device,
)
from custom_components.omada_open_api.api import OmadaApiAuthError
from custom_components.omada_open_api.const import (
    CONF_ACCESS_TOKEN,
    CONF_API_URL,
    CONF_CLIENT_ID,
    CONF_CLIENT_SCAN_INTERVAL,
    CONF_CLIENT_SECRET,
    CONF_DEVICE_SCAN_INTERVAL,
    CONF_OMADA_ID,
    CONF_REFRESH_TOKEN,
    CONF_SELECTED_APPLICATIONS,
    CONF_SELECTED_CLIENTS,
    CONF_SELECTED_SITES,
    CONF_TOKEN_EXPIRES_AT,
    DOMAIN,
)

from .conftest import (
    SAMPLE_CLIENT_WIRELESS,
    SAMPLE_DEVICE_AP,
    SAMPLE_DEVICE_GATEWAY,
    SAMPLE_DEVICE_SWITCH,
    SAMPLE_UPLINK_INFO,
    TEST_API_URL,
    TEST_CLIENT_ID,
    TEST_CLIENT_SECRET,
    TEST_OMADA_ID,
    TEST_SITE_ID,
    TEST_SITE_NAME,
    _future_token_expiry,
)

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_SITE_LIST = [{"siteId": TEST_SITE_ID, "name": TEST_SITE_NAME}]
_DEVICES = [SAMPLE_DEVICE_AP, SAMPLE_DEVICE_SWITCH, SAMPLE_DEVICE_GATEWAY]
_CLIENTS_RESPONSE = {
    "data": [SAMPLE_CLIENT_WIRELESS],
    "totalRows": 1,
    "currentPage": 1,
}


def _build_entry(hass: HomeAssistant, data_overrides: dict | None = None):
    """Create and add a MockConfigEntry."""
    data = {
        CONF_API_URL: TEST_API_URL,
        CONF_OMADA_ID: TEST_OMADA_ID,
        CONF_CLIENT_ID: TEST_CLIENT_ID,
        CONF_CLIENT_SECRET: TEST_CLIENT_SECRET,
        CONF_ACCESS_TOKEN: "valid_token",
        CONF_REFRESH_TOKEN: "valid_refresh",
        CONF_TOKEN_EXPIRES_AT: _future_token_expiry(),
        CONF_SELECTED_SITES: [TEST_SITE_ID],
        CONF_SELECTED_CLIENTS: [],
        CONF_SELECTED_APPLICATIONS: [],
    }
    if data_overrides:
        data.update(data_overrides)

    entry = MockConfigEntry(domain=DOMAIN, data=data, entry_id="test_entry_id")
    entry.add_to_hass(hass)
    return entry


def _patch_api_client(**overrides):
    """Return a context manager that patches OmadaApiClient construction."""
    mock_instance = MagicMock()
    mock_instance.get_sites = AsyncMock(return_value=_SITE_LIST)
    mock_instance.get_devices = AsyncMock(return_value=_DEVICES)
    mock_instance.get_device_uplink_info = AsyncMock(return_value=SAMPLE_UPLINK_INFO)
    mock_instance.get_clients = AsyncMock(return_value=_CLIENTS_RESPONSE)
    mock_instance.get_client_app_traffic = AsyncMock(return_value=[])
    mock_instance.get_switch_ports_poe = AsyncMock(return_value=[])
    mock_instance.get_poe_usage = AsyncMock(return_value=[])
    mock_instance.get_device_client_stats = AsyncMock(return_value=[])
    mock_instance.check_write_access = AsyncMock(return_value=True)
    mock_instance.get_gateway_info = AsyncMock(return_value={})
    mock_instance.get_site_ssids = AsyncMock(return_value=[])
    mock_instance.get_site_ssids_comprehensive = AsyncMock(return_value=[])
    mock_instance.get_ssid_detail = AsyncMock(return_value={})
    mock_instance.update_ssid_basic_config = AsyncMock()
    mock_instance.get_ap_ssid_overrides = AsyncMock(return_value={"ssidOverrides": []})
    mock_instance.update_ap_ssid_override = AsyncMock()

    for key, value in overrides.items():
        setattr(mock_instance, key, value)

    return patch(
        "custom_components.omada_open_api.OmadaApiClient",
        return_value=mock_instance,
    ), mock_instance


# ---------------------------------------------------------------------------
# Setup tests
# ---------------------------------------------------------------------------


async def test_setup_entry_success(hass: HomeAssistant) -> None:
    """Test successful integration setup with one site."""
    entry = _build_entry(hass)
    patcher, _mock_client = _patch_api_client()

    with patcher:
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.LOADED
    runtime = entry.runtime_data
    assert runtime.api_client is not None
    assert TEST_SITE_ID in runtime.coordinators
    assert runtime.has_write_access is True


async def test_setup_entry_with_clients(hass: HomeAssistant) -> None:
    """Test setup with selected clients creates client coordinators."""
    entry = _build_entry(
        hass,
        data_overrides={CONF_SELECTED_CLIENTS: ["11-22-33-44-55-AA"]},
    )
    patcher, _mock_client = _patch_api_client()

    with patcher:
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.LOADED
    assert len(entry.runtime_data.client_coordinators) == 1


async def test_setup_entry_with_app_tracking(hass: HomeAssistant) -> None:
    """Test setup with app tracking creates app traffic coordinators."""
    entry = _build_entry(
        hass,
        data_overrides={
            CONF_SELECTED_CLIENTS: ["11-22-33-44-55-AA"],
            CONF_SELECTED_APPLICATIONS: ["100", "200"],
        },
    )
    patcher, _mock_client = _patch_api_client()

    with patcher:
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.LOADED
    assert len(entry.runtime_data.app_traffic_coordinators) == 1


async def test_setup_entry_app_tracking_requires_clients(
    hass: HomeAssistant,
) -> None:
    """Test that app tracking without clients creates no app coordinators."""
    entry = _build_entry(
        hass,
        data_overrides={
            CONF_SELECTED_CLIENTS: [],  # No clients
            CONF_SELECTED_APPLICATIONS: ["100"],
        },
    )
    patcher, _mock_client = _patch_api_client()

    with patcher:
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.LOADED
    assert len(entry.runtime_data.app_traffic_coordinators) == 0


async def test_setup_entry_auth_failure(hass: HomeAssistant) -> None:
    """Test that authentication failure during setup triggers reauth."""
    entry = _build_entry(hass)
    patcher, _mock_client = _patch_api_client(
        get_sites=AsyncMock(side_effect=OmadaApiAuthError("Invalid credentials")),
    )

    with patcher:
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.SETUP_ERROR


async def test_setup_entry_skips_missing_site(hass: HomeAssistant) -> None:
    """Test that a selected site not found in API is silently skipped."""
    entry = _build_entry(
        hass,
        data_overrides={CONF_SELECTED_SITES: [TEST_SITE_ID, "nonexistent_site"]},
    )
    patcher, _mock_client = _patch_api_client()

    with patcher:
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.LOADED
    # Only the valid site should have a coordinator.
    assert TEST_SITE_ID in entry.runtime_data.coordinators
    assert "nonexistent_site" not in entry.runtime_data.coordinators


# ---------------------------------------------------------------------------
# Unload tests
# ---------------------------------------------------------------------------


async def test_unload_entry(hass: HomeAssistant) -> None:
    """Test that unloading an entry works cleanly."""
    entry = _build_entry(hass)
    patcher, _ = _patch_api_client()

    with patcher:
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.LOADED

    await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.NOT_LOADED


# ---------------------------------------------------------------------------
# Reload listener tests
# ---------------------------------------------------------------------------


async def test_reload_skipped_on_token_only_update(hass: HomeAssistant) -> None:
    """Test that updating only auth tokens does not trigger a full reload."""
    entry = _build_entry(hass)
    patcher, _ = _patch_api_client()

    with patcher:
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.LOADED

    # Simulate a token-only update (as the API client does on refresh).
    # Patch async_reload to verify it is NOT called.
    with (
        patcher,
        patch.object(
            hass.config_entries, "async_reload", new=AsyncMock()
        ) as mock_reload,
    ):
        hass.config_entries.async_update_entry(
            entry,
            data={
                **entry.data,
                CONF_ACCESS_TOKEN: "new_token",
                CONF_REFRESH_TOKEN: "new_refresh",
                CONF_TOKEN_EXPIRES_AT: "2026-02-21T00:00:00+00:00",
            },
        )
        await hass.async_block_till_done()

        # Reload should NOT have been called.
        mock_reload.assert_not_called()


# ---------------------------------------------------------------------------
# Write-access probe tests
# ---------------------------------------------------------------------------


async def test_setup_viewer_only_sets_no_write_access(hass: HomeAssistant) -> None:
    """Test that viewer-only credentials set has_write_access to False."""
    entry = _build_entry(hass)
    patcher, _mock_client = _patch_api_client(
        check_write_access=AsyncMock(return_value=False),
    )

    with patcher:
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.LOADED
    assert entry.runtime_data.has_write_access is False


# ---------------------------------------------------------------------------
# Cleanup tests (_cleanup_devices / _cleanup_entities)
# ---------------------------------------------------------------------------


async def test_cleanup_does_not_remove_infrastructure_devices(
    hass: HomeAssistant,
) -> None:
    """Test that reload does not remove infrastructure devices (APs, switches, etc.)."""
    entry = _build_entry(
        hass,
        data_overrides={CONF_SELECTED_CLIENTS: ["11-22-33-44-55-AA"]},
    )
    patcher, _ = _patch_api_client()

    with patcher:
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.LOADED

    # Register an infrastructure device (AP) — simulating what platforms do
    dev_reg = dr.async_get(hass)
    ap_device = dev_reg.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, "AA-BB-CC-DD-EE-01")},
        name="Office AP",
    )

    # Simulate adding a new client (options change triggers reload)
    with (
        patcher,
        patch.object(hass.config_entries, "async_reload", new=AsyncMock()),
    ):
        hass.config_entries.async_update_entry(
            entry,
            options={
                **entry.options,
                CONF_SELECTED_CLIENTS: ["11-22-33-44-55-AA", "66-77-88-99-00-BB"],
            },
        )
        await hass.async_block_till_done()

    # Infrastructure device should still exist
    assert dev_reg.async_get(ap_device.id) is not None


async def test_cleanup_removes_deselected_client_device(
    hass: HomeAssistant,
) -> None:
    """Test that deselecting a client removes only that client's device."""
    client_mac = "11-22-33-44-55-AA"
    entry = _build_entry(
        hass,
        data_overrides={CONF_SELECTED_CLIENTS: [client_mac]},
    )
    patcher, _ = _patch_api_client()

    with patcher:
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.LOADED

    # Register a client device and an infrastructure device
    dev_reg = dr.async_get(hass)
    client_device = dev_reg.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, client_mac)},
        name="Phone",
    )
    ap_device = dev_reg.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, "AA-BB-CC-DD-EE-01")},
        name="Office AP",
    )

    # Deselect the client (remove from selected list)
    with (
        patcher,
        patch.object(hass.config_entries, "async_reload", new=AsyncMock()),
    ):
        hass.config_entries.async_update_entry(
            entry,
            options={**entry.options, CONF_SELECTED_CLIENTS: []},
        )
        await hass.async_block_till_done()

    # Client device should be removed; AP device should remain
    assert dev_reg.async_get(client_device.id) is None
    assert dev_reg.async_get(ap_device.id) is not None


async def test_cleanup_does_not_remove_site_device(
    hass: HomeAssistant,
) -> None:
    """Test that site devices are kept when the site is still selected."""
    entry = _build_entry(hass)
    patcher, _ = _patch_api_client()

    with patcher:
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.LOADED

    # The site device is created in async_setup_entry
    dev_reg = dr.async_get(hass)
    site_device = dev_reg.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, f"site_{TEST_SITE_ID}")},
        name="Test Site",
    )

    # Trigger an options update (no client changes — just add a scan interval)
    with (
        patcher,
        patch.object(hass.config_entries, "async_reload", new=AsyncMock()),
    ):
        hass.config_entries.async_update_entry(
            entry,
            options={**entry.options, CONF_SELECTED_CLIENTS: ["AA-BB-CC-DD-EE-FF"]},
        )
        await hass.async_block_till_done()

    # Site device should still exist
    assert dev_reg.async_get(site_device.id) is not None


async def test_cleanup_no_runtime_data_is_safe(
    hass: HomeAssistant,
) -> None:
    """Test that cleanup functions are safe when runtime_data is missing."""
    entry = _build_entry(hass)
    # Don't set up the entry — no runtime_data exists.
    # These should not raise.
    await _cleanup_devices(hass, entry)
    await _cleanup_entities(hass, entry)


async def test_cleanup_entities_removes_deselected_app(
    hass: HomeAssistant,
) -> None:
    """Test that deselecting an app removes only that app's traffic entities."""
    entry = _build_entry(
        hass,
        data_overrides={
            CONF_SELECTED_CLIENTS: ["11-22-33-44-55-AA"],
            CONF_SELECTED_APPLICATIONS: ["100", "200"],
        },
    )
    patcher, _ = _patch_api_client()

    with patcher:
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.LOADED

    # Register fake app traffic entities
    ent_reg = er.async_get(hass)
    kept_entity = ent_reg.async_get_or_create(
        "sensor",
        DOMAIN,
        "11-22-33-44-55-AA_100_upload_app_traffic",
        config_entry=entry,
    )
    removed_entity = ent_reg.async_get_or_create(
        "sensor",
        DOMAIN,
        "11-22-33-44-55-AA_200_download_app_traffic",
        config_entry=entry,
    )
    unrelated_entity = ent_reg.async_get_or_create(
        "sensor",
        DOMAIN,
        "some_other_sensor",
        config_entry=entry,
    )

    # Deselect app 200, keep app 100
    with (
        patcher,
        patch.object(hass.config_entries, "async_reload", new=AsyncMock()),
    ):
        hass.config_entries.async_update_entry(
            entry,
            options={
                **entry.options,
                CONF_SELECTED_APPLICATIONS: ["100"],
            },
        )
        await hass.async_block_till_done()

    # App 100 entity should remain, app 200 entity should be removed
    assert ent_reg.async_get(kept_entity.entity_id) is not None
    assert ent_reg.async_get(removed_entity.entity_id) is None
    assert ent_reg.async_get(unrelated_entity.entity_id) is not None


async def test_cleanup_entities_keeps_all_when_no_apps_deselected(
    hass: HomeAssistant,
) -> None:
    """Test that adding an app does not remove existing app entities."""
    entry = _build_entry(
        hass,
        data_overrides={
            CONF_SELECTED_CLIENTS: ["11-22-33-44-55-AA"],
            CONF_SELECTED_APPLICATIONS: ["100"],
        },
    )
    patcher, _ = _patch_api_client()

    with patcher:
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    # Register a fake app traffic entity
    ent_reg = er.async_get(hass)
    entity = ent_reg.async_get_or_create(
        "sensor",
        DOMAIN,
        "11-22-33-44-55-AA_100_upload_app_traffic",
        config_entry=entry,
    )

    # Add a new app (no deselections)
    with (
        patcher,
        patch.object(hass.config_entries, "async_reload", new=AsyncMock()),
    ):
        hass.config_entries.async_update_entry(
            entry,
            options={
                **entry.options,
                CONF_SELECTED_APPLICATIONS: ["100", "200"],
            },
        )
        await hass.async_block_till_done()

    # Existing entity should remain
    assert ent_reg.async_get(entity.entity_id) is not None


# ---------------------------------------------------------------------------
# Migration tests
# ---------------------------------------------------------------------------


async def test_migrate_data_to_options(hass: HomeAssistant) -> None:
    """Test that legacy keys are moved from data to options."""
    entry = _build_entry(
        hass,
        data_overrides={
            CONF_DEVICE_SCAN_INTERVAL: 120,
            CONF_CLIENT_SCAN_INTERVAL: 45,
        },
    )

    # Before migration, keys are in data
    assert CONF_DEVICE_SCAN_INTERVAL in entry.data
    assert CONF_CLIENT_SCAN_INTERVAL in entry.data

    _migrate_data_to_options(hass, entry)

    # After migration, keys moved to options
    assert CONF_DEVICE_SCAN_INTERVAL not in entry.data
    assert CONF_CLIENT_SCAN_INTERVAL not in entry.data
    assert entry.options[CONF_DEVICE_SCAN_INTERVAL] == 120
    assert entry.options[CONF_CLIENT_SCAN_INTERVAL] == 45


async def test_migrate_data_to_options_noop(hass: HomeAssistant) -> None:
    """Test that migration does nothing when no legacy keys exist in data."""
    # Build an entry where options keys are already in options, not data.
    data = {
        CONF_API_URL: TEST_API_URL,
        CONF_OMADA_ID: TEST_OMADA_ID,
        CONF_CLIENT_ID: TEST_CLIENT_ID,
        CONF_CLIENT_SECRET: TEST_CLIENT_SECRET,
        CONF_ACCESS_TOKEN: "valid_token",
        CONF_REFRESH_TOKEN: "valid_refresh",
        CONF_TOKEN_EXPIRES_AT: _future_token_expiry(),
        CONF_SELECTED_SITES: [TEST_SITE_ID],
    }
    options: dict[str, Any] = {
        CONF_SELECTED_CLIENTS: [],
        CONF_SELECTED_APPLICATIONS: [],
    }
    entry = MockConfigEntry(
        domain=DOMAIN, data=data, options=options, entry_id="noop_entry"
    )
    entry.add_to_hass(hass)
    original_data = dict(entry.data)

    _migrate_data_to_options(hass, entry)

    # Data should not have changed
    assert dict(entry.data) == original_data


# ---------------------------------------------------------------------------
# Setup error tests
# ---------------------------------------------------------------------------


async def test_setup_entry_timeout_error(hass: HomeAssistant) -> None:
    """Test that TimeoutError raises ConfigEntryNotReady."""
    entry = _build_entry(hass)
    patcher, _mock_client = _patch_api_client(
        get_sites=AsyncMock(side_effect=TimeoutError("Connection timed out")),
    )

    with patcher:
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.SETUP_RETRY


async def test_setup_entry_os_error(hass: HomeAssistant) -> None:
    """Test that OSError raises ConfigEntryNotReady."""
    entry = _build_entry(hass)
    patcher, _mock_client = _patch_api_client(
        get_sites=AsyncMock(side_effect=OSError("Network unreachable")),
    )

    with patcher:
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.SETUP_RETRY


# ---------------------------------------------------------------------------
# Debug service tests
# ---------------------------------------------------------------------------


async def test_debug_ssid_switches_service(hass: HomeAssistant) -> None:
    """Test the debug_ssid_switches service with valid config entry."""
    entry = _build_entry(hass)
    patcher, _ = _patch_api_client()

    with patcher:
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.LOADED

    # Call the service — should not raise
    await hass.services.async_call(
        DOMAIN,
        "debug_ssid_switches",
        {"config_entry_id": entry.entry_id},
        blocking=True,
    )


async def test_debug_ssid_service_missing_entry(hass: HomeAssistant) -> None:
    """Test debug service with missing config entry raises error."""
    entry = _build_entry(hass)
    patcher, _ = _patch_api_client()

    with patcher:
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    # Call with non-existent entry ID
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            DOMAIN,
            "debug_ssid_switches",
            {"config_entry_id": "nonexistent_entry_id"},
            blocking=True,
        )


async def test_debug_ssid_service_no_runtime_data(hass: HomeAssistant) -> None:
    """Test debug service when runtime data is missing raises error."""
    entry = _build_entry(hass)
    patcher, _ = _patch_api_client()

    with patcher:
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    # Remove runtime data to simulate edge case
    entry.runtime_data = None  # type: ignore[assignment]

    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            DOMAIN,
            "debug_ssid_switches",
            {"config_entry_id": entry.entry_id},
            blocking=True,
        )


async def test_debug_ssid_service_with_ssids(hass: HomeAssistant) -> None:
    """Test debug service logs SSID information."""
    entry = _build_entry(hass)
    patcher, _ = _patch_api_client()

    with patcher:
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    # Add some fake SSID data to coordinator
    coordinator = entry.runtime_data.coordinators[TEST_SITE_ID]
    coordinator.data["ssids"] = [
        {"id": "ssid_1", "wlanId": "wlan_1", "name": "TestWiFi", "broadcast": True},
    ]

    # Should not raise and should log the SSID info
    await hass.services.async_call(
        DOMAIN,
        "debug_ssid_switches",
        {"config_entry_id": entry.entry_id},
        blocking=True,
    )


# ---------------------------------------------------------------------------
# async_remove_config_entry_device tests
# ---------------------------------------------------------------------------


async def test_remove_device_allows_untracked_device(hass: HomeAssistant) -> None:
    """Test that untracked devices can be removed."""
    entry = _build_entry(
        hass,
        data_overrides={CONF_SELECTED_CLIENTS: ["11-22-33-44-55-AA"]},
    )
    patcher, _ = _patch_api_client()

    with patcher:
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    # Create an untracked device
    dev_reg = dr.async_get(hass)
    untracked_device = dev_reg.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, "FF-FF-FF-FF-FF-FF")},
        name="Untracked Device",
    )

    # Should allow removal
    result = await async_remove_config_entry_device(hass, entry, untracked_device)
    assert result is True


async def test_remove_device_blocks_selected_client(hass: HomeAssistant) -> None:
    """Test that selected client devices cannot be removed."""
    client_mac = "11-22-33-44-55-AA"
    entry = _build_entry(
        hass,
        data_overrides={CONF_SELECTED_CLIENTS: [client_mac]},
    )
    patcher, _ = _patch_api_client()

    with patcher:
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    dev_reg = dr.async_get(hass)
    client_device = dev_reg.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, client_mac)},
        name="Phone",
    )

    # Should block removal
    result = await async_remove_config_entry_device(hass, entry, client_device)
    assert result is False


async def test_remove_device_blocks_selected_site(hass: HomeAssistant) -> None:
    """Test that selected site devices cannot be removed."""
    entry = _build_entry(hass)
    patcher, _ = _patch_api_client()

    with patcher:
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    dev_reg = dr.async_get(hass)
    site_device = dev_reg.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, f"site_{TEST_SITE_ID}")},
        name="Test Site",
    )

    # Should block removal (site is still selected)
    result = await async_remove_config_entry_device(hass, entry, site_device)
    assert result is False


async def test_remove_device_allows_deselected_site(hass: HomeAssistant) -> None:
    """Test that devices for deselected sites can be removed."""
    entry = _build_entry(hass)
    patcher, _ = _patch_api_client()

    with patcher:
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    dev_reg = dr.async_get(hass)
    # Create a device for a site that is NOT in selected_sites
    other_site_device = dev_reg.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, "site_other_site_id")},
        name="Other Site",
    )

    # Should allow removal (site is not selected)
    result = await async_remove_config_entry_device(hass, entry, other_site_device)
    assert result is True


async def test_remove_device_non_domain_identifiers(hass: HomeAssistant) -> None:
    """Test that devices with non-DOMAIN identifiers are allowed to be removed."""
    entry = _build_entry(hass)
    patcher, _ = _patch_api_client()

    with patcher:
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    dev_reg = dr.async_get(hass)
    # Create a device with a different domain identifier
    other_device = dev_reg.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={("other_domain", "some_id")},
        name="Other Domain Device",
    )

    result = await async_remove_config_entry_device(hass, entry, other_device)
    assert result is True


# ---------------------------------------------------------------------------
# Repair issue tests
# ---------------------------------------------------------------------------


async def test_repair_issue_write_access_denied(hass: HomeAssistant) -> None:
    """Test that a repair issue is created when write access is denied."""
    entry = _build_entry(hass)
    patcher, _mock_client = _patch_api_client(
        check_write_access=AsyncMock(return_value=False),
    )

    with patcher:
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    issue_reg = ir.async_get(hass)
    issue = issue_reg.async_get_issue(DOMAIN, "write_access_denied")
    assert issue is not None
    assert issue.severity == ir.IssueSeverity.WARNING
    assert issue.translation_key == "write_access_denied"


async def test_repair_issue_write_access_cleared(hass: HomeAssistant) -> None:
    """Test that the write-access issue is cleared when access is granted."""
    entry = _build_entry(hass)
    patcher, _mock_client = _patch_api_client(
        check_write_access=AsyncMock(return_value=True),
    )

    with patcher:
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    issue_reg = ir.async_get(hass)
    issue = issue_reg.async_get_issue(DOMAIN, "write_access_denied")
    assert issue is None


async def test_repair_issue_dpi_no_gateway(hass: HomeAssistant) -> None:
    """Test that a repair issue is created when apps selected but no gateway."""
    # Devices without a gateway
    devices_no_gw = [SAMPLE_DEVICE_AP, SAMPLE_DEVICE_SWITCH]
    entry = _build_entry(
        hass,
        data_overrides={CONF_SELECTED_APPLICATIONS: ["app_1"]},
    )
    patcher, _mock_client = _patch_api_client(
        get_devices=AsyncMock(return_value=devices_no_gw),
    )

    with patcher:
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    issue_reg = ir.async_get(hass)
    issue = issue_reg.async_get_issue(DOMAIN, "dpi_no_gateway")
    assert issue is not None
    assert issue.severity == ir.IssueSeverity.WARNING


async def test_repair_issue_dpi_cleared_with_gateway(hass: HomeAssistant) -> None:
    """Test that the DPI issue is cleared when a gateway exists."""
    entry = _build_entry(
        hass,
        data_overrides={CONF_SELECTED_APPLICATIONS: ["app_1"]},
    )
    patcher, _mock_client = _patch_api_client()  # includes gateway in default devices

    with patcher:
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    issue_reg = ir.async_get(hass)
    issue = issue_reg.async_get_issue(DOMAIN, "dpi_no_gateway")
    assert issue is None


async def test_repair_issue_dpi_cleared_no_apps(hass: HomeAssistant) -> None:
    """Test that the DPI issue is cleared when no apps are selected."""
    entry = _build_entry(hass)  # no selected apps
    patcher, _mock_client = _patch_api_client()

    with patcher:
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    issue_reg = ir.async_get(hass)
    issue = issue_reg.async_get_issue(DOMAIN, "dpi_no_gateway")
    assert issue is None


# ---------------------------------------------------------------------------
# Enhanced device removal: active infrastructure blocking
# ---------------------------------------------------------------------------


async def test_remove_device_blocks_active_infrastructure(
    hass: HomeAssistant,
) -> None:
    """Test that active infrastructure devices cannot be removed."""
    entry = _build_entry(hass)
    patcher, _ = _patch_api_client()

    with patcher:
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    dev_reg = dr.async_get(hass)
    # The AP MAC is in coordinator data — device should be blocked
    ap_device = dev_reg.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, "AA-BB-CC-DD-EE-01")},
        name="Office AP",
    )

    result = await async_remove_config_entry_device(hass, entry, ap_device)
    assert result is False
