"""Tests for persisted ownership and cleanup of auto-discovered clients."""

from __future__ import annotations

import datetime as dt
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, patch

from homeassistant.helpers import device_registry as dr, entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.omada_open_api.auto_discovery import AutoClientManager
from custom_components.omada_open_api.const import DOMAIN

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

ENTRY_ID = "auto-discovery-entry"
MAC_A = "1122334455AA"
MAC_B = "1122334455BB"
UNIQUE_A = f"{DOMAIN}_11-22-33-44-55-AA"
UNIQUE_B = f"{DOMAIN}_11-22-33-44-55-BB"


async def _manager(
    hass: HomeAssistant,
    records: dict | None,
    *,
    retention_days: int = 30,
    selected_macs: set[str] | None = None,
) -> tuple[AutoClientManager, MagicMock]:
    """Return a manager backed by a mocked Home Assistant Store."""
    store = MagicMock()
    store.async_load = AsyncMock(return_value=records)
    with patch(
        "custom_components.omada_open_api.auto_discovery.Store", return_value=store
    ):
        manager = AutoClientManager(
            hass,
            ENTRY_ID,
            retention_days=retention_days,
            selected_macs=selected_macs or set(),
        )
    await manager.async_load()
    return manager, store


async def test_last_seen_is_persisted_at_most_daily(hass: HomeAssistant) -> None:
    """Frequent sightings do not cause frequent storage writes."""
    manager, store = await _manager(hass, None)
    first_seen = dt.datetime(2026, 1, 1, 8, tzinfo=dt.UTC)

    manager.mark_seen(MAC_A, UNIQUE_A, first_seen)
    manager.mark_seen(MAC_A, UNIQUE_A, first_seen + dt.timedelta(hours=23))
    assert manager.records[MAC_A]["last_seen"] == first_seen.isoformat()

    next_day = first_seen + dt.timedelta(days=1)
    manager.mark_seen(MAC_A, UNIQUE_A, next_day)
    assert manager.records[MAC_A]["last_seen"] == next_day.isoformat()
    assert store.async_delay_save.call_count == 2


async def test_cleanup_removes_only_expired_tracker_and_orphan_device(
    hass: HomeAssistant,
) -> None:
    """Cleanup preserves devices that still own another registry entity."""
    old = dt.datetime(2026, 1, 1, tzinfo=dt.UTC).isoformat()
    manager, _store = await _manager(
        hass,
        {
            MAC_A: {"entity_unique_id": UNIQUE_A, "last_seen": old},
            MAC_B: {"entity_unique_id": UNIQUE_B, "last_seen": old},
        },
        retention_days=30,
    )
    entry = MockConfigEntry(domain=DOMAIN, entry_id=ENTRY_ID)
    entry.add_to_hass(hass)
    device_registry = dr.async_get(hass)
    entity_registry = er.async_get(hass)
    device_a = device_registry.async_get_or_create(
        config_entry_id=ENTRY_ID,
        identifiers={(DOMAIN, MAC_A)},
    )
    device_b = device_registry.async_get_or_create(
        config_entry_id=ENTRY_ID,
        identifiers={(DOMAIN, MAC_B)},
    )
    tracker_a = entity_registry.async_get_or_create(
        "device_tracker", DOMAIN, UNIQUE_A, config_entry=entry, device_id=device_a.id
    )
    tracker_b = entity_registry.async_get_or_create(
        "device_tracker", DOMAIN, UNIQUE_B, config_entry=entry, device_id=device_b.id
    )
    sensor_b = entity_registry.async_get_or_create(
        "sensor", DOMAIN, "other-b", config_entry=entry, device_id=device_b.id
    )

    removed = await manager.async_cleanup(
        visible_macs=set(),
        polls_successful=True,
        now=dt.datetime(2026, 2, 1, tzinfo=dt.UTC),
    )

    assert removed == {MAC_A, MAC_B}
    assert entity_registry.async_get(tracker_a.entity_id) is None
    assert entity_registry.async_get(tracker_b.entity_id) is None
    assert device_registry.async_get(device_a.id) is None
    assert device_registry.async_get(device_b.id) is not None
    assert entity_registry.async_get(sensor_b.entity_id) is not None
    assert manager.records == {}


async def test_cleanup_is_blocked_by_retention_zero_or_poll_failure(
    hass: HomeAssistant,
) -> None:
    """Never age records without both retention and complete fresh data."""
    old = dt.datetime(2026, 1, 1, tzinfo=dt.UTC).isoformat()
    records = {MAC_A: {"entity_unique_id": UNIQUE_A, "last_seen": old}}
    disabled, _ = await _manager(hass, records, retention_days=0)
    failed, _ = await _manager(hass, records, retention_days=1)
    now = dt.datetime(2026, 2, 1, tzinfo=dt.UTC)

    assert await disabled.async_cleanup(set(), polls_successful=True, now=now) == set()
    assert await failed.async_cleanup(set(), polls_successful=False, now=now) == set()
    assert MAC_A in disabled.records
    assert MAC_A in failed.records


async def test_selected_client_immediately_leaves_auto_management(
    hass: HomeAssistant,
) -> None:
    """Manual selection removes ownership without deleting the shared entity."""
    last_seen = dt.datetime(2026, 1, 1, tzinfo=dt.UTC).isoformat()
    manager, store = await _manager(
        hass,
        {MAC_A: {"entity_unique_id": UNIQUE_A, "last_seen": last_seen}},
        selected_macs={MAC_A},
    )

    assert manager.records == {}
    store.async_delay_save.assert_called_once()
