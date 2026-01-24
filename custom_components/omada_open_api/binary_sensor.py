"""Binary sensor platform for Omada Open API integration."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, ICON_STATUS
from .coordinator import OmadaSiteCoordinator

if TYPE_CHECKING:
    from collections.abc import Callable

    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback


@dataclass(frozen=True, kw_only=True)
class OmadaBinarySensorEntityDescription(BinarySensorEntityDescription):  # type: ignore[misc]
    """Describes Omada binary sensor entity."""

    value_fn: Callable[[dict[str, Any]], bool]
    available_fn: Callable[[dict[str, Any]], bool] = lambda device: True


DEVICE_BINARY_SENSORS: tuple[OmadaBinarySensorEntityDescription, ...] = (
    OmadaBinarySensorEntityDescription(
        key="status",
        translation_key="status",
        name="Status",
        device_class=BinarySensorDeviceClass.CONNECTIVITY,
        icon=ICON_STATUS,
        value_fn=lambda device: device.get("status") == 1,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Omada binary sensors from a config entry."""
    data = hass.data[DOMAIN][entry.entry_id]
    coordinators: dict[str, OmadaSiteCoordinator] = data["coordinators"]

    # Sort devices by dependency order to avoid via_device warnings
    # 1. Gateways first (no via_device)
    # 2. Switches second (via_device to gateway or other switch)
    # 3. Other devices last (via_device to their uplink)
    def get_device_sort_key(
        coordinator: OmadaSiteCoordinator, device_mac: str
    ) -> tuple[int, str]:
        """Get sort key for device ordering."""
        device_data = coordinator.data.get("devices", {}).get(device_mac, {})
        device_type = device_data.get("type", "").lower()

        # Priority order: gateway(0), switch(1), others(2)
        if "gateway" in device_type:
            return (0, device_mac)
        if "switch" in device_type:
            return (1, device_mac)
        return (2, device_mac)

    # Build sorted list of (coordinator, device_mac) tuples
    device_list = [
        (coordinator, device_mac)
        for coordinator in coordinators.values()
        for device_mac in coordinator.data.get("devices", {})
    ]

    # Sort by device type priority
    device_list.sort(key=lambda x: get_device_sort_key(x[0], x[1]))

    # Create binary sensors in sorted order
    entities: list[OmadaDeviceBinarySensor] = [
        OmadaDeviceBinarySensor(
            coordinator=coordinator,
            description=description,
            device_mac=device_mac,
        )
        for coordinator, device_mac in device_list
        for description in DEVICE_BINARY_SENSORS
    ]

    async_add_entities(entities)


class OmadaDeviceBinarySensor(
    CoordinatorEntity[OmadaSiteCoordinator],
    BinarySensorEntity,
):
    """Representation of an Omada device binary sensor."""

    entity_description: OmadaBinarySensorEntityDescription
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: OmadaSiteCoordinator,
        description: OmadaBinarySensorEntityDescription,
        device_mac: str,
    ) -> None:
        """Initialize the binary sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        self._device_mac = device_mac
        self._attr_unique_id = f"{device_mac}_{description.key}"

        # Set device info
        device_data = coordinator.data.get("devices", {}).get(device_mac, {})
        device_name = device_data.get("name", "Unknown Device")

        # Build connections list for MAC and IP addresses
        connections = set()
        if device_mac:
            connections.add(("mac", device_mac))
        if device_data.get("ip"):
            connections.add(("ip", device_data.get("ip")))

        # Determine device type and via_device
        device_type = device_data.get("type", "").lower()
        uplink_mac = device_data.get("uplink_device_mac")

        # Build device info
        device_info = {
            "identifiers": {(DOMAIN, device_mac)},
            "connections": connections,
            "name": device_name,
            "manufacturer": "TP-Link",
            "model": device_data.get("model"),
            "serial_number": device_data.get("sn"),
            "sw_version": device_data.get("firmware_version"),
            "configuration_url": coordinator.api_client.api_url,
        }

        # Only set via_device for non-gateway devices
        if "gateway" not in device_type and "router" not in device_type:
            # For switches and other devices, use uplink device if available
            if uplink_mac:
                device_info["via_device"] = (DOMAIN, uplink_mac)
            # No fallback - if no uplink, device is standalone

        self._attr_device_info = device_info

    @property
    def is_on(self) -> bool:
        """Return the state of the binary sensor."""
        device_data = self.coordinator.data.get("devices", {}).get(self._device_mac)
        if device_data is None:
            return False
        return self.entity_description.value_fn(device_data)

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        if not self.coordinator.last_update_success:
            return False

        device_data = self.coordinator.data.get("devices", {}).get(self._device_mac)
        if device_data is None:
            return False

        return self.entity_description.available_fn(device_data)
