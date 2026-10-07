"""Device tracker platform for Omada Open API integration."""

from __future__ import annotations

import datetime as dt
import logging
from typing import TYPE_CHECKING, Any

from homeassistant.components.device_tracker import (  # type: ignore[attr-defined]
    ScannerEntity,
    SourceType,
)
from homeassistant.core import callback
from homeassistant.helpers.entity import DeviceInfo  # type: ignore[attr-defined]

from .const import CONF_DISCONNECT_TIMEOUT, DEFAULT_DISCONNECT_TIMEOUT, DOMAIN
from .coordinator import OmadaClientCoordinator, OmadaSiteCoordinator
from .devices import build_client_device_info, format_detail_status, resolve_via_device_id
from .entity import OmadaEntity

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from .types import OmadaConfigEntry

_LOGGER = logging.getLogger(__name__)

PARALLEL_UPDATES = 0

# A device is considered connected when its status is non-zero.
# The API returns status=0 for disconnected devices and various
# positive integers (1, 14, …) for connected states.
_STATUS_DISCONNECTED = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: OmadaConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Omada device tracker from a config entry."""
    rd = entry.runtime_data

    # Client device trackers are auto-discovered from the site coordinator.
    # selected_clients remains reserved for the heavier per-client sensors and
    # controls, so users get named presence devices without opting into extra
    # polling or entity creation.
    tracked: set[str] = set()
    disconnect_timeout = entry.options.get(
        CONF_DISCONNECT_TIMEOUT, DEFAULT_DISCONNECT_TIMEOUT
    )

    # --- Device trackers (APs, switches, gateways + automatically discovered clients) ---
    known_device_macs: set[str] = set()
    site_coordinators: list[OmadaSiteCoordinator] = list(rd.coordinators.values())

    for site_coordinator in site_coordinators:

        @callback
        def _async_check_new_devices(
            coord: OmadaSiteCoordinator = site_coordinator,
        ) -> None:
            """Add newly discovered infrastructure and client device trackers."""
            devices = coord.data.get("devices", {}) if coord.data else {}
            new_macs = set(devices.keys()) - known_device_macs
            if new_macs:
                known_device_macs.update(new_macs)
                async_add_entities(
                    [OmadaDeviceTracker(coord, mac) for mac in new_macs]
                )

            all_clients = coord.data.get("all_clients", []) if coord.data else []
            new_clients: list[OmadaDiscoveredClientTracker] = []
            for client in all_clients:
                mac = client.get("mac")
                if not mac or mac in tracked:
                    continue
                _LOGGER.debug(
                    "Auto-discovered Omada client %s (%s)",
                    client.get("name", mac),
                    mac,
                )
                tracked.add(mac)
                new_clients.append(
                    OmadaDiscoveredClientTracker(
                        coord,
                        mac,
                        disconnect_timeout=disconnect_timeout,
                    )
                )
            if new_clients:
                async_add_entities(new_clients)

        _async_check_new_devices()
        entry.async_on_unload(
            site_coordinator.async_add_listener(_async_check_new_devices)
        )

    # --- Selected client trackers (backwards compatibility) ---
    client_coordinators: list[OmadaClientCoordinator] = rd.client_coordinators

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


class OmadaDiscoveredClientTracker(
    OmadaEntity[OmadaSiteCoordinator],
    ScannerEntity,
):
    """Automatically discovered Omada network client."""

    def __init__(
        self,
        coordinator: OmadaSiteCoordinator,
        client_mac: str,
        *,
        disconnect_timeout: int = DEFAULT_DISCONNECT_TIMEOUT,
    ) -> None:
        """Initialize an automatically discovered client tracker."""
        super().__init__(coordinator)
        self._client_mac = client_mac
        self._disconnect_timeout = disconnect_timeout
        self._last_seen: dt.datetime | None = dt.datetime.now(dt.UTC)

        client = self._client_data
        client_name = (
            client.get("name") or client.get("host_name") or client_mac
        )
        self._attr_name = client_name
        self._unique_id = f"{DOMAIN}_{client_mac}"
        self._attr_mac_address = client_mac.replace("-", ":").lower()
        self._update_device_info()

    @property
    def _client_data(self) -> dict[str, Any]:
        """Return the currently active client payload."""
        if not self.coordinator.data:
            return {}
        for client in self.coordinator.data.get("all_clients", []):
            if client.get("mac") == self._client_mac:
                return client
        return {}

    def _update_device_info(self) -> None:
        """Update the Home Assistant device name and metadata from Omada."""
        client = self._client_data
        if not client:
            return

        if client.get("wireless") and client.get("ap_mac"):
            parent_mac = client.get("ap_mac")
        elif client.get("switch_mac"):
            parent_mac = client.get("switch_mac")
        else:
            parent_mac = client.get("gateway_mac")

        via_identifier = (
            (DOMAIN, parent_mac)
            if parent_mac
            else (DOMAIN, f"site_{self.coordinator.site_id}")
        )
        via_device_id = resolve_via_device_id(self.coordinator.hass, via_identifier)
        self._attr_device_info = build_client_device_info(
            self._client_mac,
            client,
            self.coordinator.api_client.api_url,
            via_device_id=via_device_id,
        )

    @property
    def unique_id(self) -> str:
        """Return the stable MAC-based unique ID."""
        return self._unique_id

    @property
    def source_type(self) -> SourceType:
        """Return router as the source type."""
        return SourceType.ROUTER

    @property
    def is_connected(self) -> bool:
        """Return whether the client is currently connected or in the grace period."""
        client = self._client_data
        if client:
            self._last_seen = dt.datetime.now(dt.UTC)
            return True

        if self._disconnect_timeout > 0 and self._last_seen is not None:
            elapsed = (dt.datetime.now(dt.UTC) - self._last_seen).total_seconds()
            return elapsed < self._disconnect_timeout * 60
        return False

    @property
    def ip_address(self) -> str | None:
        """Return the current IP address."""
        value = self._client_data.get("ip")
        return value or None

    @property
    def hostname(self) -> str | None:
        """Return the client hostname."""
        client = self._client_data
        return client.get("host_name") or client.get("name")

    @property
    def extra_state_attributes(self) -> dict[str, str | None]:
        """Expose useful Omada client metadata."""
        client = self._client_data
        if not client:
            return {}

        attrs: dict[str, str | None] = {}
        for source, target in (
            ("ssid", "ssid"),
            ("ap_name", "connected_ap"),
            ("switch_name", "connected_switch"),
            ("gateway_name", "connected_gateway"),
            ("radio_band", "radio_band"),
        ):
            if client.get(source):
                attrs[target] = str(client[source])
        if client.get("channel") is not None:
            attrs["channel"] = str(client["channel"])
        if client.get("vendor"):
            attrs["vendor"] = str(client["vendor"])
        if client.get("device_type"):
            attrs["device_type"] = str(client["device_type"])
        attrs["connection_type"] = (
            "wireless" if client.get("wireless") else "wired"
        )
        return attrs

    @callback
    def _handle_coordinator_update(self) -> None:
        """Refresh device metadata and entity state."""
        self._update_device_info()
        self.async_write_ha_state()


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
    def extra_state_attributes(self) -> dict[str, str | None]:
        """Return extra state attributes."""
        client = self.coordinator.data.get(self._client_mac)
        if client is None:
            return {}
        attrs: dict[str, str | None] = {}
        if client.get("ssid"):
            attrs["ssid"] = client["ssid"]
        if client.get("ap_name"):
            attrs["connected_ap"] = client["ap_name"]
        if client.get("switch_name"):
            attrs["connected_switch"] = client["switch_name"]
        if client.get("wireless") is not None:
            attrs["connection_type"] = "wireless" if client["wireless"] else "wired"
        if client.get("radio_band"):
            attrs["radio_band"] = client["radio_band"]
        if client.get("channel") is not None:
            attrs["channel"] = str(client["channel"])
        return attrs

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self.async_write_ha_state()
