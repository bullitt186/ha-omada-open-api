"""Device tracker platform for Omada Open API integration."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from homeassistant.components.device_tracker import ScannerEntity, SourceType
from homeassistant.core import callback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import OmadaClientCoordinator, OmadaSiteCoordinator
from .devices import format_detail_status

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

_LOGGER = logging.getLogger(__name__)

PARALLEL_UPDATES = 0

# A device is considered connected when its status is non-zero.
# The API returns status=0 for disconnected devices and various
# positive integers (1, 14, …) for connected states.
_STATUS_DISCONNECTED = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Omada device tracker from a config entry."""
    data = entry.runtime_data

    # --- Device trackers (APs, switches, gateways) ---
    site_coordinators: list[OmadaSiteCoordinator] = list(
        data.get("coordinators", {}).values()
    )
    for site_coordinator in site_coordinators:
        devices = (
            site_coordinator.data.get("devices", {}) if site_coordinator.data else {}
        )
        entities: list[OmadaDeviceTracker] = [
            OmadaDeviceTracker(site_coordinator, device_mac) for device_mac in devices
        ]
        if entities:
            async_add_entities(entities)

    # --- Client trackers (network clients) ---
    client_coordinators: list[OmadaClientCoordinator] = data.get(
        "client_coordinators", []
    )

    tracked: set[str] = set()

    for coordinator in client_coordinators:

        @callback  # type: ignore[misc]
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
    CoordinatorEntity[OmadaSiteCoordinator],  # type: ignore[misc]
    ScannerEntity,  # type: ignore[misc]
):
    """Representation of an Omada network device (AP/switch/gateway) for presence detection."""

    _attr_has_entity_name = False

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

    @property
    def device_info(self) -> DeviceInfo | None:
        """Return device information to link this tracker to the device."""
        device = self._device_data
        if not device:
            return None
        return DeviceInfo(
            identifiers={(DOMAIN, self._device_mac)},
            name=device.get("name", self._device_mac),
            manufacturer="TP-Link",
            model=device.get("model"),
            sw_version=device.get("firmware_version"),
        )

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

    @callback  # type: ignore[misc]
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self.async_write_ha_state()


class OmadaClientTracker(
    CoordinatorEntity[OmadaClientCoordinator],  # type: ignore[misc]
    ScannerEntity,  # type: ignore[misc]
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
        """Return true if the client is connected to the network."""
        client = self.coordinator.data.get(self._client_mac)
        if client is None:
            return False
        return bool(client.get("active", False))

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
        return attrs

    @callback  # type: ignore[misc]
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self.async_write_ha_state()
