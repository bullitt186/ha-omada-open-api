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
    _migrate_merged_devices,
    _migrate_wan_speed_test_button_unique_ids,
    _prune_stale_infra_devices,
    async_remove_config_entry_device,
)
from custom_components.omada_open_api.api import OmadaApiAuthError, OmadaApiError
from custom_components.omada_open_api.const import (
    CONF_ACCESS_TOKEN,
    CONF_API_URL,
    CONF_CLIENT_ID,
    CONF_CLIENT_SCAN_INTERVAL,
    CONF_CLIENT_SECRET,
    CONF_CONTROLLER_TYPE,
    CONF_DEVICE_SCAN_INTERVAL,
    CONF_ENABLE_VPN_SENSORS,
    CONF_ENABLE_WAN_SPEED_TEST,
    CONF_OMADA_ID,
    CONF_REFRESH_TOKEN,
    CONF_SELECTED_APPLICATIONS,
    CONF_SELECTED_CLIENTS,
    CONF_SELECTED_SITES,
    CONF_TOKEN_EXPIRES_AT,
    CONF_VERIFY_SSL,
    CONTROLLER_TYPE_FUSION,
    CONTROLLER_TYPE_LOCAL,
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


def _build_entry(
    hass: HomeAssistant,
    data_overrides: dict | None = None,
    options: dict | None = None,
):
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

    entry = MockConfigEntry(
        domain=DOMAIN,
        data=data,
        options=options or {},
        entry_id="test_entry_id",
    )
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
    mock_instance.get_gateway_wan_status = AsyncMock(return_value=[])
    mock_instance.get_gateway_wan_speed_test_result = AsyncMock(return_value={})
    mock_instance.get_gateway_wan_speed_test_ports = AsyncMock(return_value=[])
    mock_instance.get_gateway_wan_speed_test_history = AsyncMock(return_value=None)
    mock_instance.get_vpn_s2s_stats = AsyncMock(return_value=[])
    mock_instance.get_vpn_server_stats = AsyncMock(return_value=[])
    mock_instance.get_vpn_client_stats = AsyncMock(return_value=[])
    mock_instance.get_device_stats = AsyncMock(return_value=[])
    mock_instance.get_firmware_info = AsyncMock(return_value={})
    mock_instance.start_online_upgrade = AsyncMock(return_value={})
    mock_instance.get_ap_radios = AsyncMock(return_value={})
    mock_instance.get_switch_port_details = AsyncMock(return_value=[])
    mock_instance.get_ap_radio_config = AsyncMock(return_value={})
    mock_instance.get_ap_led_setting = AsyncMock(return_value={})
    mock_instance.set_ap_radio_enabled = AsyncMock()
    mock_instance.get_wlan_optimization_status = AsyncMock(
        return_value={"status": 0, "beforeIndex": 55, "afterIndex": 80}
    )
    mock_instance.get_threat_management = AsyncMock(return_value=[])

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
    shared_session = MagicMock()

    with (
        patcher,
        patch(
            "custom_components.omada_open_api.async_get_clientsession",
            return_value=shared_session,
        ) as mock_get_clientsession,
    ):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    mock_get_clientsession.assert_called_once_with(hass, verify_ssl=True)
    assert entry.state is ConfigEntryState.LOADED
    runtime = entry.runtime_data
    assert runtime.api_client is not None
    assert TEST_SITE_ID in runtime.coordinators
    # Default (Cloud) controller type: no WAN speed-test coordinators — that
    # endpoint only exists on a Fusion Gateway. See
    # test_setup_skips_wan_speed_test_for_non_fusion_controller and
    # test_setup_entry_creates_wan_and_traffic_sensors.
    assert runtime.wan_speed_test_coordinators == {}
    assert runtime.has_write_access is True


async def test_setup_entry_local_defaults_to_unverified_ssl(
    hass: HomeAssistant,
) -> None:
    """A Local entry with no stored verify_ssl key sets up with verification off.

    Regression test for GH #54 / the v1.10 TLS-verification regression:
    Local controllers commonly present a self-signed certificate, and pre-fix
    entries (created before this option existed) must keep working exactly
    as they did before the v1.10 "restore verification" change broke them.
    """
    entry = _build_entry(
        hass, data_overrides={CONF_CONTROLLER_TYPE: CONTROLLER_TYPE_LOCAL}
    )
    patcher, _mock_client = _patch_api_client()
    shared_session = MagicMock()

    with (
        patcher,
        patch(
            "custom_components.omada_open_api.async_get_clientsession",
            return_value=shared_session,
        ) as mock_get_clientsession,
    ):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    mock_get_clientsession.assert_called_once_with(hass, verify_ssl=False)
    assert entry.state is ConfigEntryState.LOADED


async def test_setup_entry_local_respects_explicit_verify_ssl(
    hass: HomeAssistant,
) -> None:
    """A Local entry that explicitly opted into verify_ssl=True keeps it enforced."""
    entry = _build_entry(
        hass,
        data_overrides={
            CONF_CONTROLLER_TYPE: CONTROLLER_TYPE_LOCAL,
            CONF_VERIFY_SSL: True,
        },
    )
    patcher, _mock_client = _patch_api_client()
    shared_session = MagicMock()

    with (
        patcher,
        patch(
            "custom_components.omada_open_api.async_get_clientsession",
            return_value=shared_session,
        ) as mock_get_clientsession,
    ):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    mock_get_clientsession.assert_called_once_with(hass, verify_ssl=True)
    assert entry.state is ConfigEntryState.LOADED


async def test_setup_skips_disabled_vpn_and_wan_speed_test(
    hass: HomeAssistant,
) -> None:
    """Disabled gateway features create no coordinator or API traffic."""
    entry = _build_entry(
        hass,
        data_overrides={CONF_CONTROLLER_TYPE: CONTROLLER_TYPE_FUSION},
        options={
            CONF_ENABLE_VPN_SENSORS: False,
            CONF_ENABLE_WAN_SPEED_TEST: False,
        },
    )
    patcher, mock_client = _patch_api_client()

    with patcher:
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    assert entry.runtime_data.wan_speed_test_coordinators == {}
    mock_client.get_vpn_s2s_stats.assert_not_awaited()
    mock_client.get_vpn_server_stats.assert_not_awaited()
    mock_client.get_vpn_client_stats.assert_not_awaited()
    mock_client.get_gateway_wan_speed_test_ports.assert_not_awaited()


async def test_setup_skips_wan_speed_test_for_non_fusion_controller(
    hass: HomeAssistant,
) -> None:
    """A Local/Cloud controller never gets WAN speed-test coordinators.

    The speed-test endpoints only exist on a Fusion Gateway's built-in
    controller — calling them on a traditional Local/Cloud controller
    returns "-1600: Unsupported request path" on every single poll. Skip
    creating the coordinators entirely for non-Fusion entries so that
    every non-Fusion user with a gateway device isn't left with a
    permanent, harmless-but-noisy error logged on each refresh.
    """
    entry = _build_entry(
        hass,
        data_overrides={CONF_CONTROLLER_TYPE: CONTROLLER_TYPE_LOCAL},
        options={CONF_ENABLE_WAN_SPEED_TEST: True},
    )
    patcher, mock_client = _patch_api_client()

    with patcher:
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    assert entry.runtime_data.wan_speed_test_coordinators == {}
    mock_client.get_gateway_wan_speed_test_ports.assert_not_awaited()
    mock_client.get_gateway_wan_speed_test_result.assert_not_awaited()


def test_migrate_wan_speed_test_button_unique_id(hass: HomeAssistant) -> None:
    """The corrected speed-test action keeps the old entity ID."""
    gateway_mac = "AA-BB-CC-DD-EE-03"
    legacy_unique_id = f"{gateway_mac}_1_{gateway_mac}_wan_speed_test"
    corrected_unique_id = f"{gateway_mac}_1_wan_speed_test"
    registry = er.async_get(hass)
    registry.async_get_or_create(
        "button",
        DOMAIN,
        legacy_unique_id,
        suggested_object_id="wan1_run_speed_test",
    )
    legacy_sensor_unique_id = f"{gateway_mac}_1_{gateway_mac}_wan_speed_test_download"
    corrected_sensor_unique_id = f"{gateway_mac}_1_wan_speed_test_download"
    registry.async_get_or_create(
        "sensor",
        DOMAIN,
        legacy_sensor_unique_id,
        suggested_object_id="wan1_speed_test_download",
    )
    coordinator = MagicMock()
    coordinator.data = {
        "ports": [{"port": 1, "portUuid": "1_opaque-port-id", "name": "WAN1"}]
    }

    _migrate_wan_speed_test_button_unique_ids(
        hass, {("site-id", gateway_mac): coordinator}
    )

    assert registry.async_get_entity_id("button", DOMAIN, legacy_unique_id) is None
    assert registry.async_get_entity_id("button", DOMAIN, corrected_unique_id) == (
        "button.wan1_run_speed_test"
    )
    assert (
        registry.async_get_entity_id("sensor", DOMAIN, corrected_sensor_unique_id)
        == "sensor.wan1_speed_test_download"
    )


def test_migrate_wan_speed_test_button_removes_duplicate(hass: HomeAssistant) -> None:
    """A prior corrected duplicate yields its entity ID to the legacy entry."""
    gateway_mac = "AA-BB-CC-DD-EE-03"
    legacy_unique_id = f"{gateway_mac}_1_{gateway_mac}_wan_speed_test"
    corrected_unique_id = f"{gateway_mac}_1_wan_speed_test"
    registry = er.async_get(hass)
    legacy = registry.async_get_or_create(
        "button", DOMAIN, legacy_unique_id, suggested_object_id="wan1_run_speed_test"
    )
    duplicate = registry.async_get_or_create(
        "button", DOMAIN, corrected_unique_id, suggested_object_id="wan1_run_speed_test"
    )
    coordinator = MagicMock()
    coordinator.data = {"ports": [{"port": 1, "portUuid": "1_opaque-port-id"}]}

    _migrate_wan_speed_test_button_unique_ids(
        hass, {("site-id", gateway_mac): coordinator}
    )

    assert registry.async_get(duplicate.entity_id) is None
    assert registry.async_get_entity_id("button", DOMAIN, corrected_unique_id) == (
        legacy.entity_id
    )


async def test_setup_entry_creates_wan_and_traffic_sensors(
    hass: HomeAssistant,
) -> None:
    """Test setup creates WAN sensors and device traffic sensors."""
    entry = _build_entry(
        hass, data_overrides={CONF_CONTROLLER_TYPE: CONTROLLER_TYPE_FUSION}
    )
    wan_port = {
        "portName": "WAN1",
        "mode": 0,
        "status": 1,
        "internetState": 1,
        "ip": "1.2.3.4",
        "rxRate": 100,
        "txRate": 50,
        "rx": 1000,
        "tx": 500,
        "latency": 10,
        "loss": 0,
        "speed": 3,
    }
    patcher, _mock_client = _patch_api_client(
        get_gateway_wan_status=AsyncMock(return_value=[wan_port]),
        get_gateway_wan_speed_test_result=AsyncMock(
            return_value={
                "portSpeedResults": [
                    {
                        "portId": "1_AA-BB-CC-DD-EE-03",
                        "portName": "WAN1",
                        "down": 987_000_000,
                        "up": 123_000_000,
                        "latency": 7,
                    }
                ]
            }
        ),
        get_gateway_wan_speed_test_ports=AsyncMock(
            return_value=[
                {
                    "port": 1,
                    "portUuid": "1_opaque-port-id",
                    "name": "WAN1",
                }
            ]
        ),
    )
    _mock_client.get_vpn_s2s_stats = AsyncMock(return_value=[])
    _mock_client.get_vpn_server_stats = AsyncMock(return_value=[])
    _mock_client.get_vpn_client_stats = AsyncMock(return_value=[])

    with patcher:
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.LOADED
    # Verify WAN sensors were created.
    entity_reg = er.async_get(hass)
    wan_entities = [
        e
        for e in entity_reg.entities.values()
        if e.platform == DOMAIN and "wan" in e.unique_id
    ]
    assert len(wan_entities) > 0
    assert any("wan_speed_test_download" in entity.unique_id for entity in wan_entities)
    assert any(
        entity.domain == "button" and "wan_speed_test" in entity.unique_id
        for entity in entity_reg.entities.values()
    )

    # Verify device stats coordinators were created.
    assert len(entry.runtime_data.device_stats_coordinators) > 0


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
# Threat heatmap coordinator setup
# ---------------------------------------------------------------------------


async def test_setup_entry_creates_threat_heatmap_coordinators(
    hass: HomeAssistant,
) -> None:
    """Setup creates one threat heatmap coordinator per window per site."""
    entry = _build_entry(hass)
    patcher, _mock_client = _patch_api_client(
        get_threat_management=AsyncMock(return_value=[]),
    )

    with patcher:
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.LOADED
    coords = entry.runtime_data.threat_heatmap_coordinators
    assert len(coords) == 4
    assert {c.window for c in coords} == {"hourly", "daily", "weekly", "monthly"}
    assert all(c.site_id == TEST_SITE_ID for c in coords)


async def test_setup_entry_tolerates_unsupported_threat_endpoint(
    hass: HomeAssistant,
) -> None:
    """An unsupported threat-management endpoint must not block setup."""
    entry = _build_entry(hass)
    patcher, _mock_client = _patch_api_client(
        get_threat_management=AsyncMock(
            side_effect=OmadaApiError("HTTP 404: not found")
        ),
    )

    with patcher:
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.LOADED
    coords = entry.runtime_data.threat_heatmap_coordinators
    assert len(coords) == 4
    assert all(c.data["available"] is False for c in coords)


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


async def test_migrate_data_to_options_clamps_legacy_scan_intervals(
    hass: HomeAssistant,
) -> None:
    """Test that saved scan intervals below 30 seconds are raised safely."""
    entry = _build_entry(
        hass,
        options={
            CONF_DEVICE_SCAN_INTERVAL: 10,
            CONF_CLIENT_SCAN_INTERVAL: 20,
        },
    )

    _migrate_data_to_options(hass, entry)

    assert entry.options[CONF_DEVICE_SCAN_INTERVAL] == 30
    assert entry.options[CONF_CLIENT_SCAN_INTERVAL] == 30


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


# ---------------------------------------------------------------------------
# _prune_stale_infra_devices tests
# ---------------------------------------------------------------------------


async def test_prune_removes_vanished_infra_device(hass: HomeAssistant) -> None:
    """Test that an infra device whose MAC vanishes from the API is pruned.

    Simulates a device being unadopted/removed from the Omada controller
    (e.g. the user's decommissioned old "Technikkeller" AP): once a
    successful poll no longer reports it, the device and its entities must
    be removed from the registries automatically.
    """
    entry = _build_entry(hass)
    patcher, mock_client = _patch_api_client()

    with patcher:
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.LOADED

    switch_mac = "AA-BB-CC-DD-EE-02"
    dev_reg = dr.async_get(hass)
    ent_reg = er.async_get(hass)
    switch_device = dev_reg.async_get_device(identifiers={(DOMAIN, switch_mac)})
    assert switch_device is not None
    assert er.async_entries_for_device(ent_reg, switch_device.id)

    # Switch is unadopted from the controller — it no longer appears in
    # get_devices() at all (not just marked offline).
    mock_client.get_devices = AsyncMock(
        return_value=[SAMPLE_DEVICE_AP, SAMPLE_DEVICE_GATEWAY]
    )
    coordinator = entry.runtime_data.coordinators[TEST_SITE_ID]
    await coordinator.async_refresh()
    await hass.async_block_till_done()

    assert dev_reg.async_get_device(identifiers={(DOMAIN, switch_mac)}) is None
    assert er.async_entries_for_device(ent_reg, switch_device.id) == []


async def test_prune_skips_when_coordinator_unhealthy(hass: HomeAssistant) -> None:
    """Test that a transient poll failure never triggers pruning.

    A failed poll must never look like "device gone" — coordinator.data is
    left untouched by DataUpdateCoordinator on failure, so pruning based on
    it would misinterpret a network blip as a device removal.
    """
    entry = _build_entry(hass)
    patcher, mock_client = _patch_api_client()

    with patcher:
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    switch_mac = "AA-BB-CC-DD-EE-02"
    dev_reg = dr.async_get(hass)
    assert dev_reg.async_get_device(identifiers={(DOMAIN, switch_mac)}) is not None

    mock_client.get_devices = AsyncMock(side_effect=OmadaApiError("Connection lost"))
    coordinator = entry.runtime_data.coordinators[TEST_SITE_ID]
    await coordinator.async_refresh()
    await hass.async_block_till_done()

    assert coordinator.last_update_success is False
    assert dev_reg.async_get_device(identifiers={(DOMAIN, switch_mac)}) is not None


async def test_prune_does_not_touch_selected_client_or_site_devices(
    hass: HomeAssistant,
) -> None:
    """Test that selected-client and site devices survive a prune pass.

    Client devices live in a separate OmadaClientCoordinator and are never
    present in a site coordinator's data["devices"], so a naive diff would
    misclassify a currently-selected client as "vanished infra". Their
    lifecycle stays owned by _cleanup_devices, not this pass.
    """
    client_mac = "11-22-33-44-55-AA"
    entry = _build_entry(
        hass,
        data_overrides={CONF_SELECTED_CLIENTS: [client_mac]},
    )
    patcher, _mock_client = _patch_api_client()

    with patcher:
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    dev_reg = dr.async_get(hass)
    client_device = dev_reg.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, client_mac)},
        name="Phone",
    )
    site_device = dev_reg.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, f"site_{TEST_SITE_ID}")},
        name="Test Site",
    )

    coordinator = entry.runtime_data.coordinators[TEST_SITE_ID]
    await coordinator.async_refresh()
    await hass.async_block_till_done()

    assert dev_reg.async_get(client_device.id) is not None
    assert dev_reg.async_get(site_device.id) is not None


