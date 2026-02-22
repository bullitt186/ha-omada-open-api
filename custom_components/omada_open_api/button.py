"""Button platform for Omada Open API integration."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from homeassistant.components.button import ButtonDeviceClass, ButtonEntity
from homeassistant.helpers.entity import (  # type: ignore[attr-defined]
    DeviceInfo,
    EntityCategory,
)

from .api import OmadaApiError
from .const import DOMAIN
from .coordinator import OmadaClientCoordinator, OmadaSiteCoordinator
from .entity import OmadaEntity

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from .types import OmadaConfigEntry

_LOGGER = logging.getLogger(__name__)

PARALLEL_UPDATES = 1


async def async_setup_entry(
    hass: HomeAssistant,
    entry: OmadaConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Omada button entities from a config entry."""
    rd = entry.runtime_data
    entities: list[ButtonEntity] = []

    # Device reboot buttons (one per device).
    site_coordinators: list[OmadaSiteCoordinator] = list(rd.coordinators.values())
    for coordinator in site_coordinators:
        devices = coordinator.data.get("devices", {}) if coordinator.data else {}
        for device_mac in devices:
            entities.append(OmadaDeviceRebootButton(coordinator, device_mac))
            entities.append(OmadaDeviceLocateButton(coordinator, device_mac))

        # One WLAN optimization button per site.
        entities.append(OmadaWlanOptimizationButton(coordinator))

    # Client reconnect buttons (one per wireless client).
    client_coordinators: list[OmadaClientCoordinator] = rd.client_coordinators
    for coordinator in client_coordinators:  # type: ignore[assignment]
        if coordinator.data:
            for client_mac, client_data in coordinator.data.items():
                if client_data.get("wireless"):
                    entities.append(OmadaClientReconnectButton(coordinator, client_mac))  # type: ignore[arg-type]

    async_add_entities(entities)


class OmadaDeviceRebootButton(
    OmadaEntity[OmadaSiteCoordinator],
    ButtonEntity,
):
    """Button entity to reboot an Omada device (AP, switch, gateway)."""

    _attr_device_class = ButtonDeviceClass.RESTART
    _attr_icon = "mdi:restart"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(
        self,
        coordinator: OmadaSiteCoordinator,
        device_mac: str,
    ) -> None:
        """Initialize the reboot button."""
        super().__init__(coordinator)
        self._device_mac = device_mac
        self._attr_translation_key = "reboot"
        self._attr_unique_id = f"{DOMAIN}_{device_mac}_reboot"

    @property
    def _device_data(self) -> dict[str, Any]:
        """Return the current device data from the coordinator."""
        devices: dict[str, dict[str, Any]] = (
            self.coordinator.data.get("devices", {}) if self.coordinator.data else {}
        )
        result: dict[str, Any] = devices.get(self._device_mac, {})
        return result

    @property
    def device_info(self) -> DeviceInfo | None:
        """Return device information to link this button to the device."""
        device = self._device_data
        if not device:
            return None
        return DeviceInfo(identifiers={(DOMAIN, self._device_mac)})

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        if not self.coordinator.last_update_success:
            return False
        return bool(self._device_data)

    async def async_press(self) -> None:
        """Handle the button press to reboot the device."""
        try:
            await self.coordinator.api_client.reboot_device(
                self.coordinator.site_id, self._device_mac
            )
            _LOGGER.info("Reboot command sent to device %s", self._device_mac)
        except OmadaApiError:
            _LOGGER.exception("Failed to reboot device %s", self._device_mac)
            raise


