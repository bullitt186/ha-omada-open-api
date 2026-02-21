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
from .const import DEFAULT_DEVICE_SCAN_INTERVAL, DOMAIN, SCAN_INTERVAL
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
        scan_interval: int = DEFAULT_DEVICE_SCAN_INTERVAL,
    ) -> None:
        """Initialize the coordinator.

        Args:
            hass: Home Assistant instance
            api_client: Omada API client
            site_id: Site ID to fetch data for
            site_name: Site name for logging
            scan_interval: Update interval in seconds

        """
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_{site_id}",
            update_interval=timedelta(seconds=scan_interval),
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

            # Fetch and merge supplementary device data
            if device_macs:
                await self._merge_uplink_info(devices, device_macs)

            _LOGGER.debug(
                "Fetched %d devices for site %s", len(devices), self.site_name
            )

            # Fetch per-band client stats for AP devices
            await self._merge_band_client_stats(devices)

            # Fetch PoE budget (per-switch totals) from dashboard
            poe_budget = await self._fetch_poe_budget()

            # Fetch PoE port information for switches
            poe_ports: dict[str, dict[str, Any]] = {}
            try:
                poe_data = await self.api_client.get_switch_ports_poe(self.site_id)
                for port_info in poe_data:
                    # Only include ports that support PoE on switches that support PoE
                    if (
                        port_info.get("supportPoe")
                        and port_info.get("switchSupportPoe") == 1
                    ):
                        switch_mac = port_info.get("switchMac", "")
                        port_num = port_info.get("port", 0)
                        key = f"{switch_mac}_{port_num}"
                        poe_ports[key] = {
                            "switch_mac": switch_mac,
                            "switch_name": port_info.get("switchName", ""),
                            "port": port_num,
                            "port_name": port_info.get("portName", f"Port {port_num}"),
                            "poe_enabled": port_info.get("poe", 0) == 1,
                            "power": port_info.get("power", 0.0),
                            "voltage": port_info.get("voltage", 0.0),
                            "current": port_info.get("current", 0.0),
                            "poe_status": port_info.get("poeStatus", 0.0),
                            "pd_class": port_info.get("pdClass", ""),
                            "poe_display_type": port_info.get("poeDisplayType", -1),
                            "connected_status": port_info.get("connectedStatus", 1),
                        }
                _LOGGER.debug(
                    "Fetched %d PoE-capable ports for site %s",
                    len(poe_ports),
                    self.site_name,
                )
            except OmadaApiError as err:
                _LOGGER.warning(
                    "Failed to fetch PoE info for site %s: %s",
                    self.site_name,
                    err,
                )
                # Continue without PoE info - not critical

            return {  # noqa: TRY300
                "devices": devices,
                "poe_budget": poe_budget,
                "poe_ports": poe_ports,
                "site_id": self.site_id,
                "site_name": self.site_name,
            }

        except OmadaApiError as err:
            raise UpdateFailed(
                f"Error fetching data for site {self.site_name}: {err}"
            ) from err

    async def _merge_uplink_info(
        self,
        devices: dict[str, dict[str, Any]],
        device_macs: list[str],
    ) -> None:
        """Fetch and merge uplink information into device data."""
        try:
            uplink_info_list = await self.api_client.get_device_uplink_info(
                self.site_id, device_macs
            )

            for uplink_info in uplink_info_list:
                device_mac = uplink_info.get(
                    "deviceMac"
                )  # Note: API returns deviceMac not mac
                uplink_device_mac = uplink_info.get("uplinkDeviceMac")
                uplink_device_name = uplink_info.get("uplinkDeviceName")

                if device_mac and device_mac in devices:
                    devices[device_mac]["uplink_device_mac"] = uplink_device_mac
                    devices[device_mac]["uplink_device_name"] = uplink_device_name
                    devices[device_mac]["uplink_device_port"] = uplink_info.get(
                        "uplinkDevicePort"
                    )
                    devices[device_mac]["link_speed"] = uplink_info.get("linkSpeed")
                    devices[device_mac]["duplex"] = uplink_info.get("duplex")

        except OmadaApiError as err:
            _LOGGER.warning(
                "Failed to fetch uplink info for site %s: %s",
                self.site_name,
                err,
            )
            # Continue without uplink info - not critical

    async def _merge_band_client_stats(
        self,
        devices: dict[str, dict[str, Any]],
    ) -> None:
        """Fetch and merge per-band client counts for AP devices."""
        ap_macs = [
            mac for mac, dev in devices.items() if dev.get("type", "").lower() == "ap"
        ]
        if not ap_macs:
            return

        try:
            client_stats = await self.api_client.get_device_client_stats(
                self.site_id, ap_macs
            )
            for stat in client_stats:
                mac = stat.get("mac")
                if mac and mac in devices:
                    devices[mac]["client_num"] = stat.get("clientNum", 0)
                    devices[mac]["client_num_2g"] = stat.get("clientNum2g", 0)
                    devices[mac]["client_num_5g"] = stat.get("clientNum5g", 0)
                    devices[mac]["client_num_5g2"] = stat.get("clientNum5g2", 0)
                    devices[mac]["client_num_6g"] = stat.get("clientNum6g", 0)
        except OmadaApiError as err:
            _LOGGER.warning(
                "Failed to fetch per-band client stats for site %s: %s",
                self.site_name,
                err,
            )
            # Continue without per-band stats - not critical

    async def _fetch_poe_budget(self) -> dict[str, dict[str, Any]]:
        """Fetch per-switch PoE budget data from the dashboard endpoint.

        Returns:
            Dictionary keyed by switch MAC with budget metrics.

        """
        poe_budget: dict[str, dict[str, Any]] = {}
        try:
            poe_usage = await self.api_client.get_poe_usage(self.site_id)
            for switch_info in poe_usage:
                switch_mac = switch_info.get("mac", "")
                if switch_mac:
                    poe_budget[switch_mac] = {
                        "mac": switch_mac,
                        "name": switch_info.get("name", ""),
                        "port_num": switch_info.get("portNum", 0),
                        "total_power": switch_info.get("totalPower", 0),
                        "total_power_used": switch_info.get("totalPowerUsed", 0),
                        "total_percent_used": switch_info.get("totalPercentUsed", 0.0),
                    }
            _LOGGER.debug(
                "Fetched PoE budget for %d switches in site %s",
                len(poe_budget),
                self.site_name,
            )
        except OmadaApiError as err:
            _LOGGER.warning(
                "Failed to fetch PoE usage for site %s: %s",
                self.site_name,
                err,
            )
            # Continue without PoE budget - not critical
        return poe_budget


