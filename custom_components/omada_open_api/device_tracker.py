"""Device tracker platform for Omada Open API integration."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from homeassistant.components.device_tracker import ScannerEntity
from homeassistant.core import callback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import OmadaClientCoordinator

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

_LOGGER = logging.getLogger(__name__)

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Omada device tracker from a config entry."""
    data = entry.runtime_data
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
