"""Tests for granular entity type toggles in options flow (Issue #11)."""

from __future__ import annotations

import inspect
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, patch

from homeassistant.helpers import entity_registry as er
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.omada_open_api.config_flow import OmadaOptionsFlowHandler
from custom_components.omada_open_api.const import (
    CONF_ACCESS_TOKEN,
    CONF_API_URL,
    CONF_CLIENT_ID,
    CONF_CLIENT_SECRET,
    CONF_ENABLE_CLIENT_BANDWIDTH_SENSORS,
    CONF_ENABLE_CLIENT_BLOCK_SWITCH,
    CONF_ENABLE_CLIENT_RECONNECT_BUTTON,
    CONF_ENABLE_CLIENT_SIGNAL_SENSORS,
    CONF_ENABLE_DEVICE_BANDWIDTH_SENSORS,
    CONF_ENABLE_DEVICE_CLIENT_COUNT_SENSORS,
    CONF_ENABLE_DEVICE_DIAGNOSTIC_SENSORS,
    CONF_ENABLE_DEVICE_RADIO_UTILIZATION_SENSORS,
    CONF_ENABLE_THREAT_HEATMAP_SENSORS,
    CONF_ENABLE_VPN_SENSORS,
    CONF_ENABLE_WAN_SPEED_TEST,
    CONF_OMADA_ID,
    CONF_REFRESH_TOKEN,
    CONF_SELECTED_APPLICATIONS,
    CONF_SELECTED_CLIENTS,
    CONF_SELECTED_SITES,
    CONF_TOKEN_EXPIRES_AT,
    DOMAIN,
)

from .conftest import (
    SAMPLE_DEVICE_AP,
    SAMPLE_DEVICE_GATEWAY,
    SAMPLE_DEVICE_SWITCH,
    TEST_API_URL,
    TEST_SITE_ID,
    TEST_SITE_NAME,
    _future_token_expiry,
)

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant


# ---------------------------------------------------------------------------
# Constants exist and have correct semantics
# ---------------------------------------------------------------------------


def test_toggle_constants_are_strings() -> None:
    """All toggle constants are string values."""
    assert isinstance(CONF_ENABLE_DEVICE_BANDWIDTH_SENSORS, str)
    assert isinstance(CONF_ENABLE_DEVICE_CLIENT_COUNT_SENSORS, str)
    assert isinstance(CONF_ENABLE_DEVICE_DIAGNOSTIC_SENSORS, str)
    assert isinstance(CONF_ENABLE_DEVICE_RADIO_UTILIZATION_SENSORS, str)
    assert isinstance(CONF_ENABLE_CLIENT_BANDWIDTH_SENSORS, str)
    assert isinstance(CONF_ENABLE_CLIENT_SIGNAL_SENSORS, str)
    assert isinstance(CONF_ENABLE_CLIENT_BLOCK_SWITCH, str)
    assert isinstance(CONF_ENABLE_CLIENT_RECONNECT_BUTTON, str)
    assert isinstance(CONF_ENABLE_VPN_SENSORS, str)
    assert isinstance(CONF_ENABLE_WAN_SPEED_TEST, str)


def test_toggle_constants_have_distinct_values() -> None:
    """All toggle constants have distinct string values."""
    values = [
        CONF_ENABLE_DEVICE_BANDWIDTH_SENSORS,
        CONF_ENABLE_DEVICE_CLIENT_COUNT_SENSORS,
        CONF_ENABLE_DEVICE_DIAGNOSTIC_SENSORS,
        CONF_ENABLE_DEVICE_RADIO_UTILIZATION_SENSORS,
        CONF_ENABLE_CLIENT_BANDWIDTH_SENSORS,
        CONF_ENABLE_CLIENT_SIGNAL_SENSORS,
        CONF_ENABLE_CLIENT_BLOCK_SWITCH,
        CONF_ENABLE_CLIENT_RECONNECT_BUTTON,
        CONF_ENABLE_VPN_SENSORS,
        CONF_ENABLE_WAN_SPEED_TEST,
    ]
    assert len(set(values)) == len(values)


# ---------------------------------------------------------------------------
# Options flow exposes the toggle steps
# ---------------------------------------------------------------------------


def test_options_flow_has_device_entity_settings_step() -> None:
    """OmadaOptionsFlowHandler has async_step_device_entity_settings."""
    assert hasattr(OmadaOptionsFlowHandler, "async_step_device_entity_settings")


