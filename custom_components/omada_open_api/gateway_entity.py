"""Shared WAN port and VPN entity logic for the gateway platforms.

The sensor and binary sensor platforms create entities for the same WAN
ports, VPN tunnels and VPN peers. The lookups, unique IDs, device links and
discovery of new ports, tunnels and peers live here, so both platforms only
add their state (``native_value`` or ``is_on``).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import EntityDescription

from .const import DOMAIN
from .coordinator import OmadaSiteCoordinator
from .entity import OmadaEntity

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Iterator


# VPN status keys of the site coordinator data, one per VPN kind.
VPN_TYPES: tuple[str, ...] = ("s2s", "server", "client")


def wan_port_unique_id(gateway_mac: str, port_index: int, key: str) -> str:
    """Return the unique ID of a WAN port entity."""
    return f"{gateway_mac}_wan{port_index}_{key}"


def vpn_tunnel_id(tunnel: dict[str, Any]) -> Any:
    """Return a tunnel's ID: the stable config vpnId, else the stats row id."""
    return tunnel.get("vpnId", tunnel.get("id", ""))


def vpn_tunnel_unique_id(
    gateway_mac: str, vpn_type: str, tunnel_id: str, key: str
) -> str:
    """Return the unique ID of a VPN tunnel entity."""
    return f"{gateway_mac}_vpn_{vpn_type}_{tunnel_id}_{key}"


def vpn_peer_unique_id(
    gateway_mac: str, vpn_type: str, tunnel_id: str, peer_id: str, key: str
) -> str:
    """Return the unique ID of a VPN peer entity."""
    return f"{gateway_mac}_vpn_peer_{vpn_type}_{tunnel_id}_{peer_id}_{key}"


def _gateway_tunnels(
    devices: dict[str, Any], vpn_status: dict[str, list[dict[str, Any]]]
) -> Iterator[tuple[str, str, dict[str, Any]]]:
    """Yield (gateway MAC, VPN type, tunnel) for every gateway of the site."""
    gateway_macs = [
        mac for mac, dev in devices.items() if dev.get("type", "").lower() == "gateway"
    ]
    for gateway_mac in gateway_macs:
        for vpn_type in VPN_TYPES:
            for tunnel in vpn_status.get(vpn_type, []):
                yield gateway_mac, vpn_type, tunnel


def new_wan_port_entities[DescriptionT: EntityDescription, EntityT](
    wan_status: dict[str, list[dict[str, Any]]],
    known_port_keys: set[str],
    descriptions: Iterable[DescriptionT],
    create: Callable[[DescriptionT, str, int, str], EntityT],
) -> list[EntityT]:
    """Create entities for WAN ports that have none yet.

    Args:
        wan_status: WAN port lists keyed by gateway MAC
        known_port_keys: Keys ("{gateway_mac}_wan_{index}") of the ports
            that already have entities (updated in place)
        descriptions: Entity descriptions to create per port
        create: Builds one entity from (description, gateway MAC, port
            index, port name)

    Returns:
        The new entities

    """
    entities: list[EntityT] = []
    for gateway_mac, ports in wan_status.items():
        for port_index, port in enumerate(ports):
            port_key = f"{gateway_mac}_wan_{port_index}"
            if port_key in known_port_keys:
                continue
            known_port_keys.add(port_key)
            port_name = port.get("name", f"WAN{port_index + 1}")
            entities.extend(
                create(description, gateway_mac, port_index, port_name)
                for description in descriptions
            )
    return entities


def new_vpn_tunnel_entities[DescriptionT: EntityDescription, EntityT](
    devices: dict[str, Any],
    vpn_status: dict[str, list[dict[str, Any]]],
    known_unique_ids: set[str],
    descriptions: Callable[[str], Iterable[DescriptionT]],
    create: Callable[[DescriptionT, str, str, str, str], EntityT],
) -> list[EntityT]:
    """Create entities for VPN tunnels that have none yet.

    Args:
        devices: Devices of the site, to find its gateways
        vpn_status: Tunnel lists keyed by VPN type ("s2s", "server", "client")
        known_unique_ids: Unique IDs already created (updated in place)
        descriptions: Returns the entity descriptions for a VPN type
        create: Builds one entity from (description, gateway MAC, VPN type,
            tunnel ID, tunnel name)

    Returns:
        The new entities

    """
    entities: list[EntityT] = []
    for gateway_mac, vpn_type, tunnel in _gateway_tunnels(devices, vpn_status):
        tunnel_id = vpn_tunnel_id(tunnel)
        for description in descriptions(vpn_type):
            unique_id = vpn_tunnel_unique_id(
                gateway_mac, vpn_type, tunnel_id, description.key
            )
            if unique_id in known_unique_ids:
                continue
            known_unique_ids.add(unique_id)
            entities.append(
                create(
                    description,
                    gateway_mac,
                    vpn_type,
                    tunnel_id,
                    tunnel.get("name", ""),
                )
            )
    return entities


