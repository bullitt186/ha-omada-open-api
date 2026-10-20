"""Persistence and safe cleanup for automatically discovered client trackers."""

from __future__ import annotations

from copy import deepcopy
import datetime as dt
import logging
import re
from typing import TYPE_CHECKING, TypedDict

from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.helpers.storage import Store

from .clients import normalize_client_mac

if TYPE_CHECKING:
    from collections.abc import Mapping, Set as AbstractSet

    from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)

_STORE_VERSION = 1
_SAVE_DELAY_SECONDS = 60
_MAC_PATTERN = re.compile(r"[0-9A-F]{12}")


class AutoClientRecord(TypedDict):
    """Persisted ownership metadata for one auto-created tracker."""

    entity_unique_id: str
    last_seen: str


type AutoClientStoreData = dict[str, AutoClientRecord]


class AutoClientManager:
    """Own auto-created trackers and remove only expired owned entries."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry_id: str,
        *,
        retention_days: int,
        selected_macs: AbstractSet[str],
    ) -> None:
        """Initialize a per-config-entry manager and versioned store."""
        self._hass = hass
        self._entry_id = entry_id
        self._retention_days = retention_days
        self._selected_macs = frozenset(selected_macs)
        self._records: AutoClientStoreData = {}
        self._store: Store[AutoClientStoreData] = Store(
            hass, _STORE_VERSION, f"omada_open_api.auto_clients.{entry_id}"
        )

    @property
    def records(self) -> Mapping[str, AutoClientRecord]:
        """Return records for inspection and tracker restoration."""
        return self._records

    async def async_load(self) -> None:
        """Load valid owned records and stop managing selected clients."""
        loaded = await self._store.async_load()
        if loaded:
            self._records = self._validated_records(loaded)
        selected_records = self._records.keys() & self._selected_macs
        if selected_records:
            for mac in selected_records:
                self._records.pop(mac)
            self._schedule_save()

    def mark_seen(
        self,
        mac: str,
        entity_unique_id: str,
        now: dt.datetime | None = None,
    ) -> None:
        """Record a successful sighting, updating at most once per day."""
        canonical = normalize_client_mac(mac)
        if canonical in self._selected_macs or not _MAC_PATTERN.fullmatch(canonical):
            return
        seen_at = now or dt.datetime.now(dt.UTC)
        previous = self._records.get(canonical)
        if previous is not None:
            previous_seen = _parse_utc(previous["last_seen"])
            if (
                previous["entity_unique_id"] == entity_unique_id
                and previous_seen is not None
                and seen_at < previous_seen + dt.timedelta(days=1)
            ):
                return
        self._records[canonical] = {
            "entity_unique_id": entity_unique_id,
            "last_seen": seen_at.isoformat(),
        }
        self._schedule_save()

    async def async_cleanup(
        self,
        visible_macs: AbstractSet[str],
        *,
        polls_successful: bool,
        now: dt.datetime | None = None,
    ) -> set[str]:
        """Remove expired owned trackers after a complete successful poll."""
        if not polls_successful or self._retention_days == 0:
            return set()
        cleanup_at = now or dt.datetime.now(dt.UTC)
        visible = {normalize_client_mac(mac) for mac in visible_macs}
        expired: set[str] = set()
        for mac, record in self._records.items():
            last_seen = _parse_utc(record["last_seen"])
            if (
                mac not in visible
                and mac not in self._selected_macs
                and last_seen is not None
                and cleanup_at >= last_seen + dt.timedelta(days=self._retention_days)
            ):
                expired.add(mac)

        if not expired:
            return set()

        entity_registry = er.async_get(self._hass)
        device_registry = dr.async_get(self._hass)
        registry_entries = er.async_entries_for_config_entry(
            entity_registry, self._entry_id
        )
        entries_by_unique_id = {
            entry.unique_id: entry
            for entry in registry_entries
            if entry.domain == "device_tracker"
        }
        for mac in expired:
            record = self._records[mac]
            entity = entries_by_unique_id.get(record["entity_unique_id"])
            device_id = entity.device_id if entity is not None else None
            if entity is not None:
                entity_registry.async_remove(entity.entity_id)
            if device_id and not er.async_entries_for_device(
                entity_registry, device_id, include_disabled_entities=True
            ):
                device_registry.async_remove_device(device_id)
            self._records.pop(mac)
            _LOGGER.info("Removed expired auto-discovered client tracker %s", mac)
        self._schedule_save()
        return expired

    def _schedule_save(self) -> None:
        """Coalesce persistence writes without exposing mutable state."""
        self._store.async_delay_save(
            lambda: deepcopy(self._records), _SAVE_DELAY_SECONDS
        )

    @staticmethod
    def _validated_records(loaded: Mapping[str, object]) -> AutoClientStoreData:
        """Discard malformed records without risking unrelated registry data."""
        records: AutoClientStoreData = {}
        for raw_mac, raw_record in loaded.items():
            mac = normalize_client_mac(raw_mac)
            if (
                not _MAC_PATTERN.fullmatch(mac)
                or not isinstance(raw_record, dict)
                or not isinstance(unique_id := raw_record.get("entity_unique_id"), str)
                or not isinstance(last_seen := raw_record.get("last_seen"), str)
                or _parse_utc(last_seen) is None
            ):
                continue
            records[mac] = {
                "entity_unique_id": unique_id,
                "last_seen": last_seen,
            }
        return records


def _parse_utc(value: str) -> dt.datetime | None:
    """Parse a timezone-aware timestamp and normalize it to UTC."""
    try:
        parsed = dt.datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(dt.UTC)
