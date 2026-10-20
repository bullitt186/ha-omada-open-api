"""Device tracker platform for Omada Open API integration."""

from __future__ import annotations

from dataclasses import dataclass
import datetime as dt
import logging
import re
from typing import TYPE_CHECKING, Any

from homeassistant.components.device_tracker import (  # type: ignore[attr-defined]
    BaseScannerEntity,
    ScannerEntity,
    SourceType,
)
from homeassistant.core import callback
from homeassistant.helpers.entity import DeviceInfo  # type: ignore[attr-defined]
from homeassistant.helpers.event import async_track_time_interval

from .auto_discovery import AutoClientManager
from .clients import normalize_client_mac
from .const import (
    CLIENT_RADIO_BANDS,
    CONF_AUTO_DISCOVER_CLIENT_TRACKERS,
    CONF_AUTO_DISCOVERY_EXCLUDE_GUESTS,
    CONF_AUTO_DISCOVERY_EXCLUDE_LOCAL_MACS,
    CONF_AUTO_DISCOVERY_EXCLUDED_CLIENTS,
    CONF_AUTO_DISCOVERY_INCLUDE_WIRED,
    CONF_AUTO_DISCOVERY_REQUIRE_NAME,
    CONF_AUTO_DISCOVERY_RETENTION_DAYS,
    CONF_AUTO_DISCOVERY_SIGNAL_ATTRIBUTES,
    CONF_AUTO_DISCOVERY_SSIDS,
    CONF_DISCONNECT_TIMEOUT,
    CONF_SELECTED_CLIENTS,
    DEFAULT_AUTO_DISCOVERY_RETENTION_DAYS,
    DOMAIN,
)
from .coordinator import OmadaClientCoordinator, OmadaSiteCoordinator
from .devices import (
    build_client_device_info,
    format_detail_status,
    resolve_via_device_id,
)
from .entity import OmadaEntity

if TYPE_CHECKING:
    from collections.abc import Collection, Mapping

    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from .types import OmadaConfigEntry

_LOGGER = logging.getLogger(__name__)

PARALLEL_UPDATES = 0

# A device is considered connected when its status is non-zero.
# The API returns status=0 for disconnected devices and various
# positive integers (1, 14, …) for connected states.
_STATUS_DISCONNECTED = 0


@dataclass(frozen=True, slots=True)
class AutoDiscoveryFilter:
    """Options controlling which cached clients become auto trackers."""

    allowed_ssids: frozenset[str] = frozenset()
    include_wired: bool = True
    exclude_guests: bool = True
    exclude_local_macs: bool = False
    require_name: bool = False
    excluded_macs: frozenset[str] = frozenset()

    def allows(self, client: dict[str, Any], mac: str) -> bool:
        """Return whether a normalized client passes every configured filter."""
        if mac in self.excluded_macs:
            return False
        if self.exclude_guests and client.get("guest", False):
            return False
        if self.exclude_local_macs and int(mac[:2], 16) & 0x02:
            return False
        if self.require_name and not _has_meaningful_client_name(client, mac):
            return False
        if not client.get("wireless", False):
            return self.include_wired
        return not self.allowed_ssids or client.get("ssid") in self.allowed_ssids


def _has_meaningful_client_name(client: dict[str, Any], mac: str) -> bool:
    """Return whether the API supplied a name other than the client MAC."""
    for value in (client.get("name"), client.get("host_name")):
        if not isinstance(value, str) or not value.strip():
            continue
        if normalize_client_mac(value) != mac:
            return True
    return False


def _string_option_values(value: Any) -> frozenset[str]:
    """Normalize legacy comma-separated and current list-valued options."""
    values = value.split(",") if isinstance(value, str) else value
    if not isinstance(values, (list, tuple, set, frozenset)):
        return frozenset()
    return frozenset(
        item.strip() for item in values if isinstance(item, str) and item.strip()
    )


