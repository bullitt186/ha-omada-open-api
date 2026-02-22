"""Switch platform for Omada Open API integration."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from homeassistant.components.switch import SwitchDeviceClass, SwitchEntity
from homeassistant.core import callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity import (  # type: ignore[attr-defined]
    DeviceInfo,
    EntityCategory,
)

from .api import OmadaApiError
from .const import DOMAIN, ICON_WIFI, ICON_WIFI_OFF
from .coordinator import OmadaClientCoordinator, OmadaSiteCoordinator
from .entity import OmadaEntity

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from .types import OmadaConfigEntry

_LOGGER = logging.getLogger(__name__)

PARALLEL_UPDATES = 1


async def async_setup_entry(  # pylint: disable=too-many-branches,too-many-statements
    hass: HomeAssistant,
    entry: OmadaConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Omada switch entities from a config entry."""
    rd = entry.runtime_data
    has_write_access: bool = rd.has_write_access
    coordinators: dict[str, OmadaSiteCoordinator] = rd.coordinators

    # --- Static entities (one per site, don't change dynamically) ---
    if has_write_access:
        static_entities: list[SwitchEntity] = [
            OmadaLedSwitch(coordinator) for coordinator in coordinators.values()
        ]
        if static_entities:
            async_add_entities(static_entities)

    # --- Dynamic PoE + SSID + AP SSID switches (per-device/per-config) ---
    if has_write_access:
        known_poe_ports: set[str] = set()
        known_ssid_keys: set[str] = set()
        known_ap_ssid_keys: set[str] = set()

        for site_id, site_coord in coordinators.items():

            @callback
            def _async_check_new_device_switches(  # pylint: disable=too-many-locals
                coord: OmadaSiteCoordinator = site_coord,
                sid: str = site_id,
            ) -> None:
                """Add switches for newly discovered PoE ports and AP SSID overrides."""
                new_entities: list[SwitchEntity] = []

                # PoE switches for new ports.
                poe_ports = coord.data.get("poe_ports", {})
                new_poe = set(poe_ports.keys()) - known_poe_ports
                if new_poe:
                    known_poe_ports.update(new_poe)
                    new_entities.extend(
                        OmadaPoeSwitch(coordinator=coord, port_key=pk) for pk in new_poe
                    )

                # Site-wide SSID switches for new SSIDs.
                ssids = coord.data.get("ssids", [])
                site_device_identifier = f"site_{sid}"
                for ssid in ssids:
                    ssid_id = ssid.get("ssidId")
                    wlan_id = ssid.get("wlanId")
                    if not ssid_id or not wlan_id:
                        continue
                    key = f"{sid}_{ssid_id}"
                    if key not in known_ssid_keys:
                        if sid not in rd.site_devices:
                            continue
                        known_ssid_keys.add(key)
                        new_entities.append(
                            OmadaSsidSwitch(
                                coordinator=coord,
                                site_device_id=site_device_identifier,
                                ssid_data=ssid,
                            )
                        )

                # Per-AP SSID switches for new AP+SSID combos.
                ap_overrides = coord.data.get("ap_ssid_overrides", {})
                devices = coord.data.get("devices", {})
                for ap_mac, override_data in ap_overrides.items():
                    ap_device = devices.get(ap_mac, {})
                    ap_name = ap_device.get("name", ap_mac)
                    for ssid_override in override_data.get("ssidOverrides", []):
                        entry_id = ssid_override.get("ssidEntryId")
                        if entry_id is not None:
                            ap_key = f"{ap_mac}_{entry_id}"
                            if ap_key not in known_ap_ssid_keys:
                                known_ap_ssid_keys.add(ap_key)
                                new_entities.append(
                                    OmadaApSsidSwitch(
                                        coordinator=coord,
                                        ap_mac=ap_mac,
                                        ap_name=ap_name,
                                        ssid_data=ssid_override,
                                    )
                                )

                if new_entities:
                    async_add_entities(new_entities)

            _async_check_new_device_switches()
            entry.async_on_unload(
                site_coord.async_add_listener(_async_check_new_device_switches)
            )
    else:
        _LOGGER.info(
            "Skipping PoE/LED/SSID switches — API credentials have viewer-only access"
        )

    # --- Dynamic client block/unblock switches ---
    known_client_macs: set[str] = set()
    client_coordinators: list[OmadaClientCoordinator] = rd.client_coordinators

    for client_coord in client_coordinators:

        @callback
        def _async_check_new_clients(
            coord: OmadaClientCoordinator = client_coord,
        ) -> None:
            """Add block/unblock switches for newly discovered clients."""
            new_macs = set(coord.data.keys()) - known_client_macs
            if not new_macs:
                return

            known_client_macs.update(new_macs)

            new_entities: list[SwitchEntity] = [
                OmadaClientBlockSwitch(coord, mac) for mac in new_macs
            ]
            if new_entities:
                async_add_entities(new_entities)

        _async_check_new_clients()
        entry.async_on_unload(client_coord.async_add_listener(_async_check_new_clients))


