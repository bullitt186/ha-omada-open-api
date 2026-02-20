"""DataUpdateCoordinator for Omada Open API."""

from __future__ import annotations

import datetime as dt
from datetime import timedelta
import logging
from typing import TYPE_CHECKING, Any

from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import OmadaApiClient, OmadaApiError
from .clients import process_client
from .const import DOMAIN, SCAN_INTERVAL
from .devices import process_device

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)


class OmadaSiteCoordinator(DataUpdateCoordinator[dict[str, Any]]):  # type: ignore[misc]
    """Coordinator to manage fetching Omada data for a site."""

    def __init__(
        self,
        hass: HomeAssistant,
        api_client: OmadaApiClient,
        site_id: str,
        site_name: str,
    ) -> None:
        """Initialize the coordinator.

        Args:
            hass: Home Assistant instance
            api_client: Omada API client
            site_id: Site ID to fetch data for
            site_name: Site name for logging

        """
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_{site_id}",
            update_interval=timedelta(seconds=SCAN_INTERVAL),
        )
        self.api_client = api_client
        self.site_id = site_id
        self.site_name = site_name

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch data from Omada controller.

        Returns:
            Dictionary with processed device data

        Raises:
            UpdateFailed: If update fails

        """
        try:
            _LOGGER.debug(
                "Fetching data for site %s (%s)", self.site_name, self.site_id
            )

            # Fetch devices
            devices_raw = await self.api_client.get_devices(self.site_id)

            # Pre-process device data for easy access by entities
            devices = {}
            device_macs = []
            for device in devices_raw:
                mac = device.get("mac")
                if mac:
                    devices[mac] = process_device(device)
                    device_macs.append(mac)

            # Fetch uplink information for all devices
            if device_macs:
                try:
                    uplink_info_list = await self.api_client.get_device_uplink_info(
                        self.site_id, device_macs
                    )

                    # Merge uplink info into device data
                    for uplink_info in uplink_info_list:
                        device_mac = uplink_info.get(
                            "deviceMac"
                        )  # Note: API returns deviceMac not mac
                        uplink_device_mac = uplink_info.get("uplinkDeviceMac")
                        uplink_device_name = uplink_info.get("uplinkDeviceName")

                        if device_mac and device_mac in devices:
                            devices[device_mac]["uplink_device_mac"] = uplink_device_mac
                            devices[device_mac]["uplink_device_name"] = (
                                uplink_device_name
                            )
                            devices[device_mac]["uplink_device_port"] = uplink_info.get(
                                "uplinkDevicePort"
                            )
                            devices[device_mac]["link_speed"] = uplink_info.get(
                                "linkSpeed"
                            )
                            devices[device_mac]["duplex"] = uplink_info.get("duplex")

                except OmadaApiError as err:
                    _LOGGER.warning(
                        "Failed to fetch uplink info for site %s: %s",
                        self.site_name,
                        err,
                    )
                    # Continue without uplink info - not critical

            _LOGGER.debug(
                "Fetched %d devices for site %s", len(devices), self.site_name
            )

            return {  # noqa: TRY300
                "devices": devices,
                "site_id": self.site_id,
                "site_name": self.site_name,
            }

        except OmadaApiError as err:
            raise UpdateFailed(
                f"Error fetching data for site {self.site_name}: {err}"
            ) from err


class OmadaClientCoordinator(DataUpdateCoordinator[dict[str, Any]]):  # type: ignore[misc]
    """Coordinator for Omada network clients."""

    def __init__(
        self,
        hass: HomeAssistant,
        api_client: OmadaApiClient,
        site_id: str,
        site_name: str,
        selected_client_macs: list[str],
    ) -> None:
        """Initialize the client coordinator.

        Args:
            hass: Home Assistant instance
            api_client: Omada API client
            site_id: Site ID for the clients
            site_name: Human-readable site name
            selected_client_macs: List of MAC addresses to track

        """
        super().__init__(
            hass,
            _LOGGER,
            name=f"Omada Clients ({site_name})",
            update_interval=timedelta(seconds=SCAN_INTERVAL),
        )
        self.api_client = api_client
        self.site_id = site_id
        self.site_name = site_name
        self.selected_client_macs = set(selected_client_macs)

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch client data from API.

        Returns:
            Dictionary mapping client MAC addresses to client data

        """
        _LOGGER.debug(
            "Fetching client data for site %s (tracking %d clients)",
            self.site_id,
            len(self.selected_client_macs),
        )

        try:
            # Fetch all clients from the site
            result = await self.api_client.get_clients(
                self.site_id, page=1, page_size=1000
            )
            all_clients = result.get("data", [])

            # Filter to only the selected clients and index by MAC
            clients_by_mac: dict[str, Any] = {}
            for client in all_clients:
                mac = client.get("mac")
                if mac and mac in self.selected_client_macs:
                    clients_by_mac[mac] = process_client(client)

            _LOGGER.debug(
                "Fetched %d/%d selected clients from site %s",
                len(clients_by_mac),
                len(self.selected_client_macs),
                self.site_id,
            )
        except Exception as err:
            raise UpdateFailed(f"Error communicating with API: {err}") from err

        return clients_by_mac


