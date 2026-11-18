"""Binary sensor platform for Omada Open API integration."""

from __future__ import annotations

from dataclasses import dataclass
from functools import partial
from typing import TYPE_CHECKING, Any

from homeassistant.components.binary_sensor import (
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.components.binary_sensor.const import BinarySensorDeviceClass
from homeassistant.const import EntityCategory
from homeassistant.core import callback
from homeassistant.helpers.device_registry import DeviceInfo

from .const import CONF_ENABLE_VPN_SENSORS, DOMAIN
from .coordinator import (
    OmadaClientCoordinator,
    OmadaSiteCoordinator,
    OmadaWanSpeedTestCoordinator,
)
from .devices import build_linked_infra_device_info, get_device_sort_key
from .entity import OmadaEntity
from .gateway_entity import (
    OmadaVpnPeerEntity,
    OmadaVpnTunnelEntity,
    OmadaWanPortEntity,
    new_vpn_peer_entities,
    new_vpn_tunnel_entities,
    new_wan_port_entities,
)

PARALLEL_UPDATES = 0

# WLAN optimization status: 2 = actively running RF planning
_WLAN_OPT_STATUS_RUNNING = 2

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
        value_fn=lambda device: device.get("status") == 1,
    ),
)

CLIENT_BINARY_SENSORS: tuple[OmadaBinarySensorEntityDescription, ...] = (
    OmadaBinarySensorEntityDescription(
        key="power_save",
        translation_key="power_save",
        name="Power Save",
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

# VPN tunnel binary sensors (per tunnel, using translation_placeholders)
VPN_BINARY_SENSORS: tuple[OmadaBinarySensorEntityDescription, ...] = (
    OmadaBinarySensorEntityDescription(
        key="vpn_connected",
        translation_key="vpn_connected",
        device_class=BinarySensorDeviceClass.CONNECTIVITY,
        value_fn=lambda tunnel: (tunnel.get("connectedNum") or 0) > 0,
    ),
)

# VPN per-peer binary sensors (per peer inside each tunnel).
# Peer "status" field: 0=disconnected, 1=connected.
VPN_PEER_BINARY_SENSORS: tuple[OmadaBinarySensorEntityDescription, ...] = (
    OmadaBinarySensorEntityDescription(
        key="vpn_peer_connected",
        translation_key="vpn_peer_connected",
        device_class=BinarySensorDeviceClass.CONNECTIVITY,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda peer: peer.get("status") == 1,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: OmadaConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Omada binary sensors from a config entry."""
    rd = entry.runtime_data
    enable_vpn_sensors = entry.options.get(CONF_ENABLE_VPN_SENSORS, True)
    coordinators: dict[str, OmadaSiteCoordinator] = rd.coordinators
    client_coordinators: list[OmadaClientCoordinator] = rd.client_coordinators

    # --- Dynamic infrastructure device binary sensors ---
    known_device_macs: set[str] = set()
    known_wan_port_keys: set[str] = set()
    known_vpn_binary_keys: set[str] = set()
    known_vpn_peer_binary_keys: set[str] = set()

    for coordinator in coordinators.values():

        @callback
        def _async_check_new_devices(
            coord: OmadaSiteCoordinator = coordinator,
        ) -> None:
            """Add binary sensors for newly discovered devices."""
            devices = coord.data.get("devices", {}) if coord.data else {}
            new_macs = set(devices.keys()) - known_device_macs
            new_entities: list[BinarySensorEntity] = []
            if new_macs:
                known_device_macs.update(new_macs)

                # Sort new devices by dependency order.
                new_device_list = [(coord, mac) for mac in new_macs]
                new_device_list.sort(
                    key=lambda x: get_device_sort_key(
                        x[0].data.get("devices", {}).get(x[1], {}), x[1]
                    )
                )

                new_entities.extend(
                    OmadaDeviceBinarySensor(
                        coordinator=c,
                        description=description,
                        device_mac=mac,
                    )
                    for c, mac in new_device_list
                    for description in DEVICE_BINARY_SENSORS
                )

            # WAN port binary sensors for gateway devices.
            new_entities.extend(
                new_wan_port_entities(
                    coord.data.get("wan_status", {}),
                    known_wan_port_keys,
                    WAN_PORT_BINARY_SENSORS,
                    partial(OmadaWanBinarySensor, coord),
                )
            )

            # VPN tunnel binary sensors for gateway devices.
            vpn_status = coord.data.get("vpn_status", {})
            if enable_vpn_sensors and vpn_status:
                vpn_entities = _build_vpn_binary_sensors(
                    coord, devices, vpn_status, known_vpn_binary_keys
                )
                if vpn_entities:
                    new_entities.extend(vpn_entities)

            # VPN per-peer binary sensors for gateway devices.
            if enable_vpn_sensors:
                vpn_peer_entities = _build_vpn_peer_binary_sensors(
                    coord, devices, vpn_status, known_vpn_peer_binary_keys
                )
                if vpn_peer_entities:
                    new_entities.extend(vpn_peer_entities)

            if new_entities:
                async_add_entities(new_entities)

        # Populate with currently known devices, then listen for updates.
        _async_check_new_devices()
        entry.async_on_unload(coordinator.async_add_listener(_async_check_new_devices))

        # Site-level WLAN optimization binary sensor (one per site coordinator).
        async_add_entities(
            [
                OmadaWlanOptimizationBinarySensor(
                    coordinator=coordinator, site_id=coordinator.site_id
                )
            ]
        )

    _setup_wan_speed_test_running_sensors(
        rd.wan_speed_test_coordinators, async_add_entities
    )

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


def _setup_wan_speed_test_running_sensors(
    coordinators: dict[tuple[str, str], OmadaWanSpeedTestCoordinator],
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up one running-status binary sensor per WAN speed-test port."""
    entities: list[BinarySensorEntity] = []
    for (_, gateway_mac), coordinator in coordinators.items():
        for index, port in enumerate(
            (coordinator.data or {}).get("ports", []), start=1
        ):
            port_id = str(port.get("port") or port.get("portId") or index)
            entities.append(
                OmadaWanSpeedTestRunningBinarySensor(
                    coordinator,
                    gateway_mac,
                    port_id,
                    port.get("portName") or port.get("name") or port_id,
                )
            )
    if entities:
        async_add_entities(entities)


def _vpn_binary_sensor_descriptions(
    _vpn_type: str,
) -> tuple[OmadaBinarySensorEntityDescription, ...]:
    """Return the tunnel binary sensor descriptions (the same for every type)."""
    return VPN_BINARY_SENSORS


def _build_vpn_binary_sensors(
    coordinator: OmadaSiteCoordinator,
    devices: dict[str, Any],
    vpn_status: dict[str, list[dict[str, Any]]],
    known_vpn_keys: set[str],
) -> list[BinarySensorEntity]:
    """Create VPN tunnel binary sensor entities for all new tunnels."""
    return new_vpn_tunnel_entities(
        devices,
        vpn_status,
        known_vpn_keys,
        _vpn_binary_sensor_descriptions,
        partial(OmadaVpnBinarySensor, coordinator),
    )


def _build_vpn_peer_binary_sensors(
    coordinator: OmadaSiteCoordinator,
    devices: dict[str, Any],
    vpn_status: dict[str, list[dict[str, Any]]],
    known_vpn_peer_keys: set[str],
) -> list[BinarySensorEntity]:
    """Create VPN per-peer binary sensor entities for all new tunnels/peers."""
    return new_vpn_peer_entities(
        devices,
        vpn_status,
        known_vpn_peer_keys,
        VPN_PEER_BINARY_SENSORS,
        partial(OmadaVpnPeerBinarySensor, coordinator),
    )


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

        self._attr_device_info = build_linked_infra_device_info(coordinator, device_mac)

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


class OmadaWlanOptimizationBinarySensor(
    OmadaEntity[OmadaSiteCoordinator],
    BinarySensorEntity,
):
    """Binary sensor for WLAN optimization running state at the site level."""

    _attr_has_entity_name = True
    _attr_translation_key = "wlan_optimization_running"
    _attr_device_class = BinarySensorDeviceClass.RUNNING
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(
        self,
        coordinator: OmadaSiteCoordinator,
        site_id: str,
    ) -> None:
        """Initialize the WLAN optimization binary sensor.

        Args:
            coordinator: Site coordinator providing optimization data
            site_id: Site ID (used for unique_id and device linkage)

        """
        super().__init__(coordinator)
        self._site_id = site_id
        self._attr_unique_id = f"{site_id}_wlan_optimization_running"
        # Link to the site-level device (registered as "site_{site_id}")
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"site_{site_id}")},
        )

    def _get_optimization_data(self) -> dict[str, Any] | None:
        """Return wlan_optimization data, or None if unavailable."""
        if not self.coordinator.data:
            return None
        return self.coordinator.data.get("wlan_optimization")

    @property
    def is_on(self) -> bool:
        """Return True when optimization is actively running (status == 2)."""
        data = self._get_optimization_data()
        if data is None:
            return False
        return data.get("status") == _WLAN_OPT_STATUS_RUNNING

    @property
    def available(self) -> bool:
        """Return True when optimization data is present and coordinator healthy."""
        if not self.coordinator.last_update_success:
            return False
        return self._get_optimization_data() is not None


class OmadaWanBinarySensor(OmadaWanPortEntity, BinarySensorEntity):
    """Binary sensor for a WAN port status on a gateway device."""

    entity_description: OmadaBinarySensorEntityDescription

    @property
    def is_on(self) -> bool:
        """Return the state of the binary sensor."""
        port_data = self._get_port_data()
        if port_data is None:
            return False
        return self.entity_description.value_fn(port_data)


class OmadaWanSpeedTestRunningBinarySensor(
    OmadaEntity[OmadaWanSpeedTestCoordinator],
    BinarySensorEntity,
):
    """Binary sensor reporting whether a WAN speed test is in progress."""

    _attr_device_class = BinarySensorDeviceClass.RUNNING
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(
        self,
        coordinator: OmadaWanSpeedTestCoordinator,
        gateway_mac: str,
        port_id: str,
        port_name: str,
    ) -> None:
        """Initialize the speed-test progress sensor for one WAN port."""
        super().__init__(coordinator)
        self._port_id = port_id
        self._attr_unique_id = f"{gateway_mac}_{port_id}_wan_speed_test_running"
        self._attr_translation_key = "wan_speed_test_running"
        self._attr_translation_placeholders = {"port_name": port_name}
        self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, gateway_mac)})

    @property
    def is_on(self) -> bool:
        """Return True while Fusion reports this port's test as running."""
        for result in (self.coordinator.data or {}).get("activePortResults", []):
            if str(result.get("portId")) == self._port_id:
                return bool(result.get("status") == 2)
        return False

    @property
    def available(self) -> bool:
        """Return whether the speed-test coordinator has fetched data."""
        return self.coordinator.last_update_success


class OmadaVpnBinarySensor(OmadaVpnTunnelEntity, BinarySensorEntity):
    """Binary sensor for a VPN tunnel connection status on a gateway device."""

    entity_description: OmadaBinarySensorEntityDescription

    @property
    def is_on(self) -> bool:
        """Return the state of the binary sensor."""
        tunnel_data = self._get_tunnel_data()
        if tunnel_data is None:
            return False
        if self._vpn_type == "client":
            return tunnel_data.get("status") == 1
        return self.entity_description.value_fn(tunnel_data)


class OmadaVpnPeerBinarySensor(OmadaVpnPeerEntity, BinarySensorEntity):
    """Binary sensor for a per-peer VPN connection status on a gateway device."""

    entity_description: OmadaBinarySensorEntityDescription

    @property
    def is_on(self) -> bool:
        """Return the state of the binary sensor."""
        peer_data = self._get_peer_data()
        if peer_data is None:
            return False
        return self.entity_description.value_fn(peer_data)
