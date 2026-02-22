"""Tests for the Omada Open API diagnostics platform."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, patch

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.omada_open_api.const import (
    CONF_ACCESS_TOKEN,
    CONF_API_URL,
    CONF_CLIENT_ID,
    CONF_CLIENT_SECRET,
    CONF_OMADA_ID,
    CONF_REFRESH_TOKEN,
    CONF_SELECTED_APPLICATIONS,
    CONF_SELECTED_CLIENTS,
    CONF_SELECTED_SITES,
    CONF_TOKEN_EXPIRES_AT,
    DOMAIN,
)
from custom_components.omada_open_api.diagnostics import (
    async_get_config_entry_diagnostics,
)

from .conftest import (
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


def _build_entry(hass: HomeAssistant) -> MockConfigEntry:
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
    entry = MockConfigEntry(domain=DOMAIN, data=data, entry_id="diag_entry")
    entry.add_to_hass(hass)
    return entry


def _patch_api_client(**overrides):
    """Return a context manager that patches OmadaApiClient construction."""
    mock_instance = MagicMock()
    mock_instance.api_url = TEST_API_URL
    mock_instance.get_sites = AsyncMock(return_value=_SITE_LIST)
    mock_instance.get_devices = AsyncMock(return_value=_DEVICES)
    mock_instance.get_device_uplink_info = AsyncMock(return_value=SAMPLE_UPLINK_INFO)
    mock_instance.get_clients = AsyncMock(
        return_value={"data": [], "totalRows": 0, "currentPage": 1}
    )
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
    mock_instance.get_device_stats = AsyncMock(return_value=[])

    for key, value in overrides.items():
        setattr(mock_instance, key, value)

    return patch(
        "custom_components.omada_open_api.OmadaApiClient",
        return_value=mock_instance,
    ), mock_instance


# ---------------------------------------------------------------------------
# Diagnostics tests
# ---------------------------------------------------------------------------


async def test_diagnostics_basic(hass: HomeAssistant) -> None:
    """Test that diagnostics returns expected structure."""
    entry = _build_entry(hass)
    patcher, _ = _patch_api_client()

    with patcher:
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    result = await async_get_config_entry_diagnostics(hass, entry)

    assert "entry_data" in result
    assert "entry_options" in result
    assert "has_write_access" in result
    assert "site_coordinators" in result
    assert "client_coordinators" in result
    assert "app_traffic_coordinators" in result
    assert "site_devices" in result

    # Write access should be True (default mock)
    assert result["has_write_access"] is True


async def test_diagnostics_redacts_sensitive_data(hass: HomeAssistant) -> None:
    """Test that sensitive fields are redacted in diagnostics output."""
    entry = _build_entry(hass)
    patcher, _ = _patch_api_client()

    with patcher:
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    result = await async_get_config_entry_diagnostics(hass, entry)

    entry_data = result["entry_data"]
    assert entry_data[CONF_ACCESS_TOKEN] == "**REDACTED**"
    assert entry_data[CONF_REFRESH_TOKEN] == "**REDACTED**"
    assert entry_data[CONF_CLIENT_ID] == "**REDACTED**"
    assert entry_data[CONF_CLIENT_SECRET] == "**REDACTED**"
    assert entry_data[CONF_TOKEN_EXPIRES_AT] == "**REDACTED**"

    # Non-sensitive data should NOT be redacted
    assert entry_data[CONF_API_URL] == TEST_API_URL
    assert entry_data[CONF_OMADA_ID] == TEST_OMADA_ID


async def test_diagnostics_coordinator_summary(hass: HomeAssistant) -> None:
    """Test that coordinator data summaries are accurate."""
    entry = _build_entry(hass)
    patcher, _ = _patch_api_client()

    with patcher:
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    result = await async_get_config_entry_diagnostics(hass, entry)

    # Site coordinator should exist for our test site
    site_coords = result["site_coordinators"]
    assert TEST_SITE_ID in site_coords

    site_data = site_coords[TEST_SITE_ID]
    assert site_data["site_name"] == TEST_SITE_NAME
    assert site_data["last_update_success"] is True
    assert site_data["device_count"] == 3  # AP + Switch + Gateway
    assert site_data["device_types"]["ap"] == 1
    assert site_data["device_types"]["switch"] == 1
    assert site_data["device_types"]["gateway"] == 1


async def test_diagnostics_no_runtime_data(hass: HomeAssistant) -> None:
    """Test diagnostics handles missing runtime_data gracefully."""
    entry = _build_entry(hass)
    # Don't set up the entry, so no runtime_data
    entry.runtime_data = None

    result = await async_get_config_entry_diagnostics(hass, entry)

    assert result["has_write_access"] is False
    assert result["site_coordinators"] == {}
    assert result["client_coordinators"] == []
    assert result["app_traffic_coordinators"] == []
    assert result["device_stats_coordinators"] == []


async def test_diagnostics_with_client_and_app_coordinators(
    hass: HomeAssistant,
) -> None:
    """Test diagnostics includes client, app, and device stats coordinators."""
    data = {
        CONF_API_URL: TEST_API_URL,
        CONF_OMADA_ID: TEST_OMADA_ID,
        CONF_CLIENT_ID: TEST_CLIENT_ID,
        CONF_CLIENT_SECRET: TEST_CLIENT_SECRET,
        CONF_ACCESS_TOKEN: "valid_token",
        CONF_REFRESH_TOKEN: "valid_refresh",
        CONF_TOKEN_EXPIRES_AT: _future_token_expiry(),
        CONF_SELECTED_SITES: [TEST_SITE_ID],
        CONF_SELECTED_CLIENTS: ["11-22-33-44-55-AA"],
        CONF_SELECTED_APPLICATIONS: [{"applicationId": 1, "name": "YouTube"}],
    }
    entry = MockConfigEntry(domain=DOMAIN, data=data, entry_id="diag_full")
    entry.add_to_hass(hass)
    patcher, _ = _patch_api_client()

    with patcher:
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    result = await async_get_config_entry_diagnostics(hass, entry)

    # Client coordinators should be populated.
    assert len(result["client_coordinators"]) > 0
    client_summary = result["client_coordinators"][0]
    assert "site_name" in client_summary
    assert "client_count" in client_summary
    assert "last_update_success" in client_summary

    # App traffic coordinators should be populated.
    assert len(result["app_traffic_coordinators"]) > 0
    app_summary = result["app_traffic_coordinators"][0]
    assert "site_name" in app_summary
    assert "tracked_clients" in app_summary

    # Device stats coordinators should be populated.
    assert len(result["device_stats_coordinators"]) > 0
    stats_summary = result["device_stats_coordinators"][0]
    assert "site_name" in stats_summary
    assert "tracked_devices" in stats_summary
