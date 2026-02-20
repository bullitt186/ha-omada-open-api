"""Tests for Omada Open API integration setup and teardown."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, patch

from homeassistant.config_entries import ConfigEntryState
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.omada_open_api.api import OmadaApiAuthError
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
    assert "api_client" in runtime
    assert TEST_SITE_ID in runtime["coordinators"]


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
    assert len(entry.runtime_data["client_coordinators"]) == 1


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
    assert len(entry.runtime_data["app_traffic_coordinators"]) == 1


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
    assert len(entry.runtime_data["app_traffic_coordinators"]) == 0


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
    assert TEST_SITE_ID in entry.runtime_data["coordinators"]
    assert "nonexistent_site" not in entry.runtime_data["coordinators"]


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