class OmadaPoeSwitch(
    OmadaEntity[OmadaSiteCoordinator],
    SwitchEntity,
):
    """Switch entity to control PoE on a switch port."""

    _attr_device_class = SwitchDeviceClass.SWITCH
    _attr_icon = "mdi:ethernet"
    _attr_entity_category = EntityCategory.CONFIG

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
        self._attr_translation_key = "poe"
        self._attr_translation_placeholders = {"port_name": port_name}

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
                raise HomeAssistantError(
                    f"Insufficient permissions to control PoE on "
                    f"{self._switch_mac} port {self._port_num}. "
                    f"Ensure the Open API application has "
                    f"'Site Device Manager Modify' permission"
                ) from err
            raise HomeAssistantError(
                f"Failed to set PoE {'on' if enabled else 'off'} "
                f"for {self._switch_mac} port {self._port_num}"
            ) from err

        # Refresh coordinator data to reflect the change.
        await self.coordinator.async_request_refresh()


class OmadaClientBlockSwitch(
    OmadaEntity[OmadaClientCoordinator],
    SwitchEntity,
):
    """Switch entity to block/unblock a client.

    When the switch is ON the client is allowed (not blocked).
    When the switch is OFF the client is blocked.
    """

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

        self._attr_translation_key = "network_access"
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
        except OmadaApiError as err:
            raise HomeAssistantError(
                f"Failed to unblock client {self._client_mac}"
            ) from err
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Block the client (deny network access)."""
        try:
            await self.coordinator.api_client.block_client(
                self.coordinator.site_id, self._client_mac
            )
        except OmadaApiError as err:
            raise HomeAssistantError(
                f"Failed to block client {self._client_mac}"
            ) from err
        await self.coordinator.async_request_refresh()


class OmadaLedSwitch(
    OmadaEntity[OmadaSiteCoordinator],
    SwitchEntity,
):
    """Switch entity to control site-wide LED setting."""

    _attr_icon = "mdi:led-on"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(
        self,
        coordinator: OmadaSiteCoordinator,
    ) -> None:
        """Initialize the LED switch."""
        super().__init__(coordinator)
        self._attr_translation_key = "led"
        self._attr_translation_placeholders = {
            "site_name": coordinator.site_name,
        }
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
        except OmadaApiError as err:
            raise HomeAssistantError(
                f"Failed to enable LED for site {self.coordinator.site_id}"
            ) from err
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Disable LEDs."""
        try:
            await self.coordinator.api_client.set_led_setting(
                self.coordinator.site_id, enable=False
            )
            self._led_enabled = False
        except OmadaApiError as err:
            raise HomeAssistantError(
                f"Failed to disable LED for site {self.coordinator.site_id}"
            ) from err
        self.async_write_ha_state()


class OmadaSsidSwitch(
    OmadaEntity[OmadaSiteCoordinator],
    SwitchEntity,
):
    """Switch entity to control SSID broadcast (visibility) site-wide.

    Note: This switch controls whether the SSID is broadcast (visible to clients).
    It does NOT enable/disable the wireless network itself - the network remains
    active but hidden when broadcast is disabled.

    For full enable/disable control per access point, use OmadaApSsidSwitch instead.
    """

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
        self._attr_translation_key = "ssid_broadcast"
        self._attr_translation_placeholders = {"ssid_name": self._ssid_name}
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
                raise HomeAssistantError(
                    f"Permission denied when enabling SSID {self._ssid_name}. "
                    f"API credentials may have viewer-only access."
                ) from err
            raise HomeAssistantError(
                f"Failed to enable SSID {self._ssid_name}"
            ) from err

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
                raise HomeAssistantError(
                    f"Permission denied when disabling SSID {self._ssid_name}. "
                    f"API credentials may have viewer-only access."
                ) from err
            raise HomeAssistantError(
                f"Failed to disable SSID {self._ssid_name}"
            ) from err


class OmadaApSsidSwitch(
    OmadaEntity[OmadaSiteCoordinator],
    SwitchEntity,
):
    """Switch entity to enable/disable SSID on a specific AP.

    This switch controls whether the wireless network (SSID) is active on
    this specific access point. When disabled, the AP will not provide this
    SSID at all (not just hidden - completely disabled).
    """

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
        self._ssid_entry_id: int = int(ssid_data.get("ssidEntryId", 0))
        self._ssid_name = ssid_data.get("ssidName", "Unknown SSID")
        self._enabled: bool = bool(ssid_data.get("ssidEnable", True))

        self._attr_unique_id = f"omada_open_api_{ap_mac}_ssid_{self._ssid_id}"
        self._attr_translation_key = "ap_ssid"
        self._attr_translation_placeholders = {"ssid_name": self._ssid_name}

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
                raise HomeAssistantError(
                    f"Permission denied when enabling SSID {self._ssid_name} "
                    f"on AP {self._ap_name}. "
                    f"API credentials may have viewer-only access."
                ) from err
            raise HomeAssistantError(
                f"Failed to enable SSID {self._ssid_name} on AP {self._ap_name}"
            ) from err

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
                raise HomeAssistantError(
                    f"Permission denied when disabling SSID {self._ssid_name} "
                    f"on AP {self._ap_name}. "
                    f"API credentials may have viewer-only access."
                ) from err
            raise HomeAssistantError(
                f"Failed to disable SSID {self._ssid_name} on AP {self._ap_name}"
            ) from err
