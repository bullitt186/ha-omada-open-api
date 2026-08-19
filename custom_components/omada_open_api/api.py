"""API client for Omada Open API."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

import aiohttp

from .auth import ClientCredentialsAuth, OmadaAuthStrategy
from .const import DEFAULT_TIMEOUT

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable
    import datetime as dt

_LOGGER = logging.getLogger(__name__)


class OmadaApiClient:
    """Omada Open API client."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        token_update_callback: Callable[[str, str, str], Awaitable[None]],
        api_url: str,
        omada_id: str,
        client_id: str,
        client_secret: str,
        access_token: str,
        refresh_token: str,
        token_expires_at: dt.datetime,
        *,
        auth: OmadaAuthStrategy | None = None,
    ) -> None:
        """Initialize the API client.

        Args:
            session: aiohttp client session (injected from HA)
            token_update_callback: Async callback to persist updated tokens.
                Called with (access_token, refresh_token, expires_at_iso).
            api_url: Base API URL (cloud or local controller)
            omada_id: Omada controller ID
            client_id: OAuth2 client ID
            client_secret: OAuth2 client secret
            access_token: Current access token
            refresh_token: Current refresh token
            token_expires_at: When the access token expires
            auth: Optional pre-built auth strategy (overrides credential args)

        """
        self._session = session
        self._api_url = api_url.rstrip("/")
        self._omada_id = omada_id
        self._use_v1_clients = False

        if auth is not None:
            self._auth = auth
        else:
            self._auth = ClientCredentialsAuth(
                session=session,
                token_update_callback=token_update_callback,
                api_url=api_url,
                omada_id=omada_id,
                client_id=client_id,
                client_secret=client_secret,
                access_token=access_token,
                refresh_token=refresh_token,
                token_expires_at=token_expires_at,
            )

    @property
    def api_url(self) -> str:
        """Return the API URL."""
        return self._api_url

    async def _authenticated_request(
        self,
        method: str,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        json_data: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Make an authenticated API request with automatic token renewal.

        Handles HTTP 401 and API error codes -44112 (token expired) and
        -44113 (token invalid) by refreshing the token and retrying once.

        Args:
            method: HTTP method ("get", "post", or "put")
            url: Full URL to request
            params: Query parameters
            json_data: JSON body (for POST requests)

        Returns:
            Parsed JSON response dictionary

        Raises:
            OmadaApiError: If the request fails after retry

        """
        await self._auth.ensure_valid_session()

        for attempt in range(2):
            headers: dict[str, str] = {"Content-Type": "application/json"}
            self._auth.decorate_request(headers)

            try:
                request_kwargs: dict[str, Any] = {
                    "headers": headers,
                    "timeout": aiohttp.ClientTimeout(total=DEFAULT_TIMEOUT),
                }
                if params:
                    request_kwargs["params"] = params
                if json_data is not None:
                    request_kwargs["json"] = json_data

                async with getattr(self._session, method)(
                    url, **request_kwargs
                ) as response:
                    if response.status == 401:
                        if attempt == 0:
                            _LOGGER.debug(
                                "HTTP 401 on API request, refreshing token and "
                                "retrying (attempt %s)",
                                attempt + 1,
                            )
                            await self._auth.handle_auth_failure()
                            continue
                        response_text = await response.text()
                        raise OmadaApiError(
                            f"HTTP 401 after token refresh: {response_text}"
                        )

                    if response.status != 200:
                        response_text = await response.text()
                        if response.status == 404:
                            _LOGGER.debug("HTTP 404 (endpoint not supported): %s", url)
                        else:
                            _LOGGER.error(
                                "HTTP error %s: %s", response.status, response_text
                            )
                        raise OmadaApiError(f"HTTP {response.status}: {response_text}")

                    result = await response.json(content_type=None)
                    error_code = result.get("errorCode")

                    # Token-related errors: refresh and retry
                    if error_code in (-44112, -44113):
                        if attempt == 0:
                            _LOGGER.info(
                                "API returned token error %s: %s, refreshing "
                                "token and retrying",
                                error_code,
                                result.get("msg", ""),
                            )
                            await self._auth.handle_auth_failure()
                            continue
                        raise OmadaApiError(
                            f"Token error {error_code} persists after refresh: "
                            f"{result.get('msg', '')}"
                        )

                    if error_code != 0:
                        error_msg = result.get("msg", "Unknown error")
                        raise OmadaApiError(
                            f"API error {error_code}: {error_msg}",
                            error_code=error_code,
                        )

                    return result  # type: ignore[no-any-return]

            except aiohttp.ClientError as err:
                raise OmadaApiError(f"Connection error: {err}") from err

        # Should not reach here, but just in case
        raise OmadaApiError("Request failed after all retry attempts")

    async def get_sites(self) -> list[dict[str, Any]]:
        """Get list of sites from Omada controller.

        Returns:
            List of site dictionaries

        Raises:
            OmadaApiError: If API request fails

        """
        url = f"{self._api_url}/openapi/v1/{self._omada_id}/sites"
        params = {"pageSize": 100, "page": 1}

        result = await self._authenticated_request("get", url, params=params)
        return result["result"]["data"]  # type: ignore[no-any-return]

    async def get_devices(self, site_id: str) -> list[dict[str, Any]]:
        """Fetch devices for a specific site.

        Args:
            site_id: The site ID to fetch devices for

        Returns:
            List of device dictionaries

        Raises:
            OmadaApiError: If fetching devices fails

        """
        url = f"{self._api_url}/openapi/v1/{self._omada_id}/sites/{site_id}/devices"
        params = {"pageSize": 100, "page": 1}

        _LOGGER.debug("Fetching devices from %s", url)

        result = await self._authenticated_request("get", url, params=params)
        return result["result"]["data"]  # type: ignore[no-any-return]

    async def get_device_uplink_info(
        self, site_id: str, device_macs: list[str]
    ) -> list[dict[str, Any]]:
        """Get uplink information for specified devices.

        Args:
            site_id: Site ID
            device_macs: List of device MAC addresses to query

        Returns:
            List of uplink info dictionaries containing uplinkDeviceMac,
            uplinkDeviceName, uplinkDevicePort, linkSpeed, duplex

        Raises:
            OmadaApiError: If fetching uplink info fails

        """
        if not device_macs:
            return []

        url = (
            f"{self._api_url}/openapi/v1/{self._omada_id}"
            f"/sites/{site_id}/devices/uplink-info"
        )

        _LOGGER.debug(
            "Fetching uplink info for %d devices from %s", len(device_macs), url
        )

        result = await self._authenticated_request(
            "post", url, json_data={"deviceMacs": device_macs}
        )
        return result["result"]  # type: ignore[no-any-return]

    async def get_clients(
        self, site_id: str, page: int = 1, page_size: int = 100, scope: int = 1
    ) -> dict[str, Any]:
        """Get clients for a site.

        Tries the v2 POST endpoint first. On error -1600 (unsupported on
        Fusion firmware), falls back to the v1 GET endpoint permanently.

        Args:
            site_id: Site ID to get clients for
            page: Page number (starts at 1)
            page_size: Number of clients per page (1-1000)
            scope: Client scope filter — 0: all, 1: online (default),
                2: offline, 3: blocked

        Returns:
            Dictionary with client data including totalRows, currentPage,
            and data list

        """
        if self._use_v1_clients:
            return await self._get_clients_v1(site_id, page, page_size)

        try:
            url = f"{self._api_url}/openapi/v2/{self._omada_id}/sites/{site_id}/clients"
            body = {
                "page": page,
                "pageSize": page_size,
                "scope": scope,
                "filters": {},
            }
            result = await self._authenticated_request("post", url, json_data=body)
            return result["result"]  # type: ignore[no-any-return]
        except OmadaApiError as err:
            if err.error_code == -1600:
                _LOGGER.info("v2 clients endpoint unsupported, falling back to v1 GET")
                self._use_v1_clients = True
                return await self._get_clients_v1(site_id, page, page_size)
            raise

    async def _get_clients_v1(
        self, site_id: str, page: int = 1, page_size: int = 100
    ) -> dict[str, Any]:
        """Get clients using the v1 GET endpoint (Fusion fallback)."""
        url = f"{self._api_url}/openapi/v1/{self._omada_id}/sites/{site_id}/clients"
        params = {"page": page, "pageSize": page_size}
        result = await self._authenticated_request("get", url, params=params)
        return result["result"]  # type: ignore[no-any-return]

    async def get_applications(
        self, site_id: str, page: int = 1, page_size: int = 1000
    ) -> dict[str, Any]:
        """Get all available applications for DPI tracking.

        Args:
            site_id: Site ID to get applications for
            page: Page number (starts at 1)
            page_size: Number of applications per page (1-1000)

        Returns:
            Dictionary with application data including totalRows, currentPage,
            and data list. Each app has: applicationId, applicationName,
            description, family

        """
        url = (
            f"{self._api_url}/openapi/v1/{self._omada_id}"
            f"/sites/{site_id}/applicationControl/applications"
        )
        params = {"page": page, "pageSize": page_size}

        result = await self._authenticated_request("get", url, params=params)
        return result["result"]  # type: ignore[no-any-return]

    async def get_client_app_traffic(
        self, site_id: str, client_mac: str, start: int, end: int
    ) -> list[dict[str, Any]]:
        """Get application traffic data for a specific client.

        Args:
            site_id: Site ID
            client_mac: Client MAC address
            start: Start timestamp in seconds (Unix timestamp)
            end: End timestamp in seconds (Unix timestamp)

        Returns:
            List of application traffic data, each with:
            applicationId, applicationName, upload, download, traffic, etc.

        """
        url = (
            f"{self._api_url}/openapi/v1/{self._omada_id}"
            f"/sites/{site_id}/dashboard/specificClientInfo/{client_mac}"
        )
        params = {"start": start, "end": end}

        result = await self._authenticated_request("get", url, params=params)
        return result.get("result", [])  # type: ignore[no-any-return]

    async def get_poe_usage(self, site_id: str) -> list[dict[str, Any]]:
        """Get PoE usage summary for all switches in a site.

        Fetches per-switch PoE budget data including total power,
        power used, and percentage used.

        Args:
            site_id: Site ID to get PoE usage for

        Returns:
            List of switch PoE usage dictionaries, each containing mac,
            name, portNum, totalPowerUsed, totalPercentUsed, totalPower,
            and poePorts breakdown.

        Raises:
            OmadaApiError: If fetching PoE usage data fails

        """
        url = (
            f"{self._api_url}/openapi/v1/{self._omada_id}"
            f"/sites/{site_id}/dashboard/poe-usage"
        )

        _LOGGER.debug("Fetching PoE usage from %s", url)

        result = await self._authenticated_request("get", url)
        return result.get("result", [])  # type: ignore[no-any-return]

    async def get_switch_ports_poe(self, site_id: str) -> list[dict[str, Any]]:
        """Get PoE information for all switch ports in a site.

        Fetches all pages of PoE port data in a single loop.

        Args:
            site_id: Site ID to get PoE port data for

        Returns:
            List of PoE port dictionaries, each containing port, switchMac,
            switchName, portName, supportPoe, poe, power, voltage, current,
            poeStatus, pdClass, poeDisplayType, connectedStatus, etc.

        Raises:
            OmadaApiError: If fetching PoE data fails

        """
        url = (
            f"{self._api_url}/openapi/v1/{self._omada_id}"
            f"/sites/{site_id}/switches/ports/poe-info"
        )
        page_size = 1000
        page = 1
        all_ports: list[dict[str, Any]] = []

        while True:
            params = {"page": page, "pageSize": page_size}
            result = await self._authenticated_request("get", url, params=params)
            data = result.get("result", {})
            ports = data.get("data", [])
            total_rows = data.get("totalRows", 0)
            all_ports.extend(ports)

            if len(all_ports) >= total_rows or len(ports) < page_size:
                break
            page += 1

        _LOGGER.debug(
            "Fetched %d PoE port records for site %s", len(all_ports), site_id
        )
        return all_ports

    async def get_device_client_stats(
        self,
        site_id: str,
        device_macs: list[str],
    ) -> list[dict[str, Any]]:
        """Get per-band client counts for devices.

        Uses the global client stat endpoint to fetch per-radio client
        counts (2.4 GHz, 5 GHz, 5 GHz-2, 6 GHz) for up to 1000 devices
        in a single batch call.

        Args:
            site_id: Site ID the devices belong to
            device_macs: List of device MAC addresses to query

        Returns:
            List of dicts, each with mac, clientNum, clientNum2g,
            clientNum5g, clientNum5g2, clientNum6g

        Raises:
            OmadaApiError: If fetching client stats fails

        """
        if not device_macs:
            return []

        url = f"{self._api_url}/openapi/v1/{self._omada_id}/clients/stat/devices"
        devices = [{"mac": mac, "siteId": site_id} for mac in device_macs]

        _LOGGER.debug("Fetching per-band client stats for %d devices", len(device_macs))

        result = await self._authenticated_request(
            "post", url, json_data={"devices": devices}
        )
        return result.get("result", [])  # type: ignore[no-any-return]

    async def set_port_profile_override(
        self,
        site_id: str,
        switch_mac: str,
        port: int,
        *,
        enable: bool,
    ) -> None:
        """Enable or disable profile override for a switch port.

        Uses the multi-ports batch endpoint because the single-port
        endpoint returns error -1 on many controller firmware versions.

        Profile override must be enabled before changing PoE mode.

        Args:
            site_id: Site ID the switch belongs to
            switch_mac: MAC address of the switch (AA-BB-CC-DD-EE-FF format)
            port: Port number
            enable: Whether to enable profile override

        Raises:
            OmadaApiError: If the request fails

        """
        url = (
            f"{self._api_url}/openapi/v1/{self._omada_id}"
            f"/sites/{site_id}/switches/{switch_mac}"
            f"/multi-ports/profile-override"
        )
        _LOGGER.debug(
            "Setting profile override for %s port %d to %s",
            switch_mac,
            port,
            enable,
        )
        await self._authenticated_request(
            "put",
            url,
            json_data={
                "portList": [port],
                "profileOverrideEnable": enable,
            },
        )

    async def set_port_poe_mode(
        self,
        site_id: str,
        switch_mac: str,
        port: int,
        *,
        poe_enabled: bool,
    ) -> None:
        """Set PoE mode for a switch port.

        Uses the multi-ports batch endpoint because the single-port
        endpoint returns error -1 on many controller firmware versions.

        Profile override must be enabled first via set_port_profile_override.

        Args:
            site_id: Site ID the switch belongs to
            switch_mac: MAC address of the switch (AA-BB-CC-DD-EE-FF format)
            port: Port number
            poe_enabled: True for PoE on (802.3at/af), False for off

        Raises:
            OmadaApiError: If the request fails

        """
        url = (
            f"{self._api_url}/openapi/v1/{self._omada_id}"
            f"/sites/{site_id}/switches/{switch_mac}"
            f"/multi-ports/poe-mode"
        )
        poe_mode = 1 if poe_enabled else 0
        _LOGGER.debug(
            "Setting PoE mode for %s port %d to %d", switch_mac, port, poe_mode
        )
        await self._authenticated_request(
            "put",
            url,
            json_data={"portList": [port], "poeMode": poe_mode},
        )

    async def reboot_device(self, site_id: str, device_mac: str) -> None:
        """Reboot a device (AP, switch, or gateway).

        Args:
            site_id: Site ID the device belongs to
            device_mac: MAC address of the device (AA-BB-CC-DD-EE-FF format)

        Raises:
            OmadaApiError: If the request fails

        """
        url = (
            f"{self._api_url}/openapi/v1/{self._omada_id}"
            f"/sites/{site_id}/devices/{device_mac}/reboot"
        )
        _LOGGER.debug("Rebooting device %s", device_mac)
        await self._authenticated_request("post", url)

    async def reconnect_client(self, site_id: str, client_mac: str) -> None:
        """Reconnect a wireless client.

        Args:
            site_id: Site ID the client belongs to
            client_mac: MAC address of the client

        Raises:
            OmadaApiError: If the request fails

        """
        url = (
            f"{self._api_url}/openapi/v1/{self._omada_id}"
            f"/sites/{site_id}/clients/{client_mac}/reconnect"
        )
        _LOGGER.debug("Reconnecting client %s", client_mac)
        await self._authenticated_request("post", url)

    async def start_wlan_optimization(self, site_id: str, *, strategy: int = 0) -> None:
        """Start WLAN/RF optimization for a site.

        Args:
            site_id: Site ID to optimize
            strategy: 0 = Global Optimization, 1 = Optimization Adjustment

        Raises:
            OmadaApiError: If the request fails

        """
        url = (
            f"{self._api_url}/openapi/v1/{self._omada_id}"
            f"/sites/{site_id}/cmd/rfPlanning/rrmOptimization"
        )
        _LOGGER.debug(
            "Starting WLAN optimization for site %s (strategy=%d)", site_id, strategy
        )
        await self._authenticated_request(
            "post", url, json_data={"optimizationStrategy": strategy}
        )

    async def block_client(self, site_id: str, client_mac: str) -> None:
        """Block a client from the network.

        Args:
            site_id: Site ID the client belongs to
            client_mac: MAC address of the client

        Raises:
            OmadaApiError: If the request fails

        """
        url = (
            f"{self._api_url}/openapi/v1/{self._omada_id}"
            f"/sites/{site_id}/clients/{client_mac}/block"
        )
        _LOGGER.debug("Blocking client %s", client_mac)
        await self._authenticated_request("post", url)

    async def unblock_client(self, site_id: str, client_mac: str) -> None:
        """Unblock a client from the network.

        Args:
            site_id: Site ID the client belongs to
            client_mac: MAC address of the client

        Raises:
            OmadaApiError: If the request fails

        """
        url = (
            f"{self._api_url}/openapi/v1/{self._omada_id}"
            f"/sites/{site_id}/clients/{client_mac}/unblock"
        )
        _LOGGER.debug("Unblocking client %s", client_mac)
        await self._authenticated_request("post", url)

    async def get_firmware_info(self, site_id: str, device_mac: str) -> dict[str, Any]:
        """Get latest firmware information for a device.

        Args:
            site_id: Site ID containing the device
            device_mac: MAC address of the device

        Returns:
            Dictionary with curFwVer, lastFwVer, fwReleaseLog

        Raises:
            OmadaApiError: If the request fails

        """
        url = (
            f"{self._api_url}/openapi/v1/{self._omada_id}"
            f"/sites/{site_id}/devices/{device_mac}/latest-firmware-info"
        )
        _LOGGER.debug("Fetching firmware info for %s", device_mac)
        result = await self._authenticated_request("get", url)
        return result.get("result", {})  # type: ignore[no-any-return]

    async def start_online_upgrade(
        self, site_id: str, device_mac: str
    ) -> dict[str, Any]:
        """Start online firmware upgrade for a device.

        Args:
            site_id: Site ID containing the device
            device_mac: MAC address of the device

        Returns:
            API response

        Raises:
            OmadaApiError: If the request fails

        """
        url = (
            f"{self._api_url}/openapi/v1/{self._omada_id}"
            f"/sites/{site_id}/devices/{device_mac}/start-online-upgrade"
        )
        _LOGGER.debug("Starting online upgrade for %s", device_mac)
        result = await self._authenticated_request("post", url)
        return result.get("result", {})  # type: ignore[no-any-return]

    async def get_led_setting(self, site_id: str) -> dict[str, Any]:
        """Get LED setting for a site.

        Args:
            site_id: Site ID

        Returns:
            Dictionary with 'enable' boolean

        Raises:
            OmadaApiError: If the request fails

        """
        url = f"{self._api_url}/openapi/v1/{self._omada_id}/sites/{site_id}/led"
        _LOGGER.debug("Fetching LED setting for site %s", site_id)
        result = await self._authenticated_request("get", url)
        return result.get("result", {})  # type: ignore[no-any-return]

    async def set_led_setting(self, site_id: str, *, enable: bool) -> dict[str, Any]:
        """Set LED setting for a site.

        Args:
            site_id: Site ID
            enable: Whether to enable LEDs

        Returns:
            API response

        Raises:
            OmadaApiError: If the request fails

        """
        url = f"{self._api_url}/openapi/v1/{self._omada_id}/sites/{site_id}/led"
        _LOGGER.debug("Setting LED %s for site %s", "on" if enable else "off", site_id)
        result = await self._authenticated_request(
            "put", url, json_data={"enable": enable}
        )
        return result.get("result", {})  # type: ignore[no-any-return]

    async def get_ap_led_setting(self, site_id: str, ap_mac: str) -> dict[str, Any]:
        """Get LED setting for a specific AP.

        Args:
            site_id: Site ID
            ap_mac: AP MAC address

        Returns:
            AP general config payload containing ledSetting

        Raises:
            OmadaApiError: If the request fails

        """
        url = (
            f"{self._api_url}/openapi/v1/{self._omada_id}"
            f"/sites/{site_id}/aps/{ap_mac}/general-config"
        )
        _LOGGER.debug("Fetching AP LED setting for %s in site %s", ap_mac, site_id)
        result = await self._authenticated_request("get", url)
        return result.get("result", {})  # type: ignore[no-any-return]

    async def set_ap_led_setting(
        self, site_id: str, ap_mac: str, *, led_setting: int
    ) -> dict[str, Any]:
        """Set LED setting for a specific AP.

        Args:
            site_id: Site ID
            ap_mac: AP MAC address
            led_setting: 0=off, 1=on, 2=follow site setting

        Returns:
            API response payload

        Raises:
            OmadaApiError: If the request fails

        """
        url = (
            f"{self._api_url}/openapi/v1/{self._omada_id}"
            f"/sites/{site_id}/aps/{ap_mac}/general-config"
        )
        _LOGGER.debug(
            "Setting AP LED mode %s for %s in site %s",
            led_setting,
            ap_mac,
            site_id,
        )
        result = await self._authenticated_request(
            "patch",
            url,
            json_data={"ledSetting": led_setting},
        )
        return result.get("result", {})  # type: ignore[no-any-return]

    async def check_write_access(self, site_id: str) -> bool:
        """Check if the API credentials have write access to a site.

        Performs a non-destructive probe by reading the current LED setting
        and writing the same value back. If the write succeeds the credentials
        have editing rights; a permissions error means viewer-only access.

        Args:
            site_id: Site ID to test against

        Returns:
            True if write access is available, False otherwise.

        """
        try:
            current = await self.get_led_setting(site_id)
            led_enabled = current.get("enable", True)
            await self.set_led_setting(site_id, enable=led_enabled)
        except OmadaApiError as err:
            if err.error_code in (-1005, -1007):
                _LOGGER.info(
                    "API credentials have viewer-only access to site %s "
                    "(write probe returned error %s). "
                    "PoE and LED switches will not be created",
                    site_id,
                    err.error_code,
                )
                return False
            # Unexpected error — log but assume write access to avoid
            # hiding entities unnecessarily.
            _LOGGER.warning(
                "Unexpected error during write-access probe for site %s: %s",
                site_id,
                err,
            )
            return True
        except Exception:
            _LOGGER.debug(
                "Write-access probe failed for site %s, assuming write access",
                site_id,
                exc_info=True,
            )
            return True
        _LOGGER.debug("Write-access probe succeeded for site %s", site_id)
        return True

    async def locate_device(
        self, site_id: str, device_mac: str, *, enable: bool
    ) -> None:
        """Enable or disable the locate function on a device.

        Args:
            site_id: Site ID containing the device
            device_mac: MAC address of the device
            enable: True to start locating, False to stop

        Raises:
            OmadaApiError: If the request fails

        """
        url = (
            f"{self._api_url}/openapi/v1/{self._omada_id}"
            f"/sites/{site_id}/devices/{device_mac}/locate"
        )
        _LOGGER.debug(
            "%s locate for %s",
            "Enabling" if enable else "Disabling",
            device_mac,
        )
        await self._authenticated_request(
            "post", url, json_data={"locateEnable": enable}
        )

    async def get_ap_radios(self, site_id: str, ap_mac: str) -> dict[str, Any]:
        """Get radio information for an AP.

        Args:
            site_id: Site ID containing the AP
            ap_mac: MAC address of the AP

        Returns:
            Dictionary with radio traffic and channel info per band

        Raises:
            OmadaApiError: If the request fails

        """
        url = (
            f"{self._api_url}/openapi/v1/{self._omada_id}"
            f"/sites/{site_id}/aps/{ap_mac}/radios"
        )
        _LOGGER.debug("Fetching radio info for AP %s", ap_mac)
        result = await self._authenticated_request("get", url)
        return result.get("result", {})  # type: ignore[no-any-return]

    async def get_gateway_info(self, site_id: str, gateway_mac: str) -> dict[str, Any]:
        """Get gateway information including temperature.

        Args:
            site_id: Site ID containing the gateway
            gateway_mac: MAC address of the gateway

        Returns:
            Dictionary with gateway info including temp field

        Raises:
            OmadaApiError: If the request fails

        """
        url = (
            f"{self._api_url}/openapi/v1/{self._omada_id}"
            f"/sites/{site_id}/gateways/{gateway_mac}"
        )
        _LOGGER.debug("Fetching gateway info for %s", gateway_mac)
        result = await self._authenticated_request("get", url)
        return result.get("result", {})  # type: ignore[no-any-return]

    async def get_site_ssids(self, site_id: str) -> list[dict[str, Any]]:
        """Get all SSIDs for a site.

        Args:
            site_id: Site ID

        Returns:
            List of SSID configurations (flattened from all WLANs)

        Raises:
            OmadaApiError: If the request fails

        """
        url = (
            f"{self._api_url}/openapi/v1/{self._omada_id}"
            f"/sites/{site_id}/wireless-network/ssids?type=3"
        )
        _LOGGER.debug("Fetching SSIDs for site %s (type=3: all device types)", site_id)
        result = await self._authenticated_request("get", url)

        # Response structure: {"errorCode": 0, "result": [{"wlanId": "...", "ssidList": [...]}]}
        wlans = result.get("result", [])

        # Log detailed WLAN information for debugging
        _LOGGER.debug("Raw SSID API response: %d WLANs returned", len(wlans))
        for i, wlan in enumerate(wlans):
            wlan_name = wlan.get("wlanName", "Unknown")
            ssid_count = len(wlan.get("ssidList", []))
            ssid_names = [s.get("ssidName", "?") for s in wlan.get("ssidList", [])]
            _LOGGER.debug(
                "  WLAN %d: '%s' - %d SSIDs: %s",
                i + 1,
                wlan_name,
                ssid_count,
                ssid_names,
            )

        # Flatten all SSIDs from all WLANs into a single list
        all_ssids: list[dict[str, Any]] = []
        for wlan in wlans:
            ssid_list = wlan.get("ssidList", [])
            # Add wlanId and wlanName to each SSID for context
            for ssid in ssid_list:
                ssid_with_wlan = ssid.copy()
                ssid_with_wlan["wlanId"] = wlan.get("wlanId")
                ssid_with_wlan["wlanName"] = wlan.get("wlanName")
                all_ssids.append(ssid_with_wlan)

        _LOGGER.debug(
            "Fetched %d SSIDs across %d WLANs for site %s",
            len(all_ssids),
            len(wlans),
            site_id,
        )
        return all_ssids

    async def get_site_ssids_comprehensive(self, site_id: str) -> list[dict[str, Any]]:
        """Get all SSIDs for a site by iterating through all WLAN groups.

        This method uses the more comprehensive approach:
        1. Get all WLAN groups for the site
        2. For each WLAN group, get all SSIDs (with pagination)

        This returns ALL SSIDs regardless of MAC authentication configuration,
        unlike get_site_ssids which may filter SSIDs.

        Args:
            site_id: Site ID

        Returns:
            List of SSID configurations (flattened from all WLANs)

        Raises:
            OmadaApiError: If the request fails

        """
        # Step 1: Get all WLAN groups
        wlans_url = (
            f"{self._api_url}/openapi/v1/{self._omada_id}"
            f"/sites/{site_id}/wireless-network/wlans"
        )
        _LOGGER.debug("Fetching WLAN groups for site %s", site_id)
        wlans_result = await self._authenticated_request("get", wlans_url)
        wlan_groups = wlans_result.get("result", [])
        _LOGGER.debug("Found %d WLAN groups for site %s", len(wlan_groups), site_id)

        # Step 2: Get SSIDs for each WLAN group
        all_ssids: list[dict[str, Any]] = []
        for wlan in wlan_groups:
            wlan_id = wlan.get("wlanId")
            wlan_name = wlan.get("name", "Unknown")
            if not wlan_id:
                continue

            # Fetch SSIDs for this WLAN group with pagination
            ssids_url = (
                f"{self._api_url}/openapi/v1/{self._omada_id}"
                f"/sites/{site_id}/wireless-network/wlans/{wlan_id}/ssids"
            )

            # Fetch all pages
            page = 1
            page_size = 100
            wlan_ssids: list[dict[str, Any]] = []

            while True:
                params = {"page": page, "pageSize": page_size}
                _LOGGER.debug(
                    "Fetching SSIDs for WLAN '%s' (page %d, pageSize %d)",
                    wlan_name,
                    page,
                    page_size,
                )
                ssids_result = await self._authenticated_request(
                    "get", ssids_url, params=params
                )

                result_data = ssids_result.get("result", {})
                ssid_page_data = result_data.get("data", [])
                total_rows = result_data.get("totalRows", 0)

                _LOGGER.debug(
                    "  Page %d: got %d SSIDs (total: %d)",
                    page,
                    len(ssid_page_data),
                    total_rows,
                )

                # Add wlanId and wlanName to each SSID, and normalize field names
                for ssid in ssid_page_data:
                    ssid_with_wlan = ssid.copy()
                    ssid_with_wlan["wlanId"] = wlan_id
                    ssid_with_wlan["wlanName"] = wlan_name
                    # Normalize field names: this endpoint uses "name"/"ssidId"
                    # but we want consistent "ssidName"/"ssidId" everywhere
                    if "name" in ssid_with_wlan and "ssidName" not in ssid_with_wlan:
                        ssid_with_wlan["ssidName"] = ssid_with_wlan["name"]
                    wlan_ssids.append(ssid_with_wlan)

                # Check if we've fetched all SSIDs
                if len(wlan_ssids) >= total_rows or len(ssid_page_data) < page_size:
                    break
                page += 1

            ssid_names = [s.get("ssidName", s.get("name", "?")) for s in wlan_ssids]
            _LOGGER.debug(
                "WLAN '%s': fetched %d SSIDs: %s",
                wlan_name,
                len(wlan_ssids),
                ssid_names,
            )
            all_ssids.extend(wlan_ssids)

        _LOGGER.debug(
            "Fetched %d total SSIDs across %d WLAN groups for site %s",
            len(all_ssids),
            len(wlan_groups),
            site_id,
        )
        return all_ssids

    async def update_ssid_basic_config(
        self,
        site_id: str,
        wlan_id: str,
        ssid_id: str,
        config: dict[str, Any],
    ) -> None:
        """Update SSID basic configuration.

        Args:
            site_id: Site ID
            wlan_id: WLAN group ID
            ssid_id: SSID ID
            config: Configuration dictionary (name, band, broadcast, etc.)

        Raises:
            OmadaApiError: If the request fails

        """
        url = (
            f"{self._api_url}/openapi/v1/{self._omada_id}"
            f"/sites/{site_id}/wireless-network/wlans/{wlan_id}"
            f"/ssids/{ssid_id}/update-basic-config"
        )
        _LOGGER.debug("Updating SSID %s basic config in site %s", ssid_id, site_id)
        await self._authenticated_request("patch", url, json_data=config)

    async def get_ssid_detail(
        self, site_id: str, wlan_id: str, ssid_id: str
    ) -> dict[str, Any]:
        """Get detailed SSID information.

        Args:
            site_id: Site ID
            wlan_id: WLAN group ID
            ssid_id: SSID ID

        Returns:
            Dictionary with SSID details

        Raises:
            OmadaApiError: If the request fails

        """
        url = (
            f"{self._api_url}/openapi/v1/{self._omada_id}"
            f"/sites/{site_id}/wireless-network/wlans/{wlan_id}"
            f"/ssids/{ssid_id}"
        )
        _LOGGER.debug("Fetching SSID %s detail from site %s", ssid_id, site_id)
        result = await self._authenticated_request("get", url)
        return result.get("result", {})  # type: ignore[no-any-return]

    async def get_ap_ssid_overrides(self, site_id: str, ap_mac: str) -> dict[str, Any]:
        """Get AP SSID override configuration.

        Args:
            site_id: Site ID
            ap_mac: AP MAC address (format: AA-BB-CC-DD-EE-FF)

        Returns:
            Dictionary with SSID override configuration:
            {
                "ssidOverrides": [
                    {
                        "ssidId": "...",
                        "ssidEntryId": 123,
                        "ssidName": "...",
                        "ssidEnable": true,
                        "band": [0, 1],
                        "security": 3,
                        ...
                    }
                ]
            }

        Raises:
            OmadaApiError: If the request fails

        """
        url = (
            f"{self._api_url}/openapi/v2/{self._omada_id}"
            f"/sites/{site_id}/aps/{ap_mac}/override"
        )
        _LOGGER.debug("Fetching SSID overrides for AP %s in site %s", ap_mac, site_id)
        result = await self._authenticated_request("get", url)
        return result.get("result", {})  # type: ignore[no-any-return]

    async def update_ap_ssid_override(
        self,
        site_id: str,
        ap_mac: str,
        ssid_entry_id: int,
        ssid_name: str,
        ssid_enable: bool,
    ) -> None:
        """Enable/disable SSID on a specific AP.

        This method fetches the current override configuration, modifies the
        specified SSID, and sends back the complete list. The API requires
        sending all SSIDs in the override list, not just the one being changed.

        Args:
            site_id: Site ID
            ap_mac: AP MAC address (format: AA-BB-CC-DD-EE-FF)
            ssid_entry_id: SSID entry ID from get_ap_ssid_overrides
            ssid_name: SSID name (for logging only, not modified in API)
            ssid_enable: True to enable, False to disable

        Raises:
            OmadaApiError: If the request fails

        """
        # First, get current override configuration
        current_config = await self.get_ap_ssid_overrides(site_id, ap_mac)
        ssid_overrides = current_config.get("ssidOverrides", [])

        # Build the PATCH payload with the required fields per schema
        # SsidOverrideOpenApiV2VO requires: ssidEntryId, overrideSsidEnable, overrideVlanEnable
        # Plus ssidEnable to actually control whether the SSID is enabled on this AP
        patch_overrides = []
        for override in ssid_overrides:
            ssid_entry = override.get("ssidEntryId")

            # Build override entry with required fields
            # Keep overrideSsidEnable and overrideVlanEnable at their current values
            patch_entry = {
                "ssidEntryId": ssid_entry,
                "overrideSsidEnable": override.get("overrideSsidEnable", False),
                "overrideVlanEnable": override.get("overrideVlanEnable", False),
            }

            # If this is the SSID we're modifying, set ssidEnable to control enable/disable
            if ssid_entry == ssid_entry_id:
                patch_entry["ssidEnable"] = ssid_enable
            # Preserve existing ssidEnable state for other SSIDs
            elif override.get("ssidEnable") is not None:
                patch_entry["ssidEnable"] = override["ssidEnable"]

            patch_overrides.append(patch_entry)

        # Send the complete list back to the API
        url = (
            f"{self._api_url}/openapi/v2/{self._omada_id}"
            f"/sites/{site_id}/aps/{ap_mac}/override"
        )

        payload = {"ssidOverrides": patch_overrides}

        _LOGGER.debug(
            "Updating SSID override for AP %s in site %s: entry_id=%d, name=%s, enable=%s (total overrides: %d)",
            ap_mac,
            site_id,
            ssid_entry_id,
            ssid_name,
            ssid_enable,
            len(patch_overrides),
        )
        await self._authenticated_request("patch", url, json_data=payload)

    async def get_gateway_wan_status(
        self, site_id: str, gateway_mac: str
    ) -> list[dict[str, Any]]:
        """Get WAN port status for a gateway including live traffic rates.

        Args:
            site_id: Site ID containing the gateway
            gateway_mac: MAC address of the gateway

        Returns:
            List of WAN port status dictionaries with traffic rates,
            latency, packet loss, and connection status.
            Only ports in WAN mode (mode == 0) are returned.

        Raises:
            OmadaApiError: If the request fails

        """
        url = (
            f"{self._api_url}/openapi/v1/{self._omada_id}"
            f"/sites/{site_id}/gateways/{gateway_mac}/wan-status"
        )
        _LOGGER.debug("Fetching WAN status for gateway %s", gateway_mac)
        result = await self._authenticated_request("get", url)
        wan_ports: list[dict[str, Any]] = result.get("result", [])
        # Filter to only WAN-mode ports (mode == 0)
        return [p for p in wan_ports if p.get("mode") == 0]

    async def get_device_stats(
        self,
        site_id: str,
        device_mac: str,
        device_type: str,
        interval: str,
        start: int,
        end: int,
        attrs: list[str],
    ) -> list[dict[str, Any]]:
        """Get device statistics for a given time range.

        Args:
            site_id: Site ID containing the device
            device_mac: MAC address of the device
            device_type: Device type ("ap", "gateway", "switch")
            interval: Time interval ("5min", "hourly", "daily")
            start: Start timestamp (Unix epoch seconds)
            end: End timestamp (Unix epoch seconds)
            attrs: List of attributes to query (e.g. ["tx", "rx"])

        Returns:
            List of stat entries, each a dict with requested attrs and a timestamp.

        Raises:
            OmadaApiError: If the request fails

        """
        url = (
            f"{self._api_url}/openapi/v2/{self._omada_id}"
            f"/sites/{site_id}/stat/{device_mac}/{interval}"
        )
        params = {"type": device_type}
        json_data = {
            "start": start,
            "end": end,
            "attrs": attrs,
        }
        _LOGGER.debug(
            "Fetching %s stats for %s %s (attrs: %s)",
            interval,
            device_type,
            device_mac,
            attrs,
        )
        result = await self._authenticated_request(
            "post", url, params=params, json_data=json_data
        )
        raw = result.get("result", [])
        if isinstance(raw, list):
            return raw
        # Single object returned — wrap in a list for consistency.
        return [raw]

    async def get_ap_radio_config(self, site_id: str, ap_mac: str) -> dict[str, Any]:
        """Get radio configuration for an AP.

        Args:
            site_id: Site ID containing the AP
            ap_mac: MAC address of the AP

        Returns:
            Dictionary with radioSetting2g/5g/5g1/5g2/6g keys, each containing
            radioEnable and other radio configuration fields.

        Raises:
            OmadaApiError: If the request fails

        """
        url = (
            f"{self._api_url}/openapi/v1/{self._omada_id}"
            f"/sites/{site_id}/aps/{ap_mac}/radio-config"
        )
        _LOGGER.debug("Fetching radio config for AP %s", ap_mac)
        result = await self._authenticated_request("get", url)
        return result.get("result", {})  # type: ignore[no-any-return]

    async def set_ap_radio_enabled(
        self, site_id: str, ap_mac: str, *, band: str, enabled: bool
    ) -> None:
        """Enable or disable a radio band on an AP.

        Args:
            site_id: Site ID containing the AP
            ap_mac: MAC address of the AP
            band: Band identifier ("2g", "5g", "5g1", "5g2", "6g")
            enabled: True to enable the radio, False to disable

        Raises:
            OmadaApiError: If the request fails

        """
        url = (
            f"{self._api_url}/openapi/v1/{self._omada_id}"
            f"/sites/{site_id}/aps/{ap_mac}/radio-config"
        )
        band_key = f"radioSetting{band}"
        payload = {band_key: {"radioEnable": enabled}}
        _LOGGER.debug(
            "%s radio band %s on AP %s",
            "Enabling" if enabled else "Disabling",
            band,
            ap_mac,
        )
        await self._authenticated_request("patch", url, json_data=payload)

    async def get_wlan_optimization_status(self, site_id: str) -> dict[str, Any]:
        """Get WLAN/RF planning optimization status for a site.

        Args:
            site_id: Site ID to query

        Returns:
            Dictionary with status (0-3), beforeIndex, afterIndex fields.
            status: 0=completed/applied, 1=no result, 2=running, 3=canceling

        Raises:
            OmadaApiError: If the request fails

        """
        url = (
            f"{self._api_url}/openapi/v1/{self._omada_id}"
            f"/sites/{site_id}/radio-frequency-planning/result"
        )
        _LOGGER.debug("Fetching WLAN optimization status for site %s", site_id)
        result = await self._authenticated_request("get", url)
        return result.get("result", {})  # type: ignore[no-any-return]

    async def get_switch_port_details(
        self,
        site_id: str,
    ) -> list[dict[str, Any]]:
        """Get switch port details — confirms which MACs have wired ports.

        Returns an empty list if the endpoint is unavailable or returns an error,
        making the caller resilient to missing data.

        Args:
            site_id: Site ID to query

        Returns:
            List of switch port detail dicts, each containing at least a 'mac' field.

        """
        url = (
            f"{self._api_url}/openapi/v1/{self._omada_id}"
            f"/sites/{site_id}/switches/ports/switch-detail"
        )
        try:
            result = await self._authenticated_request("get", url)
        except OmadaApiError:
            return []
        raw = result.get("result", {})
        # API may return a list directly or wrapped in data.
        if isinstance(raw, list):
            return raw
        return raw.get("data", [])  # type: ignore[no-any-return]

    async def get_threat_management(
        self,
        *,
        site_id: str,
        start_time: int,
        end_time: int,
        archived: bool = False,
        page_size: int = 100,
    ) -> list[dict[str, Any]]:
        """Fetch threat-management rows for a site within a time window.

        Fetches all pages until every row has been retrieved. Callers are
        responsible for treating ``OmadaApiError`` (e.g. HTTP 404 on
        controllers that don't support this endpoint) as unavailable data
        rather than an integration setup failure.

        Args:
            site_id: Site ID to query
            start_time: Window start, Unix timestamp in seconds
            end_time: Window end, Unix timestamp in seconds
            archived: False for active threat rows (default)
            page_size: Rows per page (1-1000)

        Returns:
            List of raw threat-management row dictionaries

        Raises:
            OmadaApiError: If the request fails

        """
        url = f"{self._api_url}/openapi/v1/{self._omada_id}/security/threat-management"
        page = 1
        all_rows: list[dict[str, Any]] = []

        while True:
            params: dict[str, Any] = {
                "siteList": site_id,
                "archived": str(archived).lower(),
                "page": page,
                "pageSize": page_size,
                "filters.startTime": start_time,
                "filters.endTime": end_time,
                "sorts.time": "desc",
            }
            result = await self._authenticated_request("get", url, params=params)
            data = result.get("result", {})
            rows = data.get("data", [])
            total_rows = data.get("totalRows", 0)
            all_rows.extend(rows)

            if len(all_rows) >= total_rows or len(rows) < page_size:
                break
            page += 1

        _LOGGER.debug(
            "Fetched %d threat-management rows for site %s", len(all_rows), site_id
        )
        return all_rows

    async def get_wan_speed_test_stats(self, site_id: str) -> dict[str, Any]:
        """Get WAN speed test statistics.

        Args:
            site_id: The site identifier

        Returns:
            Dict containing speed test status/results

        """
        return await self._authenticated_request(
            "get",
            f"sites/{site_id}/statistics/speedTest",
        )

    async def trigger_wan_speed_test(
        self,
        site_id: str,
        wan_id: str | None = None,
    ) -> dict[str, Any]:
        """Trigger a WAN speed test.

        Args:
            site_id: The site identifier
            wan_id: Optional WAN port ID to test

        Returns:
            Dict containing trigger result

        """
        payload: dict[str, Any] = {}
        if wan_id is not None:
            payload["id"] = wan_id
        return await self._authenticated_request(
            "post",
            f"sites/{site_id}/statistics/speedTest",
            json_data=payload,
        )

    @property
    def auth(self) -> OmadaAuthStrategy:
        """Return the auth strategy."""
        return self._auth

    @property
    def session(self) -> aiohttp.ClientSession:
        """Return the underlying aiohttp session (carries the Fusion cookie jar)."""
        return self._session


class OmadaApiError(Exception):
    """General API exception."""

    def __init__(self, message: str, error_code: int | None = None) -> None:
        """Initialize with optional error code."""
        super().__init__(message)
        self.error_code = error_code


class OmadaApiAuthError(OmadaApiError):
    """Authentication exception."""
