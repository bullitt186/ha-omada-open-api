"""Tests for options flow update intervals step."""

from __future__ import annotations

import datetime as dt
from typing import TYPE_CHECKING
from unittest.mock import patch

from homeassistant.data_entry_flow import FlowResultType

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.omada_open_api.const import (
    CONF_ACCESS_TOKEN,
    CONF_API_URL,
    CONF_APP_SCAN_INTERVAL,
    CONF_CLIENT_ID,
    CONF_CLIENT_SCAN_INTERVAL,
    CONF_CLIENT_SECRET,
    CONF_DEVICE_SCAN_INTERVAL,
    CONF_OMADA_ID,
    CONF_REFRESH_TOKEN,
    CONF_SELECTED_SITES,
    CONF_TOKEN_EXPIRES_AT,
    DOMAIN,
)


def _future_token_expiry() -> str:
    """Return an ISO timestamp 1 hour in the future."""
    return (dt.datetime.now(dt.UTC) + dt.timedelta(hours=1)).isoformat()


def _create_config_entry(
    hass: HomeAssistant,
    **overrides: object,
) -> MockConfigEntry:
    """Create a mock config entry with default data."""
    data = {
        CONF_API_URL: "https://test.example.com",
        CONF_OMADA_ID: "test_omada",
        CONF_CLIENT_ID: "cid",
        CONF_CLIENT_SECRET: "csecret",
        CONF_ACCESS_TOKEN: "token",
        CONF_REFRESH_TOKEN: "rtoken",
        CONF_TOKEN_EXPIRES_AT: _future_token_expiry(),
        CONF_SELECTED_SITES: ["site_001"],
    }
    data.update(overrides)  # type: ignore[arg-type]

    entry = MockConfigEntry(domain=DOMAIN, data=data)
    entry.add_to_hass(hass)
    return entry


# ---------------------------------------------------------------------------
# Menu shows update_intervals option
# ---------------------------------------------------------------------------


async def test_options_menu_shows_update_intervals(hass: HomeAssistant) -> None:
    """Test that the options menu includes the update_intervals option."""
    entry = _create_config_entry(hass)

    with patch("custom_components.omada_open_api.async_setup_entry", return_value=True):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    result = await hass.config_entries.options.async_init(entry.entry_id)

    assert result["type"] == FlowResultType.MENU
    assert "update_intervals" in result["menu_options"]


# ---------------------------------------------------------------------------
# Update intervals step: defaults
# ---------------------------------------------------------------------------


async def test_update_intervals_shows_defaults(hass: HomeAssistant) -> None:
    """Test update intervals form shows default values when none configured."""
    entry = _create_config_entry(hass)

    with patch("custom_components.omada_open_api.async_setup_entry", return_value=True):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {"next_step_id": "update_intervals"},
    )

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "update_intervals"

    # Schema should have the three interval fields
    schema_keys = [str(k) for k in result["data_schema"].schema]
    assert CONF_DEVICE_SCAN_INTERVAL in schema_keys
    assert CONF_CLIENT_SCAN_INTERVAL in schema_keys
    assert CONF_APP_SCAN_INTERVAL in schema_keys


# ---------------------------------------------------------------------------
# Update intervals step: saves values
# ---------------------------------------------------------------------------


async def test_update_intervals_saves_values(hass: HomeAssistant) -> None:
    """Test that submitting update intervals saves values to config entry."""
    entry = _create_config_entry(hass)

    with patch("custom_components.omada_open_api.async_setup_entry", return_value=True):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {"next_step_id": "update_intervals"},
    )

    with patch("custom_components.omada_open_api.async_setup_entry", return_value=True):
        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            {
                CONF_DEVICE_SCAN_INTERVAL: 120,
                CONF_CLIENT_SCAN_INTERVAL: 15,
                CONF_APP_SCAN_INTERVAL: 600,
            },
        )

    assert result["type"] == FlowResultType.CREATE_ENTRY

    # Verify saved values
    assert entry.data[CONF_DEVICE_SCAN_INTERVAL] == 120
    assert entry.data[CONF_CLIENT_SCAN_INTERVAL] == 15
    assert entry.data[CONF_APP_SCAN_INTERVAL] == 600


# ---------------------------------------------------------------------------
# Update intervals step: preserves existing values
# ---------------------------------------------------------------------------


async def test_update_intervals_preserves_existing(hass: HomeAssistant) -> None:
    """Test that the form pre-fills with previously saved intervals."""
    entry = _create_config_entry(
        hass,
        **{
            CONF_DEVICE_SCAN_INTERVAL: 90,
            CONF_CLIENT_SCAN_INTERVAL: 45,
            CONF_APP_SCAN_INTERVAL: 180,
        },
    )

    with patch("custom_components.omada_open_api.async_setup_entry", return_value=True):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {"next_step_id": "update_intervals"},
    )

    assert result["type"] == FlowResultType.FORM
    # Verify defaults reflect existing config
    for key in result["data_schema"].schema:
        if str(key) == CONF_DEVICE_SCAN_INTERVAL:
            assert key.default() == 90
        elif str(key) == CONF_CLIENT_SCAN_INTERVAL:
            assert key.default() == 45
        elif str(key) == CONF_APP_SCAN_INTERVAL:
            assert key.default() == 180
