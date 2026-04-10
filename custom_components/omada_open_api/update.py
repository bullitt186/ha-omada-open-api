"""Update platform for Omada Open API integration."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from homeassistant.components.update import (
    UpdateDeviceClass,
    UpdateEntity,
    UpdateEntityFeature,
)
from homeassistant.core import callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import EntityCategory  # type: ignore[attr-defined]

from .api import OmadaApiError
from .const import DOMAIN
from .coordinator import OmadaSiteCoordinator
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
    """Set up Omada update entities from a config entry."""
    coordinators: dict[str, OmadaSiteCoordinator] = entry.runtime_data.coordinators

    known_device_macs: set[str] = set()

    for coordinator in coordinators.values():

        @callback
        def _async_check_new_devices(
            coord: OmadaSiteCoordinator = coordinator,
        ) -> None:
            """Add update entities for newly discovered devices."""
            devices: dict[str, Any] = (
                coord.data.get("devices", {}) if coord.data else {}
            )
            new_macs = set(devices.keys()) - known_device_macs
            if not new_macs:
                return

            known_device_macs.update(new_macs)

            new_entities = [
                OmadaDeviceUpdateEntity(coordinator=coord, device_mac=mac)
                for mac in new_macs
            ]
            if new_entities:
                async_add_entities(new_entities)

        _async_check_new_devices()
        entry.async_on_unload(coordinator.async_add_listener(_async_check_new_devices))


class OmadaDeviceUpdateEntity(
    OmadaEntity[OmadaSiteCoordinator],
    UpdateEntity,
):
    """Update entity for Omada device firmware."""

    _attr_device_class = UpdateDeviceClass.FIRMWARE
    _attr_supported_features = (
        UpdateEntityFeature.INSTALL
        | UpdateEntityFeature.PROGRESS
        | UpdateEntityFeature.RELEASE_NOTES
    )
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(
        self,
        coordinator: OmadaSiteCoordinator,
        device_mac: str,
    ) -> None:
        """Initialize the update entity."""
        super().__init__(coordinator)
        self._device_mac = device_mac

        self._attr_unique_id = f"{DOMAIN}_{device_mac}_firmware"
        self._attr_translation_key = "firmware"

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info with current firmware version."""
        device = self.coordinator.data.get("devices", {}).get(self._device_mac, {})
        return DeviceInfo(
            identifiers={(DOMAIN, self._device_mac)},
            sw_version=device.get("firmware_version"),
        )

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
        fw_info: dict[str, Any] = self.coordinator.data.get("firmware_info", {}).get(
            self._device_mac, {}
        )
        latest = fw_info.get("lastFwVer")
        if latest:
            return str(latest)
        return self.installed_version

    @property
    def release_summary(self) -> str | None:
        """Return the release notes for the latest version."""
        fw_info: dict[str, Any] = self.coordinator.data.get("firmware_info", {}).get(
            self._device_mac, {}
        )
        return fw_info.get("fwReleaseLog")

    async def async_release_notes(self) -> str | None:
        """Return full release notes for the latest version."""
        fw_info: dict[str, Any] = self.coordinator.data.get("firmware_info", {}).get(
            self._device_mac, {}
        )
        notes: str | None = fw_info.get("fwReleaseLog")
        if notes is not None:
            # Add two trailing spaces before each newline for markdown line breaks.
            return notes.replace("\n", "  \n")
        return None

    @property
    def in_progress(self) -> bool:
        """Return True when the device is upgrading or rebooting after upgrade."""
        device = self.coordinator.data.get("devices", {}).get(self._device_mac)
        if device is None:
            return False
        # detailStatus 12 = Upgrading, 13 = Rebooting.
        return device.get("detail_status") in (12, 13)

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        if not self.coordinator.last_update_success:
            return False
        return (
            self.coordinator.data.get("devices", {}).get(self._device_mac) is not None
        )

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
        except OmadaApiError as err:
            raise HomeAssistantError(
                f"Failed to start firmware upgrade for {self._device_mac}"
            ) from err
        # Activate fast polling immediately so progress is tracked.
        self.coordinator.start_upgrade_polling()
        await self.coordinator.async_request_refresh()
