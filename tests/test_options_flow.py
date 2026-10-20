"""Tests for options flow update intervals step."""

from __future__ import annotations

import datetime as dt
from typing import TYPE_CHECKING
from unittest.mock import patch

from homeassistant.data_entry_flow import FlowResultType, InvalidData
import pytest

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.omada_open_api.const import (
    CONF_ACCESS_TOKEN,
    CONF_API_URL,
    CONF_APP_SCAN_INTERVAL,
    CONF_AUTO_DISCOVER_CLIENT_TRACKERS,
    CONF_AUTO_DISCOVERY_EXCLUDE_GUESTS,
    CONF_AUTO_DISCOVERY_EXCLUDE_LOCAL_MACS,
    CONF_AUTO_DISCOVERY_EXCLUDED_CLIENTS,
    CONF_AUTO_DISCOVERY_INCLUDE_WIRED,
    CONF_AUTO_DISCOVERY_REQUIRE_NAME,
    CONF_AUTO_DISCOVERY_RETENTION_DAYS,
    CONF_AUTO_DISCOVERY_SIGNAL_ATTRIBUTES,
    CONF_AUTO_DISCOVERY_SSIDS,
    CONF_CLIENT_ID,
    CONF_CLIENT_SCAN_INTERVAL,
    CONF_CLIENT_SECRET,
    CONF_DEVICE_SCAN_INTERVAL,
    CONF_DISCONNECT_TIMEOUT,
    CONF_ENABLE_THREAT_HEATMAP_SENSORS,
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
                CONF_CLIENT_SCAN_INTERVAL: 30,
                CONF_APP_SCAN_INTERVAL: 600,
            },
        )

    assert result["type"] == FlowResultType.CREATE_ENTRY

    # Verify saved values are in entry.options (not entry.data)
    assert entry.options[CONF_DEVICE_SCAN_INTERVAL] == 120
    assert entry.options[CONF_CLIENT_SCAN_INTERVAL] == 30
    assert entry.options[CONF_APP_SCAN_INTERVAL] == 600


async def test_update_intervals_rejects_too_frequent_polling(
    hass: HomeAssistant,
) -> None:
    """Test that cloud polling intervals below 30 seconds are rejected."""
    entry = _create_config_entry(hass)

    with patch("custom_components.omada_open_api.async_setup_entry", return_value=True):
        await hass.config_entries.async_setup(entry.entry_id)
        result = await hass.config_entries.options.async_init(entry.entry_id)
        result = await hass.config_entries.options.async_configure(
            result["flow_id"], {"next_step_id": "update_intervals"}
        )
        with pytest.raises(InvalidData, match=CONF_DEVICE_SCAN_INTERVAL):
            await hass.config_entries.options.async_configure(
                result["flow_id"],
                {
                    CONF_DEVICE_SCAN_INTERVAL: 29,
                    CONF_CLIENT_SCAN_INTERVAL: 30,
                    CONF_APP_SCAN_INTERVAL: 300,
                },
            )


# ---------------------------------------------------------------------------
# Update intervals step: preserves existing values
# ---------------------------------------------------------------------------


async def test_update_intervals_preserves_existing(hass: HomeAssistant) -> None:
    """Test that the form pre-fills with previously saved intervals."""
    entry = _create_config_entry(hass)
    # Store intervals in options where they belong
    hass.config_entries.async_update_entry(
        entry,
        options={
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


# ---------------------------------------------------------------------------
# Site entity settings step: threat heatmap toggle
# ---------------------------------------------------------------------------


async def test_options_menu_shows_site_entity_settings(hass: HomeAssistant) -> None:
    """Test that the options menu includes the site_entity_settings option."""
    entry = _create_config_entry(hass)

    with patch("custom_components.omada_open_api.async_setup_entry", return_value=True):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    result = await hass.config_entries.options.async_init(entry.entry_id)

    assert result["type"] == FlowResultType.MENU
    assert "site_entity_settings" in result["menu_options"]


async def test_site_entity_settings_defaults_to_enabled(hass: HomeAssistant) -> None:
    """Test the threat heatmap toggle defaults to True when unconfigured."""
    entry = _create_config_entry(hass)

    with patch("custom_components.omada_open_api.async_setup_entry", return_value=True):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {"next_step_id": "site_entity_settings"},
    )

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "site_entity_settings"
    schema_keys = list(result["data_schema"].schema)
    key = next(k for k in schema_keys if str(k) == CONF_ENABLE_THREAT_HEATMAP_SENSORS)
    assert key.default() is True


async def test_site_entity_settings_saves_value(hass: HomeAssistant) -> None:
    """Test submitting the site entity settings step saves the toggle."""
    entry = _create_config_entry(hass)

    with patch("custom_components.omada_open_api.async_setup_entry", return_value=True):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {"next_step_id": "site_entity_settings"},
    )

    with patch("custom_components.omada_open_api.async_setup_entry", return_value=True):
        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            {CONF_ENABLE_THREAT_HEATMAP_SENSORS: False},
        )

    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert entry.options[CONF_ENABLE_THREAT_HEATMAP_SENSORS] is False


