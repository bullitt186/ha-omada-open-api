"""Switch platform for Omada Open API integration."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from homeassistant.components.switch import SwitchDeviceClass, SwitchEntity
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import OmadaApiError
from .const import DOMAIN
from .coordinator import OmadaClientCoordinator, OmadaSiteCoordinator

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
    entities: list[SwitchEntity] = []

    # PoE switches.
    coordinators: dict[str, OmadaSiteCoordinator] = data.get("coordinators", {})
    entities.extend(
        OmadaPoeSwitch(coordinator=coordinator, port_key=port_key)
        for coordinator in coordinators.values()
        for port_key in coordinator.data.get("poe_ports", {})
    )

    # Client block/unblock switches.
    client_coordinators: list[OmadaClientCoordinator] = data.get(
        "client_coordinators", []
    )
    for coordinator in client_coordinators:
        if coordinator.data:
            entities.extend(
                OmadaClientBlockSwitch(coordinator, client_mac)
                for client_mac in coordinator.data
            )

    # LED switch (one per site).
    site_coordinators: list[OmadaSiteCoordinator] = data.get("site_coordinators", [])
    entities.extend(OmadaLedSwitch(coordinator) for coordinator in site_coordinators)

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


class OmadaClientBlockSwitch(
    CoordinatorEntity[OmadaClientCoordinator],  # type: ignore[misc]
    SwitchEntity,  # type: ignore[misc]
):
    """Switch entity to block/unblock a client.

    When the switch is ON the client is allowed (not blocked).
    When the switch is OFF the client is blocked.
    """

    _attr_has_entity_name = True
    _attr_device_class = SwitchDeviceClass.SWITCH
    _attr_icon = "mdi:account-lock"

    def __init__(
        self,
        coordinator: OmadaClientCoordinator,
        client_mac: str,
    ) -> None:
        """Initialize the client block switch."""
        super().__init__(coordinator)
        self._client_mac = client_mac

        client_data = coordinator.data.get(client_mac, {})
        client_name = (
            client_data.get("name") or client_data.get("host_name") or client_mac
        )

        self._attr_name = f"{client_name} Network Access"
        self._attr_unique_id = f"{DOMAIN}_{client_mac}_block"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"client_{client_mac}")},
        )

    # ------------------------------------------------------------------
    # State
    # ------------------------------------------------------------------

    @property
    def is_on(self) -> bool | None:
        """Return True if client is NOT blocked (has network access)."""
        client = self.coordinator.data.get(self._client_mac)
        if client is None:
            return None
        # Inverted: is_on = not blocked.
        return not client.get("blocked", False)

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        if not self.coordinator.last_update_success:
            return False
        return self.coordinator.data.get(self._client_mac) is not None

    # ------------------------------------------------------------------
    # Control
    # ------------------------------------------------------------------

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Unblock the client (allow network access)."""
        try:
            await self.coordinator.api_client.unblock_client(
                self.coordinator.site_id, self._client_mac
            )
        except OmadaApiError:
            _LOGGER.exception("Failed to unblock client %s", self._client_mac)
            return
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Block the client (deny network access)."""
        try:
            await self.coordinator.api_client.block_client(
                self.coordinator.site_id, self._client_mac
            )
        except OmadaApiError:
            _LOGGER.exception("Failed to block client %s", self._client_mac)
            return
        await self.coordinator.async_request_refresh()


class OmadaLedSwitch(
    CoordinatorEntity[OmadaSiteCoordinator],  # type: ignore[misc]
    SwitchEntity,  # type: ignore[misc]
):
    """Switch entity to control site-wide LED setting."""

    _attr_has_entity_name = False
    _attr_icon = "mdi:led-on"

    def __init__(
        self,
        coordinator: OmadaSiteCoordinator,
    ) -> None:
        """Initialize the LED switch."""
        super().__init__(coordinator)
        self._attr_name = f"{coordinator.site_name} LED"
        self._attr_unique_id = f"{DOMAIN}_{coordinator.site_id}_led"
        self._led_enabled: bool | None = None

    @property
    def is_on(self) -> bool | None:
        """Return True if LED is enabled."""
        return self._led_enabled

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return bool(self.coordinator.last_update_success)

    async def async_update(self) -> None:
        """Fetch current LED state from the API."""
        await super().async_update()
        try:
            result = await self.coordinator.api_client.get_led_setting(
                self.coordinator.site_id
            )
            self._led_enabled = result.get("enable", False)
        except OmadaApiError:
            _LOGGER.debug(
                "Could not fetch LED setting for site %s",
                self.coordinator.site_id,
            )

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Enable LEDs."""
        try:
            await self.coordinator.api_client.set_led_setting(
                self.coordinator.site_id, enable=True
            )
            self._led_enabled = True
        except OmadaApiError:
            _LOGGER.exception(
                "Failed to enable LED for site %s", self.coordinator.site_id
            )
            return
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Disable LEDs."""
        try:
            await self.coordinator.api_client.set_led_setting(
                self.coordinator.site_id, enable=False
            )
            self._led_enabled = False
        except OmadaApiError:
            _LOGGER.exception(
                "Failed to disable LED for site %s", self.coordinator.site_id
            )
            return
        self.async_write_ha_state()
