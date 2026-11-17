"""Tests for the gateway ACL coordinator, switch and option."""

from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, patch

from homeassistant.config_entries import ConfigEntryState
from homeassistant.data_entry_flow import InvalidData
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er
import pytest

from custom_components.omada_open_api.api import OmadaApiError
from custom_components.omada_open_api.const import (
    CONF_ACL_SCAN_INTERVAL,
    CONF_ENABLE_GATEWAY_ACL_SWITCHES,
    DEFAULT_ACL_SCAN_INTERVAL,
    DOMAIN,
)
from custom_components.omada_open_api.coordinator import OmadaAclCoordinator
from custom_components.omada_open_api.switch import OmadaAclSwitch

from .conftest import TEST_SITE_ID, TEST_SITE_NAME
from .test_entity_toggles import _build_entry, _build_mock_api

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

RULE_ON = {"id": "acl-1", "description": "Block IoT", "status": True}
RULE_OFF = {"id": "acl-2", "description": "Guest to LAN", "status": False}


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


async def test_setup_survives_failing_acl_endpoint(hass: HomeAssistant) -> None:
    """A failing ACL endpoint must not break the switch platform (no data yet)."""
    entry = _build_entry(
        hass, {CONF_ENABLE_GATEWAY_ACL_SWITCHES: True}, "test_acl_switch_err"
    )
    mock = _build_mock_api([])
    mock.get_gateway_acls = AsyncMock(side_effect=OmadaApiError("General error"))

    with patch("custom_components.omada_open_api.OmadaApiClient", return_value=mock):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.LOADED


async def test_switch_name_falls_back_to_rule_id(
    hass: HomeAssistant, mock_api_client: MagicMock
) -> None:
    """A rule without description gets its ID as display name."""
    coordinator = _coordinator(hass, mock_api_client)
    coordinator.data = {"acl-9": {"id": "acl-9", "status": True}}

    switch = OmadaAclSwitch(coordinator, "acl-9")

    assert switch.translation_placeholders == {"acl_name": "acl-9"}


async def test_switch_name_starts_with_zero_padded_index(
    hass: HomeAssistant, mock_api_client: MagicMock
) -> None:
    """The index prefix keeps the entity list in the controller's order."""
    coordinator = _coordinator(hass, mock_api_client)
    coordinator.data = {
        "acl-4": {
            "id": "acl-4",
            "index": 4,
            "description": "Home Connect",
            "status": True,
        },
        "acl-12": {
            "id": "acl-12",
            "index": 12,
            "description": "Doorspy",
            "status": True,
        },
    }

    first = OmadaAclSwitch(coordinator, "acl-4")
    second = OmadaAclSwitch(coordinator, "acl-12")

    assert first.translation_placeholders == {"acl_name": "04 Home Connect"}
    assert second.translation_placeholders == {"acl_name": "12 Doorspy"}
    # Alphabetical order equals the controller order.
    assert (
        first.translation_placeholders["acl_name"]
        < second.translation_placeholders["acl_name"]
    )


async def test_switch_name_follows_reordering_in_controller(
    hass: HomeAssistant, mock_api_client: MagicMock
) -> None:
    """Moving a rule in Omada updates the index in the entity name."""
    coordinator = _coordinator(hass, mock_api_client)
    coordinator.data = {
        "acl-4": {
            "id": "acl-4",
            "index": 4,
            "description": "Home Connect",
            "status": True,
        }
    }
    switch = OmadaAclSwitch(coordinator, "acl-4")
    # The entity is not added to a platform here, so skip the state write.
    switch.async_write_ha_state = MagicMock()  # type: ignore[method-assign]

    coordinator.data = {
        "acl-4": {
            "id": "acl-4",
            "index": 7,
            "description": "Home Connect",
            "status": True,
        }
    }
    switch._handle_coordinator_update()

    assert switch.translation_placeholders == {"acl_name": "07 Home Connect"}