async def test_auto_discovery_is_off_by_default_and_saves_choice(
    hass: HomeAssistant,
) -> None:
    """Discovery is opt-in; signal attributes default on when enabled."""
    entry = _create_config_entry(hass)
    with patch("custom_components.omada_open_api.async_setup_entry", return_value=True):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    menu = await hass.config_entries.options.async_init(entry.entry_id)
    form = await hass.config_entries.options.async_configure(
        menu["flow_id"], {"next_step_id": "tracker_settings"}
    )
    assert form["type"] == FlowResultType.FORM
    defaults = {
        k.schema: k.default() if callable(k.default) else k.default
        for k in form["data_schema"].schema
    }
    assert defaults[CONF_AUTO_DISCOVER_CLIENT_TRACKERS] is False
    assert defaults[CONF_AUTO_DISCOVERY_RETENTION_DAYS] == 30
    assert defaults[CONF_AUTO_DISCOVERY_INCLUDE_WIRED] is True
    assert defaults[CONF_AUTO_DISCOVERY_EXCLUDE_GUESTS] is True
    assert defaults[CONF_AUTO_DISCOVERY_EXCLUDE_LOCAL_MACS] is False
    assert defaults[CONF_AUTO_DISCOVERY_REQUIRE_NAME] is False
    assert defaults[CONF_AUTO_DISCOVERY_SIGNAL_ATTRIBUTES] is True

    with patch("custom_components.omada_open_api.async_setup_entry", return_value=True):
        result = await hass.config_entries.options.async_configure(
            form["flow_id"],
            {
                CONF_DISCONNECT_TIMEOUT: 5,
                CONF_AUTO_DISCOVER_CLIENT_TRACKERS: True,
                CONF_AUTO_DISCOVERY_RETENTION_DAYS: 45,
                CONF_AUTO_DISCOVERY_INCLUDE_WIRED: False,
                CONF_AUTO_DISCOVERY_EXCLUDE_GUESTS: False,
                CONF_AUTO_DISCOVERY_EXCLUDE_LOCAL_MACS: True,
                CONF_AUTO_DISCOVERY_REQUIRE_NAME: True,
                CONF_AUTO_DISCOVERY_EXCLUDED_CLIENTS: ["AA-BB-CC-DD-EE-FF"],
                CONF_AUTO_DISCOVERY_SIGNAL_ATTRIBUTES: True,
                CONF_AUTO_DISCOVERY_SSIDS: ["Home", "Guest"],
            },
        )
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert entry.options[CONF_AUTO_DISCOVER_CLIENT_TRACKERS] is True
    assert entry.options[CONF_AUTO_DISCOVERY_RETENTION_DAYS] == 45
    assert entry.options[CONF_AUTO_DISCOVERY_INCLUDE_WIRED] is False
    assert entry.options[CONF_AUTO_DISCOVERY_EXCLUDE_GUESTS] is False
    assert entry.options[CONF_AUTO_DISCOVERY_EXCLUDE_LOCAL_MACS] is True
    assert entry.options[CONF_AUTO_DISCOVERY_REQUIRE_NAME] is True
    assert entry.options[CONF_AUTO_DISCOVERY_EXCLUDED_CLIENTS] == ["AA-BB-CC-DD-EE-FF"]
    assert entry.options[CONF_AUTO_DISCOVERY_SIGNAL_ATTRIBUTES] is True
    assert entry.options[CONF_AUTO_DISCOVERY_SSIDS] == ["Home", "Guest"]
    assert entry.options[CONF_DISCONNECT_TIMEOUT] == 5


@pytest.mark.parametrize("retention_days", [-1, 3651])
async def test_auto_discovery_retention_rejects_out_of_range_values(
    hass: HomeAssistant,
    retention_days: int,
) -> None:
    """Retention accepts zero through ten years only."""
    entry = _create_config_entry(hass)
    with patch("custom_components.omada_open_api.async_setup_entry", return_value=True):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    menu = await hass.config_entries.options.async_init(entry.entry_id)
    form = await hass.config_entries.options.async_configure(
        menu["flow_id"], {"next_step_id": "tracker_settings"}
    )
    with pytest.raises(InvalidData, match=CONF_AUTO_DISCOVERY_RETENTION_DAYS):
        await hass.config_entries.options.async_configure(
            form["flow_id"],
            {
                CONF_DISCONNECT_TIMEOUT: 5,
                CONF_AUTO_DISCOVER_CLIENT_TRACKERS: True,
                CONF_AUTO_DISCOVERY_RETENTION_DAYS: retention_days,
                CONF_AUTO_DISCOVERY_INCLUDE_WIRED: True,
                CONF_AUTO_DISCOVERY_EXCLUDE_GUESTS: True,
                CONF_AUTO_DISCOVERY_EXCLUDE_LOCAL_MACS: False,
                CONF_AUTO_DISCOVERY_REQUIRE_NAME: False,
                CONF_AUTO_DISCOVERY_EXCLUDED_CLIENTS: [],
                CONF_AUTO_DISCOVERY_SIGNAL_ATTRIBUTES: True,
                CONF_AUTO_DISCOVERY_SSIDS: [],
            },
        )
