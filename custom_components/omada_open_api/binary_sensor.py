"""Binary sensor platform for Omada Open API integration."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.core import callback
from homeassistant.helpers.entity import (  # type: ignore[attr-defined]
    DeviceInfo,
    EntityCategory,
)

from .const import DOMAIN, ICON_POWER_SAVE, ICON_STATUS
from .coordinator import OmadaClientCoordinator, OmadaSiteCoordinator
from .devices import get_device_sort_key
from .entity import OmadaEntity

PARALLEL_UPDATES = 0

if TYPE_CHECKING:
    from collections.abc import Callable

    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from .types import OmadaConfigEntry


@dataclass(frozen=True, kw_only=True)
class OmadaBinarySensorEntityDescription(BinarySensorEntityDescription):
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

CLIENT_BINARY_SENSORS: tuple[OmadaBinarySensorEntityDescription, ...] = (
    OmadaBinarySensorEntityDescription(
        key="power_save",
        translation_key="power_save",
        name="Power Save",
        icon=ICON_POWER_SAVE,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda client: client.get("power_save", False),
        available_fn=lambda client: client.get("wireless", False),
    ),
)

# WAN port binary sensors (per-port, using translation_placeholders)
WAN_PORT_BINARY_SENSORS: tuple[OmadaBinarySensorEntityDescription, ...] = (
    OmadaBinarySensorEntityDescription(
        key="wan_connected",
        translation_key="wan_connected",
        device_class=BinarySensorDeviceClass.CONNECTIVITY,
        value_fn=lambda port: port.get("status") == 1,
    ),
    OmadaBinarySensorEntityDescription(
        key="wan_internet",
        translation_key="wan_internet",
        device_class=BinarySensorDeviceClass.CONNECTIVITY,
        value_fn=lambda port: port.get("internetState") == 1,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: OmadaConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Omada binary sensors from a config entry."""
    rd = entry.runtime_data
    coordinators: dict[str, OmadaSiteCoordinator] = rd.coordinators
    client_coordinators: list[OmadaClientCoordinator] = rd.client_coordinators

    # --- Dynamic infrastructure device binary sensors ---
    known_device_macs: set[str] = set()
    known_wan_port_keys: set[str] = set()

    for coordinator in coordinators.values():

        @callback
        def _async_check_new_devices(
            coord: OmadaSiteCoordinator = coordinator,
        ) -> None:
            """Add binary sensors for newly discovered devices."""
            devices = coord.data.get("devices", {}) if coord.data else {}
            new_macs = set(devices.keys()) - known_device_macs
            if not new_macs:
                return

            known_device_macs.update(new_macs)

            # Sort new devices by dependency order.
            new_device_list = [(coord, mac) for mac in new_macs]
            new_device_list.sort(
                key=lambda x: get_device_sort_key(
                    x[0].data.get("devices", {}).get(x[1], {}), x[1]
                )
            )

            new_entities: list[BinarySensorEntity] = [
                OmadaDeviceBinarySensor(
                    coordinator=c,
                    description=description,
                    device_mac=mac,
                )
                for c, mac in new_device_list
                for description in DEVICE_BINARY_SENSORS
            ]
            if new_entities:
                async_add_entities(new_entities)

            # WAN port binary sensors for gateway devices.
            wan_status = coord.data.get("wan_status", {})
            wan_entities: list[BinarySensorEntity] = []
            for gw_mac, ports in wan_status.items():
                for port_idx, port_data in enumerate(ports):
                    port_name = port_data.get("name", f"WAN{port_idx + 1}")
                    wan_key = f"{gw_mac}_wan_{port_idx}"
                    if wan_key not in known_wan_port_keys:
                        known_wan_port_keys.add(wan_key)
                        wan_entities.extend(
                            OmadaWanBinarySensor(
                                coordinator=coord,
                                description=desc,
                                gateway_mac=gw_mac,
                                port_index=port_idx,
                                port_name=port_name,
                            )
                            for desc in WAN_PORT_BINARY_SENSORS
                        )
            if wan_entities:
                async_add_entities(wan_entities)

        # Populate with currently known devices, then listen for updates.
        _async_check_new_devices()
        entry.async_on_unload(coordinator.async_add_listener(_async_check_new_devices))

    # --- Dynamic client binary sensors ---
    known_client_macs: set[str] = set()

    for client_coord in client_coordinators:

        @callback
        def _async_check_new_clients(
            coord: OmadaClientCoordinator = client_coord,
        ) -> None:
            """Add binary sensors for newly discovered clients."""
            new_macs = set(coord.data.keys()) - known_client_macs
            if not new_macs:
                return

            known_client_macs.update(new_macs)

            new_entities: list[BinarySensorEntity] = [
                OmadaClientBinarySensor(
                    coordinator=coord,
                    description=description,
                    client_mac=mac,
                )
                for mac in new_macs
                for description in CLIENT_BINARY_SENSORS
            ]
            if new_entities:
                async_add_entities(new_entities)

        _async_check_new_clients()
        entry.async_on_unload(client_coord.async_add_listener(_async_check_new_clients))


