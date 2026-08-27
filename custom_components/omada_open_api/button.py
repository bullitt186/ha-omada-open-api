"""Button platform for Omada Open API integration."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from homeassistant.components.button import ButtonDeviceClass, ButtonEntity
from homeassistant.core import callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity import (  # type: ignore[attr-defined]
    DeviceInfo,
    EntityCategory,
)

from .api import OmadaApiError
from .const import DOMAIN
from .coordinator import (
    OmadaClientCoordinator,
    OmadaSiteCoordinator,
    OmadaWanSpeedTestCoordinator,
)
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

    # --- Static entities (one per site, don't change dynamically) ---
    site_coordinators: list[OmadaSiteCoordinator] = list(rd.coordinators.values())
    static_entities: list[ButtonEntity] = [
        OmadaWlanOptimizationButton(coordinator) for coordinator in site_coordinators
    ]
    for (_, gateway_mac), speed_coordinator in rd.wan_speed_test_coordinators.items():
        port_definitions = (speed_coordinator.data or {}).get("ports", [])
        for index, port in enumerate(port_definitions, start=1):
            port_uuid = port.get("portUuid")
            if not port_uuid:
                continue
            port_id = str(port.get("port") or port.get("portId") or index)
            static_entities.append(
                OmadaWanSpeedTestButton(
                    coordinator=speed_coordinator,
                    gateway_mac=gateway_mac,
                    port_id=port_id,
                    port_uuid=port_uuid,
                    port_name=port.get("portName") or port.get("name") or port_id,
                )
            )
    if static_entities:
        async_add_entities(static_entities)

    # --- Dynamic infrastructure device buttons ---
    known_device_macs: set[str] = set()

    for coordinator in site_coordinators:

        @callback
        def _async_check_new_devices(
            coord: OmadaSiteCoordinator = coordinator,
        ) -> None:
            """Add buttons for newly discovered devices."""
            devices = coord.data.get("devices", {}) if coord.data else {}
            new_macs = set(devices.keys()) - known_device_macs
            if not new_macs:
                return

            known_device_macs.update(new_macs)

            new_entities: list[ButtonEntity] = []
            for mac in new_macs:
                new_entities.append(OmadaDeviceRebootButton(coord, mac))
                new_entities.append(OmadaDeviceLocateButton(coord, mac))
            if new_entities:
                async_add_entities(new_entities)

        _async_check_new_devices()
        entry.async_on_unload(coordinator.async_add_listener(_async_check_new_devices))

    # --- Dynamic client buttons ---
    known_client_macs: set[str] = set()
    client_coordinators: list[OmadaClientCoordinator] = rd.client_coordinators

    for client_coord in client_coordinators:

        @callback
        def _async_check_new_clients(
            coord: OmadaClientCoordinator = client_coord,
        ) -> None:
            """Add reconnect buttons for newly discovered wireless clients."""
            new_macs = set(coord.data.keys()) - known_client_macs
            if not new_macs:
                return

            known_client_macs.update(new_macs)

            new_entities: list[ButtonEntity] = [
                OmadaClientReconnectButton(coord, mac)
                for mac in new_macs
                if coord.data.get(mac, {}).get("wireless")
            ]
            if new_entities:
                async_add_entities(new_entities)

        _async_check_new_clients()
        entry.async_on_unload(client_coord.async_add_listener(_async_check_new_clients))


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
        except OmadaApiError as err:
            raise HomeAssistantError(
                f"Failed to reboot device {self._device_mac}"
            ) from err


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
        except OmadaApiError as err:
            raise HomeAssistantError(
                f"Failed to reconnect client {self._client_mac}"
            ) from err


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
        except OmadaApiError as err:
            raise HomeAssistantError(
                f"Failed to start WLAN optimization for site "
                f"{self.coordinator.site_name}"
            ) from err


class OmadaWanSpeedTestButton(
    OmadaEntity[OmadaWanSpeedTestCoordinator],
    ButtonEntity,
):
    """Button to run a speed test for one gateway WAN port."""

    _attr_icon = "mdi:speedometer"

    def __init__(
        self,
        coordinator: OmadaWanSpeedTestCoordinator,
        gateway_mac: str,
        port_id: str,
        port_uuid: str,
        port_name: str,
    ) -> None:
        """Initialize the WAN speed-test button."""
        super().__init__(coordinator)
        self._port_id = port_id
        self._port_uuid = port_uuid
        self._attr_unique_id = f"{gateway_mac}_{port_id}_wan_speed_test"
        self._attr_translation_key = "wan_speed_test"
        self._attr_translation_placeholders = {"port_name": port_name}
        self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, gateway_mac)})

    async def async_press(self) -> None:
        """Start the speed test and refresh the latest result."""
        try:
            await self.coordinator.api_client.trigger_gateway_wan_speed_test(
                self.coordinator.site_id,
                self.coordinator.gateway_mac,
                [self._port_uuid],
            )
        except OmadaApiError as err:
            raise HomeAssistantError("Failed to start WAN speed test") from err
        await self.coordinator.async_request_refresh()


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
        except OmadaApiError as err:
            raise HomeAssistantError(
                f"Failed to locate device {self._device_mac}"
            ) from err
