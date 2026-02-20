"""Sensor platform for Omada Open API integration."""

from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import TYPE_CHECKING, Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import PERCENTAGE, UnitOfInformation, UnitOfTime
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
from .coordinator import (
    OmadaAppTrafficCoordinator,
    OmadaClientCoordinator,
    OmadaSiteCoordinator,
)
from .devices import format_link_speed, get_device_sort_key

_LOGGER = logging.getLogger(__name__)

if TYPE_CHECKING:
    from collections.abc import Callable

    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback
    from homeassistant.helpers.typing import StateType


def _auto_scale_bytes(
    bytes_value: float | None,
) -> tuple[float | None, str | None]:
    """Auto-scale bytes to appropriate unit (B, KB, MB, GB, TB).

    Returns tuple of (scaled_value, unit).
    """
    if bytes_value is None:
        return None, None

    # Convert to float for calculations
    value = float(bytes_value)

    # Define thresholds and units (using decimal: 1 KB = 1000 B)
    if value >= 1_000_000_000_000:  # >= 1 TB
        return value / 1_000_000_000_000, UnitOfInformation.TERABYTES
    if value >= 1_000_000_000:  # >= 1 GB
        return value / 1_000_000_000, UnitOfInformation.GIGABYTES
    if value >= 1_000_000:  # >= 1 MB
        return value / 1_000_000, UnitOfInformation.MEGABYTES
    if value >= 1_000:  # >= 1 KB
        return value / 1_000, UnitOfInformation.KILOBYTES

    return value, UnitOfInformation.BYTES


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
        value_fn=lambda device: format_link_speed(device.get("link_speed")),
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