def _auto_discovery_filter(options: Mapping[str, Any]) -> AutoDiscoveryFilter:
    """Build a typed filter from config-entry options."""
    excluded_macs = frozenset(
        normalized
        for value in _string_option_values(
            options.get(CONF_AUTO_DISCOVERY_EXCLUDED_CLIENTS, [])
        )
        if re.fullmatch(r"[0-9A-F]{12}", normalized := normalize_client_mac(value))
    )
    return AutoDiscoveryFilter(
        allowed_ssids=_string_option_values(options.get(CONF_AUTO_DISCOVERY_SSIDS, [])),
        include_wired=options.get(CONF_AUTO_DISCOVERY_INCLUDE_WIRED, True),
        exclude_guests=options.get(CONF_AUTO_DISCOVERY_EXCLUDE_GUESTS, True),
        exclude_local_macs=options.get(CONF_AUTO_DISCOVERY_EXCLUDE_LOCAL_MACS, False),
        require_name=options.get(CONF_AUTO_DISCOVERY_REQUIRE_NAME, False),
        excluded_macs=excluded_macs,
    )


def _all_client_polls_successful(
    site_coordinators: list[OmadaSiteCoordinator],
) -> bool:
    """Return whether every relevant site has a complete fresh client snapshot."""
    return bool(site_coordinators) and all(
        coord.last_update_success
        and bool(coord.data)
        and coord.data.get("clients_poll_ok", True) is not False
        for coord in site_coordinators
    )


def _visible_auto_clients(
    site_coordinators: list[OmadaSiteCoordinator],
    discovery_filter: AutoDiscoveryFilter,
) -> dict[str, dict[str, Any]]:
    """Collect filtered clients from successful cached site snapshots."""
    visible: dict[str, dict[str, Any]] = {}
    for coord in site_coordinators:
        if (
            not coord.last_update_success
            or not coord.data
            or coord.data.get("clients_poll_ok", True) is False
        ):
            continue
        for client in coord.data.get("all_clients", []):
            raw_mac = client.get("mac")
            if not isinstance(raw_mac, str):
                continue
            mac = normalize_client_mac(raw_mac)
            if re.fullmatch(r"[0-9A-F]{12}", mac) and discovery_filter.allows(
                client, mac
            ):
                visible[mac] = client
    return visible