class OmadaClientCoordinator(DataUpdateCoordinator[dict[str, Any]]):  # type: ignore[misc]
    """Coordinator for Omada network clients."""

    def __init__(
        self,
        hass: HomeAssistant,
        api_client: OmadaApiClient,
        site_id: str,
        site_name: str,
        selected_client_macs: list[str],
        scan_interval: int = SCAN_INTERVAL,
    ) -> None:
        """Initialize the client coordinator.

        Args:
            hass: Home Assistant instance
            api_client: Omada API client
            site_id: Site ID for the clients
            site_name: Human-readable site name
            selected_client_macs: List of MAC addresses to track
            scan_interval: Update interval in seconds

        """
        super().__init__(
            hass,
            _LOGGER,
            name=f"Omada Clients ({site_name})",
            update_interval=timedelta(seconds=scan_interval),
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
        scan_interval: int = SCAN_INTERVAL,
    ) -> None:
        """Initialize the app traffic coordinator.

        Args:
            hass: Home Assistant instance
            api_client: Omada API client
            site_id: Site ID for the clients
            site_name: Human-readable site name
            selected_client_macs: List of client MAC addresses to track
            selected_app_ids: List of application IDs to track
            scan_interval: Update interval in seconds

        """
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_app_traffic_{site_id}",
            update_interval=timedelta(seconds=scan_interval),
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
