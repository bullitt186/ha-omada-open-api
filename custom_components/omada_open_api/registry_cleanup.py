"""Device and entity registry cleanup of the Omada Open API integration."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from homeassistant.helpers import device_registry as dr, entity_registry as er

from .clients import normalize_client_mac
from .const import (
    CONF_AUTO_DISCOVER_CLIENT_TRACKERS,
    CONF_SELECTED_APPLICATIONS,
    CONF_SELECTED_CLIENTS,
    CONF_SELECTED_SITES,
    DOMAIN,
)
from .devices import normalize_site_id
from .migrations import non_site_domain_idents
from .types import OmadaRuntimeData

if TYPE_CHECKING:
    from collections.abc import Mapping

    from homeassistant.core import HomeAssistant

    from .coordinator import OmadaSiteCoordinator
    from .types import OmadaConfigEntry

_LOGGER = logging.getLogger(__name__)


async def cleanup_devices(hass: HomeAssistant, entry: OmadaConfigEntry) -> None:
    """Remove devices for clients/sites that were deselected.

    Only removes devices whose identifier matches a previously-selected
    client MAC or site that is no longer selected.  Infrastructure devices
    (router, switches, APs) are never touched — they are managed by the
    coordinator and will be re-created during setup.

    Args:
        hass: Home Assistant instance
        entry: Config entry

    """
    rd = getattr(entry, "runtime_data", None)
    if not rd or not isinstance(rd, OmadaRuntimeData):
        return

    prev_options: dict[str, Any] = rd.prev_options
    prev_data: dict[str, Any] = rd.prev_data

    # Compute deselected clients (previously selected but no longer)
    prev_clients = {
        normalize_client_mac(m) for m in prev_options.get(CONF_SELECTED_CLIENTS, [])
    }
    curr_clients = {
        normalize_client_mac(m) for m in entry.options.get(CONF_SELECTED_CLIENTS, [])
    }
    deselected_clients = prev_clients - curr_clients

    # Compute deselected sites
    prev_sites = {normalize_site_id(s) for s in prev_data.get(CONF_SELECTED_SITES, [])}
    curr_sites = {normalize_site_id(s) for s in entry.data.get(CONF_SELECTED_SITES, [])}
    deselected_sites = prev_sites - curr_sites

    if not deselected_clients and not deselected_sites:
        return

    device_registry = dr.async_get(hass)
    devices = dr.async_entries_for_config_entry(device_registry, entry.entry_id)

    removed_count = 0
    for device in devices:
        for identifier in device.identifiers:
            if identifier[0] != DOMAIN:
                continue
            device_id = normalize_client_mac(identifier[1])

            # Remove deselected client devices
            if device_id in deselected_clients and not entry.options.get(
                CONF_AUTO_DISCOVER_CLIENT_TRACKERS, False
            ):
                _LOGGER.info("Removing deselected client device: %s", device.name)
                device_registry.async_remove_device(device.id)
                removed_count += 1
                break

            # Remove deselected site devices (identifier: "site_{id}")
            if device_id.startswith("SITE_"):
                raw_site_id = device_id[5:]  # Strip "SITE_" prefix
                if raw_site_id in deselected_sites:
                    _LOGGER.info("Removing deselected site device: %s", device.name)
                    device_registry.async_remove_device(device.id)
                    removed_count += 1
                    break

    if removed_count > 0:
        _LOGGER.info("Removed %d deselected device(s)", removed_count)


async def cleanup_entities(hass: HomeAssistant, entry: OmadaConfigEntry) -> None:
    """Remove entities for applications that were deselected.

    Only removes app-traffic sensor entities whose application was
    previously selected but is no longer in the current selection.

    Args:
        hass: Home Assistant instance
        entry: Config entry

    """
    rd = getattr(entry, "runtime_data", None)
    if not rd or not isinstance(rd, OmadaRuntimeData):
        return

    prev_options: dict[str, Any] = rd.prev_options

    prev_apps = {str(a) for a in prev_options.get(CONF_SELECTED_APPLICATIONS, [])}
    curr_apps = {str(a) for a in entry.options.get(CONF_SELECTED_APPLICATIONS, [])}
    deselected_apps = prev_apps - curr_apps

    if not deselected_apps:
        return

    entity_reg = er.async_get(hass)
    entities = er.async_entries_for_config_entry(entity_reg, entry.entry_id)

    removed_count = 0
    for entity in entities:
        # App traffic entities: "{mac}_{app_id}_{upload|download}_app_traffic"
        if not (entity.unique_id and entity.unique_id.endswith("_app_traffic")):
            continue

        parts = entity.unique_id.split("_")
        # parts: [mac, app_id, metric, "app", "traffic"]  (5 elements minimum)
        if len(parts) >= 5:
            app_id = parts[-4]  # app_id is 4th from end

            if app_id in deselected_apps:
                _LOGGER.info(
                    "Removing entity for deselected application: %s (app_id: %s)",
                    entity.entity_id,
                    app_id,
                )
                entity_reg.async_remove(entity.entity_id)
                removed_count += 1

    if removed_count > 0:
        _LOGGER.info(
            "Removed %d entity/entities for deselected applications", removed_count
        )


def active_infra_device_macs(rd: OmadaRuntimeData) -> set[str]:
    """Collect infra device MACs currently reported by any site coordinator."""
    return {
        normalize_client_mac(mac)
        for coordinator in rd.coordinators.values()
        for mac in (coordinator.data.get("devices", {}) if coordinator.data else {})
    }


def can_remove_device(entry: OmadaConfigEntry, device_entry: dr.DeviceEntry) -> bool:
    """Return whether a device may be removed from the integration.

    Devices that are still selected (clients, sites) or still reported by a
    site coordinator would reappear on the next poll, so they are kept.
    """
    # A device carrying more than one non-site (DOMAIN, mac) identifier is
    # always a historical registry merge (see migrate_merged_devices) — no
    # legitimate code path creates that today. Always allow removing it,
    # bypassing the "still active" block below, which exists to protect
    # normal single-MAC devices and would otherwise block this every time
    # (a merged device is, by definition, still linked to at least one
    # live MAC).
    non_site_idents = non_site_domain_idents(device_entry.identifiers)
    if len(non_site_idents) > 1:
        _LOGGER.info(
            "Allowing removal of merged device %s (identifiers: %s) — "
            "clean per-device entries will be recreated",
            device_entry.name,
            non_site_idents,
        )
        return True

    # Get the list of selected clients and sites
    selected_client_macs = entry.options.get(CONF_SELECTED_CLIENTS, [])
    selected_site_ids = entry.data.get(CONF_SELECTED_SITES, [])

    # Normalize MAC addresses to match format (with hyphens)
    selected_client_macs_normalized = {
        normalize_client_mac(mac) for mac in selected_client_macs
    }
    selected_site_ids_normalized = {
        normalize_site_id(site_id) for site_id in selected_site_ids
    }

    # Collect all infrastructure device MACs still reported by coordinators.
    # Blocking removal of live devices prevents accidental deletion of
    # devices that would immediately reappear on the next poll.
    rd: OmadaRuntimeData | None = getattr(entry, "runtime_data", None)
    active_device_macs: set[str] = active_infra_device_macs(rd) if rd else set()

    # Check if this device is still in the selected lists
    for identifier in device_entry.identifiers:
        if identifier[0] == DOMAIN:
            device_id = normalize_client_mac(identifier[1])

            # Check if it's a selected client (client devices use MAC format)
            if device_id in selected_client_macs_normalized:
                _LOGGER.debug(
                    "Device %s is still a selected client, not removing", device_id
                )
                return False

            # Check if it's a selected site (identifier: "site_{id}")
            if device_id.startswith("SITE_"):
                raw_site_id = device_id[5:]  # Strip "SITE_" prefix
                if raw_site_id in selected_site_ids_normalized:
                    _LOGGER.debug(
                        "Device %s is still a selected site, not removing",
                        device_id,
                    )
                    return False

            # Block removal of infrastructure devices still in coordinator data
            if device_id in active_device_macs:
                _LOGGER.debug(
                    "Device %s is still active in coordinator data, not removing",
                    device_id,
                )
                return False

    # Device is not in any selected list, allow removal
    _LOGGER.info("Allowing removal of device %s", device_entry.name)
    return True


def setup_stale_infra_device_pruning(
    hass: HomeAssistant,
    entry: OmadaConfigEntry,
    coordinators: dict[str, OmadaSiteCoordinator],
) -> None:
    """Prune infra devices now, then re-prune after every successful poll."""
    prune_stale_infra_devices(hass, entry)
    for coordinator in coordinators.values():
        entry.async_on_unload(
            coordinator.async_add_listener(
                lambda: prune_stale_infra_devices(hass, entry)
            )
        )


def prune_stale_infra_devices(hass: HomeAssistant, entry: OmadaConfigEntry) -> None:
    """Remove infra devices whose MAC no longer appears in coordinator data.

    A MAC missing from every site coordinator's data means the device was
    unadopted/removed on the Omada controller. Skips entirely if any site
    coordinator hasn't completed a successful update, so a transient poll
    failure can never look like "device gone" — DataUpdateCoordinator
    leaves .data untouched on a failed refresh.
    """
    rd: OmadaRuntimeData | None = getattr(entry, "runtime_data", None)
    if not rd:
        return

    if any(not c.last_update_success for c in rd.coordinators.values()):
        return

    active_macs = active_infra_device_macs(rd)
    selected_client_macs = {
        normalize_client_mac(m) for m in entry.options.get(CONF_SELECTED_CLIENTS, [])
    }

    device_registry = dr.async_get(hass)
    devices = dr.async_entries_for_config_entry(device_registry, entry.entry_id)

    # Presence-only clients reuse the legacy unique IDs. Never mistake them
    # for stale AP/switch/gateway devices: removing them destroys customizations.
    auto_clients: set[str] = set()
    # Previously auto-discovered tracker devices must survive even when the
    # option is disabled; disabled discovery must not remove customizations.
    registry = er.async_get(hass)
    for entity in er.async_entries_for_config_entry(registry, entry.entry_id):
        if (
            entity.domain == "device_tracker"
            and entity.unique_id
            and entity.unique_id.startswith(f"{DOMAIN}_")
            and not entity.unique_id.startswith(f"{DOMAIN}_device_")
        ):
            auto_clients.add(normalize_client_mac(entity.unique_id[len(DOMAIN) + 1 :]))

    removed_count = 0
    for device in devices:
        for identifier in device.identifiers:
            if identifier[0] != DOMAIN:
                continue
            device_id = normalize_client_mac(identifier[1])

            # Site devices are managed by site selection, not this pass.
            if device_id.startswith("SITE_"):
                break

            # Auto-discovered presence entities must remain in the registry when
            # disconnected or stale. The user may have customized them.
            if device_id in auto_clients:
                break

            # Selected clients are managed by cleanup_devices, not this
            # pass — a client not currently connected is not the same as a
            # device removed from the controller.
            if device_id in selected_client_macs:
                break

            # Infra device candidate: prune if it's no longer reported.
            if device_id not in active_macs:
                _LOGGER.info(
                    "Removing stale infrastructure device: %s (%s)",
                    device.name,
                    device_id,
                )
                device_registry.async_remove_device(device.id)
                removed_count += 1
            break

    if removed_count > 0:
        _LOGGER.info("Pruned %d stale infrastructure device(s)", removed_count)


def purge_absent_band_entities(
    hass: HomeAssistant,
    entry: OmadaConfigEntry,
    coordinators: dict[str, OmadaSiteCoordinator],
    band_data_keys: Mapping[str, str],
) -> None:
    """Remove registry entries of AP band sensors whose band the AP lacks.

    Args:
        hass: Home Assistant instance
        entry: Config entry
        coordinators: Site coordinators with the current device data
        band_data_keys: Per-band sensor key -> device data key that is
            present when the AP has that band

    """
    reg = er.async_get(hass)
    present_keys: set[tuple[str, str]] = set()
    for coord in coordinators.values():
        devices = coord.data.get("devices", {}) if coord.data else {}
        for mac, device_data in devices.items():
            if device_data.get("type", "").lower() != "ap":
                continue
            present_keys.update(
                (mac, key)
                for key, data_key in band_data_keys.items()
                if data_key in device_data
            )

    for entity_entry in er.async_entries_for_config_entry(reg, entry.entry_id):
        if entity_entry.platform != DOMAIN:
            continue
        parts = entity_entry.unique_id.split("_", 1)
        if len(parts) != 2:
            continue
        mac, key = parts
        if key in band_data_keys and (mac, key) not in present_keys:
            reg.async_remove(entity_entry.entity_id)
