"""Type definitions for the Omada Open API integration."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from homeassistant.config_entries import ConfigEntry

if TYPE_CHECKING:
    from homeassistant.helpers import device_registry as dr

    from .api import OmadaApiClient
    from .coordinator import (
        OmadaAppTrafficCoordinator,
        OmadaClientCoordinator,
        OmadaDeviceStatsCoordinator,
        OmadaSiteCoordinator,
        OmadaThreatHeatmapCoordinator,
        OmadaWanSpeedTestCoordinator,
    )


@dataclass
class OmadaRuntimeData:
    """Runtime data for the Omada Open API integration."""

    api_client: OmadaApiClient
    coordinators: dict[str, OmadaSiteCoordinator]
    client_coordinators: list[OmadaClientCoordinator]
    app_traffic_coordinators: list[OmadaAppTrafficCoordinator]
    device_stats_coordinators: list[OmadaDeviceStatsCoordinator]
    has_write_access: bool
    site_devices: dict[str, dr.DeviceEntry]
    prev_data: dict[str, Any] = field(default_factory=dict)
    prev_options: dict[str, Any] = field(default_factory=dict)
    threat_heatmap_coordinators: list[OmadaThreatHeatmapCoordinator] = field(
        default_factory=list
    )
    wan_speed_test_coordinators: dict[tuple[str, str], OmadaWanSpeedTestCoordinator] = (
        field(default_factory=dict)
    )


type OmadaConfigEntry = ConfigEntry[OmadaRuntimeData]
