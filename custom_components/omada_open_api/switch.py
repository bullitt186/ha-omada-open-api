"""Switch platform for Omada Open API integration."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from homeassistant.components.switch import SwitchDeviceClass, SwitchEntity
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import OmadaApiError
from .const import DOMAIN, ICON_WIFI, ICON_WIFI_OFF
from .coordinator import OmadaClientCoordinator, OmadaSiteCoordinator

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

_LOGGER = logging.getLogger(__name__)

PARALLEL_UPDATES = 1


async def async_setup_entry(  # pylint: disable=too-many-branches,too-many-statements
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Omada switch entities from a config entry."""
    data = entry.runtime_data
    entities: list[SwitchEntity] = []
    has_write_access: bool = data.get("has_write_access", True)

    # PoE switches (only when API credentials have editing rights).
    coordinators: dict[str, OmadaSiteCoordinator] = data.get("coordinators", {})
    if has_write_access:
        entities.extend(
            OmadaPoeSwitch(coordinator=coordinator, port_key=port_key)
            for coordinator in coordinators.values()
            for port_key in coordinator.data.get("poe_ports", {})
        )
    else:
        _LOGGER.info("Skipping PoE switches — API credentials have viewer-only access")

    # Client block/unblock switches.
    client_coordinators: list[OmadaClientCoordinator] = data.get(
        "client_coordinators", []
    )
    for coordinator in client_coordinators:
        if coordinator.data:
            entities.extend(
                OmadaClientBlockSwitch(coordinator, client_mac)
                for client_mac in coordinator.data
            )

    # LED switch (one per site, only when API credentials have editing rights).
    if has_write_access:
        site_coordinators: list[OmadaSiteCoordinator] = list(
            data.get("coordinators", {}).values()
        )
        entities.extend(
            OmadaLedSwitch(coordinator) for coordinator in site_coordinators
        )

    # SSID switches (site-wide, only when API credentials have editing rights).
    _LOGGER.debug(
        "SSID switch setup: has_write_access=%s, coordinator_count=%d",
        has_write_access,
        len(coordinators),
    )

    if has_write_access:
        ssid_switch_count = 0
        for site_id, coordinator in coordinators.items():
            ssids = coordinator.data.get("ssids", [])
            # Site devices stored with bare site_id as key in runtime_data
            # but device identifier uses "site_{site_id}" prefix
            runtime_data_key = site_id

            _LOGGER.debug(
                "Processing site '%s': found %d SSIDs: %s",
                site_id,
                len(ssids),
                [s.get("ssidName", "Unknown") for s in ssids] if ssids else "none",
            )

            # Validate SSID data structure before creating switches
            valid_ssids = []
            for ssid in ssids:
                if not ssid.get("ssidId") or not ssid.get("wlanId"):
                    _LOGGER.warning(
                        "Invalid SSID data for site %s: missing required fields (ssidId/wlanId): %s",
                        site_id,
                        ssid,
                    )
                    continue
                valid_ssids.append(ssid)

            if len(valid_ssids) != len(ssids):
                _LOGGER.warning(
                    "Site %s: filtered out %d invalid SSIDs, %d valid remaining",
                    site_id,
                    len(ssids) - len(valid_ssids),
                    len(valid_ssids),
                )

            # Verify site device exists (stored with bare site_id key)
            if runtime_data_key not in data.get("site_devices", {}):
                _LOGGER.error(
                    "Site device for site '%s' not found in runtime_data for SSID switches. "
                    "Available site devices: %s",
                    runtime_data_key,
                    list(data.get("site_devices", {}).keys()),
                )
                continue

            _LOGGER.debug(
                "Site device found for site %s, creating switches for %d valid SSIDs",
                site_id,
                len(valid_ssids),
            )

            # Pass device identifier (with site_ prefix) to entity for device_info
            site_device_identifier = f"site_{site_id}"

            entities.extend(
                OmadaSsidSwitch(
                    coordinator=coordinator,
                    site_device_id=site_device_identifier,
                    ssid_data=ssid,
                )
                for ssid in valid_ssids
            )
            ssid_switch_count += len(valid_ssids)

        total_ssids = sum(len(c.data.get("ssids", [])) for c in coordinators.values())
        _LOGGER.info(
            "Created %d SSID switches from %d total SSIDs across %d site(s)",
            ssid_switch_count,
            total_ssids,
            len(coordinators),
        )

        if total_ssids > 0 and ssid_switch_count == 0:
            _LOGGER.warning(
                "Write access is enabled and %d SSIDs were found, but no SSID switches "
                "were created. This may indicate invalid SSID data or missing site devices.",
                total_ssids,
            )
    else:
        _LOGGER.info("Skipping SSID switches — API credentials have viewer-only access")

    # Per-AP SSID switches (only when API credentials have editing rights).
    if has_write_access:
        ap_ssid_switch_count = 0
        for site_id, coordinator in coordinators.items():
            ap_overrides = coordinator.data.get("ap_ssid_overrides", {})
            devices = coordinator.data.get("devices", {})

            _LOGGER.debug(
                "Processing per-AP SSID switches for site '%s': %d APs with overrides",
                site_id,
                len(ap_overrides),
            )

            for ap_mac, override_data in ap_overrides.items():
                ap_device = devices.get(ap_mac, {})
                ap_name = ap_device.get("name", ap_mac)

                ssid_overrides = override_data.get("ssidOverrides", [])
                _LOGGER.debug(
                    "AP %s (%s): %d SSID overrides available",
                    ap_name,
                    ap_mac,
                    len(ssid_overrides),
                )

                for ssid_override in ssid_overrides:
                    # Only create switch if we have a valid ssidEntryId
                    if ssid_override.get("ssidEntryId") is not None:
                        entities.append(
                            OmadaApSsidSwitch(
                                coordinator=coordinator,
                                ap_mac=ap_mac,
                                ap_name=ap_name,
                                ssid_data=ssid_override,
                            )
                        )
                        ap_ssid_switch_count += 1

        _LOGGER.info(
            "Created %d per-AP SSID switches across %d site(s)",
            ap_ssid_switch_count,
            len(coordinators),
        )

    async_add_entities(entities)


