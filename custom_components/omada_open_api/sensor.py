"""Sensor platform for Omada Open API integration."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import PERCENTAGE, UnitOfTime
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    DOMAIN,
    ICON_CLIENTS,
    ICON_CPU,
    ICON_FIRMWARE,
    ICON_MEMORY,
    ICON_UPTIME,
)
from .coordinator import OmadaSiteCoordinator

if TYPE_CHECKING:
    from collections.abc import Callable

    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback
    from homeassistant.helpers.typing import StateType


@dataclass(frozen=True, kw_only=True)
class OmadaSensorEntityDescription(SensorEntityDescription):  # type: ignore[misc]
    """Describes Omada sensor entity."""

    value_fn: Callable[[dict[str, Any]], StateType]
    available_fn: Callable[[dict[str, Any]], bool] = lambda device: True


DEVICE_SENSORS: tuple[OmadaSensorEntityDescription, ...] = (
    OmadaSensorEntityDescription(
        key="client_num",
        translation_key="client_num",
        name="Connected clients",
        icon=ICON_CLIENTS,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda device: device.get("client_num", 0),
    ),
    OmadaSensorEntityDescription(
        key="uptime",
        translation_key="uptime",
        name="Uptime",
        icon=ICON_UPTIME,
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.SECONDS,
        value_fn=lambda device: device.get("uptime"),
        available_fn=lambda device: device.get("uptime") is not None,
    ),
    OmadaSensorEntityDescription(
        key="cpu_util",
        translation_key="cpu_util",
        name="CPU utilization",
        icon=ICON_CPU,
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
        value_fn=lambda device: device.get("cpu_util"),
        available_fn=lambda device: device.get("cpu_util") is not None,
    ),
    OmadaSensorEntityDescription(
        key="mem_util",
        translation_key="mem_util",
        name="Memory utilization",
        icon=ICON_MEMORY,
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
        value_fn=lambda device: device.get("mem_util"),
        available_fn=lambda device: device.get("mem_util") is not None,
    ),
    OmadaSensorEntityDescription(
        key="model",
        translation_key="model",
        name="Model",
        icon=ICON_FIRMWARE,
        entity_registry_enabled_default=False,
        value_fn=lambda device: device.get("model"),
        available_fn=lambda device: device.get("model") is not None,
    ),
    OmadaSensorEntityDescription(
        key="firmware_version",
        translation_key="firmware_version",
        name="Firmware version",
        icon=ICON_FIRMWARE,
        entity_registry_enabled_default=False,
        value_fn=lambda device: device.get("firmware_version"),
        available_fn=lambda device: device.get("firmware_version") is not None,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Omada sensors from a config entry."""
    data = hass.data[DOMAIN][entry.entry_id]
    coordinators: dict[str, OmadaSiteCoordinator] = data["coordinators"]

    entities: list[OmadaDeviceSensor] = [
        OmadaDeviceSensor(
            coordinator=coordinator,
            description=description,
            device_mac=device_mac,
        )
        for coordinator in coordinators.values()
        for device_mac in coordinator.data.get("devices", {})
        for description in DEVICE_SENSORS
    ]

    async_add_entities(entities)


class OmadaDeviceSensor(CoordinatorEntity[OmadaSiteCoordinator], SensorEntity):  # type: ignore[misc]
    """Representation of an Omada device sensor."""

    entity_description: OmadaSensorEntityDescription
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: OmadaSiteCoordinator,
        description: OmadaSensorEntityDescription,
        device_mac: str,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        self._device_mac = device_mac
        self._attr_unique_id = f"{device_mac}_{description.key}"

        # Set device info
        device_data = coordinator.data.get("devices", {}).get(device_mac, {})
        device_name = device_data.get("name", "Unknown Device")

        self._attr_device_info = {
            "identifiers": {(DOMAIN, device_mac)},
            "name": device_name,
            "manufacturer": "TP-Link",
            "model": device_data.get("model"),
            "sw_version": device_data.get("firmware_version"),
            "configuration_url": coordinator.api_client.api_url,
            "via_device": (DOMAIN, coordinator.site_id),
        }

    @property
    def native_value(self) -> StateType:
        """Return the state of the sensor."""
        device_data = self.coordinator.data.get("devices", {}).get(self._device_mac)
        if device_data is None:
            return None
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
