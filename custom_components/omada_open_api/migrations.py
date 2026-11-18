"""Config entry and registry migrations of the Omada Open API integration."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from homeassistant.helpers import device_registry as dr, entity_registry as er

from .const import (
    CONF_APP_SCAN_INTERVAL,
    CONF_CLIENT_SCAN_INTERVAL,
    CONF_DEVICE_SCAN_INTERVAL,
    CONF_SELECTED_APPLICATIONS,
    CONF_SELECTED_CLIENTS,
    DOMAIN,
    MIN_SCAN_INTERVAL,
)

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

    from .coordinator import OmadaWanSpeedTestCoordinator
    from .types import OmadaConfigEntry

_LOGGER = logging.getLogger(__name__)

# Keys that belong in entry.options rather than entry.data.
_OPTIONS_KEYS = {
    CONF_SELECTED_CLIENTS,
    CONF_SELECTED_APPLICATIONS,
    CONF_DEVICE_SCAN_INTERVAL,
    CONF_CLIENT_SCAN_INTERVAL,
    CONF_APP_SCAN_INTERVAL,
}
_SCAN_INTERVAL_KEYS = {
    CONF_DEVICE_SCAN_INTERVAL,
    CONF_CLIENT_SCAN_INTERVAL,
    CONF_APP_SCAN_INTERVAL,
}


def migrate_data_to_options(hass: HomeAssistant, entry: OmadaConfigEntry) -> None:
    """Move preferences to options and enforce the safe polling floor.

    Older versions stored scan intervals and selections in entry.data.
    This migration moves them to entry.options and raises previously saved
    polling intervals that are no longer permitted.

    Args:
        hass: Home Assistant instance
        entry: Config entry to migrate

    """
    migrated: dict[str, Any] = {}
    for key in _OPTIONS_KEYS:
        if key in entry.data:
            migrated[key] = entry.data[key]

    new_data = {k: v for k, v in entry.data.items() if k not in _OPTIONS_KEYS}
    new_options = {**migrated, **dict(entry.options)}
    clamped_intervals = 0
    for key in _SCAN_INTERVAL_KEYS:
        value = new_options.get(key)
        if isinstance(value, int) and value < MIN_SCAN_INTERVAL:
            new_options[key] = MIN_SCAN_INTERVAL
            clamped_intervals += 1

    if not migrated and not clamped_intervals:
        return

    if migrated:
        _LOGGER.info(
            "Migrating %d key(s) from entry.data to entry.options", len(migrated)
        )
    if clamped_intervals:
        _LOGGER.info(
            "Raised %d saved scan interval(s) to the %d-second minimum",
            clamped_intervals,
            MIN_SCAN_INTERVAL,
        )

    hass.config_entries.async_update_entry(
        entry,
        data=new_data,
        options=new_options,
    )


def non_site_domain_idents(identifiers: set[tuple[str, str]]) -> list[str]:
    """Return this integration's device MACs, excluding site identifiers.

    More than one entry means the device carries multiple distinct Omada
    MACs — the structural signature of a historical registry merge.
    """
    return [
        identifier[1].upper()
        for identifier in identifiers
        if identifier[0] == DOMAIN and not identifier[1].upper().startswith("SITE_")
    ]


def migrate_merged_devices(hass: HomeAssistant, entry: OmadaConfigEntry) -> None:
    """Remove devices carrying more than one non-site (DOMAIN, mac) identifier.

    This is the structural signature left by the pre-v1.8.1 IP-connections
    merge bug: a single HA device incorrectly carrying multiple distinct
    Omada MACs. No legitimate code path in this integration creates that
    today — every device_info construction site sets exactly one identifier
    — so any device found with more than one is always safe to remove.
    Clean per-MAC devices are recreated when platforms set up immediately
    afterward, now that connections are MAC-only and can't re-merge.
    """
    device_registry = dr.async_get(hass)
    devices = dr.async_entries_for_config_entry(device_registry, entry.entry_id)

    removed_count = 0
    for device in devices:
        non_site_idents = non_site_domain_idents(device.identifiers)
        if len(non_site_idents) > 1:
            _LOGGER.info(
                "Removing merged device %s (identifiers: %s) from a "
                "historical registry merge — clean devices will be recreated",
                device.name,
                non_site_idents,
            )
            device_registry.async_remove_device(device.id)
            removed_count += 1

    if removed_count > 0:
        _LOGGER.info("Migrated %d merged device(s)", removed_count)


def migrate_wan_speed_test_button_unique_ids(
    hass: HomeAssistant,
    coordinators: dict[tuple[str, str], OmadaWanSpeedTestCoordinator],
) -> None:
    """Migrate the initial, invalid port-ID-derived speed-test entity IDs."""
    registry = er.async_get(hass)
    for (_, gateway_mac), coordinator in coordinators.items():
        for index, port in enumerate(
            (coordinator.data or {}).get("ports", []), start=1
        ):
            port_id = str(port.get("port") or port.get("portId") or index)
            for domain, suffix in (
                ("button", ""),
                ("sensor", "_download"),
                ("sensor", "_upload"),
                ("sensor", "_latency"),
                ("sensor", "_last_test"),
            ):
                legacy_unique_id = (
                    f"{gateway_mac}_{port_id}_{gateway_mac}_wan_speed_test{suffix}"
                )
                corrected_unique_id = f"{gateway_mac}_{port_id}_wan_speed_test{suffix}"
                legacy_entity_id = registry.async_get_entity_id(
                    domain, DOMAIN, legacy_unique_id
                )
                if legacy_entity_id is None:
                    continue
                corrected_entity_id = registry.async_get_entity_id(
                    domain, DOMAIN, corrected_unique_id
                )
                if corrected_entity_id is not None:
                    registry.async_remove(corrected_entity_id)
                registry.async_update_entity(
                    legacy_entity_id, new_unique_id=corrected_unique_id
                )


_5G_BAND_KEYS: frozenset[str] = frozenset(
    {
        "clients_5g",
        "radio_tx_util_5g",
        "radio_rx_util_5g",
        "radio_inter_util_5g",
        "radio_busy_util_5g",
    }
)


def migrate_5g_entity_ids(
    hass: HomeAssistant,
    entry: OmadaConfigEntry,
) -> None:
    """Rename legacy _5_ghz_1 entity IDs to _5_ghz after translations dropped the -1."""
    reg = er.async_get(hass)
    for entity_entry in er.async_entries_for_config_entry(reg, entry.entry_id):
        if entity_entry.platform != DOMAIN:
            continue
        parts = entity_entry.unique_id.split("_", 1)
        if len(parts) != 2 or parts[1] not in _5G_BAND_KEYS:
            continue
        old_id = entity_entry.entity_id
        if not old_id.endswith("_5_ghz_1"):
            continue
        new_id = old_id[:-2]  # strip trailing "_1"
        if reg.async_get(new_id) is None:
            reg.async_update_entity(old_id, new_entity_id=new_id)
