"""Update platform for Omada Open API integration."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from homeassistant.components.update import (
    UpdateDeviceClass,
    UpdateEntity,
    UpdateEntityFeature,
)

from .api import OmadaApiError
from .const import DOMAIN
from .coordinator import OmadaSiteCoordinator
from .entity import OmadaEntity

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
    """Set up Omada update entities from a config entry."""
    data = entry.runtime_data
    coordinators: dict[str, OmadaSiteCoordinator] = data.get("coordinators", {})

    entities: list[OmadaDeviceUpdateEntity] = []
    for coordinator in coordinators.values():
        devices = coordinator.data.get("devices", {})
        entities.extend(
            OmadaDeviceUpdateEntity(coordinator=coordinator, device_mac=mac)
            for mac in devices
        )
    async_add_entities(entities)


class OmadaDeviceUpdateEntity(
    OmadaEntity[OmadaSiteCoordinator],
    UpdateEntity,  # type: ignore[misc]
):
    """Update entity for Omada device firmware."""

    _attr_device_class = UpdateDeviceClass.FIRMWARE
    _attr_supported_features = UpdateEntityFeature.INSTALL

    def __init__(
        self,
        coordinator: OmadaSiteCoordinator,
        device_mac: str,
    ) -> None:
        """Initialize the update entity."""
        super().__init__(coordinator)
        self._device_mac = device_mac

        device = coordinator.data.get("devices", {}).get(device_mac, {})
        device_name = device.get("name") or device.get("model") or device_mac

        self._attr_unique_id = f"{DOMAIN}_{device_mac}_firmware"
        self._attr_name = f"{device_name} Firmware"
        self._attr_device_info = {"identifiers": {(DOMAIN, device_mac)}}

        # Cache firmware info to avoid polling per-entity.
        self._latest_version: str | None = None
        self._release_notes: str | None = None

    @property
    def installed_version(self) -> str | None:
        """Return the current firmware version."""
        device = self.coordinator.data.get("devices", {}).get(self._device_mac)
        if device is None:
            return None
        return str(device["firmware_version"]) if "firmware_version" in device else None

    @property
    def latest_version(self) -> str | None:
        """Return the latest available firmware version."""
        if self._latest_version is not None:
            return self._latest_version
        return self.installed_version

    @property
    def release_summary(self) -> str | None:
        """Return the release notes for the latest version."""
        return self._release_notes

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        if not self.coordinator.last_update_success:
            return False
        return (
            self.coordinator.data.get("devices", {}).get(self._device_mac) is not None
        )

    async def async_update(self) -> None:
        """Fetch latest firmware info from the API."""
        await super().async_update()
        site_id: str = self.coordinator.data.get("site_id", "")
        try:
            info = await self.coordinator.api_client.get_firmware_info(
                site_id, self._device_mac
            )
            self._latest_version = info.get("lastFwVer") or self.installed_version
            self._release_notes = info.get("fwReleaseLog")
        except OmadaApiError:
            _LOGGER.debug("Could not fetch firmware info for %s", self._device_mac)
            # Fall back to installed version if firmware check fails.
            if self._latest_version is None:
                self._latest_version = self.installed_version

    async def async_install(
        self,
        version: str | None,
        backup: bool,
        **kwargs: Any,
    ) -> None:
        """Install the latest firmware update."""
        site_id: str = self.coordinator.data.get("site_id", "")
        try:
            await self.coordinator.api_client.start_online_upgrade(
                site_id, self._device_mac
            )
        except OmadaApiError:
            _LOGGER.exception(
                "Failed to start firmware upgrade for %s", self._device_mac
            )
            return
        await self.coordinator.async_request_refresh()
