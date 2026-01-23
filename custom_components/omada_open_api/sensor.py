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
    ICON_DEVICE_TYPE,
    ICON_FIRMWARE,
    ICON_LINK,
    ICON_MEMORY,
    ICON_TAG,
    ICON_UPTIME,
)
from .coordinator import OmadaSiteCoordinator

if TYPE_CHECKING:
    from collections.abc import Callable

    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback
    from homeassistant.helpers.typing import StateType


def _format_link_speed(speed: int | None) -> str | None:
    """Format link speed enum to readable string.

    0: Auto, 1: 10M, 2: 100M, 3: 1000M (1G), 4: 2500M (2.5G),
    5: 10G, 6: 5G, 7: 25G, 8: 100G
    """
    if speed is None:
        return None

    speed_map = {
        0: "Auto",
        1: "10 Mbps",
        2: "100 Mbps",
        3: "1 Gbps",
        4: "2.5 Gbps",
        5: "10 Gbps",
        6: "5 Gbps",
        7: "25 Gbps",
        8: "100 Gbps",
    }
    return speed_map.get(speed, f"Unknown ({speed})")


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
        value_fn=lambda device: device.get("model"),
        available_fn=lambda device: device.get("model") is not None,
    ),
    OmadaSensorEntityDescription(
        key="firmware_version",
        translation_key="firmware_version",
        name="Firmware version",
        icon=ICON_FIRMWARE,
        value_fn=lambda device: device.get("firmware_version"),
        available_fn=lambda device: device.get("firmware_version") is not None,
    ),
    OmadaSensorEntityDescription(
        key="device_type",
        translation_key="device_type",
        name="Device type",
        icon=ICON_DEVICE_TYPE,
        value_fn=lambda device: device.get("type"),
        available_fn=lambda device: device.get("type") is not None,
    ),
    OmadaSensorEntityDescription(
        key="tag",
        translation_key="tag",
        name="Tag",
        icon=ICON_TAG,
        value_fn=lambda device: device.get("tag_name"),
        available_fn=lambda device: device.get("tag_name") is not None,
    ),
    OmadaSensorEntityDescription(
        key="uplink_device",
        translation_key="uplink_device",
        name="Uplink device",
        icon=ICON_LINK,
        value_fn=lambda device: device.get("uplink_device_name"),
        available_fn=lambda device: device.get("uplink_device_name") is not None,
    ),
    OmadaSensorEntityDescription(
        key="uplink_port",
        translation_key="uplink_port",
        name="Uplink port",
        icon=ICON_LINK,
        value_fn=lambda device: device.get("uplink_device_port"),
        available_fn=lambda device: device.get("uplink_device_port") is not None,
    ),
    OmadaSensorEntityDescription(
        key="link_speed",
        translation_key="link_speed",
        name="Link speed",
        icon=ICON_LINK,
        value_fn=lambda device: _format_link_speed(device.get("link_speed")),
        available_fn=lambda device: device.get("link_speed") is not None,
    ),
    OmadaSensorEntityDescription(
        key="public_ip",
        translation_key="public_ip",
        name="Public IP",
        icon="mdi:ip-network",
        value_fn=lambda device: device.get("public_ip"),
        available_fn=lambda device: device.get("public_ip") is not None,
    ),
    OmadaSensorEntityDescription(
        key="ipv6",
        translation_key="ipv6",
        name="IPv6 addresses",
        icon="mdi:ip-network",
        value_fn=lambda device: ", ".join(device.get("ipv6", []))
        if device.get("ipv6")
        else None,
        available_fn=lambda device: bool(device.get("ipv6")),
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

        # Build connections list for MAC and IP addresses
        connections = set()
        if device_mac:
            connections.add(("mac", device_mac))
        if device_data.get("ip"):
            connections.add(("ip", device_data.get("ip")))

        self._attr_device_info = {
            "identifiers": {(DOMAIN, device_mac)},
            "connections": connections,
            "name": device_name,
            "manufacturer": "TP-Link",
            "model": device_data.get("model"),
            "serial_number": device_data.get("sn"),
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