async def test_prune_does_not_touch_selected_client_with_colon_format_mac(
    hass: HomeAssistant,
) -> None:
    """Test that a selected client survives a prune pass in real-world MAC format.

    Regression test for GH #25: the config flow stores CONF_SELECTED_CLIENTS
    using the raw colon-separated MAC exactly as returned by the Omada API
    (e.g. "0C:C4:13:1B:30:2F"), and client device identifiers are built from
    that same raw string. Comparing a hyphen-normalized selected-client set
    against a colon-format device identifier always misses, so a freshly
    created client device was immediately pruned as "stale infrastructure"
    on every setup.
    """
    client_mac = "0C:C4:13:1B:30:2F"
    entry = _build_entry(
        hass,
        data_overrides={CONF_SELECTED_CLIENTS: [client_mac]},
    )
    patcher, _mock_client = _patch_api_client()

    with patcher:
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    dev_reg = dr.async_get(hass)
    client_device = dev_reg.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, client_mac)},
        name="Pixel-6",
    )

    coordinator = entry.runtime_data.coordinators[TEST_SITE_ID]
    await coordinator.async_refresh()
    await hass.async_block_till_done()

    assert dev_reg.async_get(client_device.id) is not None


async def test_prune_no_runtime_data_is_safe(hass: HomeAssistant) -> None:
    """Test that pruning is safe when runtime_data is missing."""
    entry = _build_entry(hass)
    # Don't set up the entry — no runtime_data exists.
    _prune_stale_infra_devices(hass, entry)