class OmadaClientReconnectButton(
    OmadaEntity[OmadaClientCoordinator],
    ButtonEntity,
):
    """Button entity to reconnect a wireless client."""

    _attr_icon = "mdi:wifi-refresh"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(
        self,
        coordinator: OmadaClientCoordinator,
        client_mac: str,
    ) -> None:
        """Initialize the reconnect button."""
        super().__init__(coordinator)
        self._client_mac = client_mac
        self._attr_translation_key = "reconnect"
        self._attr_unique_id = f"{DOMAIN}_{client_mac}_reconnect"

    @property
    def device_info(self) -> DeviceInfo | None:
        """Return device information to link this button to the client."""
        client_data = self.coordinator.data.get(self._client_mac, {})
        client_name = (
            client_data.get("name") or client_data.get("host_name") or self._client_mac
        )
        return DeviceInfo(
            identifiers={(DOMAIN, self._client_mac)},
            name=client_name,
        )

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        if not self.coordinator.last_update_success:
            return False
        client = self.coordinator.data.get(self._client_mac)
        if client is None:
            return False
        return bool(client.get("active", False))

    async def async_press(self) -> None:
        """Handle the button press to reconnect the client."""
        try:
            await self.coordinator.api_client.reconnect_client(
                self.coordinator.site_id, self._client_mac
            )
            _LOGGER.info("Reconnect command sent to client %s", self._client_mac)
        except OmadaApiError:
            _LOGGER.exception("Failed to reconnect client %s", self._client_mac)
            raise


class OmadaWlanOptimizationButton(
    OmadaEntity[OmadaSiteCoordinator],
    ButtonEntity,
):
    """Button entity to trigger WLAN optimization for a site."""

    _attr_icon = "mdi:wifi-cog"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(
        self,
        coordinator: OmadaSiteCoordinator,
    ) -> None:
        """Initialize the WLAN optimization button."""
        super().__init__(coordinator)
        self._attr_translation_key = "wlan_optimization"
        self._attr_translation_placeholders = {
            "site_name": coordinator.site_name,
        }
        self._attr_unique_id = f"{DOMAIN}_{coordinator.site_id}_wlan_optimization"

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return bool(self.coordinator.last_update_success)

    async def async_press(self) -> None:
        """Handle the button press to start WLAN optimization."""
        try:
            await self.coordinator.api_client.start_wlan_optimization(
                self.coordinator.site_id
            )
            _LOGGER.info(
                "WLAN optimization started for site %s",
                self.coordinator.site_name,
            )
        except OmadaApiError:
            _LOGGER.exception(
                "Failed to start WLAN optimization for site %s",
                self.coordinator.site_name,
            )
            raise


class OmadaDeviceLocateButton(
    OmadaEntity[OmadaSiteCoordinator],
    ButtonEntity,
):
    """Button entity to trigger the locate function on a device."""

    _attr_icon = "mdi:crosshairs-gps"
    _attr_device_class = ButtonDeviceClass.IDENTIFY
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(
        self,
        coordinator: OmadaSiteCoordinator,
        device_mac: str,
    ) -> None:
        """Initialize the locate button."""
        super().__init__(coordinator)
        self._device_mac = device_mac
        self._attr_translation_key = "locate"
        self._attr_unique_id = f"{DOMAIN}_{device_mac}_locate"

    @property
    def _device_data(self) -> dict[str, Any]:
        """Return the current device data from the coordinator."""
        devices: dict[str, dict[str, Any]] = (
            self.coordinator.data.get("devices", {}) if self.coordinator.data else {}
        )
        result: dict[str, Any] = devices.get(self._device_mac, {})
        return result

    @property
    def device_info(self) -> DeviceInfo | None:
        """Return device information to link this button to the device."""
        device = self._device_data
        if not device:
            return None
        return DeviceInfo(identifiers={(DOMAIN, self._device_mac)})

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        if not self.coordinator.last_update_success:
            return False
        return bool(self._device_data)

    async def async_press(self) -> None:
        """Handle the button press to locate the device."""
        try:
            await self.coordinator.api_client.locate_device(
                self.coordinator.site_id, self._device_mac, enable=True
            )
            _LOGGER.info("Locate command sent to device %s", self._device_mac)
        except OmadaApiError:
            _LOGGER.exception("Failed to locate device %s", self._device_mac)
            raise