# Client sensor descriptions
CLIENT_SENSORS: tuple[OmadaSensorEntityDescription, ...] = (
    OmadaSensorEntityDescription(
        key="connection_status",
        translation_key="connection_status",
        name="Connection Status",
        icon="mdi:network",
        value_fn=lambda client: "Connected" if client.get("active") else "Disconnected",
    ),
    OmadaSensorEntityDescription(
        key="ip_address",
        translation_key="ip_address",
        name="IP Address",
        icon="mdi:ip-network",
        value_fn=lambda client: client.get("ip"),
    ),
    OmadaSensorEntityDescription(
        key="signal_strength",
        translation_key="signal_strength",
        name="Signal Strength",
        icon="mdi:wifi-strength-4",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda client: client.get("signal_level"),
        available_fn=lambda client: client.get("wireless", False)
        and client.get("signal_level") is not None,
    ),
    OmadaSensorEntityDescription(
        key="connected_to",
        translation_key="connected_to",
        name="Connected To",
        icon="mdi:access-point",
        value_fn=lambda client: client.get("ap_name")
        or client.get("switch_name")
        or client.get("gateway_name"),
    ),
    OmadaSensorEntityDescription(
        key="ssid",
        translation_key="ssid",
        name="SSID",
        icon="mdi:wifi",
        value_fn=lambda client: client.get("ssid"),
        available_fn=lambda client: client.get("wireless", False),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Omada sensors from a config entry."""
    data = entry.runtime_data
    coordinators: dict[str, OmadaSiteCoordinator] = data["coordinators"]
    client_coordinators: list[OmadaClientCoordinator] = data.get(
        "client_coordinators", []
    )
    app_traffic_coordinators: list[OmadaAppTrafficCoordinator] = data.get(
        "app_traffic_coordinators", []
    )

    # Sort devices by dependency order to avoid via_device warnings
    # 1. Gateways first (no via_device)
    # 2. Switches second (via_device to gateway or other switch)
    # 3. Other devices last (via_device to their uplink)
    # Build sorted list of (coordinator, device_mac) tuples
    device_list = [
        (coordinator, device_mac)
        for coordinator in coordinators.values()
        for device_mac in coordinator.data.get("devices", {})
    ]

    # Sort by device type priority
    device_list.sort(
        key=lambda x: get_device_sort_key(
            x[0].data.get("devices", {}).get(x[1], {}), x[1]
        )
    )

    # Create device sensors in sorted order
    entities: list[SensorEntity] = [
        OmadaDeviceSensor(
            coordinator=coordinator,
            description=description,
            device_mac=device_mac,
        )
        for coordinator, device_mac in device_list
        for description in DEVICE_SENSORS
    ]

    # Create client sensors
    entities.extend(
        [
            OmadaClientSensor(
                coordinator=coordinator,
                description=description,
                client_mac=client_mac,
            )
            for coordinator in client_coordinators
            for client_mac in coordinator.data
            for description in CLIENT_SENSORS
        ]
    )

    # Create app traffic sensors
    entities.extend(
        [
            OmadaClientAppTrafficSensor(
                coordinator=coordinator,
                client_mac=client_mac,
                app_id=app_id,
                app_name=app_data.get("app_name", "Unknown"),
                metric_type=metric_type,
            )
            for coordinator in app_traffic_coordinators
            for client_mac, client_apps in coordinator.data.items()
            for app_id, app_data in client_apps.items()
            for metric_type in ("upload", "download")
        ]
    )

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


class OmadaClientSensor(CoordinatorEntity[OmadaClientCoordinator], SensorEntity):  # type: ignore[misc]
    """Representation of an Omada client sensor."""

    entity_description: OmadaSensorEntityDescription
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: OmadaClientCoordinator,
        description: OmadaSensorEntityDescription,
        client_mac: str,
    ) -> None:
        """Initialize the client sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        self._client_mac = client_mac
        self._attr_unique_id = f"{client_mac}_{description.key}"

        # Set device info
        client_data = coordinator.data.get(client_mac, {})
        _LOGGER.debug(
            "Initializing client sensor for MAC %s, data available: %s",
            client_mac,
            bool(client_data),
        )
        client_name = (
            client_data.get("name") or client_data.get("host_name") or client_mac
        )

        # Build connections list for MAC and IP addresses
        connections = set()
        if client_mac:
            connections.add(("mac", client_mac))
        if client_data.get("ip"):
            connections.add(("ip", client_data.get("ip")))

        # Determine parent device (AP, switch, or gateway)
        parent_device_mac = None
        if client_data.get("wireless") and client_data.get("ap_mac"):
            # Wireless client connected to AP
            parent_device_mac = client_data.get("ap_mac")
        elif client_data.get("switch_mac"):
            # Wired client connected to switch
            parent_device_mac = client_data.get("switch_mac")
        elif client_data.get("gateway_mac"):
            # Client connected to gateway
            parent_device_mac = client_data.get("gateway_mac")

        # Use parent device as via_device if identified, otherwise use site
        via_device = (
            (DOMAIN, parent_device_mac)
            if parent_device_mac
            else (DOMAIN, coordinator.site_id)
        )

        self._attr_device_info = {
            "identifiers": {(DOMAIN, client_mac)},
            "connections": connections,
            "name": client_name,
            "manufacturer": client_data.get("vendor") or "Unknown",
            "model": client_data.get("device_type") or client_data.get("model"),
            "sw_version": client_data.get("os_name"),
            "configuration_url": coordinator.api_client.api_url,
            "via_device": via_device,
        }
        _LOGGER.debug(
            "Client sensor device_info for %s: parent=%s, via_device=%s",
            client_name,
            parent_device_mac,
            via_device,
        )

    @property
    def native_value(self) -> StateType:
        """Return the state of the sensor."""
        client_data = self.coordinator.data.get(self._client_mac)
        if client_data is None:
            return None
        return self.entity_description.value_fn(client_data)

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        if not self.coordinator.last_update_success:
            return False

        client_data = self.coordinator.data.get(self._client_mac)
        if client_data is None:
            return False

        return self.entity_description.available_fn(client_data)


class OmadaClientAppTrafficSensor(
    CoordinatorEntity[OmadaAppTrafficCoordinator],  # type: ignore[misc]
    SensorEntity,  # type: ignore[misc]
):
    """Representation of an Omada client application traffic sensor."""

    _attr_has_entity_name = True
    _attr_state_class = SensorStateClass.TOTAL_INCREASING

    def __init__(
        self,
        coordinator: OmadaAppTrafficCoordinator,
        client_mac: str,
        app_id: str,
        app_name: str,
        metric_type: str,
    ) -> None:
        """Initialize the app traffic sensor."""
        super().__init__(coordinator)
        self._client_mac = client_mac
        self._app_id = app_id
        self._app_name = app_name
        self._metric_type = metric_type  # "upload" or "download"

        # Create unique ID
        self._attr_unique_id = f"{client_mac}_{app_id}_{metric_type}_app_traffic"

        # Set name based on metric type
        metric_name = "Upload" if metric_type == "upload" else "Download"
        self._attr_name = f"{app_name} {metric_name}"

        # Set icon based on metric type
        self._attr_icon = (
            "mdi:upload-network" if metric_type == "upload" else "mdi:download-network"
        )

        # Get client data to set up device info
        # Note: coordinator.data structure is dict[client_mac][app_id] = {...}
        # We need to get client info from the client coordinator
        # For now, use the client MAC to link to the client device
        self._attr_device_info = {
            "identifiers": {(DOMAIN, client_mac)},
        }

        # Initial unit (will be dynamically updated based on value)
        self._attr_native_unit_of_measurement = UnitOfInformation.BYTES
        self._attr_suggested_display_precision = 2

    @property
    def native_value(self) -> float | None:
        """Return the state of the sensor with auto-scaled value."""
        # Get data from coordinator
        client_data = self.coordinator.data.get(self._client_mac, {})
        app_data = client_data.get(self._app_id, {})

        # Get raw byte value
        raw_bytes = app_data.get(self._metric_type, 0)

        # Auto-scale and update unit
        scaled_value, unit = _auto_scale_bytes(raw_bytes)

        # Update unit dynamically
        if unit:
            self._attr_native_unit_of_measurement = unit

        return scaled_value

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes."""
        client_data = self.coordinator.data.get(self._client_mac, {})
        app_data = client_data.get(self._app_id, {})

        attributes = {
            "application_id": self._app_id,
            "application_name": app_data.get("app_name", self._app_name),
            "raw_bytes": app_data.get(self._metric_type, 0),
        }

        # Add optional attributes if available
        if app_desc := app_data.get("app_description"):
            attributes["application_description"] = app_desc
        if family := app_data.get("family"):
            attributes["family"] = family

        # Add total traffic if available
        if total_traffic := app_data.get("traffic"):
            attributes["total_traffic_bytes"] = total_traffic
            scaled_total, total_unit = _auto_scale_bytes(total_traffic)
            if scaled_total and total_unit:
                attributes["total_traffic"] = f"{scaled_total:.2f} {total_unit}"

        return attributes

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        if not self.coordinator.last_update_success:
            return False

        # Check if we have data for this client and app
        client_data = self.coordinator.data.get(self._client_mac, {})
        return self._app_id in client_data