def new_vpn_peer_entities[DescriptionT: EntityDescription, EntityT](
    devices: dict[str, Any],
    vpn_status: dict[str, list[dict[str, Any]]],
    known_unique_ids: set[str],
    descriptions: Iterable[DescriptionT],
    create: Callable[[DescriptionT, str, str, str, str, str, str], EntityT],
) -> list[EntityT]:
    """Create entities for VPN peers that have none yet.

    Args:
        devices: Devices of the site, to find its gateways
        vpn_status: Tunnel lists keyed by VPN type, each tunnel with "peers"
        known_unique_ids: Unique IDs already created (updated in place)
        descriptions: Entity descriptions to create per peer
        create: Builds one entity from (description, gateway MAC, VPN type,
            tunnel ID, tunnel name, peer ID, peer name)

    Returns:
        The new entities

    """
    entities: list[EntityT] = []
    for gateway_mac, vpn_type, tunnel in _gateway_tunnels(devices, vpn_status):
        tunnel_id = vpn_tunnel_id(tunnel)
        for peer in tunnel.get("peers", []):
            peer_id = str(peer.get("id", ""))
            for description in descriptions:
                unique_id = vpn_peer_unique_id(
                    gateway_mac, vpn_type, tunnel_id, peer_id, description.key
                )
                if unique_id in known_unique_ids:
                    continue
                known_unique_ids.add(unique_id)
                entities.append(
                    create(
                        description,
                        gateway_mac,
                        vpn_type,
                        tunnel_id,
                        tunnel.get("name", ""),
                        peer_id,
                        peer.get("name", ""),
                    )
                )
    return entities


class _OmadaGatewayChildEntity(OmadaEntity[OmadaSiteCoordinator]):
    """Entity attached to a gateway device, named by its description key."""

    def __init__(
        self,
        coordinator: OmadaSiteCoordinator,
        description: EntityDescription,
        gateway_mac: str,
        unique_id: str,
        placeholders: dict[str, str],
    ) -> None:
        """Initialize the shared entity attributes."""
        super().__init__(coordinator)
        self.entity_description = description
        self._gateway_mac = gateway_mac
        self._attr_unique_id = unique_id
        self._attr_translation_key = description.key
        self._attr_translation_placeholders = placeholders
        self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, gateway_mac)})

    def _get_data(self) -> dict[str, Any] | None:
        """Return this entity's data from the coordinator, or None."""
        raise NotImplementedError

    @property
    def available(self) -> bool:
        """Return True while the coordinator succeeds and reports the data."""
        if not self.coordinator.last_update_success:
            return False
        return self._get_data() is not None


class OmadaWanPortEntity(_OmadaGatewayChildEntity):
    """Entity for one WAN port of a gateway."""

    def __init__(
        self,
        coordinator: OmadaSiteCoordinator,
        description: EntityDescription,
        gateway_mac: str,
        port_index: int,
        port_name: str,
    ) -> None:
        """Initialize the WAN port entity.

        Args:
            coordinator: Site coordinator providing WAN status data
            description: Entity description
            gateway_mac: MAC address of the gateway
            port_index: Index into the gateway's WAN port list
            port_name: Human-readable port name (e.g. "WAN1")

        """
        super().__init__(
            coordinator,
            description,
            gateway_mac,
            wan_port_unique_id(gateway_mac, port_index, description.key),
            {"port_name": port_name},
        )
        self._port_index = port_index

    def _get_data(self) -> dict[str, Any] | None:
        """Return the WAN port data dict, or None if unavailable."""
        return self._get_port_data()

    def _get_port_data(self) -> dict[str, Any] | None:
        """Return the WAN port data dict, or None if unavailable."""
        ports = self.coordinator.data.get("wan_status", {}).get(self._gateway_mac, [])
        if self._port_index < len(ports):
            return ports[self._port_index]  # type: ignore[no-any-return]
        return None