def test_options_flow_has_client_entity_settings_step() -> None:
    """OmadaOptionsFlowHandler has async_step_client_entity_settings."""
    assert hasattr(OmadaOptionsFlowHandler, "async_step_client_entity_settings")


def test_options_flow_menu_includes_entity_settings() -> None:
    """The options flow init menu includes both entity settings steps."""
    source = inspect.getsource(
        OmadaOptionsFlowHandler.async_step_init  # type: ignore[attr-defined]
    )
    assert "device_entity_settings" in source
    assert "client_entity_settings" in source
    assert "site_entity_settings" in source


def test_options_flow_has_site_entity_settings_step() -> None:
    """OmadaOptionsFlowHandler has async_step_site_entity_settings."""
    assert hasattr(OmadaOptionsFlowHandler, "async_step_site_entity_settings")


def test_options_flow_has_gateway_entity_settings_step() -> None:
    """Gateway diagnostics and actions are configurable from options."""
    assert hasattr(OmadaOptionsFlowHandler, "async_step_gateway_entity_settings")
    source = inspect.getsource(
        OmadaOptionsFlowHandler.async_step_init  # type: ignore[attr-defined]
    )
    assert "gateway_entity_settings" in source


# ---------------------------------------------------------------------------
# Helper: shared mock API builder
# ---------------------------------------------------------------------------


def _build_mock_api(devices: list) -> AsyncMock:
    """Build a mock API client for integration tests."""
    mock = AsyncMock()
    mock.get_sites = AsyncMock(
        return_value=[{"siteId": TEST_SITE_ID, "name": TEST_SITE_NAME}]
    )
    mock.get_devices = AsyncMock(return_value=devices)
    mock.get_device_uplink_info = AsyncMock(return_value=[])
    mock.get_device_client_stats = AsyncMock(return_value=[])
    mock.get_ap_radios = AsyncMock(return_value={})
    mock.get_gateway_info = AsyncMock(return_value={})
    mock.get_site_ssids_comprehensive = AsyncMock(return_value=[])
    mock.get_ap_ssid_overrides = AsyncMock(return_value={"ssidOverrides": []})
    mock.get_poe_usage = AsyncMock(return_value=[])
    mock.get_switch_ports_poe = AsyncMock(return_value=[])
    mock.get_clients = AsyncMock(
        return_value={"data": [], "totalRows": 0, "currentPage": 1}
    )
    mock.get_gateway_wan_status = AsyncMock(return_value=[])
    mock.get_gateway_wan_speed_test_result = AsyncMock(return_value={})
    mock.get_vpn_s2s_stats = AsyncMock(return_value=[])
    mock.get_vpn_server_stats = AsyncMock(return_value=[])
    mock.get_vpn_client_stats = AsyncMock(return_value=[])
    mock.get_firmware_info = AsyncMock(return_value={})
    mock.get_switch_port_details = AsyncMock(return_value=[])
    mock.get_ap_radio_config = AsyncMock(return_value={})
    mock.get_ap_led_setting = AsyncMock(return_value={})
    mock.set_ap_radio_enabled = AsyncMock()
    mock.get_wlan_optimization_status = AsyncMock(
        return_value={"status": 0, "beforeIndex": 55, "afterIndex": 80}
    )
    mock.get_device_stats = AsyncMock(return_value=[])
    mock.check_write_access = AsyncMock(return_value=True)
    mock.get_threat_management = AsyncMock(return_value=[])
    mock.api_url = TEST_API_URL
    return mock