async def test_prune_ignores_non_domain_identifiers(hass: HomeAssistant) -> None:
    """Test that devices with a non-DOMAIN identifier are left untouched.

    Mirrors the real-world merged-device case: a device can carry
    identifiers from another integration (e.g. "fritz") alongside ours —
    those identifiers must be skipped, not misread as an infra MAC.
    """
    entry = _build_entry(hass)
    patcher, _mock_client = _patch_api_client()

    with patcher:
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    dev_reg = dr.async_get(hass)
    other_device = dev_reg.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={("other_domain", "some_id")},
        name="Other Domain Device",
    )

    coordinator = entry.runtime_data.coordinators[TEST_SITE_ID]
    await coordinator.async_refresh()
    await hass.async_block_till_done()

    assert dev_reg.async_get(other_device.id) is not None


# ---------------------------------------------------------------------------
# _migrate_merged_devices tests
# ---------------------------------------------------------------------------


async def test_migrate_merged_devices_removes_multi_mac_device(
    hass: HomeAssistant,
) -> None:
    """Test that a device with 2+ non-site DOMAIN identifiers is removed.

    This mirrors the structural signature left by the pre-v1.8.1 IP-
    connections merge bug: a single HA device carrying multiple distinct
    Omada MACs. No legitimate code path creates this today, so it's always
    safe to remove — clean per-MAC devices get recreated on setup.
    """
    entry = _build_entry(hass)
    dev_reg = dr.async_get(hass)
    ent_reg = er.async_get(hass)

    mac_a = "AA-BB-CC-DD-EE-01"
    mac_b = "AA-BB-CC-DD-EE-02"
    merged_device = dev_reg.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, mac_a), (DOMAIN, mac_b)},
        name="Merged Device",
    )
    entity_entry = ent_reg.async_get_or_create(
        "sensor",
        DOMAIN,
        f"{mac_a}_cpu_util",
        config_entry=entry,
        device_id=merged_device.id,
    )

    _migrate_merged_devices(hass, entry)

    assert dev_reg.async_get(merged_device.id) is None
    assert ent_reg.async_get(entity_entry.entity_id) is None