async def async_setup_entry(
    hass: HomeAssistant,
    entry: OmadaConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Omada device tracker from a config entry."""
    rd = entry.runtime_data

    # --- Device trackers (APs, switches, gateways) ---
    known_device_macs: set[str] = set()
    site_coordinators: list[OmadaSiteCoordinator] = list(rd.coordinators.values())

    for site_coordinator in site_coordinators:

        @callback
        def _async_check_new_devices(
            coord: OmadaSiteCoordinator = site_coordinator,
        ) -> None:
            """Add device trackers for newly discovered infrastructure devices."""
            devices = coord.data.get("devices", {}) if coord.data else {}
            new_macs = set(devices.keys()) - known_device_macs
            if not new_macs:
                return

            known_device_macs.update(new_macs)

            new_entities = [OmadaDeviceTracker(coord, mac) for mac in new_macs]
            if new_entities:
                async_add_entities(new_entities)

        _async_check_new_devices()
        entry.async_on_unload(
            site_coordinator.async_add_listener(_async_check_new_devices)
        )

    await _setup_auto_client_trackers(
        hass, entry, site_coordinators, async_add_entities
    )

    # --- Client trackers (network clients) ---
    client_coordinators: list[OmadaClientCoordinator] = rd.client_coordinators

    tracked: set[str] = set()

    for coordinator in client_coordinators:

        @callback
        def _async_update_items(
            coord: OmadaClientCoordinator = coordinator,
        ) -> None:
            """Add new device tracker entities for newly discovered clients."""
            new_entities: list[OmadaClientTracker] = []
            for mac in coord.data:
                if mac not in tracked:
                    _LOGGER.debug("Adding device tracker for client %s", mac)
                    new_entities.append(OmadaClientTracker(coord, mac))
                    tracked.add(mac)
            if new_entities:
                async_add_entities(new_entities)

        # Register listener for future updates.
        entry.async_on_unload(coordinator.async_add_listener(_async_update_items))

        # Populate with currently known clients.
        _async_update_items(coordinator)


async def _setup_auto_client_trackers(
    hass: HomeAssistant,
    entry: OmadaConfigEntry,
    site_coordinators: list[OmadaSiteCoordinator],
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Discover opted-in client presence via already fetched site data."""
    selected_macs = {
        normalize_client_mac(mac)
        for mac in entry.options.get(CONF_SELECTED_CLIENTS, [])
    }
    discovery_enabled = entry.options.get(CONF_AUTO_DISCOVER_CLIENT_TRACKERS, False)
    discovery_filter = _auto_discovery_filter(entry.options)
    manager = AutoClientManager(
        hass,
        entry.entry_id,
        retention_days=entry.options.get(
            CONF_AUTO_DISCOVERY_RETENTION_DAYS,
            DEFAULT_AUTO_DISCOVERY_RETENTION_DAYS,
        ),
        selected_macs=selected_macs,
    )
    await manager.async_load()
    entry.runtime_data.auto_client_manager = manager
    if not discovery_enabled and not manager.records:
        return
    discovered_macs = set(manager.records)

    previously_discovered = _restore_auto_client_trackers(
        entry, site_coordinators, manager, discovery_filter
    )
    if previously_discovered:
        async_add_entities(previously_discovered)

    last_cleanup: dt.datetime | None = None
    cleanup_pending = False

    async def _async_cleanup(visible_macs: set[str], now: dt.datetime) -> None:
        nonlocal cleanup_pending, last_cleanup
        try:
            removed = await manager.async_cleanup(
                visible_macs,
                polls_successful=_all_client_polls_successful(site_coordinators),
                now=now,
            )
            discovered_macs.difference_update(removed)
            last_cleanup = now
        finally:
            cleanup_pending = False

    @callback
    def _async_discover_clients(*, force_cleanup: bool = False) -> None:
        """Create only never-seen presence entities; retain missing ones offline."""
        nonlocal cleanup_pending
        visible = _visible_auto_clients(site_coordinators, discovery_filter)
        new_entities: list[OmadaAutoClientTracker] = []
        for mac in visible:
            record = manager.records.get(mac)
            if record is not None:
                manager.mark_seen(mac, record["entity_unique_id"])
                continue
            if not discovery_enabled or mac in selected_macs or mac in discovered_macs:
                continue
            client_mac = "-".join(mac[index : index + 2] for index in range(0, 12, 2))
            unique_id = f"{DOMAIN}_{client_mac}"
            manager.mark_seen(mac, unique_id)
            discovered_macs.add(mac)
            new_entities.append(
                OmadaAutoClientTracker(
                    site_coordinators,
                    client_mac,
                    entry.runtime_data.site_devices,
                    entry.options.get(CONF_DISCONNECT_TIMEOUT, 0),
                    discovery_filter.allowed_ssids,
                    entry.options.get(CONF_AUTO_DISCOVERY_SIGNAL_ATTRIBUTES, True),
                    discovery_filter,
                    unique_id,
                )
            )
        if new_entities:
            async_add_entities(new_entities)

        now = dt.datetime.now(dt.UTC)
        cleanup_due = last_cleanup is None or now >= last_cleanup + dt.timedelta(days=1)
        if (
            _all_client_polls_successful(site_coordinators)
            and not cleanup_pending
            and (force_cleanup or cleanup_due)
        ):
            cleanup_pending = True
            hass.async_create_task(
                _async_cleanup(set(visible), now),
                "Clean up expired Omada auto-discovered clients",
            )

    for site_coord in site_coordinators:
        entry.async_on_unload(site_coord.async_add_listener(_async_discover_clients))
    _async_discover_clients()
    entry.async_on_unload(
        async_track_time_interval(
            hass,
            lambda _now: _async_discover_clients(force_cleanup=True),
            dt.timedelta(days=1),
        )
    )


def _restore_auto_client_trackers(
    entry: OmadaConfigEntry,
    site_coordinators: list[OmadaSiteCoordinator],
    manager: AutoClientManager,
    discovery_filter: AutoDiscoveryFilter,
) -> list[OmadaAutoClientTracker]:
    """Restore only tracker IDs proven to be owned by the manager store."""
    restored: list[OmadaAutoClientTracker] = []
    for canonical, record in manager.records.items():
        client_mac = "-".join(canonical[index : index + 2] for index in range(0, 12, 2))
        restored.append(
            OmadaAutoClientTracker(
                site_coordinators,
                client_mac,
                entry.runtime_data.site_devices,
                entry.options.get(CONF_DISCONNECT_TIMEOUT, 0),
                discovery_filter.allowed_ssids,
                entry.options.get(CONF_AUTO_DISCOVERY_SIGNAL_ATTRIBUTES, True),
                discovery_filter,
                record["entity_unique_id"],
            )
        )
    return restored


class OmadaAutoClientTracker(BaseScannerEntity):
    """Presence-only client tracker; one stable entity across all sites.

    The existing manually selected OmadaClientTracker uses the same unique ID.
    Setup excludes selected MACs, so the two implementations never coexist.
    Devices that disappear are retained as away: the integration never deletes
    user-customized entities or automations automatically.
    """

    _attr_should_poll = False

    def __init__(
        self,
        site_coordinators: list[OmadaSiteCoordinator],
        client_mac: str,
        site_devices: dict[str, Any],
        disconnect_timeout: int = 0,
        allowed_ssids: Collection[str] | None = None,
        signal_attributes: bool = True,
        discovery_filter: AutoDiscoveryFilter | None = None,
        entity_unique_id: str | None = None,
    ) -> None:
        """Use the existing site snapshots, never poll per client."""
        self._coordinators = site_coordinators
        self._client_mac = client_mac
        self._canonical_mac = normalize_client_mac(client_mac)
        self._site_devices = site_devices
        self._disconnect_timeout = disconnect_timeout
        self._discovery_filter = discovery_filter or AutoDiscoveryFilter(
            allowed_ssids=frozenset(allowed_ssids or set())
        )
        self._signal_attributes = signal_attributes
        self._last_seen: dt.datetime | None = None
        self._unique_id = entity_unique_id or f"{DOMAIN}_{client_mac}"
        self._attr_mac_address = client_mac.replace("-", ":").lower()
        self._attr_name = client_mac
        # Keep the old device registry link even when this client was offline
        # during HA startup and has no live API data yet.
        first_site = site_coordinators[0] if site_coordinators else None
        site_device = site_devices.get(first_site.site_id) if first_site else None
        self._client_device_info: DeviceInfo | None = (
            build_client_device_info(
                client_mac,
                {},
                first_site.api_client.api_url,
                site_device.id if site_device else None,
            )
            if first_site
            else None
        )
        self._refresh_metadata()

    def _current_client(self) -> tuple[OmadaSiteCoordinator, dict[str, Any]] | None:
        """Find this MAC at any configured site, including after site roaming."""
        for coord in self._coordinators:
            if (
                not coord.last_update_success
                or not coord.data
                or coord.data.get("clients_poll_ok", True) is False
            ):
                continue
            index = coord.data.get("client_index")
            if isinstance(index, dict):
                client = index.get(self._canonical_mac)
                if client is not None and self._discovery_filter.allows(
                    client, self._canonical_mac
                ):
                    return coord, client
                continue
            # Compatibility for earlier cached coordinator snapshots.
            for client in coord.data.get("all_clients", []):
                mac = client.get("mac")
                if (
                    isinstance(mac, str)
                    and normalize_client_mac(mac) == self._canonical_mac
                    and self._discovery_filter.allows(client, self._canonical_mac)
                ):
                    return coord, client
        return None

    def _refresh_metadata(self) -> None:
        """Update details without replacing the entity's stable unique ID."""
        found = self._current_client()
        if not found:
            return
        coord, client = found
        self._last_seen = dt.datetime.now(dt.UTC)
        self._attr_name = (
            client.get("name") or client.get("host_name") or self._client_mac
        )
        parent_mac = (
            client.get("ap_mac") if client.get("wireless") else client.get("switch_mac")
        ) or client.get("gateway_mac")
        parent_id = (
            resolve_via_device_id(coord.hass, parent_mac, coord.config_entry)
            if parent_mac
            else None
        )
        if parent_id is None:
            site = self._site_devices.get(coord.site_id)
            parent_id = site.id if site else None
        self._client_device_info = build_client_device_info(
            self._client_mac, client, coord.api_client.api_url, parent_id
        )

    async def async_added_to_hass(self) -> None:
        """Subscribe to the site coordinators already fetching active clients."""
        await super().async_added_to_hass()
        for coord in self._coordinators:
            self.async_on_remove(coord.async_add_listener(self._handle_site_update))

    @callback
    def _handle_site_update(self) -> None:
        """Track status and site transitions; never prune a missing client."""
        self._refresh_metadata()
        self.async_write_ha_state()

    @property
    def unique_id(self) -> str:
        """Use the established Omada unique ID, independent of raw MAC."""
        return self._unique_id

    @property
    def device_info(self) -> DeviceInfo | None:
        """Expose a parent-aware registry device, even for restored offline IDs."""
        return self._client_device_info

    @property
    def mac_address(self) -> str | None:
        """Return the MAC as reported to the Home Assistant device registry."""
        return self._attr_mac_address

    @property
    def source_type(self) -> SourceType:
        """Presence is detected by the Omada router/controller."""
        return SourceType.ROUTER

    @property
    def is_connected(self) -> bool:
        """Return online state with the configured disconnection grace period."""
        if self._current_client() is not None:
            return True
        if self._last_seen is not None and self._disconnect_timeout > 0:
            elapsed = (dt.datetime.now(dt.UTC) - self._last_seen).total_seconds()
            return elapsed < self._disconnect_timeout * 60
        return False

    @property
    def available(self) -> bool:
        """Avoid false away states when a site's API refresh has failed."""
        return self._current_client() is not None or all(
            coord.last_update_success
            and (not coord.data or coord.data.get("clients_poll_ok", True))
            for coord in self._coordinators
        )

    @property
    def ip_address(self) -> str | None:
        """Report last-known IP only while online."""
        found = self._current_client()
        return found[1].get("ip") if found else None

    @property
    def hostname(self) -> str | None:
        """Expose the currently reported hostname."""
        found = self._current_client()
        return found[1].get("host_name") if found else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Expose only fields the Omada API actually reported."""
        found = self._current_client()
        if not found:
            return {}
        client = found[1]
        attrs: dict[str, Any] = {}
        for source, target in (("ssid", "ssid"), ("channel", "channel")):
            if client.get(source) is not None:
                attrs[target] = client[source]
        if client.get("wireless") is not None:
            attrs["connection_type"] = "wireless" if client["wireless"] else "wired"
        if client.get("wireless"):
            radio_id = client.get("radio_id")
            band = (
                CLIENT_RADIO_BANDS.get(radio_id) if isinstance(radio_id, int) else None
            )
            if band:
                attrs["band"] = band
            if self._signal_attributes:
                # Snapshot values are per-device, not per-SSID: roaming
                # updates this existing tracker's attributes in place.
                for key, attr in (
                    ("rssi", "rssi_dbm"),
                    ("snr", "snr_db"),
                    ("signal_level", "signal_strength_percent"),
                ):
                    value = client.get(key)
                    if isinstance(value, (int, float)) and not isinstance(value, bool):
                        attrs[attr] = value
        return attrs


class OmadaDeviceTracker(
    OmadaEntity[OmadaSiteCoordinator],
    ScannerEntity,
):
    """Representation of an Omada network device (AP/switch/gateway) for presence detection."""

    def __init__(
        self,
        coordinator: OmadaSiteCoordinator,
        device_mac: str,
    ) -> None:
        """Initialize the device tracker."""
        super().__init__(coordinator)
        self._device_mac = device_mac

        device_data = self._device_data
        device_name = device_data.get("name", device_mac)

        self._attr_name = device_name
        self._unique_id = f"{DOMAIN}_device_{device_mac}"
        self._attr_mac_address = device_mac.replace("-", ":").lower()
        self._update_device_info()

    @property
    def _device_data(self) -> dict[str, Any]:
        """Return the current device data from the coordinator."""
        devices: dict[str, dict[str, Any]] = (
            self.coordinator.data.get("devices", {}) if self.coordinator.data else {}
        )
        result: dict[str, Any] = devices.get(self._device_mac, {})
        return result

    # ------------------------------------------------------------------
    # ScannerEntity properties
    # ------------------------------------------------------------------

    @property
    def unique_id(self) -> str:
        """Return unique ID of the entity."""
        return self._unique_id

    @property
    def source_type(self) -> SourceType:
        """Return the source type."""
        return SourceType.ROUTER

    @property
    def is_connected(self) -> bool:
        """Return true if the device is connected to the network."""
        device = self._device_data
        if not device:
            return False
        status: int = device.get("status", 0)
        return status != _STATUS_DISCONNECTED

    @property
    def ip_address(self) -> str | None:
        """Return the IP address of the device."""
        device = self._device_data
        if not device:
            return None
        ip: str | None = device.get("ip")
        return ip

    @property
    def hostname(self) -> str | None:
        """Return the hostname (name) of the device."""
        device = self._device_data
        if not device:
            return None
        name: str | None = device.get("name")
        return name

    def _update_device_info(self) -> None:
        """Update device_info from current coordinator data."""
        device = self._device_data
        if device:
            self._attr_device_info: DeviceInfo | None = DeviceInfo(  # type: ignore[assignment]
                identifiers={(DOMAIN, self._device_mac)},
                name=device.get("name", self._device_mac),
                manufacturer="TP-Link",
                model=device.get("model"),
                sw_version=device.get("firmware_version"),
            )

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self._update_device_info()
        self.async_write_ha_state()

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes."""
        device = self._device_data
        if not device:
            return {}
        attrs: dict[str, Any] = {}
        if device.get("type"):
            attrs["device_type"] = device["type"]
        if device.get("model"):
            attrs["model"] = device["model"]
        if device.get("firmware_version"):
            attrs["firmware_version"] = device["firmware_version"]
        if device.get("ip"):
            attrs["ip_address"] = device["ip"]
        detail = format_detail_status(device.get("detail_status"))
        if detail:
            attrs["detail_status"] = detail
        return attrs


class OmadaClientTracker(
    OmadaEntity[OmadaClientCoordinator],
    ScannerEntity,
):
    """Representation of an Omada network client for presence detection."""

    def __init__(
        self,
        coordinator: OmadaClientCoordinator,
        client_mac: str,
    ) -> None:
        """Initialize the device tracker."""
        super().__init__(coordinator)
        self._client_mac = client_mac

        client_data = coordinator.data.get(client_mac, {})
        client_name = (
            client_data.get("name") or client_data.get("host_name") or client_mac
        )

        self._attr_name = client_name
        self._unique_id = f"{DOMAIN}_{client_mac}"
        self._attr_mac_address = client_mac.replace("-", ":").lower()

    # ------------------------------------------------------------------
    # ScannerEntity properties
    # ------------------------------------------------------------------

    @property
    def unique_id(self) -> str:
        """Return unique ID of the entity."""
        return self._unique_id

    @property
    def is_connected(self) -> bool:
        """Return true if the client is connected or within the grace period."""
        client = self.coordinator.data.get(self._client_mac)

        # Client present and active → connected
        if client is not None and client.get("active"):
            return True

        # Check grace period if disconnect_timeout > 0
        timeout_minutes: int = getattr(self.coordinator, "disconnect_timeout", 0)
        if timeout_minutes > 0:
            last_seen = self.coordinator.last_seen.get(self._client_mac)
            if last_seen is not None:
                elapsed = (dt.datetime.now(dt.UTC) - last_seen).total_seconds()
                if elapsed < timeout_minutes * 60:
                    return True

        return False

    @property
    def ip_address(self) -> str | None:
        """Return the IP address of the client."""
        client = self.coordinator.data.get(self._client_mac)
        if client is None:
            return None
        ip: str | None = client.get("ip")
        return ip

    @property
    def hostname(self) -> str | None:
        """Return the hostname of the client."""
        client = self.coordinator.data.get(self._client_mac)
        if client is None:
            return None
        host: str | None = client.get("host_name")
        return host

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes."""
        client = self.coordinator.data.get(self._client_mac)
        if client is None:
            return {}
        attrs: dict[str, Any] = {}
        if client.get("ssid"):
            attrs["ssid"] = client["ssid"]
        if client.get("ap_name"):
            attrs["connected_ap"] = client["ap_name"]
        if client.get("switch_name"):
            attrs["connected_switch"] = client["switch_name"]
        if client.get("wireless") is not None:
            attrs["connection_type"] = "wireless" if client["wireless"] else "wired"
        if client.get("wireless"):
            band = CLIENT_RADIO_BANDS.get(client.get("radio_id"))
            if band:
                attrs["band"] = band
            if client.get("channel") is not None:
                attrs["channel"] = client["channel"]
        return attrs

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self.async_write_ha_state()