def _build_entry(hass: HomeAssistant, options: dict, entry_id: str) -> MockConfigEntry:
    """Create and add a config entry with given options."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        entry_id=entry_id,
        data={
            CONF_API_URL: TEST_API_URL,
            CONF_OMADA_ID: "test_omada_id",
            CONF_CLIENT_ID: "test_client_id",
            CONF_CLIENT_SECRET: "test_secret",
            CONF_ACCESS_TOKEN: "tok",
            CONF_REFRESH_TOKEN: "rtok",
            CONF_TOKEN_EXPIRES_AT: _future_token_expiry(),
            CONF_SELECTED_SITES: [TEST_SITE_ID],
            CONF_SELECTED_CLIENTS: [],
            CONF_SELECTED_APPLICATIONS: [],
        },
        options={
            CONF_SELECTED_CLIENTS: [],
            CONF_SELECTED_APPLICATIONS: [],
            **options,
        },
    )
    entry.add_to_hass(hass)
    return entry


# ---------------------------------------------------------------------------
# Entity creation is skipped when toggles are off
# ---------------------------------------------------------------------------


async def test_device_bandwidth_sensors_skipped_when_disabled(
    hass: HomeAssistant,
) -> None:
    """Daily download/upload sensors not created when bandwidth toggle is False."""
    entry = _build_entry(
        hass, {CONF_ENABLE_DEVICE_BANDWIDTH_SENSORS: False}, "test_toggle_bw"
    )
    mock = _build_mock_api([SAMPLE_DEVICE_SWITCH, SAMPLE_DEVICE_GATEWAY])

    sw_mac = SAMPLE_DEVICE_SWITCH["mac"]
    gw_mac = SAMPLE_DEVICE_GATEWAY["mac"]

    with patch("custom_components.omada_open_api.OmadaApiClient", return_value=mock):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    reg = er.async_get(hass)
    assert reg.async_get_entity_id("sensor", DOMAIN, f"{sw_mac}_daily_download") is None
    assert reg.async_get_entity_id("sensor", DOMAIN, f"{gw_mac}_daily_download") is None


async def test_device_diagnostic_sensors_skipped_when_disabled(
    hass: HomeAssistant,
) -> None:
    """CPU/memory/uptime sensors not created when diagnostic toggle is False."""
    entry = _build_entry(
        hass, {CONF_ENABLE_DEVICE_DIAGNOSTIC_SENSORS: False}, "test_toggle_diag"
    )
    mock = _build_mock_api([SAMPLE_DEVICE_AP])

    ap_mac = SAMPLE_DEVICE_AP["mac"]

    with patch("custom_components.omada_open_api.OmadaApiClient", return_value=mock):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    reg = er.async_get(hass)
    assert reg.async_get_entity_id("sensor", DOMAIN, f"{ap_mac}_cpu_util") is None
    assert reg.async_get_entity_id("sensor", DOMAIN, f"{ap_mac}_mem_util") is None


@pytest.mark.parametrize("toggle_key", [CONF_ENABLE_DEVICE_BANDWIDTH_SENSORS])
async def test_toggle_defaults_to_true_on_upgrade(
    hass: HomeAssistant, toggle_key: str
) -> None:
    """When toggle option absent from entry (existing user on upgrade), defaults to True."""
    # No toggle options set — simulates existing user who hasn't seen the new options yet
    entry = _build_entry(hass, {}, "test_toggle_default")
    mock = _build_mock_api([SAMPLE_DEVICE_SWITCH])

    sw_mac = SAMPLE_DEVICE_SWITCH["mac"]

    with patch("custom_components.omada_open_api.OmadaApiClient", return_value=mock):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    reg = er.async_get(hass)
    # daily_download should be created (default on)
    assert (
        reg.async_get_entity_id("sensor", DOMAIN, f"{sw_mac}_daily_download")
        is not None
    )


async def test_threat_heatmap_sensors_created_by_default(
    hass: HomeAssistant,
) -> None:
    """Threat heatmap sensors are created when the toggle is unset (default True)."""
    entry = _build_entry(hass, {}, "test_threat_heatmap_default")
    mock = _build_mock_api([SAMPLE_DEVICE_AP])

    with patch("custom_components.omada_open_api.OmadaApiClient", return_value=mock):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    reg = er.async_get(hass)
    assert (
        reg.async_get_entity_id(
            "sensor", DOMAIN, f"site_{TEST_SITE_ID}_threat_heatmap_daily"
        )
        is not None
    )
    assert (
        reg.async_get_entity_id(
            "sensor", DOMAIN, f"site_{TEST_SITE_ID}_threat_heatmap_hourly"
        )
        is not None
    )
    assert len(entry.runtime_data.threat_heatmap_coordinators) == 4


async def test_threat_heatmap_sensors_skipped_when_disabled(
    hass: HomeAssistant,
) -> None:
    """No threat heatmap coordinators/sensors are created when toggle is False."""
    entry = _build_entry(
        hass,
        {CONF_ENABLE_THREAT_HEATMAP_SENSORS: False},
        "test_threat_heatmap_disabled",
    )
    mock = _build_mock_api([SAMPLE_DEVICE_AP])

    with patch("custom_components.omada_open_api.OmadaApiClient", return_value=mock):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    reg = er.async_get(hass)
    assert (
        reg.async_get_entity_id(
            "sensor", DOMAIN, f"site_{TEST_SITE_ID}_threat_heatmap_daily"
        )
        is None
    )
    assert entry.runtime_data.threat_heatmap_coordinators == []