class OmadaPoeSwitch(
    CoordinatorEntity[OmadaSiteCoordinator],  # type: ignore[misc]
    SwitchEntity,  # type: ignore[misc]
):
    """Switch entity to control PoE on a switch port."""

    _attr_has_entity_name = True
    _attr_device_class = SwitchDeviceClass.SWITCH
    _attr_icon = "mdi:ethernet"

    def __init__(
        self,
        coordinator: OmadaSiteCoordinator,
        port_key: str,
    ) -> None:
        """Initialize the PoE switch entity.

        Args:
            coordinator: Site coordinator that provides PoE data
            port_key: Key in poe_ports dict (format: switchMac_portNum)

        """
        super().__init__(coordinator)
        self._port_key = port_key

        port_data = coordinator.data.get("poe_ports", {}).get(port_key, {})
        switch_mac: str = port_data.get("switch_mac", "")
        port_num: int = port_data.get("port", 0)
        port_name: str = port_data.get("port_name", f"Port {port_num}")

        self._switch_mac = switch_mac
        self._port_num = port_num

        self._attr_unique_id = f"{switch_mac}_port{port_num}_poe"
        self._attr_name = f"{port_name} PoE"

        # Link to the parent switch device.
        self._attr_device_info = {
            "identifiers": {(DOMAIN, switch_mac)},
        }

    # ------------------------------------------------------------------
    # State
    # ------------------------------------------------------------------

    @property
    def is_on(self) -> bool | None:
        """Return True if PoE is enabled on this port."""
        port_data = self.coordinator.data.get("poe_ports", {}).get(self._port_key)
        if port_data is None:
            return None
        return bool(port_data.get("poe_enabled", False))

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes."""
        port_data = self.coordinator.data.get("poe_ports", {}).get(self._port_key)
        if port_data is None:
            return {}
        return {
            "port": port_data.get("port"),
            "port_name": port_data.get("port_name"),
            "power": port_data.get("power"),
            "voltage": port_data.get("voltage"),
            "current": port_data.get("current"),
        }

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        if not self.coordinator.last_update_success:
            return False
        return (
            self.coordinator.data.get("poe_ports", {}).get(self._port_key) is not None
        )

    # ------------------------------------------------------------------
    # Control
    # ------------------------------------------------------------------

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Enable PoE on this port."""
        await self._set_poe(enabled=True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Disable PoE on this port."""
        await self._set_poe(enabled=False)

    async def _set_poe(self, *, enabled: bool) -> None:
        """Set PoE mode after enabling profile override.

        Args:
            enabled: Whether to enable or disable PoE

        """
        site_id: str = self.coordinator.data.get("site_id", "")
        api = self.coordinator.api_client

        try:
            # Profile override must be enabled first.
            await api.set_port_profile_override(
                site_id, self._switch_mac, self._port_num, enable=True
            )
            await api.set_port_poe_mode(
                site_id, self._switch_mac, self._port_num, poe_enabled=enabled
            )
        except OmadaApiError as err:
            if err.error_code in (-1005, -1007):
                _LOGGER.warning(
                    "Insufficient permissions to control PoE on %s port %d. "
                    "Ensure the Open API application has "
                    "'Site Device Manager Modify' permission",
                    self._switch_mac,
                    self._port_num,
                )
            else:
                _LOGGER.exception(
                    "Failed to set PoE %s for %s port %d",
                    "on" if enabled else "off",
                    self._switch_mac,
                    self._port_num,
                )
            return

        # Refresh coordinator data to reflect the change.
        await self.coordinator.async_request_refresh()


class OmadaClientBlockSwitch(
    CoordinatorEntity[OmadaClientCoordinator],  # type: ignore[misc]
    SwitchEntity,  # type: ignore[misc]
):
    """Switch entity to block/unblock a client.

    When the switch is ON the client is allowed (not blocked).
    When the switch is OFF the client is blocked.
    """

    _attr_has_entity_name = True
    _attr_device_class = SwitchDeviceClass.SWITCH
    _attr_icon = "mdi:account-lock"

    def __init__(
        self,
        coordinator: OmadaClientCoordinator,
        client_mac: str,
    ) -> None:
        """Initialize the client block switch."""
        super().__init__(coordinator)
        self._client_mac = client_mac

        client_data = coordinator.data.get(client_mac, {})
        client_name = (
            client_data.get("name") or client_data.get("host_name") or client_mac
        )

        self._attr_name = f"{client_name} Network Access"
        self._attr_unique_id = f"{DOMAIN}_{client_mac}_block"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, client_mac)},
            name=client_name,
        )

    # ------------------------------------------------------------------
    # State
    # ------------------------------------------------------------------

    @property
    def is_on(self) -> bool | None:
        """Return True if client is NOT blocked (has network access)."""
        client = self.coordinator.data.get(self._client_mac)
        if client is None:
            return None
        # Inverted: is_on = not blocked.
        return not client.get("blocked", False)

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        if not self.coordinator.last_update_success:
            return False
        return self.coordinator.data.get(self._client_mac) is not None

    # ------------------------------------------------------------------
    # Control
    # ------------------------------------------------------------------

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Unblock the client (allow network access)."""
        try:
            await self.coordinator.api_client.unblock_client(
                self.coordinator.site_id, self._client_mac
            )
        except OmadaApiError:
            _LOGGER.exception("Failed to unblock client %s", self._client_mac)
            return
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Block the client (deny network access)."""
        try:
            await self.coordinator.api_client.block_client(
                self.coordinator.site_id, self._client_mac
            )
        except OmadaApiError:
            _LOGGER.exception("Failed to block client %s", self._client_mac)
            return
        await self.coordinator.async_request_refresh()


class OmadaLedSwitch(
    CoordinatorEntity[OmadaSiteCoordinator],  # type: ignore[misc]
    SwitchEntity,  # type: ignore[misc]
):
    """Switch entity to control site-wide LED setting."""

    _attr_has_entity_name = True
    _attr_icon = "mdi:led-on"

    def __init__(
        self,
        coordinator: OmadaSiteCoordinator,
    ) -> None:
        """Initialize the LED switch."""
        super().__init__(coordinator)
        self._attr_name = f"{coordinator.site_name} LED"
        self._attr_unique_id = f"{DOMAIN}_{coordinator.site_id}_led"
        self._led_enabled: bool | None = None

    @property
    def is_on(self) -> bool | None:
        """Return True if LED is enabled."""
        return self._led_enabled

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return bool(self.coordinator.last_update_success)

    async def async_update(self) -> None:
        """Fetch current LED state from the API."""
        await super().async_update()
        try:
            result = await self.coordinator.api_client.get_led_setting(
                self.coordinator.site_id
            )
            self._led_enabled = result.get("enable", False)
        except OmadaApiError:
            _LOGGER.debug(
                "Could not fetch LED setting for site %s",
                self.coordinator.site_id,
            )

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Enable LEDs."""
        try:
            await self.coordinator.api_client.set_led_setting(
                self.coordinator.site_id, enable=True
            )
            self._led_enabled = True
        except OmadaApiError:
            _LOGGER.exception(
                "Failed to enable LED for site %s", self.coordinator.site_id
            )
            return
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Disable LEDs."""
        try:
            await self.coordinator.api_client.set_led_setting(
                self.coordinator.site_id, enable=False
            )
            self._led_enabled = False
        except OmadaApiError:
            _LOGGER.exception(
                "Failed to disable LED for site %s", self.coordinator.site_id
            )
            return
        self.async_write_ha_state()


class OmadaSsidSwitch(
    CoordinatorEntity[OmadaSiteCoordinator],  # type: ignore[misc]
    SwitchEntity,  # type: ignore[misc]
):
    """Switch entity to control SSID broadcast (visibility) site-wide.

    Note: This switch controls whether the SSID is broadcast (visible to clients).
    It does NOT enable/disable the wireless network itself - the network remains
    active but hidden when broadcast is disabled.

    For full enable/disable control per access point, use OmadaApSsidSwitch instead.
    """

    _attr_has_entity_name = True
    _attr_device_class = SwitchDeviceClass.SWITCH

    def __init__(
        self,
        coordinator: OmadaSiteCoordinator,
        site_device_id: str,
        ssid_data: dict[str, Any],
    ) -> None:
        """Initialize the SSID broadcast switch entity.

        Args:
            coordinator: Site coordinator
            site_device_id: Site device identifier (e.g., "site_12345")
            ssid_data: SSID configuration from API

        """
        super().__init__(coordinator)
        self._site_device_id = site_device_id
        self._ssid_id = ssid_data.get("ssidId", "")
        self._wlan_id = ssid_data.get("wlanId", "")
        self._ssid_name = ssid_data.get("ssidName", "Unknown SSID")

        # Determine enabled state from schedule or broadcast
        # Note: SSID can be disabled via wlanSchedule or by disabling broadcast
        self._enabled = ssid_data.get("broadcast", True) and not ssid_data.get(
            "wlanSchedule", {}
        ).get("scheduleEnable", False)

        self._attr_unique_id = (
            f"omada_open_api_{coordinator.site_id}_ssid_{self._ssid_id}"
        )
        self._attr_name = f"{self._ssid_name} Broadcast"
        self._attr_entity_category = None  # Make it a primary control, not config

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info to link this entity to the Site device."""
        return DeviceInfo(
            identifiers={(DOMAIN, self._site_device_id)},
        )

    @property
    def icon(self) -> str:
        """Return icon based on current state."""
        return ICON_WIFI if self._enabled else ICON_WIFI_OFF

    @property
    def is_on(self) -> bool:
        """Return True if SSID is enabled."""
        return self._enabled

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return bool(self.coordinator.last_update_success)

    async def async_update(self) -> None:
        """Fetch current SSID state from coordinator data."""
        await super().async_update()
        ssids = self.coordinator.data.get("ssids", [])
        for ssid in ssids:
            if ssid.get("ssidId") == self._ssid_id:
                self._enabled = ssid.get("broadcast", True) and not ssid.get(
                    "wlanSchedule", {}
                ).get("scheduleEnable", False)
                break

    def _sanitize_ssid_config(self, ssid_detail: dict[str, Any]) -> dict[str, Any]:
        """Sanitize SSID config for API update.

        The API has conditional requirements:
        - If vlanSetting.mode is 0 (Default), vlanId and customConfig must not be present
        - If vlanId is used, vlanSetting must be null

        Args:
            ssid_detail: Complete SSID configuration from get_ssid_detail

        Returns:
            Sanitized config dict safe for update_ssid_basic_config

        """
        config = dict(ssid_detail)

        # Handle VLAN configuration conflicts
        vlan_setting = config.get("vlanSetting", {})
        vlan_mode = vlan_setting.get("mode", 0)

        if vlan_mode == 0:  # Default mode
            # Remove vlanId and customConfig when using default VLAN mode
            config.pop("vlanId", None)
            if "vlanSetting" in config and "customConfig" in config["vlanSetting"]:
                config["vlanSetting"].pop("customConfig", None)

        # Remove read-only or metadata fields that shouldn't be in updates
        read_only_fields = ["ssidId", "wlanId", "createTime", "updateTime"]
        for field in read_only_fields:
            config.pop(field, None)

        return config

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Enable the SSID."""
        try:
            # Get current SSID configuration
            ssid_detail = await self.coordinator.api_client.get_ssid_detail(
                self.coordinator.site_id, self._wlan_id, self._ssid_id
            )

            # Sanitize and update broadcast field
            config = self._sanitize_ssid_config(ssid_detail)
            config["broadcast"] = True

            await self.coordinator.api_client.update_ssid_basic_config(
                self.coordinator.site_id, self._wlan_id, self._ssid_id, config
            )
            self._enabled = True
            await self.coordinator.async_request_refresh()
        except OmadaApiError as err:
            if err.error_code in (-1005, -1007):
                _LOGGER.warning(
                    "Permission denied when enabling SSID %s. "
                    "API credentials may have viewer-only access.",
                    self._ssid_name,
                )
            else:
                _LOGGER.exception("Failed to enable SSID %s", self._ssid_name)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Disable the SSID."""
        try:
            # Get current SSID configuration
            ssid_detail = await self.coordinator.api_client.get_ssid_detail(
                self.coordinator.site_id, self._wlan_id, self._ssid_id
            )

            # Sanitize and update broadcast field
            config = self._sanitize_ssid_config(ssid_detail)
            config["broadcast"] = False

            await self.coordinator.api_client.update_ssid_basic_config(
                self.coordinator.site_id, self._wlan_id, self._ssid_id, config
            )
            self._enabled = False
            await self.coordinator.async_request_refresh()
        except OmadaApiError as err:
            if err.error_code in (-1005, -1007):
                _LOGGER.warning(
                    "Permission denied when disabling SSID %s. "
                    "API credentials may have viewer-only access.",
                    self._ssid_name,
                )
            else:
                _LOGGER.exception("Failed to disable SSID %s", self._ssid_name)


class OmadaApSsidSwitch(
    CoordinatorEntity[OmadaSiteCoordinator],  # type: ignore[misc]
    SwitchEntity,  # type: ignore[misc]
):
    """Switch entity to enable/disable SSID on a specific AP.

    This switch controls whether the wireless network (SSID) is active on
    this specific access point. When disabled, the AP will not provide this
    SSID at all (not just hidden - completely disabled).
    """

    _attr_has_entity_name = True
    _attr_device_class = SwitchDeviceClass.SWITCH

    def __init__(
        self,
        coordinator: OmadaSiteCoordinator,
        ap_mac: str,
        ap_name: str,
        ssid_data: dict[str, Any],
    ) -> None:
        """Initialize the per-AP SSID switch.

        Args:
            coordinator: Site coordinator
            ap_mac: AP MAC address
            ap_name: AP device name
            ssid_data: SSID override data from API

        """
        super().__init__(coordinator)
        self._ap_mac = ap_mac
        self._ap_name = ap_name
        self._ssid_id = ssid_data.get("ssidId", "")
        self._ssid_entry_id = ssid_data.get("ssidEntryId")
        self._ssid_name = ssid_data.get("ssidName", "Unknown SSID")
        self._enabled: bool = bool(ssid_data.get("ssidEnable", True))

        self._attr_unique_id = f"omada_open_api_{ap_mac}_ssid_{self._ssid_id}"
        self._attr_name = f"{self._ssid_name} SSID"

    @property
    def device_info(self) -> DeviceInfo:
        """Link to AP device."""
        return DeviceInfo(
            identifiers={(DOMAIN, self._ap_mac)},
        )

    @property
    def is_on(self) -> bool:
        """Return True if SSID is enabled on this AP."""
        return self._enabled

    @property
    def icon(self) -> str:
        """Return icon based on state."""
        return ICON_WIFI if self._enabled else ICON_WIFI_OFF

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return bool(self.coordinator.last_update_success)

    async def async_update(self) -> None:
        """Fetch current state from coordinator."""
        await super().async_update()
        # Refresh from coordinator data stored in "ap_ssid_overrides"
        ap_overrides = self.coordinator.data.get("ap_ssid_overrides", {})
        ap_data = ap_overrides.get(self._ap_mac, {})
        ssid_overrides = ap_data.get("ssidOverrides", [])

        for override in ssid_overrides:
            if override.get("ssidId") == self._ssid_id:
                self._enabled = override.get("ssidEnable", True)
                break

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Enable SSID on this AP."""
        try:
            await self.coordinator.api_client.update_ap_ssid_override(
                self.coordinator.site_id,
                self._ap_mac,
                self._ssid_entry_id,
                self._ssid_name,
                ssid_enable=True,
            )
            self._enabled = True
            await self.coordinator.async_request_refresh()
        except OmadaApiError as err:
            if err.error_code in (-1005, -1007):
                _LOGGER.warning(
                    "Permission denied when enabling SSID %s on AP %s. "
                    "API credentials may have viewer-only access.",
                    self._ssid_name,
                    self._ap_name,
                )
            else:
                _LOGGER.exception(
                    "Failed to enable SSID %s on AP %s",
                    self._ssid_name,
                    self._ap_name,
                )

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Disable SSID on this AP."""
        try:
            await self.coordinator.api_client.update_ap_ssid_override(
                self.coordinator.site_id,
                self._ap_mac,
                self._ssid_entry_id,
                self._ssid_name,
                ssid_enable=False,
            )
            self._enabled = False
            await self.coordinator.async_request_refresh()
        except OmadaApiError as err:
            if err.error_code in (-1005, -1007):
                _LOGGER.warning(
                    "Permission denied when disabling SSID %s on AP %s. "
                    "API credentials may have viewer-only access.",
                    self._ssid_name,
                    self._ap_name,
                )
            else:
                _LOGGER.exception(
                    "Failed to disable SSID %s on AP %s",
                    self._ssid_name,
                    self._ap_name,
                )