async def test_coordinator_default_and_custom_interval(
    hass: HomeAssistant, mock_api_client: MagicMock
) -> None:
    """The ACL poll interval defaults to 60 s and can be overridden."""
    default = OmadaAclCoordinator(hass, mock_api_client, TEST_SITE_ID, TEST_SITE_NAME)
    custom = OmadaAclCoordinator(
        hass, mock_api_client, TEST_SITE_ID, TEST_SITE_NAME, scan_interval=300
    )

    assert DEFAULT_ACL_SCAN_INTERVAL == 60
    assert default.update_interval == timedelta(seconds=60)
    assert custom.update_interval == timedelta(seconds=300)


async def test_setup_uses_configured_acl_interval(hass: HomeAssistant) -> None:
    """The acl_scan_interval option sets the coordinator's poll interval."""
    entry = _build_entry(
        hass,
        {CONF_ENABLE_GATEWAY_ACL_SWITCHES: True, CONF_ACL_SCAN_INTERVAL: 300},
        "test_acl_interval",
    )
    mock = _build_mock_api([])
    mock.get_gateway_acls = AsyncMock(return_value=[RULE_ON])

    with patch("custom_components.omada_open_api.OmadaApiClient", return_value=mock):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    coordinator = entry.runtime_data.acl_coordinators[TEST_SITE_ID]
    assert coordinator.update_interval == timedelta(seconds=300)


async def test_update_intervals_step_saves_acl_interval(hass: HomeAssistant) -> None:
    """The update-intervals options step stores the ACL interval."""
    entry = _build_entry(hass, {}, "test_acl_interval_flow")

    result = await hass.config_entries.options.async_init(
        entry.entry_id, context={"source": "init"}
    )
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": "update_intervals"}
    )
    keys = {str(k): k for k in result["data_schema"].schema}
    assert keys[CONF_ACL_SCAN_INTERVAL].default() == 60

    with patch("custom_components.omada_open_api.async_setup_entry", return_value=True):
        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            {
                "device_scan_interval": 60,
                "client_scan_interval": 30,
                "app_scan_interval": 300,
                CONF_ACL_SCAN_INTERVAL: 120,
            },
        )

    assert result["type"] == "create_entry"
    assert entry.options[CONF_ACL_SCAN_INTERVAL] == 120


async def test_coordinator_name_and_site_are_exposed(
    hass: HomeAssistant, mock_api_client: MagicMock
) -> None:
    """The coordinator is named per site and keeps hass, client and site."""
    coordinator = OmadaAclCoordinator(
        hass, mock_api_client, TEST_SITE_ID, TEST_SITE_NAME
    )

    assert coordinator.hass is hass
    assert coordinator.name == f"{DOMAIN}_{TEST_SITE_ID}_gateway_acls"
    assert coordinator.site_name == TEST_SITE_NAME
    assert coordinator.site_id == TEST_SITE_ID
    assert coordinator.api_client is mock_api_client


async def test_coordinator_error_message_names_the_site(
    hass: HomeAssistant, mock_api_client: MagicMock
) -> None:
    """A failed refresh explains which site's ACL list could not be read."""
    mock_api_client.get_gateway_acls = AsyncMock(side_effect=OmadaApiError("boom"))
    coordinator = OmadaAclCoordinator(
        hass, mock_api_client, TEST_SITE_ID, TEST_SITE_NAME
    )

    await coordinator.async_refresh()

    assert TEST_SITE_NAME in str(coordinator.last_exception)
    assert "boom" in str(coordinator.last_exception)


async def test_switch_for_unknown_rule_falls_back_to_its_id(
    hass: HomeAssistant, mock_api_client: MagicMock
) -> None:
    """A switch for a rule that is not in the data yet does not crash."""
    coordinator = _coordinator(hass, mock_api_client)

    switch = OmadaAclSwitch(coordinator, "not-there")

    assert switch.translation_placeholders == {"acl_name": "not-there"}
    assert switch.is_on is None


