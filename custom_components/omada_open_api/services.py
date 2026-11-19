"""Services of the Omada Open API integration."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import callback
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import entity_registry as er

from .const import DOMAIN

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant, ServiceCall

    from .types import OmadaRuntimeData

_LOGGER = logging.getLogger(__name__)


@callback
def async_setup_services(hass: HomeAssistant) -> None:
    """Register the integration's services (action-setup rule)."""

    async def debug_ssid_switches_service(call: ServiceCall) -> None:
        """Service to dump SSID switch diagnostic information."""
        config_entry_id = call.data.get("config_entry_id")
        if not config_entry_id:
            # Documented fallback: use the first loaded Omada entry.
            loaded = hass.config_entries.async_loaded_entries(DOMAIN)
            if not loaded:
                raise ServiceValidationError(
                    translation_domain=DOMAIN,
                    translation_key="no_loaded_entry",
                )
            config_entry_id = loaded[0].entry_id
        target_entry = hass.config_entries.async_get_entry(config_entry_id)
        if not target_entry or target_entry.domain != DOMAIN:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="config_entry_not_found",
                translation_placeholders={"config_entry_id": config_entry_id},
            )
        if target_entry.state is not ConfigEntryState.LOADED:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="config_entry_not_loaded",
                translation_placeholders={"config_entry_id": config_entry_id},
            )
        runtime_data: OmadaRuntimeData = target_entry.runtime_data
        coordinators = runtime_data.coordinators
        has_write_access = runtime_data.has_write_access
        site_devices = runtime_data.site_devices
        _LOGGER.info("=== SSID Switch Diagnostic Info ===")
        _LOGGER.info("Config Entry: %s (%s)", target_entry.title, config_entry_id)
        _LOGGER.info("Write Access: %s", has_write_access)
        _LOGGER.info("Coordinators: %d", len(coordinators))
        _LOGGER.info("Site Devices: %d", len(site_devices))
        total_ssids = 0
        for site_id, coordinator in coordinators.items():
            ssids = coordinator.data.get("ssids", [])
            total_ssids += len(ssids)
            _LOGGER.info(
                "  Site '%s': %d SSIDs",
                site_id,
                len(ssids),
            )
            for ssid in ssids:
                _LOGGER.info(
                    "    - ID: %s, wlanId: %s, name: %s, broadcast: %s",
                    ssid.get("id", "missing"),
                    ssid.get("wlanId", "missing"),
                    ssid.get("name", "missing"),
                    ssid.get("broadcast", "missing"),
                )
        _LOGGER.info("Total SSIDs across all sites: %d", total_ssids)
        entity_reg = er.async_get(hass)
        ssid_switches = [
            ent
            for ent in entity_reg.entities.values()
            if ent.config_entry_id == config_entry_id
            and ent.domain == "switch"
            and "ssid" in ent.unique_id
        ]
        _LOGGER.info("SSID switch entities created: %d", len(ssid_switches))
        for ent in ssid_switches:
            _LOGGER.info("  - %s (%s)", ent.entity_id, ent.unique_id)
        _LOGGER.info("=== End SSID Switch Diagnostic Info ===")

    hass.services.async_register(
        DOMAIN,
        "debug_ssid_switches",
        debug_ssid_switches_service,
    )
