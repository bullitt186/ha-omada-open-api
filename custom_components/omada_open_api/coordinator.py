"""DataUpdateCoordinator for Omada Open API."""

from __future__ import annotations

from datetime import timedelta
import logging
import re
from typing import TYPE_CHECKING, Any

from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

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
            "type": device.get("type", "unknown"),
            # Status
            "status": device.get("status"),
            "statusCategory": device.get("statusCategory"),
            "need_upgrade": device.get("needUpgrade", False),
            # Network
            "ip": device.get("ip"),
            "uptime": self._parse_uptime(device.get("uptime")),
            # Hardware info
            "cpu_util": device.get("cpuUtil"),
            "mem_util": device.get("memUtil"),
            "firmware_version": device.get("firmwareVersion"),
            # Client info
            "client_num": device.get("clientNum", 0),
            # LED
            "led_setting": device.get("ledSetting"),
            # Location (if available)
            "site": device.get("site"),
        }