async def test_switch_name_uses_legacy_name_when_no_description(
    hass: HomeAssistant, mock_api_client: MagicMock
) -> None:
    """Rules that carry 'name' instead of 'description' keep their name."""
    coordinator = _coordinator(hass, mock_api_client)
    coordinator.data = {"acl-5": {"id": "acl-5", "name": "Legacy", "status": True}}

    switch = OmadaAclSwitch(coordinator, "acl-5")

    assert switch.translation_placeholders == {"acl_name": "Legacy"}


async def test_switch_write_error_carries_translation_details(
    hass: HomeAssistant, mock_api_client: MagicMock
) -> None:
    """The error shown to the user is translatable and names the rule."""
    mock_api_client.set_gateway_acl_status = AsyncMock(
        side_effect=OmadaApiError("denied")
    )
    switch = OmadaAclSwitch(_coordinator(hass, mock_api_client), "acl-1")

    with pytest.raises(HomeAssistantError) as raised:
        await switch.async_turn_off()

    assert raised.value.translation_domain == DOMAIN
    assert raised.value.translation_key == "gateway_acl_failed"
    assert raised.value.translation_placeholders == {"acl_name": "Block IoT"}


async def test_rules_added_later_get_a_switch_and_unload_stops_listening(
    hass: HomeAssistant,
) -> None:
    """A rule that appears after setup gets a switch; unload removes the listener."""
    entry = _build_entry(
        hass, {CONF_ENABLE_GATEWAY_ACL_SWITCHES: True}, "test_acl_listener"
    )
    mock = _build_mock_api([])
    mock.get_gateway_acls = AsyncMock(return_value=[RULE_ON])

    with patch("custom_components.omada_open_api.OmadaApiClient", return_value=mock):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    reg = er.async_get(hass)
    unique_id = f"{DOMAIN}_{TEST_SITE_ID}_acl_acl-2"
    assert reg.async_get_entity_id("switch", DOMAIN, unique_id) is None

    coordinator = entry.runtime_data.acl_coordinators[TEST_SITE_ID]
    coordinator.async_set_updated_data({"acl-1": RULE_ON, "acl-2": RULE_OFF})
    await hass.async_block_till_done()
    assert reg.async_get_entity_id("switch", DOMAIN, unique_id) is not None

    listeners_before = len(coordinator._listeners)
    await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert len(coordinator._listeners) < listeners_before


async def test_acl_interval_field_shows_saved_value_and_enforces_range(
    hass: HomeAssistant,
) -> None:
    """The ACL interval field defaults to the saved value and accepts 30-3600."""
    entry = _build_entry(hass, {CONF_ACL_SCAN_INTERVAL: 120}, "test_acl_range")

    result = await hass.config_entries.options.async_init(
        entry.entry_id, context={"source": "init"}
    )
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": "update_intervals"}
    )
    keys = {str(k): k for k in result["data_schema"].schema}
    assert keys[CONF_ACL_SCAN_INTERVAL].default() == 120

    base = {
        "device_scan_interval": 60,
        "client_scan_interval": 30,
        "app_scan_interval": 300,
    }
    for invalid in (29, 3601):
        with pytest.raises(InvalidData, match=CONF_ACL_SCAN_INTERVAL):
            await hass.config_entries.options.async_configure(
                result["flow_id"], {**base, CONF_ACL_SCAN_INTERVAL: invalid}
            )


async def test_acl_switch_option_form_shows_saved_value(hass: HomeAssistant) -> None:
    """The gateway settings form defaults to the saved ACL switch option."""
    entry = _build_entry(
        hass, {CONF_ENABLE_GATEWAY_ACL_SWITCHES: True}, "test_acl_option_default"
    )

    result = await hass.config_entries.options.async_init(
        entry.entry_id, context={"source": "init"}
    )
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": "gateway_entity_settings"}
    )

    keys = {str(k): k for k in result["data_schema"].schema}
    assert keys[CONF_ENABLE_GATEWAY_ACL_SWITCHES].default() is True