async def test_migrate_merged_devices_leaves_single_identifier_devices_alone(
    hass: HomeAssistant,
) -> None:
    """Test that a normal single-MAC device is untouched."""
    entry = _build_entry(hass)
    dev_reg = dr.async_get(hass)
    device = dev_reg.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, "AA-BB-CC-DD-EE-01")},
        name="Office AP",
    )

    _migrate_merged_devices(hass, entry)

    assert dev_reg.async_get(device.id) is not None


async def test_migrate_merged_devices_ignores_site_identifier(
    hass: HomeAssistant,
) -> None:
    """Test that a site device (single site identifier) is untouched."""
    entry = _build_entry(hass)
    dev_reg = dr.async_get(hass)
    site_device = dev_reg.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, f"site_{TEST_SITE_ID}")},
        name="Test Site",
    )

    _migrate_merged_devices(hass, entry)

    assert dev_reg.async_get(site_device.id) is not None


async def test_setup_entry_recreates_clean_devices_after_merge(
    hass: HomeAssistant,
) -> None:
    """Test that setup migrates a merged device before platforms load.

    Registering the merged device before calling async_setup simulates the
    real-world case: a device that was already merged by the old bug before
    the user upgraded. After setup, it must be gone and replaced by clean,
    separate per-MAC devices — with no manual UI action required.
    """
    entry = _build_entry(hass)
    patcher, _mock_client = _patch_api_client()

    ap_mac = "AA-BB-CC-DD-EE-01"
    switch_mac = "AA-BB-CC-DD-EE-02"

    dev_reg = dr.async_get(hass)
    dev_reg.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, ap_mac), (DOMAIN, switch_mac)},
        name="Wohnzimmer",
    )

    with patcher:
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.LOADED

    # Each MAC now has its own device carrying exactly one identifier — the
    # merge is gone, replaced by clean, separate per-MAC devices.
    ap_device = dev_reg.async_get_device(identifiers={(DOMAIN, ap_mac)})
    switch_device = dev_reg.async_get_device(identifiers={(DOMAIN, switch_mac)})
    assert ap_device is not None
    assert switch_device is not None
    assert ap_device.identifiers == {(DOMAIN, ap_mac)}
    assert switch_device.identifiers == {(DOMAIN, switch_mac)}


# ---------------------------------------------------------------------------
# async_remove_config_entry_device — merged device fallback
# ---------------------------------------------------------------------------


async def test_remove_device_allows_merged_device(hass: HomeAssistant) -> None:
    """Test that a merged device can be manually removed even though one of
    its MACs is still actively reported by the coordinator.

    This is the defensive fallback for async_remove_config_entry_device:
    the "still active" block that protects normal single-MAC devices must
    never prevent removal of a device carrying multiple merged identifiers.
    """
    entry = _build_entry(hass)
    patcher, _ = _patch_api_client()

    with patcher:
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    dev_reg = dr.async_get(hass)
    # AA-BB-CC-DD-EE-01 is the live AP MAC (still in coordinator data);
    # FF-FF-FF-FF-FF-FF is a bogus second identifier simulating the merge.
    merged_device = dev_reg.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, "AA-BB-CC-DD-EE-01"), (DOMAIN, "FF-FF-FF-FF-FF-FF")},
        name="Merged Device",
    )

    result = await async_remove_config_entry_device(hass, entry, merged_device)
    assert result is True
