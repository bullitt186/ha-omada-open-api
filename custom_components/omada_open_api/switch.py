"""Switch platform for Omada Open API integration."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from homeassistant.components.switch import SwitchDeviceClass, SwitchEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import OmadaApiError
from .const import DOMAIN
from .coordinator import OmadaSiteCoordinator

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

_LOGGER = logging.getLogger(__name__)

PARALLEL_UPDATES = 1


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Omada switch entities from a config entry."""
    data = entry.runtime_data
    coordinators: dict[str, OmadaSiteCoordinator] = data.get("coordinators", {})

    entities: list[OmadaPoeSwitch] = [
        OmadaPoeSwitch(coordinator=coordinator, port_key=port_key)
        for coordinator in coordinators.values()
        for port_key in coordinator.data.get("poe_ports", {})
    ]

    async_add_entities(entities)


class OmadaPoeSwitch(
    CoordinatorEntity[OmadaSiteCoordinator],  # type: ignore[misc]
    SwitchEntity,  # type: ignore[misc]
):
    """Switch entity to control PoE on a switch port."""

    _attr_has_entity_name = True
    _attr_device_class = SwitchDeviceClass.SWITCH
    _attr_icon = "mdi:ethernet"

    def __init__(
        self,
        coordinator: OmadaSiteCoordinator,
        port_key: str,
    ) -> None:
        """Initialize the PoE switch entity.

        Args:
            coordinator: Site coordinator that provides PoE data
            port_key: Key in poe_ports dict (format: switchMac_portNum)

        """
        super().__init__(coordinator)
        self._port_key = port_key

        port_data = coordinator.data.get("poe_ports", {}).get(port_key, {})
        switch_mac: str = port_data.get("switch_mac", "")
        port_num: int = port_data.get("port", 0)
        port_name: str = port_data.get("port_name", f"Port {port_num}")

        self._switch_mac = switch_mac
        self._port_num = port_num

        self._attr_unique_id = f"{switch_mac}_port{port_num}_poe"
        self._attr_name = f"{port_name} PoE"

        # Link to the parent switch device.
        self._attr_device_info = {
            "identifiers": {(DOMAIN, switch_mac)},
        }

    # ------------------------------------------------------------------
    # State
    # ------------------------------------------------------------------

    @property
    def is_on(self) -> bool | None:
        """Return True if PoE is enabled on this port."""
        port_data = self.coordinator.data.get("poe_ports", {}).get(self._port_key)
        if port_data is None:
            return None
        return bool(port_data.get("poe_enabled", False))

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes."""
        port_data = self.coordinator.data.get("poe_ports", {}).get(self._port_key)
        if port_data is None:
            return {}
        return {
            "port": port_data.get("port"),
            "port_name": port_data.get("port_name"),
            "power": port_data.get("power"),
            "voltage": port_data.get("voltage"),
            "current": port_data.get("current"),
        }

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        if not self.coordinator.last_update_success:
            return False
        return (
            self.coordinator.data.get("poe_ports", {}).get(self._port_key) is not None
        )

    # ------------------------------------------------------------------
    # Control
    # ------------------------------------------------------------------

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Enable PoE on this port."""
        await self._set_poe(enabled=True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Disable PoE on this port."""
        await self._set_poe(enabled=False)

    async def _set_poe(self, *, enabled: bool) -> None:
        """Set PoE mode after enabling profile override.

        Args:
            enabled: Whether to enable or disable PoE

        """
        site_id: str = self.coordinator.data.get("site_id", "")
        api = self.coordinator.api_client

        try:
            # Profile override must be enabled first.
            await api.set_port_profile_override(
                site_id, self._switch_mac, self._port_num, enable=True
            )
            await api.set_port_poe_mode(
                site_id, self._switch_mac, self._port_num, poe_enabled=enabled
            )
        except OmadaApiError:
            _LOGGER.exception(
                "Failed to set PoE %s for %s port %d",
                "on" if enabled else "off",
                self._switch_mac,
                self._port_num,
            )
            return

        # Refresh coordinator data to reflect the change.
        await self.coordinator.async_request_refresh()
