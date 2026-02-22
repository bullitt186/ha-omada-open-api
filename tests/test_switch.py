"""Tests for Omada switch entities (PoE and client block)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

from custom_components.omada_open_api.api import OmadaApiError
from custom_components.omada_open_api.clients import process_client
from custom_components.omada_open_api.const import DOMAIN
from custom_components.omada_open_api.coordinator import (
    OmadaClientCoordinator,
    OmadaSiteCoordinator,
)
from custom_components.omada_open_api.switch import (
    OmadaClientBlockSwitch,
    OmadaLedSwitch,
    OmadaPoeSwitch,
    async_setup_entry,
)

from .conftest import SAMPLE_CLIENT_WIRELESS, TEST_SITE_ID, TEST_SITE_NAME

# ---------------------------------------------------------------------------
# Sample data
# ---------------------------------------------------------------------------

SAMPLE_PORT_ENABLED = {
    "switch_mac": "AA-BB-CC-DD-EE-02",
    "switch_name": "Core Switch",
    "port": 1,
    "port_name": "Port 1",
    "poe_enabled": True,
    "power": 12.5,
    "voltage": 53.2,
    "current": 235.0,
    "poe_status": 1.0,
    "pd_class": "Class 4",
    "poe_display_type": 4,
    "connected_status": 0,
}

SAMPLE_PORT_DISABLED = {
    "switch_mac": "AA-BB-CC-DD-EE-02",
    "switch_name": "Core Switch",
    "port": 2,
    "port_name": "Port 2",
    "poe_enabled": False,
    "power": 0.0,
    "voltage": 0.0,
    "current": 0.0,
    "poe_status": 0.0,
    "pd_class": "",
    "poe_display_type": 4,
    "connected_status": 1,
}


def _build_coordinator_data(
    poe_ports: dict | None = None,
) -> dict:
    """Build coordinator data dict with PoE ports."""
    return {
        "devices": {},
        "poe_ports": poe_ports or {},
        "poe_budget": {},
        "site_id": TEST_SITE_ID,
        "site_name": TEST_SITE_NAME,
    }


def _create_switch(
    hass: HomeAssistant,
    port_key: str,
    poe_ports: dict,
) -> OmadaPoeSwitch:
    """Create an OmadaPoeSwitch with a mock coordinator."""
    api_client = MagicMock()
    api_client.set_port_profile_override = AsyncMock()
    api_client.set_port_poe_mode = AsyncMock()

    coordinator = OmadaSiteCoordinator(
        hass=hass,
        api_client=api_client,
        site_id=TEST_SITE_ID,
        site_name=TEST_SITE_NAME,
    )
    coordinator.data = _build_coordinator_data(poe_ports)

    return OmadaPoeSwitch(coordinator=coordinator, port_key=port_key)


# ---------------------------------------------------------------------------
# Initialization & identity
# ---------------------------------------------------------------------------


def test_unique_id(hass: HomeAssistant) -> None:
    """Test unique ID format."""
    switch = _create_switch(
        hass, "AA-BB-CC-DD-EE-02_1", {"AA-BB-CC-DD-EE-02_1": SAMPLE_PORT_ENABLED}
    )
    assert switch.unique_id == "AA-BB-CC-DD-EE-02_port1_poe"


def test_name(hass: HomeAssistant) -> None:
    """Test entity name."""
    switch = _create_switch(
        hass, "AA-BB-CC-DD-EE-02_1", {"AA-BB-CC-DD-EE-02_1": SAMPLE_PORT_ENABLED}
    )
    assert switch.translation_key == "poe"
    assert switch.translation_placeholders == {"port_name": "Port 1"}


def test_device_info(hass: HomeAssistant) -> None:
    """Test device info links to parent switch."""
    switch = _create_switch(
        hass, "AA-BB-CC-DD-EE-02_1", {"AA-BB-CC-DD-EE-02_1": SAMPLE_PORT_ENABLED}
    )
    assert switch.device_info == {"identifiers": {(DOMAIN, "AA-BB-CC-DD-EE-02")}}


# ---------------------------------------------------------------------------
# State: is_on
# ---------------------------------------------------------------------------


def test_is_on_enabled(hass: HomeAssistant) -> None:
    """Test is_on when PoE is enabled."""
    switch = _create_switch(
        hass, "AA-BB-CC-DD-EE-02_1", {"AA-BB-CC-DD-EE-02_1": SAMPLE_PORT_ENABLED}
    )
    assert switch.is_on is True


def test_is_on_disabled(hass: HomeAssistant) -> None:
    """Test is_on when PoE is disabled."""
    switch = _create_switch(
        hass, "AA-BB-CC-DD-EE-02_2", {"AA-BB-CC-DD-EE-02_2": SAMPLE_PORT_DISABLED}
    )
    assert switch.is_on is False


def test_is_on_missing_port(hass: HomeAssistant) -> None:
    """Test is_on when port data is missing."""
    switch = _create_switch(hass, "AA-BB-CC-DD-EE-02_1", {})
    assert switch.is_on is None


# ---------------------------------------------------------------------------
# Extra state attributes
# ---------------------------------------------------------------------------


def test_extra_state_attributes(hass: HomeAssistant) -> None:
    """Test extra state attributes with port data."""
    switch = _create_switch(
        hass, "AA-BB-CC-DD-EE-02_1", {"AA-BB-CC-DD-EE-02_1": SAMPLE_PORT_ENABLED}
    )
    attrs = switch.extra_state_attributes
    assert attrs["port"] == 1
    assert attrs["port_name"] == "Port 1"
    assert attrs["power"] == 12.5
    assert attrs["voltage"] == 53.2
    assert attrs["current"] == 235.0


def test_extra_state_attributes_missing_port(hass: HomeAssistant) -> None:
    """Test extra state attributes when port data is missing."""
    switch = _create_switch(hass, "AA-BB-CC-DD-EE-02_1", {})
    assert switch.extra_state_attributes == {}


# ---------------------------------------------------------------------------
# Availability
# ---------------------------------------------------------------------------


def test_available_with_data(hass: HomeAssistant) -> None:
    """Test entity is available when port data exists."""
    switch = _create_switch(
        hass, "AA-BB-CC-DD-EE-02_1", {"AA-BB-CC-DD-EE-02_1": SAMPLE_PORT_ENABLED}
    )
    # Simulate successful update.
    switch.coordinator.last_update_success = True
    assert switch.available is True


def test_unavailable_missing_port(hass: HomeAssistant) -> None:
    """Test entity is unavailable when port data is missing."""
    switch = _create_switch(hass, "AA-BB-CC-DD-EE-02_1", {})
    switch.coordinator.last_update_success = True
    assert switch.available is False


def test_unavailable_coordinator_failure(hass: HomeAssistant) -> None:
    """Test entity is unavailable when coordinator fails."""
    switch = _create_switch(
        hass, "AA-BB-CC-DD-EE-02_1", {"AA-BB-CC-DD-EE-02_1": SAMPLE_PORT_ENABLED}
    )
    switch.coordinator.last_update_success = False
    assert switch.available is False


# ---------------------------------------------------------------------------
# Turn on / turn off
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_turn_on(hass: HomeAssistant) -> None:
    """Test turning PoE on enables profile override and sets PoE mode."""
    switch = _create_switch(
        hass, "AA-BB-CC-DD-EE-02_1", {"AA-BB-CC-DD-EE-02_1": SAMPLE_PORT_ENABLED}
    )
    api = switch.coordinator.api_client

    with patch.object(switch.coordinator, "async_request_refresh", new=AsyncMock()):
        await switch.async_turn_on()

    api.set_port_profile_override.assert_awaited_once_with(
        TEST_SITE_ID, "AA-BB-CC-DD-EE-02", 1, enable=True
    )
    api.set_port_poe_mode.assert_awaited_once_with(
        TEST_SITE_ID, "AA-BB-CC-DD-EE-02", 1, poe_enabled=True
    )


@pytest.mark.asyncio
async def test_turn_off(hass: HomeAssistant) -> None:
    """Test turning PoE off enables profile override and disables PoE mode."""
    switch = _create_switch(
        hass, "AA-BB-CC-DD-EE-02_1", {"AA-BB-CC-DD-EE-02_1": SAMPLE_PORT_ENABLED}
    )
    api = switch.coordinator.api_client

    with patch.object(switch.coordinator, "async_request_refresh", new=AsyncMock()):
        await switch.async_turn_off()

    api.set_port_profile_override.assert_awaited_once_with(
        TEST_SITE_ID, "AA-BB-CC-DD-EE-02", 1, enable=True
    )
    api.set_port_poe_mode.assert_awaited_once_with(
        TEST_SITE_ID, "AA-BB-CC-DD-EE-02", 1, poe_enabled=False
    )


@pytest.mark.asyncio
async def test_turn_on_api_error(hass: HomeAssistant) -> None:
    """Test turn_on handles API errors gracefully."""
    switch = _create_switch(
        hass, "AA-BB-CC-DD-EE-02_1", {"AA-BB-CC-DD-EE-02_1": SAMPLE_PORT_ENABLED}
    )
    api = switch.coordinator.api_client
    api.set_port_profile_override.side_effect = OmadaApiError("Profile override failed")

    with patch.object(switch.coordinator, "async_request_refresh", new=AsyncMock()):
        await switch.async_turn_on()

    # PoE mode should NOT have been called since profile override failed.
    api.set_port_poe_mode.assert_not_awaited()


@pytest.mark.asyncio
async def test_turn_off_poe_mode_error(hass: HomeAssistant) -> None:
    """Test turn_off handles PoE mode API error gracefully."""
    switch = _create_switch(
        hass, "AA-BB-CC-DD-EE-02_1", {"AA-BB-CC-DD-EE-02_1": SAMPLE_PORT_ENABLED}
    )
    api = switch.coordinator.api_client
    api.set_port_poe_mode.side_effect = OmadaApiError("PoE mode failed")

    with patch.object(switch.coordinator, "async_request_refresh", new=AsyncMock()):
        await switch.async_turn_off()

    # Profile override was called, but PoE mode failed.
    api.set_port_profile_override.assert_awaited_once()
    api.set_port_poe_mode.assert_awaited_once()


@pytest.mark.asyncio
async def test_turn_on_poe_permissions_error(hass: HomeAssistant) -> None:
    """Test PoE permissions error (-1007) logs a warning instead of exception."""
    switch = _create_switch(
        hass, "AA-BB-CC-DD-EE-02_1", {"AA-BB-CC-DD-EE-02_1": SAMPLE_PORT_ENABLED}
    )
    api = switch.coordinator.api_client
    api.set_port_profile_override.side_effect = OmadaApiError(
        "No permission", error_code=-1007
    )

    with patch.object(switch.coordinator, "async_request_refresh", new=AsyncMock()):
        await switch.async_turn_on()

    # PoE mode should NOT be called since profile override failed with permissions.
    api.set_port_poe_mode.assert_not_awaited()


@pytest.mark.asyncio
async def test_turn_off_poe_permissions_error_1005(hass: HomeAssistant) -> None:
    """Test PoE permissions error (-1005) logs a warning instead of exception."""
    switch = _create_switch(
        hass, "AA-BB-CC-DD-EE-02_1", {"AA-BB-CC-DD-EE-02_1": SAMPLE_PORT_ENABLED}
    )
    api = switch.coordinator.api_client
    api.set_port_poe_mode.side_effect = OmadaApiError("Access denied", error_code=-1005)

    with patch.object(switch.coordinator, "async_request_refresh", new=AsyncMock()):
        await switch.async_turn_off()

    # Profile override was called; PoE mode failed with permissions.
    api.set_port_profile_override.assert_awaited_once()
    api.set_port_poe_mode.assert_awaited_once()


@pytest.mark.asyncio
async def test_turn_on_refreshes_coordinator(hass: HomeAssistant) -> None:
    """Test that successful turn_on triggers coordinator refresh."""
    switch = _create_switch(
        hass, "AA-BB-CC-DD-EE-02_1", {"AA-BB-CC-DD-EE-02_1": SAMPLE_PORT_ENABLED}
    )

    with patch.object(
        switch.coordinator, "async_request_refresh", new=AsyncMock()
    ) as mock_refresh:
        await switch.async_turn_on()

    mock_refresh.assert_awaited_once()


@pytest.mark.asyncio
async def test_state_reflects_coordinator_update(hass: HomeAssistant) -> None:
    """Test that state changes when coordinator data changes."""
    poe_ports = {"AA-BB-CC-DD-EE-02_1": {**SAMPLE_PORT_ENABLED}}
    switch = _create_switch(hass, "AA-BB-CC-DD-EE-02_1", poe_ports)

    assert switch.is_on is True

    # Simulate coordinator update disabling PoE.
    switch.coordinator.data["poe_ports"]["AA-BB-CC-DD-EE-02_1"]["poe_enabled"] = False
    assert switch.is_on is False


# ===========================================================================
# OmadaClientBlockSwitch tests
# ===========================================================================

WIRELESS_MAC = "11-22-33-44-55-AA"
WIRED_MAC = "11-22-33-44-55-BB"


def _build_client_coordinator(
    hass: HomeAssistant,
    clients: dict[str, dict[str, Any]] | None = None,
) -> OmadaClientCoordinator:
    """Create a client coordinator with mock data."""
    coordinator = OmadaClientCoordinator(
        hass=hass,
        api_client=MagicMock(),
        site_id=TEST_SITE_ID,
        site_name=TEST_SITE_NAME,
        selected_client_macs=[WIRELESS_MAC, WIRED_MAC],
    )
    coordinator.data = clients or {}
    coordinator.api_client.block_client = AsyncMock()
    coordinator.api_client.unblock_client = AsyncMock()
    return coordinator


def _create_block_switch(
    hass: HomeAssistant,
    client_mac: str,
    clients: dict[str, dict[str, Any]],
) -> OmadaClientBlockSwitch:
    """Create an OmadaClientBlockSwitch entity."""
    coordinator = _build_client_coordinator(hass, clients)
    return OmadaClientBlockSwitch(coordinator=coordinator, client_mac=client_mac)


async def test_block_switch_unique_id(hass: HomeAssistant) -> None:
    """Test block switch unique ID format."""
    data = process_client(SAMPLE_CLIENT_WIRELESS)
    switch = _create_block_switch(hass, WIRELESS_MAC, {WIRELESS_MAC: data})
    assert switch.unique_id == f"omada_open_api_{WIRELESS_MAC}_block"


async def test_block_switch_name(hass: HomeAssistant) -> None:
    """Test block switch name includes client name."""
    data = process_client(SAMPLE_CLIENT_WIRELESS)
    switch = _create_block_switch(hass, WIRELESS_MAC, {WIRELESS_MAC: data})
    assert switch.translation_key == "network_access"


async def test_block_switch_is_on_not_blocked(hass: HomeAssistant) -> None:
    """Test switch is ON when client is NOT blocked."""
    data = process_client(SAMPLE_CLIENT_WIRELESS)
    switch = _create_block_switch(hass, WIRELESS_MAC, {WIRELESS_MAC: data})
    assert switch.is_on is True


async def test_block_switch_is_on_blocked(hass: HomeAssistant) -> None:
    """Test switch is OFF when client IS blocked."""
    raw = dict(SAMPLE_CLIENT_WIRELESS)
    raw["blocked"] = True
    data = process_client(raw)
    switch = _create_block_switch(hass, WIRELESS_MAC, {WIRELESS_MAC: data})
    assert switch.is_on is False


async def test_block_switch_is_on_missing(hass: HomeAssistant) -> None:
    """Test switch returns None when client missing."""
    switch = _create_block_switch(hass, WIRELESS_MAC, {})
    assert switch.is_on is None


async def test_block_switch_available(hass: HomeAssistant) -> None:
    """Test switch available when client exists."""
    data = process_client(SAMPLE_CLIENT_WIRELESS)
    switch = _create_block_switch(hass, WIRELESS_MAC, {WIRELESS_MAC: data})
    assert switch.available is True


async def test_block_switch_unavailable_missing(hass: HomeAssistant) -> None:
    """Test switch unavailable when client missing."""
    switch = _create_block_switch(hass, WIRELESS_MAC, {})
    assert switch.available is False


async def test_block_switch_unavailable_coordinator_failure(
    hass: HomeAssistant,
) -> None:
    """Test switch unavailable on coordinator failure."""
    data = process_client(SAMPLE_CLIENT_WIRELESS)
    switch = _create_block_switch(hass, WIRELESS_MAC, {WIRELESS_MAC: data})
    switch.coordinator.last_update_success = False
    assert switch.available is False


async def test_block_switch_turn_off_blocks(hass: HomeAssistant) -> None:
    """Test turning switch OFF blocks the client."""
    data = process_client(SAMPLE_CLIENT_WIRELESS)
    coordinator = _build_client_coordinator(hass, {WIRELESS_MAC: data})
    switch = OmadaClientBlockSwitch(coordinator=coordinator, client_mac=WIRELESS_MAC)

    with patch.object(
        switch.coordinator, "async_request_refresh", new=AsyncMock()
    ) as mock_refresh:
        await switch.async_turn_off()

    coordinator.api_client.block_client.assert_called_once_with(
        TEST_SITE_ID, WIRELESS_MAC
    )
    mock_refresh.assert_awaited_once()


async def test_block_switch_turn_on_unblocks(hass: HomeAssistant) -> None:
    """Test turning switch ON unblocks the client."""
    raw = dict(SAMPLE_CLIENT_WIRELESS)
    raw["blocked"] = True
    data = process_client(raw)
    coordinator = _build_client_coordinator(hass, {WIRELESS_MAC: data})
    switch = OmadaClientBlockSwitch(coordinator=coordinator, client_mac=WIRELESS_MAC)

    with patch.object(
        switch.coordinator, "async_request_refresh", new=AsyncMock()
    ) as mock_refresh:
        await switch.async_turn_on()

    coordinator.api_client.unblock_client.assert_called_once_with(
        TEST_SITE_ID, WIRELESS_MAC
    )
    mock_refresh.assert_awaited_once()


async def test_block_switch_turn_off_api_error(hass: HomeAssistant) -> None:
    """Test block switch handles API error gracefully."""
    data = process_client(SAMPLE_CLIENT_WIRELESS)
    coordinator = _build_client_coordinator(hass, {WIRELESS_MAC: data})
    switch = OmadaClientBlockSwitch(coordinator=coordinator, client_mac=WIRELESS_MAC)
    coordinator.api_client.block_client.side_effect = OmadaApiError("fail")
    # Should not raise.
    await switch.async_turn_off()


async def test_block_switch_turn_on_api_error(hass: HomeAssistant) -> None:
    """Test unblock switch handles API error gracefully."""
    data = process_client(SAMPLE_CLIENT_WIRELESS)
    coordinator = _build_client_coordinator(hass, {WIRELESS_MAC: data})
    switch = OmadaClientBlockSwitch(coordinator=coordinator, client_mac=WIRELESS_MAC)
    coordinator.api_client.unblock_client.side_effect = OmadaApiError("fail")
    # Should not raise.
    await switch.async_turn_on()


async def test_block_switch_device_info(hass: HomeAssistant) -> None:
    """Test block switch device info."""
    data = process_client(SAMPLE_CLIENT_WIRELESS)
    switch = _create_block_switch(hass, WIRELESS_MAC, {WIRELESS_MAC: data})
    info = switch.device_info
    assert info is not None
    assert info["identifiers"] == {("omada_open_api", WIRELESS_MAC)}


# ===========================================================================
# OmadaLedSwitch tests
# ===========================================================================


def _create_led_switch(hass: HomeAssistant) -> OmadaLedSwitch:
    """Create an OmadaLedSwitch entity."""
    coordinator = OmadaSiteCoordinator(
        hass=hass,
        api_client=MagicMock(),
        site_id=TEST_SITE_ID,
        site_name=TEST_SITE_NAME,
    )
    coordinator.data = {
        "devices": {},
        "poe_budget": {},
        "poe_ports": {},
        "site_id": TEST_SITE_ID,
        "site_name": TEST_SITE_NAME,
    }
    coordinator.api_client.get_led_setting = AsyncMock(return_value={"enable": True})
    coordinator.api_client.set_led_setting = AsyncMock(return_value={})
    return OmadaLedSwitch(coordinator)


async def test_led_switch_unique_id(hass: HomeAssistant) -> None:
    """Test LED switch unique ID format."""
    switch = _create_led_switch(hass)
    assert switch.unique_id == f"omada_open_api_{TEST_SITE_ID}_led"


async def test_led_switch_name(hass: HomeAssistant) -> None:
    """Test LED switch name includes site name."""
    switch = _create_led_switch(hass)
    assert switch.translation_key == "led"
    assert switch.translation_placeholders == {"site_name": TEST_SITE_NAME}


async def test_led_switch_is_on_initial(hass: HomeAssistant) -> None:
    """Test LED switch is_on is None before first update."""
    switch = _create_led_switch(hass)
    assert switch.is_on is None


async def test_led_switch_is_on_after_update(hass: HomeAssistant) -> None:
    """Test LED switch is_on reflects API after update."""
    switch = _create_led_switch(hass)
    await switch.async_update()
    assert switch.is_on is True


async def test_led_switch_available(hass: HomeAssistant) -> None:
    """Test LED switch available when coordinator is healthy."""
    switch = _create_led_switch(hass)
    assert switch.available is True


async def test_led_switch_unavailable(hass: HomeAssistant) -> None:
    """Test LED switch unavailable on coordinator failure."""
    switch = _create_led_switch(hass)
    switch.coordinator.last_update_success = False
    assert switch.available is False


async def test_led_switch_turn_on(hass: HomeAssistant) -> None:
    """Test turning LED switch ON calls set_led_setting(enable=True)."""
    switch = _create_led_switch(hass)
    switch.hass = hass
    with patch.object(switch, "async_write_ha_state"):
        await switch.async_turn_on()
    switch.coordinator.api_client.set_led_setting.assert_called_once_with(
        TEST_SITE_ID, enable=True
    )
    assert switch.is_on is True


async def test_led_switch_turn_off(hass: HomeAssistant) -> None:
    """Test turning LED switch OFF calls set_led_setting(enable=False)."""
    switch = _create_led_switch(hass)
    switch.hass = hass
    with patch.object(switch, "async_write_ha_state"):
        await switch.async_turn_off()
    switch.coordinator.api_client.set_led_setting.assert_called_once_with(
        TEST_SITE_ID, enable=False
    )
    assert switch.is_on is False


async def test_led_switch_turn_on_api_error(hass: HomeAssistant) -> None:
    """Test LED switch handles turn on error gracefully."""
    switch = _create_led_switch(hass)
    switch.coordinator.api_client.set_led_setting.side_effect = OmadaApiError("fail")
    # Should not raise.
    await switch.async_turn_on()
    assert switch.is_on is None  # Stays None since never successfully fetched.


async def test_led_switch_turn_off_api_error(hass: HomeAssistant) -> None:
    """Test LED switch handles turn off error gracefully."""
    switch = _create_led_switch(hass)
    switch.coordinator.api_client.set_led_setting.side_effect = OmadaApiError("fail")
    await switch.async_turn_off()
    assert switch.is_on is None


async def test_led_switch_update_api_error(hass: HomeAssistant) -> None:
    """Test LED switch handles update error gracefully."""
    switch = _create_led_switch(hass)
    switch.coordinator.api_client.get_led_setting.side_effect = OmadaApiError("fail")
    await switch.async_update()
    assert switch.is_on is None


# ---------------------------------------------------------------------------
# Viewer-only access — no PoE / LED switches
# ---------------------------------------------------------------------------


async def test_setup_entry_viewer_only_skips_poe_and_led(
    hass: HomeAssistant,
) -> None:
    """Test that PoE and LED switches are not created with viewer-only access."""
    coordinator = OmadaSiteCoordinator(
        hass=hass,
        api_client=MagicMock(),
        site_id=TEST_SITE_ID,
        site_name=TEST_SITE_NAME,
    )
    coordinator.data = _build_coordinator_data(
        {"AA-BB-CC-DD-EE-02_1": SAMPLE_PORT_ENABLED}
    )

    entry = MagicMock()
    entry.runtime_data = MagicMock()
    entry.runtime_data.coordinators = {TEST_SITE_ID: coordinator}
    entry.runtime_data.client_coordinators = []
    entry.runtime_data.has_write_access = False

    added_entities: list = []

    def capture_entities(entities: list) -> None:
        added_entities.extend(entities)

    await async_setup_entry(hass, entry, capture_entities)

    # No PoE or LED switches should be created.
    assert not any(isinstance(e, OmadaPoeSwitch) for e in added_entities)
    assert not any(isinstance(e, OmadaLedSwitch) for e in added_entities)