class OmadaAppTrafficCoordinator(DataUpdateCoordinator[dict[str, dict[str, Any]]]):  # type: ignore[misc]
    """Coordinator for Omada application traffic data with daily reset."""

    def __init__(
        self,
        hass: HomeAssistant,
        api_client: OmadaApiClient,
        site_id: str,
        site_name: str,
        selected_client_macs: list[str],
        selected_app_ids: list[str],
    ) -> None:
        """Initialize the app traffic coordinator.

        Args:
            hass: Home Assistant instance
            api_client: Omada API client
            site_id: Site ID for the clients
            site_name: Human-readable site name
            selected_client_macs: List of client MAC addresses to track
            selected_app_ids: List of application IDs to track

        """
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_app_traffic_{site_id}",
            update_interval=timedelta(seconds=SCAN_INTERVAL),
        )
        self.api_client = api_client
        self.site_id = site_id
        self.site_name = site_name
        self.selected_client_macs = selected_client_macs
        self.selected_app_ids = selected_app_ids
        self._last_reset: dt.datetime | None = None

    def _get_midnight_today(self) -> dt.datetime:
        """Get midnight of current day in HA timezone."""
        now = dt_util.now()
        midnight: dt.datetime = dt_util.start_of_local_day(now)
        return midnight

    def _should_reset(self) -> bool:
        """Check if data should be reset (new day)."""
        midnight_today = self._get_midnight_today()

        if self._last_reset is None:
            return True

        # Reset if we've crossed into a new day
        return self._last_reset < midnight_today

    async def _async_update_data(self) -> dict[str, dict[str, Any]]:
        """Fetch application traffic data for all selected clients.

        Returns:
            Dictionary mapping client MAC -> app_id -> traffic data
            Format: {
                "AA:BB:CC:DD:EE:FF": {
                    "123": {"upload": 1024, "download": 2048, "app_name": "Netflix"},
                    "456": {"upload": 512, "download": 1024, "app_name": "YouTube"},
                },
            }

        """
        try:
            # Check if we should reset (new day)
            if self._should_reset():
                _LOGGER.debug(
                    "Resetting app traffic data for new day in site %s", self.site_name
                )
                self._last_reset = self._get_midnight_today()

            # Get time range: midnight today to now
            midnight = self._get_midnight_today()
            now = dt_util.now()
            start_timestamp = int(midnight.timestamp())
            end_timestamp = int(now.timestamp())

            # Fetch app traffic for each client
            client_app_data: dict[str, dict[str, Any]] = {}

            for client_mac in self.selected_client_macs:
                try:
                    # Get app traffic for this client
                    app_traffic_list = await self.api_client.get_client_app_traffic(
                        self.site_id,
                        client_mac,
                        start_timestamp,
                        end_timestamp,
                    )

                    # Process and filter to only selected apps
                    client_apps: dict[str, Any] = {}
                    for app_data in app_traffic_list:
                        app_id = str(app_data.get("applicationId", ""))

                        if app_id in self.selected_app_ids:
                            client_apps[app_id] = {
                                "upload": app_data.get("upload", 0),
                                "download": app_data.get("download", 0),
                                "traffic": app_data.get("traffic", 0),
                                "app_name": app_data.get("applicationName", "Unknown"),
                                "app_description": app_data.get(
                                    "applicationDescription"
                                ),
                                "family": app_data.get("familyName"),
                            }

                    if client_apps:
                        client_app_data[client_mac] = client_apps

                except OmadaApiError as err:
                    _LOGGER.warning(
                        "Failed to fetch app traffic for client %s: %s",
                        client_mac,
                        err,
                    )
                    # Continue with other clients even if one fails

            _LOGGER.debug(
                "Fetched app traffic for %d/%d clients in site %s",
                len(client_app_data),
                len(self.selected_client_macs),
                self.site_name,
            )

        except OmadaApiError as err:
            raise UpdateFailed(f"Error communicating with API: {err}") from err

        return client_app_data