class OmadaDeviceBinarySensor(
    OmadaEntity[OmadaSiteCoordinator],
    BinarySensorEntity,
):
    """Representation of an Omada device binary sensor."""

    entity_description: OmadaBinarySensorEntityDescription

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
        di = DeviceInfo(
            identifiers={(DOMAIN, device_mac)},
            connections=connections,
            name=device_name,
            manufacturer="TP-Link",
            model=device_data.get("model"),
            serial_number=device_data.get("sn"),
            sw_version=device_data.get("firmware_version"),
            configuration_url=coordinator.api_client.api_url,
        )

        # Only set via_device for non-gateway devices
        if "gateway" not in device_type and "router" not in device_type:
            # For switches and other devices, use uplink device if available
            if uplink_mac:
                di["via_device"] = (DOMAIN, uplink_mac)
            # No fallback - if no uplink, device is standalone

        self._attr_device_info = di

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


class OmadaClientBinarySensor(
    OmadaEntity[OmadaClientCoordinator],
    BinarySensorEntity,
):
    """Representation of an Omada client binary sensor."""

    entity_description: OmadaBinarySensorEntityDescription

    def __init__(
        self,
        coordinator: OmadaClientCoordinator,
        description: OmadaBinarySensorEntityDescription,
        client_mac: str,
    ) -> None:
        """Initialize the client binary sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        self._client_mac = client_mac
        self._attr_unique_id = f"{client_mac}_{description.key}"

        # Link to the client device
        self._attr_device_info = {
            "identifiers": {(DOMAIN, client_mac)},
        }

    @property
    def is_on(self) -> bool:
        """Return the state of the binary sensor."""
        client_data = self.coordinator.data.get(self._client_mac)
        if client_data is None:
            return False
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


class OmadaWanBinarySensor(
    OmadaEntity[OmadaSiteCoordinator],
    BinarySensorEntity,
):
    """Binary sensor for a WAN port status on a gateway device."""

    entity_description: OmadaBinarySensorEntityDescription

    def __init__(
        self,
        coordinator: OmadaSiteCoordinator,
        description: OmadaBinarySensorEntityDescription,
        gateway_mac: str,
        port_index: int,
        port_name: str,
    ) -> None:
        """Initialize the WAN port binary sensor.

        Args:
            coordinator: Site coordinator providing WAN status data
            description: Binary sensor entity description
            gateway_mac: MAC address of the gateway
            port_index: Index into the WAN ports list
            port_name: Human-readable port name (e.g. "WAN1")

        """
        super().__init__(coordinator)
        self.entity_description = description
        self._gateway_mac = gateway_mac
        self._port_index = port_index
        self._attr_unique_id = f"{gateway_mac}_wan{port_index}_{description.key}"
        self._attr_translation_key = description.key
        self._attr_translation_placeholders = {"port_name": port_name}

        # Link to the parent gateway device.
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, gateway_mac)},
        )

    def _get_port_data(self) -> dict[str, Any] | None:
        """Return the WAN port data dict, or None if unavailable."""
        ports = self.coordinator.data.get("wan_status", {}).get(self._gateway_mac, [])
        if self._port_index < len(ports):
            return ports[self._port_index]  # type: ignore[no-any-return]
        return None

    @property
    def is_on(self) -> bool:
        """Return the state of the binary sensor."""
        port_data = self._get_port_data()
        if port_data is None:
            return False
        return self.entity_description.value_fn(port_data)

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        if not self.coordinator.last_update_success:
            return False
        return self._get_port_data() is not None
