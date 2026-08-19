"""Tests for dynamic per-band entity creation in sensor setup — TDD Cycle 2."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, patch

from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.omada_open_api.const import (
    CONF_ACCESS_TOKEN,
    CONF_API_URL,
    CONF_CLIENT_ID,
    CONF_CLIENT_SECRET,
    CONF_OMADA_ID,
    CONF_REFRESH_TOKEN,
    CONF_SELECTED_APPLICATIONS,
    CONF_SELECTED_CLIENTS,
    CONF_SELECTED_SITES,
    CONF_TOKEN_EXPIRES_AT,
    DOMAIN,
)

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

from .conftest import (
    SAMPLE_DEVICE_AP,
    SAMPLE_DEVICE_SWITCH,
    SAMPLE_UPLINK_INFO,
    TEST_API_URL,
    TEST_CLIENT_ID,
    TEST_CLIENT_SECRET,
    TEST_OMADA_ID,
    TEST_SITE_ID,
    TEST_SITE_NAME,
    _future_token_expiry,
)

AP_MAC = SAMPLE_DEVICE_AP["mac"]  # "AA-BB-CC-DD-EE-01"
_SITE_LIST = [{"siteId": TEST_SITE_ID, "name": TEST_SITE_NAME}]


def _build_entry(hass: HomeAssistant) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN,
        entry_id="test_band_dynamic",
        data={
            CONF_API_URL: TEST_API_URL,
            CONF_OMADA_ID: TEST_OMADA_ID,
            CONF_CLIENT_ID: TEST_CLIENT_ID,
            CONF_CLIENT_SECRET: TEST_CLIENT_SECRET,
            CONF_ACCESS_TOKEN: "valid_token",
            CONF_REFRESH_TOKEN: "valid_refresh",
            CONF_TOKEN_EXPIRES_AT: _future_token_expiry(),
            CONF_SELECTED_SITES: [TEST_SITE_ID],
            CONF_SELECTED_CLIENTS: [],
            CONF_SELECTED_APPLICATIONS: [],
        },
    )
    entry.add_to_hass(hass)
    return entry


def _patch_api_client(**overrides) -> tuple:
    """Build a minimal mock API client for band-dynamic tests."""
    mock = MagicMock()
    mock.get_sites = AsyncMock(return_value=_SITE_LIST)
    mock.get_devices = AsyncMock(return_value=[SAMPLE_DEVICE_AP, SAMPLE_DEVICE_SWITCH])
    mock.get_device_uplink_info = AsyncMock(return_value=SAMPLE_UPLINK_INFO)
    mock.get_clients = AsyncMock(
        return_value={"data": [], "totalRows": 0, "currentPage": 1}
    )
    mock.get_client_app_traffic = AsyncMock(return_value=[])
    mock.get_switch_ports_poe = AsyncMock(return_value=[])
    mock.get_poe_usage = AsyncMock(return_value=[])
    mock.get_device_client_stats = AsyncMock(return_value=[])
    mock.check_write_access = AsyncMock(return_value=True)
    mock.get_gateway_info = AsyncMock(return_value={})
    mock.get_site_ssids = AsyncMock(return_value=[])
    mock.get_site_ssids_comprehensive = AsyncMock(return_value=[])
    mock.get_ssid_detail = AsyncMock(return_value={})
    mock.update_ssid_basic_config = AsyncMock()
    mock.get_ap_ssid_overrides = AsyncMock(return_value={"ssidOverrides": []})
    mock.update_ap_ssid_override = AsyncMock()
    mock.get_gateway_wan_status = AsyncMock(return_value=[])
    mock.get_device_stats = AsyncMock(return_value=[])
    mock.get_firmware_info = AsyncMock(return_value={})
    mock.start_online_upgrade = AsyncMock(return_value={})
    mock.get_ap_radios = AsyncMock(return_value={})
    mock.get_switch_port_details = AsyncMock(return_value=[])
    mock.get_ap_radio_config = AsyncMock(return_value={})
    mock.get_ap_led_setting = AsyncMock(return_value={})
    mock.set_ap_radio_enabled = AsyncMock()
    mock.get_wlan_optimization_status = AsyncMock(
        return_value={"status": 0, "beforeIndex": 55, "afterIndex": 80}
    )
    mock.get_threat_management = AsyncMock(return_value=[])
    mock.api_url = TEST_API_URL  # used as configuration_url in device_info
    for key, value in overrides.items():
        setattr(mock, key, value)
    return patch(
        "custom_components.omada_open_api.OmadaApiClient", return_value=mock
    ), mock


def _entity_registered(hass: HomeAssistant, mac: str, desc_key: str) -> bool:
    """Return True if an entity with unique_id '{mac}_{desc_key}' exists."""
    reg = er.async_get(hass)
    return reg.async_get_entity_id("sensor", DOMAIN, f"{mac}_{desc_key}") is not None


# ---------------------------------------------------------------------------
# Client band sensors — dual-band AP omits clientNum5g2 / clientNum6g
# ---------------------------------------------------------------------------


async def test_clients_5g2_not_created_when_absent(hass: HomeAssistant) -> None:
    """clients_5g2 entity must not be created when API omits clientNum5g2."""
    patcher, _mock = _patch_api_client(
        get_device_client_stats=AsyncMock(
            return_value=[
                {
                    "mac": AP_MAC,
                    "clientNum": 5,
                    "clientNum2g": 3,
                    "clientNum5g": 2,
                    # clientNum5g2 absent → dual-band AP
                }
            ]
        ),
    )
    entry = _build_entry(hass)
    with patcher:
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    assert not _entity_registered(hass, AP_MAC, "clients_5g2")
    assert not _entity_registered(hass, AP_MAC, "clients_6g")


async def test_clients_2g_and_5g_created_for_dual_band_ap(hass: HomeAssistant) -> None:
    """clients_2g and clients_5g must be created even when 5g2/6g are absent."""
    patcher, _mock = _patch_api_client(
        get_device_client_stats=AsyncMock(
            return_value=[
                {
                    "mac": AP_MAC,
                    "clientNum": 5,
                    "clientNum2g": 3,
                    "clientNum5g": 2,
                }
            ]
        ),
    )
    entry = _build_entry(hass)
    with patcher:
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    assert _entity_registered(hass, AP_MAC, "clients_2g")
    assert _entity_registered(hass, AP_MAC, "clients_5g")


async def test_clients_5g2_created_when_api_returns_it(hass: HomeAssistant) -> None:
    """clients_5g2 entity must be created when API returns clientNum5g2 (even 0)."""
    patcher, _mock = _patch_api_client(
        get_device_client_stats=AsyncMock(
            return_value=[
                {
                    "mac": AP_MAC,
                    "clientNum": 5,
                    "clientNum2g": 3,
                    "clientNum5g": 2,
                    "clientNum5g2": 0,
                    "clientNum6g": 0,
                }
            ]
        ),
    )
    entry = _build_entry(hass)
    with patcher:
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    assert _entity_registered(hass, AP_MAC, "clients_5g2")
    assert _entity_registered(hass, AP_MAC, "clients_6g")


# ---------------------------------------------------------------------------
# Radio util sensors — dual-band AP has no wp5g2 / wp6g in radios response
# ---------------------------------------------------------------------------


async def test_radio_util_5g2_not_created_when_band_absent(
    hass: HomeAssistant,
) -> None:
    """Radio util 5g2 entities must not be created when wp5g2 absent from API."""
    patcher, _mock = _patch_api_client(
        get_ap_radios=AsyncMock(
            return_value={
                "wp2g": {"actualChannel": "6", "busyUtil": 22},
                "wp5g": {"actualChannel": "36", "busyUtil": 1},
                # wp5g2 and wp6g absent
            }
        ),
    )
    entry = _build_entry(hass)
    with patcher:
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    assert not _entity_registered(hass, AP_MAC, "radio_busy_util_5g2")
    assert not _entity_registered(hass, AP_MAC, "radio_tx_util_5g2")
    assert not _entity_registered(hass, AP_MAC, "radio_busy_util_6g")


async def test_radio_util_2g_and_5g_created_for_dual_band_ap(
    hass: HomeAssistant,
) -> None:
    """Radio util entities for existing bands must be created."""
    patcher, _mock = _patch_api_client(
        get_ap_radios=AsyncMock(
            return_value={
                "wp2g": {"actualChannel": "6", "busyUtil": 22},
                "wp5g": {"actualChannel": "36", "busyUtil": 1},
            }
        ),
    )
    entry = _build_entry(hass)
    with patcher:
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    assert _entity_registered(hass, AP_MAC, "radio_busy_util_2g")
    assert _entity_registered(hass, AP_MAC, "radio_busy_util_5g")
    assert _entity_registered(hass, AP_MAC, "radio_tx_util_2g")


async def test_radio_util_5g2_created_when_band_present(hass: HomeAssistant) -> None:
    """Radio util 5g2 entities must be created when wp5g2 has a non-empty channel."""
    patcher, _mock = _patch_api_client(
        get_ap_radios=AsyncMock(
            return_value={
                "wp2g": {"actualChannel": "6", "busyUtil": 22},
                "wp5g": {"actualChannel": "36", "busyUtil": 1},
                "wp5g2": {"actualChannel": "149", "busyUtil": 0},
            }
        ),
    )
    entry = _build_entry(hass)
    with patcher:
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    assert _entity_registered(hass, AP_MAC, "radio_busy_util_5g2")
    assert _entity_registered(hass, AP_MAC, "radio_tx_util_5g2")


# ---------------------------------------------------------------------------
# Dynamic addition — band entity added on subsequent coordinator update
# ---------------------------------------------------------------------------


async def test_clients_5g2_added_dynamically_on_subsequent_update(
    hass: HomeAssistant,
) -> None:
    """clients_5g2 entity must be added when 5g2 data appears in a later refresh."""
    # First refresh: dual-band only (no 5g2 data).
    patcher, mock = _patch_api_client(
        get_device_client_stats=AsyncMock(
            return_value=[
                {"mac": AP_MAC, "clientNum": 5, "clientNum2g": 3, "clientNum5g": 2}
            ]
        ),
    )
    entry = _build_entry(hass)
    with patcher:
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    assert not _entity_registered(hass, AP_MAC, "clients_5g2")

    # Now the AP gets a firmware update that adds a second 5 GHz radio.
    coordinator = entry.runtime_data.coordinators[TEST_SITE_ID]
    mock.get_device_client_stats = AsyncMock(
        return_value=[
            {
                "mac": AP_MAC,
                "clientNum": 5,
                "clientNum2g": 3,
                "clientNum5g": 2,
                "clientNum5g2": 0,  # new band data!
            }
        ]
    )
    await coordinator.async_refresh()
    await hass.async_block_till_done()

    assert _entity_registered(hass, AP_MAC, "clients_5g2")


# ---------------------------------------------------------------------------
# Purge — orphaned band entities removed at setup when band absent
# ---------------------------------------------------------------------------


async def test_orphaned_clients_5g2_purged_at_setup(hass: HomeAssistant) -> None:
    """Pre-existing clients_5g2 registry entry must be removed when band absent."""
    entry = _build_entry(hass)
    # Simulate a stale entity left over from before the dynamic-creation fix.
    reg = er.async_get(hass)
    reg.async_get_or_create(
        "sensor",
        DOMAIN,
        f"{AP_MAC}_clients_5g2",
        config_entry=entry,
    )
    assert _entity_registered(hass, AP_MAC, "clients_5g2")

    patcher, _mock = _patch_api_client(
        get_device_client_stats=AsyncMock(
            return_value=[
                {"mac": AP_MAC, "clientNum": 5, "clientNum2g": 3, "clientNum5g": 2}
                # clientNum5g2 absent — dual-band AP
            ]
        ),
    )
    with patcher:
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    assert not _entity_registered(hass, AP_MAC, "clients_5g2")


async def test_orphaned_radio_util_5g2_purged_at_setup(hass: HomeAssistant) -> None:
    """Pre-existing radio_busy_util_5g2 registry entry must be removed when band absent."""
    entry = _build_entry(hass)
    reg = er.async_get(hass)
    reg.async_get_or_create(
        "sensor",
        DOMAIN,
        f"{AP_MAC}_radio_busy_util_5g2",
        config_entry=entry,
    )
    assert _entity_registered(hass, AP_MAC, "radio_busy_util_5g2")

    patcher, _mock = _patch_api_client(
        get_ap_radios=AsyncMock(
            return_value={
                "wp2g": {"actualChannel": "6", "busyUtil": 22},
                "wp5g": {"actualChannel": "36", "busyUtil": 1},
                # wp5g2 absent
            }
        ),
    )
    with patcher:
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    assert not _entity_registered(hass, AP_MAC, "radio_busy_util_5g2")


async def test_present_band_entity_not_purged(hass: HomeAssistant) -> None:
    """A band entity whose band IS present must not be removed at setup."""
    entry = _build_entry(hass)
    reg = er.async_get(hass)
    reg.async_get_or_create(
        "sensor",
        DOMAIN,
        f"{AP_MAC}_clients_5g2",
        config_entry=entry,
    )

    patcher, _mock = _patch_api_client(
        get_device_client_stats=AsyncMock(
            return_value=[
                {
                    "mac": AP_MAC,
                    "clientNum": 5,
                    "clientNum2g": 3,
                    "clientNum5g": 2,
                    "clientNum5g2": 0,
                }
            ]
        ),
    )
    with patcher:
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    assert _entity_registered(hass, AP_MAC, "clients_5g2")


# ---------------------------------------------------------------------------
# Entity-ID migration — _5_ghz_1 → _5_ghz when translations drop the "-1"
# ---------------------------------------------------------------------------


async def test_5g_entity_id_migrated_from_5_ghz_1_to_5_ghz(
    hass: HomeAssistant,
) -> None:
    """Existing 5g sensor entity with legacy _5_ghz_1 entity_id is renamed at setup."""
    entry = _build_entry(hass)
    reg = er.async_get(hass)
    entity_entry = reg.async_get_or_create(
        "sensor",
        DOMAIN,
        f"{AP_MAC}_radio_busy_util_5g",
        config_entry=entry,
        suggested_object_id="schlafzimmer_channel_busy_5_ghz_1",
    )
    assert entity_entry.entity_id == "sensor.schlafzimmer_channel_busy_5_ghz_1"

    patcher, _mock = _patch_api_client(
        get_ap_radios=AsyncMock(
            return_value={
                "wp2g": {"actualChannel": "6", "busyUtil": 22},
                "wp5g": {"actualChannel": "36", "busyUtil": 1},
            }
        ),
    )
    with patcher:
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    assert reg.async_get("sensor.schlafzimmer_channel_busy_5_ghz_1") is None
    assert reg.async_get("sensor.schlafzimmer_channel_busy_5_ghz") is not None


async def test_5g2_entity_id_not_migrated(hass: HomeAssistant) -> None:
    """5g2 entities ending in _5_ghz_2 must not be renamed — only _5_ghz_1 is legacy."""
    entry = _build_entry(hass)
    reg = er.async_get(hass)
    reg.async_get_or_create(
        "sensor",
        DOMAIN,
        f"{AP_MAC}_radio_busy_util_5g2",
        config_entry=entry,
        suggested_object_id="schlafzimmer_channel_busy_5_ghz_2",
    )

    patcher, _mock = _patch_api_client(
        get_ap_radios=AsyncMock(
            return_value={
                "wp2g": {"actualChannel": "6", "busyUtil": 22},
                "wp5g": {"actualChannel": "36", "busyUtil": 1},
                "wp5g2": {"actualChannel": "149", "busyUtil": 0},
            }
        ),
    )
    with patcher:
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    assert reg.async_get("sensor.schlafzimmer_channel_busy_5_ghz_2") is not None