class _OmadaVpnEntity(_OmadaGatewayChildEntity):
    """Entity that reads a VPN tunnel of its VPN type from the coordinator."""

    def __init__(
        self,
        coordinator: OmadaSiteCoordinator,
        description: EntityDescription,
        gateway_mac: str,
        vpn_type: str,
        tunnel_id: str,
        unique_id: str,
        placeholders: dict[str, str],
    ) -> None:
        """Initialize the shared VPN entity attributes."""
        super().__init__(coordinator, description, gateway_mac, unique_id, placeholders)
        self._vpn_type = vpn_type
        self._tunnel_id = tunnel_id

    def _get_tunnel_data(self) -> dict[str, Any] | None:
        """Return the tunnel data dict, or None if unavailable."""
        tunnels = self.coordinator.data.get("vpn_status", {}).get(self._vpn_type, [])
        for tunnel in tunnels:
            if tunnel.get("vpnId", tunnel.get("id")) == self._tunnel_id:
                return tunnel  # type: ignore[no-any-return]
        return None


class OmadaVpnTunnelEntity(_OmadaVpnEntity):
    """Entity for one VPN tunnel reported for a gateway."""

    def __init__(
        self,
        coordinator: OmadaSiteCoordinator,
        description: EntityDescription,
        gateway_mac: str,
        vpn_type: str,
        tunnel_id: str,
        tunnel_name: str,
    ) -> None:
        """Initialize the VPN tunnel entity.

        Args:
            coordinator: Site coordinator providing VPN status data
            description: Entity description
            gateway_mac: MAC address of the parent gateway
            vpn_type: VPN type key ("s2s", "server", "client")
            tunnel_id: Tunnel ID (vpnId, else the stats row id)
            tunnel_name: Human-readable tunnel name

        """
        super().__init__(
            coordinator,
            description,
            gateway_mac,
            vpn_type,
            tunnel_id,
            vpn_tunnel_unique_id(gateway_mac, vpn_type, tunnel_id, description.key),
            {"tunnel_name": tunnel_name},
        )

    def _get_data(self) -> dict[str, Any] | None:
        """Return the tunnel data dict, or None if unavailable."""
        return self._get_tunnel_data()


class OmadaVpnPeerEntity(_OmadaVpnEntity):
    """Entity for one peer of a VPN tunnel reported for a gateway."""

    def __init__(
        self,
        coordinator: OmadaSiteCoordinator,
        description: EntityDescription,
        gateway_mac: str,
        vpn_type: str,
        tunnel_id: str,
        tunnel_name: str,
        peer_id: str,
        peer_name: str,
    ) -> None:
        """Initialize the VPN peer entity.

        Args:
            coordinator: Site coordinator providing VPN status data
            description: Entity description
            gateway_mac: MAC address of the parent gateway
            vpn_type: VPN type key ("s2s", "server", "client")
            tunnel_id: Tunnel ID (vpnId, else the stats row id)
            tunnel_name: Human-readable tunnel name
            peer_id: Peer ID within the tunnel
            peer_name: Human-readable peer name

        """
        super().__init__(
            coordinator,
            description,
            gateway_mac,
            vpn_type,
            tunnel_id,
            vpn_peer_unique_id(
                gateway_mac, vpn_type, tunnel_id, peer_id, description.key
            ),
            {"peer_name": peer_name, "tunnel_name": tunnel_name},
        )
        self._peer_id = peer_id

    def _get_data(self) -> dict[str, Any] | None:
        """Return the peer data dict within the tunnel, or None if unavailable."""
        return self._get_peer_data()

    def _get_peer_data(self) -> dict[str, Any] | None:
        """Return the peer data dict within the tunnel, or None if unavailable."""
        tunnel = self._get_tunnel_data()
        if tunnel is None:
            return None
        for peer in tunnel.get("peers", []):
            if str(peer.get("id")) == self._peer_id:
                return peer  # type: ignore[no-any-return]
        return None
