"""Tests for the debug_ssid_switches service."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING
from unittest.mock import MagicMock

from homeassistant.config_entries import ConfigEntryState
from homeassistant.exceptions import ServiceValidationError
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.omada_open_api import async_setup
from custom_components.omada_open_api.const import DOMAIN
from custom_components.omada_open_api.types import OmadaRuntimeData

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

SERVICE = "debug_ssid_switches"


def _entry(hass: HomeAssistant, state: ConfigEntryState) -> MockConfigEntry:
    """Add an Omada entry in the given state."""
    entry = MockConfigEntry(domain=DOMAIN, title="Omada", data={})
    entry.add_to_hass(hass)
    entry.mock_state(hass, state)
    coordinator = MagicMock()
    coordinator.data = {"ssids": [{"id": "s1", "wlanId": "w1", "name": "Home"}]}
    entry.runtime_data = MagicMock(
        spec=OmadaRuntimeData,
        coordinators={"site": coordinator},
        has_write_access=True,
        site_devices={},
    )
    return entry


async def _call(hass: HomeAssistant, data: dict[str, str]) -> None:
    await async_setup(hass, {})
    await hass.services.async_call(DOMAIN, SERVICE, data, blocking=True)


async def test_without_entry_id_uses_first_loaded_entry(
    hass: HomeAssistant, caplog: pytest.LogCaptureFixture
) -> None:
    """Without config_entry_id the first loaded Omada entry is used."""
    caplog.set_level(logging.INFO)
    _entry(hass, ConfigEntryState.NOT_LOADED)
    loaded = _entry(hass, ConfigEntryState.LOADED)

    await _call(hass, {})

    assert f"Config Entry: Omada ({loaded.entry_id})" in caplog.text
    assert "Total SSIDs across all sites: 1" in caplog.text


@pytest.mark.parametrize(
    ("state", "data_fn", "key"),
    [
        (None, lambda e: {}, "no_loaded_entry"),
        (None, lambda e: {"config_entry_id": "missing"}, "config_entry_not_found"),
        (
            ConfigEntryState.SETUP_RETRY,
            lambda e: {"config_entry_id": e.entry_id},
            "config_entry_not_loaded",
        ),
    ],
)
async def test_invalid_target_raises(
    hass: HomeAssistant, state: ConfigEntryState | None, data_fn, key: str
) -> None:
    """Unusable targets raise a translated ServiceValidationError."""
    entry = _entry(hass, state) if state else None

    with pytest.raises(ServiceValidationError) as exc_info:
        await _call(hass, data_fn(entry))

    assert exc_info.value.translation_key == key
