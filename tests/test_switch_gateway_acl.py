"""Tests for the gateway ACL coordinator, switch and option."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, patch

from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er
import pytest

from custom_components.omada_open_api.api import OmadaApiError
from custom_components.omada_open_api.const import (
    CONF_ENABLE_GATEWAY_ACL_SWITCHES,
    DOMAIN,
)
from custom_components.omada_open_api.coordinator import OmadaAclCoordinator
from custom_components.omada_open_api.switch import OmadaAclSwitch

from .conftest import TEST_SITE_ID, TEST_SITE_NAME
from .test_entity_toggles import _build_entry, _build_mock_api

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

RULE_ON = {"id": "acl-1", "name": "Block IoT", "status": True}
RULE_OFF = {"id": "acl-2", "name": "Guest to LAN", "status": False}


def _coordinator(hass: HomeAssistant, api: MagicMock) -> OmadaAclCoordinator:
    """Create an ACL coordinator with pre-filled data."""
    coordinator = OmadaAclCoordinator(hass, api, TEST_SITE_ID, TEST_SITE_NAME)
    coordinator.data = {"acl-1": RULE_ON, "acl-2": RULE_OFF}
    return coordinator


def test_option_constant() -> None:
    """The option key is stable (stored in config entry options)."""
    assert CONF_ENABLE_GATEWAY_ACL_SWITCHES == "enable_gateway_acl_switches"


async def test_coordinator_keys_rules_by_id(
    hass: HomeAssistant, mock_api_client: MagicMock
) -> None:
    """Coordinator data maps rule ID to rule."""
    mock_api_client.get_gateway_acls = AsyncMock(return_value=[RULE_ON, RULE_OFF])
    coordinator = OmadaAclCoordinator(
        hass, mock_api_client, TEST_SITE_ID, TEST_SITE_NAME
    )

    await coordinator.async_refresh()

    assert coordinator.last_update_success is True
    assert coordinator.data == {"acl-1": RULE_ON, "acl-2": RULE_OFF}
    mock_api_client.get_gateway_acls.assert_awaited_once_with(TEST_SITE_ID)


async def test_coordinator_api_error_marks_update_failed(
    hass: HomeAssistant, mock_api_client: MagicMock
) -> None:
    """An API error fails the refresh instead of raising."""
    mock_api_client.get_gateway_acls = AsyncMock(side_effect=OmadaApiError("boom"))
    coordinator = OmadaAclCoordinator(
        hass, mock_api_client, TEST_SITE_ID, TEST_SITE_NAME
    )

    await coordinator.async_refresh()

    assert coordinator.last_update_success is False


async def test_switch_identity_and_state(
    hass: HomeAssistant, mock_api_client: MagicMock
) -> None:
    """Switch mirrors the rule status and has a stable unique ID."""
    coordinator = _coordinator(hass, mock_api_client)
    on_switch = OmadaAclSwitch(coordinator, "acl-1")
    off_switch = OmadaAclSwitch(coordinator, "acl-2")

    assert on_switch.unique_id == f"{DOMAIN}_{TEST_SITE_ID}_acl_acl-1"
    assert on_switch.translation_key == "gateway_acl"
    assert on_switch.translation_placeholders == {"acl_name": "Block IoT"}
    assert on_switch.device_info == {"identifiers": {(DOMAIN, f"site_{TEST_SITE_ID}")}}
    assert on_switch.is_on is True
    assert off_switch.is_on is False


async def test_switch_unavailable_when_rule_removed(
    hass: HomeAssistant, mock_api_client: MagicMock
) -> None:
    """A rule deleted on the controller makes the entity unavailable."""
    coordinator = _coordinator(hass, mock_api_client)
    switch = OmadaAclSwitch(coordinator, "acl-1")
    coordinator.last_update_success = True
    assert switch.available is True

    coordinator.data = {"acl-2": RULE_OFF}

    assert switch.available is False
    assert switch.is_on is None


@pytest.mark.parametrize(
    ("method", "enabled"), [("turn_on", True), ("turn_off", False)]
)
async def test_switch_writes_status_and_refreshes(
    hass: HomeAssistant, mock_api_client: MagicMock, method: str, enabled: bool
) -> None:
    """Turning the switch on/off writes the status and refreshes the data."""
    mock_api_client.set_gateway_acl_status = AsyncMock()
    coordinator = _coordinator(hass, mock_api_client)
    coordinator.async_request_refresh = AsyncMock()  # type: ignore[method-assign]
    switch = OmadaAclSwitch(coordinator, "acl-1")

    await getattr(switch, f"async_{method}")()

    mock_api_client.set_gateway_acl_status.assert_awaited_once_with(
        TEST_SITE_ID, "acl-1", enabled=enabled
    )
    coordinator.async_request_refresh.assert_awaited_once()


async def test_switch_write_error_raises_homeassistant_error(
    hass: HomeAssistant, mock_api_client: MagicMock
) -> None:
    """API failures surface as HomeAssistantError."""
    mock_api_client.set_gateway_acl_status = AsyncMock(
        side_effect=OmadaApiError("denied")
    )
    switch = OmadaAclSwitch(_coordinator(hass, mock_api_client), "acl-1")

    with pytest.raises(HomeAssistantError):
        await switch.async_turn_off()


async def test_setup_creates_switches_when_option_on(hass: HomeAssistant) -> None:
    """With the option on (and write access) a switch per rule is created."""
    entry = _build_entry(
        hass, {CONF_ENABLE_GATEWAY_ACL_SWITCHES: True}, "test_acl_switch_on"
    )
    mock = _build_mock_api([])
    mock.get_gateway_acls = AsyncMock(return_value=[RULE_ON, RULE_OFF])

    with patch("custom_components.omada_open_api.OmadaApiClient", return_value=mock):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    reg = er.async_get(hass)
    assert (
        reg.async_get_entity_id("switch", DOMAIN, f"{DOMAIN}_{TEST_SITE_ID}_acl_acl-1")
        is not None
    )
    assert (
        reg.async_get_entity_id("switch", DOMAIN, f"{DOMAIN}_{TEST_SITE_ID}_acl_acl-2")
        is not None
    )


async def test_setup_skips_acl_polling_by_default(hass: HomeAssistant) -> None:
    """Without the option no ACL API call is made and no switch is created."""
    entry = _build_entry(hass, {}, "test_acl_switch_default")
    mock = _build_mock_api([])
    mock.get_gateway_acls = AsyncMock(return_value=[RULE_ON])

    with patch("custom_components.omada_open_api.OmadaApiClient", return_value=mock):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    mock.get_gateway_acls.assert_not_awaited()
    reg = er.async_get(hass)
    assert (
        reg.async_get_entity_id("switch", DOMAIN, f"{DOMAIN}_{TEST_SITE_ID}_acl_acl-1")
        is None
    )


async def test_setup_skips_switches_without_write_access(hass: HomeAssistant) -> None:
    """Read-only credentials never get ACL switches."""
    entry = _build_entry(
        hass, {CONF_ENABLE_GATEWAY_ACL_SWITCHES: True}, "test_acl_switch_ro"
    )
    mock = _build_mock_api([])
    mock.check_write_access = AsyncMock(return_value=False)
    mock.get_gateway_acls = AsyncMock(return_value=[RULE_ON])

    with patch("custom_components.omada_open_api.OmadaApiClient", return_value=mock):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    mock.get_gateway_acls.assert_not_awaited()
    reg = er.async_get(hass)
    assert (
        reg.async_get_entity_id("switch", DOMAIN, f"{DOMAIN}_{TEST_SITE_ID}_acl_acl-1")
        is None
    )


async def test_options_flow_stores_acl_switch_option(hass: HomeAssistant) -> None:
    """The gateway settings step persists the opt-in toggle (default off)."""
    entry = _build_entry(hass, {}, "test_acl_options")

    result = await hass.config_entries.options.async_init(
        entry.entry_id, context={"source": "init"}
    )
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": "gateway_entity_settings"}
    )
    schema_keys = {str(k): k for k in result["data_schema"].schema}
    assert schema_keys[CONF_ENABLE_GATEWAY_ACL_SWITCHES].default() is False

    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_ENABLE_GATEWAY_ACL_SWITCHES: True}
    )

    assert result["type"] == "create_entry"
    assert result["data"][CONF_ENABLE_GATEWAY_ACL_SWITCHES] is True
