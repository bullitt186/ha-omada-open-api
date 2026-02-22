"""Type definitions for the Omada Open API integration."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, TypeAlias

from homeassistant.config_entries import ConfigEntry

if TYPE_CHECKING:
    from homeassistant.helpers import device_registry as dr

    from .api import OmadaApiClient
    from .coordinator import (
        OmadaAppTrafficCoordinator,
        OmadaClientCoordinator,
        OmadaSiteCoordinator,
    )


@dataclass
class OmadaRuntimeData:
    """Runtime data for the Omada Open API integration."""

    api_client: OmadaApiClient
    coordinators: dict[str, OmadaSiteCoordinator]
    client_coordinators: list[OmadaClientCoordinator]
    app_traffic_coordinators: list[OmadaAppTrafficCoordinator]
    has_write_access: bool
    site_devices: dict[str, dr.DeviceEntry]
    prev_data: dict[str, Any] = field(default_factory=dict)
    prev_options: dict[str, Any] = field(default_factory=dict)


OmadaConfigEntry: TypeAlias = ConfigEntry[OmadaRuntimeData]
