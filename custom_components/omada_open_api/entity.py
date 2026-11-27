"""Base entity for the Omada Open API integration."""

from __future__ import annotations

from typing import TYPE_CHECKING, TypeVar

from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
)

from .devices import build_infra_device_info, resolve_via_device_id

if TYPE_CHECKING:
    from homeassistant.helpers.device_registry import DeviceInfo

    from .coordinator import OmadaSiteCoordinator

_CoordinatorT = TypeVar("_CoordinatorT", bound=DataUpdateCoordinator)


class OmadaEntity(CoordinatorEntity[_CoordinatorT]):
    """Base entity for all Omada Open API entities.

    Provides shared defaults that apply to every entity in the integration.
    """

    _attr_has_entity_name = True


def build_linked_infra_device_info(
    coordinator: OmadaSiteCoordinator, device_mac: str
) -> DeviceInfo:
    """Build DeviceInfo for an infrastructure device, linked to its uplink.

    Devices other than gateways and routers are linked via_device to their
    uplink device once that device is registered; without a known uplink
    the device stays standalone.
    """
    device_data = coordinator.data.get("devices", {}).get(device_mac, {})
    via_device_id = None
    device_type = device_data.get("type", "").lower()
    uplink_mac = device_data.get("uplink_device_mac")
    if uplink_mac and "gateway" not in device_type and "router" not in device_type:
        via_device_id = resolve_via_device_id(
            coordinator.hass, uplink_mac, coordinator.config_entry
        )
    return build_infra_device_info(
        device_mac,
        device_data,
        coordinator.api_client.api_url,
        via_device_id=via_device_id,
    )
