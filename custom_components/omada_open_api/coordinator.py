"""DataUpdateCoordinator for Omada Open API."""

from __future__ import annotations

import datetime as dt
from datetime import timedelta
import logging
import re
from typing import TYPE_CHECKING, Any

from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import OmadaApiClient, OmadaApiError
from .const import DOMAIN, SCAN_INTERVAL

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
            for device in devices_raw:
                mac = device.get("mac")
                if mac:
                    devices[mac] = self._process_device(device)

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

    def _parse_uptime(self, uptime_str: str | int | None) -> int | None:
        """Parse uptime string to seconds.

        Args:
            uptime_str: Uptime as string (e.g., "4day(s) 17h 26m 57s") or int (seconds)

        Returns:
            Uptime in seconds, or None if parsing fails

        """
        if uptime_str is None:
            return None

        # If already an integer, return it
        if isinstance(uptime_str, int):
            return uptime_str

        # Parse formatted string like "4day(s) 17h 26m 57s"
        try:
            total_seconds = 0
            # Extract days
            days_match = re.search(r"(\d+)day", str(uptime_str))
            if days_match:
                total_seconds += int(days_match.group(1)) * 86400

            # Extract hours
            hours_match = re.search(r"(\d+)h", str(uptime_str))
            if hours_match:
                total_seconds += int(hours_match.group(1)) * 3600

            # Extract minutes
            minutes_match = re.search(r"(\d+)m", str(uptime_str))
            if minutes_match:
                total_seconds += int(minutes_match.group(1)) * 60

            # Extract seconds
            seconds_match = re.search(r"(\d+)s", str(uptime_str))
            if seconds_match:
                total_seconds += int(seconds_match.group(1))

            return total_seconds if total_seconds > 0 else None  # noqa: TRY300
        except (ValueError, AttributeError) as err:
            _LOGGER.warning("Failed to parse uptime '%s': %s", uptime_str, err)
            return None

    def _process_device(self, device: dict[str, Any]) -> dict[str, Any]:
        """Process raw device data into a normalized format.

        Args:
            device: Raw device data from API

        Returns:
            Processed device data

        """
        return {
            # Identification
            "mac": device.get("mac"),
            "name": device.get("name", "Unknown Device"),
            "model": device.get("model", "Unknown"),
            "model_name": device.get("modelName"),
            "model_version": device.get("modelVersion"),
            "type": device.get("type", "unknown"),
            "subtype": device.get("subtype"),
            "device_series_type": device.get("deviceSeriesType"),
            "sn": device.get("sn"),
            # Status
            "status": device.get("status"),
            "status_category": device.get("statusCategory"),
            "detail_status": device.get("detailStatus"),
            "need_upgrade": device.get("needUpgrade", False),
            "last_seen": device.get("lastSeen"),
            # Network
            "ip": device.get("ip"),
            "ipv6": device.get("ipv6", []),
            "public_ip": device.get("publicIp"),
            "uptime": self._parse_uptime(device.get("uptime")),
            # Hardware info
            "cpu_util": device.get("cpuUtil"),
            "mem_util": device.get("memUtil"),
            "firmware_version": device.get("firmwareVersion"),
            "compatible": device.get("compatible"),
            "active": device.get("active"),
            # Client info
            "client_num": device.get("clientNum", 0),
            # Uplink info
            "uplink_device_mac": device.get("uplinkDeviceMac"),
            "uplink_device_name": device.get("uplinkDeviceName"),
            "uplink_device_port": device.get("uplinkDevicePort"),
            "link_speed": device.get("linkSpeed"),
            "duplex": device.get("duplex"),
            # Tags and organization
            "tag_name": device.get("tagName"),
            "license_status": device.get("licenseStatus"),
            "in_white_list": device.get("inWhiteList"),
            "switch_consistent": device.get("switchConsistent"),
            # LED
            "led_setting": device.get("ledSetting"),
            # Location (if available)
            "site": device.get("site"),
        }


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
                    clients_by_mac[mac] = self._process_client(client)

            _LOGGER.debug(
                "Fetched %d/%d selected clients from site %s",
                len(clients_by_mac),
                len(self.selected_client_macs),
                self.site_id,
            )
        except Exception as err:
            raise UpdateFailed(f"Error communicating with API: {err}") from err

        return clients_by_mac

    def _process_client(self, client: dict[str, Any]) -> dict[str, Any]:
        """Process and normalize client data.

        Args:
            client: Raw client data from API

        Returns:
            Processed client dictionary with normalized fields

        """
        return {
            # Identity
            "mac": client.get("mac"),
            "name": client.get("name") or client.get("hostName") or "Unknown",
            "host_name": client.get("hostName"),
            "ip": client.get("ip"),
            "ipv6_list": client.get("ipv6List", []),
            # Device info
            "vendor": client.get("vendor"),
            "device_type": client.get("deviceType"),
            "device_category": client.get("deviceCategory"),
            "os_name": client.get("osName"),
            "model": client.get("model"),
            # Connection info
            "active": client.get("active", False),
            "wireless": client.get("wireless", False),
            "connect_dev_type": client.get("connectDevType"),
            "ssid": client.get("ssid"),
            "signal_level": client.get("signalLevel"),
            "signal_rank": client.get("signalRank"),
            "rssi": client.get("rssi"),
            # AP connection (wireless)
            "ap_name": client.get("apName"),
            "ap_mac": client.get("apMac"),
            "radio_id": client.get("radioId"),
            "channel": client.get("channel"),
            # Switch connection (wired)
            "switch_name": client.get("switchName"),
            "switch_mac": client.get("switchMac"),
            "port": client.get("port"),
            "port_name": client.get("portName"),
            # Gateway connection
            "gateway_name": client.get("gatewayName"),
            "gateway_mac": client.get("gatewayMac"),
            # Network
            "network_name": client.get("networkName"),
            "vid": client.get("vid"),
            # Traffic
            "activity": client.get("activity"),
            "upload_activity": client.get("uploadActivity"),
            "traffic_down": client.get("trafficDown"),
            "traffic_up": client.get("trafficUp"),
            # Status
            "uptime": client.get("uptime"),
            "last_seen": client.get("lastSeen"),
            "blocked": client.get("blocked", False),
            "guest": client.get("guest", False),
            "auth_status": client.get("authStatus"),
        }


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
