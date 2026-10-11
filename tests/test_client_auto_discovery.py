"""Regression tests for opt-in presence-only client discovery (GH #88)."""

from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

from homeassistant.components.device_tracker import SourceType

from custom_components.omada_open_api.const import (
    CONF_AUTO_DISCOVER_CLIENT_TRACKERS,
    CONF_AUTO_DISCOVERY_SSIDS,
    CONF_SELECTED_CLIENTS,
    DOMAIN,
)
from custom_components.omada_open_api.device_tracker import (
    OmadaAutoClientTracker,
    OmadaClientTracker,
    async_setup_entry,
)

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

MAC_A = "11-22-33-44-55-AA"
MAC_B = "11-22-33-44-55-BB"
MAC_C = "11-22-33-44-55-CC"


def _site(hass: HomeAssistant, site_id: str, clients: list[dict]) -> MagicMock:
    """Mock an existing Omada site coordinator's cached active-client list."""
    site = MagicMock()
    site.hass = hass
    site.site_id = site_id
    site.api_client.api_url = "https://omada.example.test"
    site.last_update_success = True
    site.data = {"devices": {}, "all_clients": clients}
    return site


def _client(mac: str, name: str, ssid: str | None = "Home") -> dict:
    """Return a minimal site-coordinator client snapshot."""
    return {
        "mac": mac,
        "name": name,
        "host_name": "laptop.local",
        "ip": "192.0.2.11",
        "ssid": ssid,
        "wireless": ssid is not None,
        "radio_id": 3,
        "channel": 5,
    }


def _entry(sites: list[MagicMock], options: dict) -> MagicMock:
    """Provide runtime_data without fetching from the controller."""
    entry = MagicMock()
    entry.options = options
    entry.runtime_data = SimpleNamespace(
        coordinators={s.site_id: s for s in sites},
        site_devices={},
        client_coordinators=[],
    )
    return entry


async def test_existing_installations_remain_opted_out(hass: HomeAssistant) -> None:
    """Default-off does not silently add hundreds of entities."""
    site = _site(hass, "office", [_client(MAC_A, "Phone")])
    added: list = []
    await async_setup_entry(hass, _entry([site], {}), added.extend)
    assert added == []


async def test_opt_in_discovers_without_existing_client_coordinator(
    hass: HomeAssistant,
) -> None:
    """Presence-only trackers work when selected_clients is empty."""
    site = _site(hass, "office", [_client(MAC_A, "Phone")])
    added: list = []
    await async_setup_entry(
        hass, _entry([site], {CONF_AUTO_DISCOVER_CLIENT_TRACKERS: True}), added.extend
    )
    assert len(added) == 1
    assert isinstance(added[0], OmadaAutoClientTracker)
    assert added[0].unique_id == f"{DOMAIN}_{MAC_A}"
    assert added[0].source_type == SourceType.ROUTER
    assert added[0].is_connected
    assert added[0].ip_address == "192.0.2.11"
    assert added[0].extra_state_attributes["band"] == "6 GHz"


async def test_selected_client_not_duplicated(hass: HomeAssistant) -> None:
    """Selected clients retain the same legacy ID and richer entities."""
    site = _site(hass, "office", [_client(MAC_A, "Phone")])
    added: list = []
    await async_setup_entry(
        hass,
        _entry(
            [site],
            {
                CONF_AUTO_DISCOVER_CLIENT_TRACKERS: True,
                CONF_SELECTED_CLIENTS: ["11:22:33:44:55:AA"],
            },
        ),
        added.extend,
    )
    assert added == []
    # Existing selected tracker format is intentionally unchanged.
    selected = MagicMock()
    selected.data = {MAC_A: _client(MAC_A, "Phone")}
    selected.last_seen = {}
    selected.disconnect_timeout = 0
    selected.hass = hass
    existing_tracker = OmadaClientTracker(selected, MAC_A)
    assert existing_tracker.unique_id == f"{DOMAIN}_{MAC_A}"


async def test_site_roaming_and_name_change_keep_entity_id(
    hass: HomeAssistant,
) -> None:
    """One unique ID covers a client roaming between controller sites."""
    site_a = _site(hass, "a", [_client(MAC_A, "Old name")])
    site_b = _site(hass, "b", [])
    tracker = OmadaAutoClientTracker([site_a, site_b], MAC_A, {})
    original_id = tracker.unique_id
    assert tracker.name == "Old name"
    site_a.data["all_clients"] = []
    site_b.data["all_clients"] = [_client(MAC_A, "New name")]
    tracker._refresh_metadata()
    assert tracker.is_connected
    assert tracker.name == "New name"
    assert tracker.unique_id == original_id


async def test_absent_clients_are_away_without_deleting_the_entity(
    hass: HomeAssistant,
) -> None:
    """A missing client remains a registered tracker with an away state."""
    site = _site(hass, "a", [_client(MAC_A, "Tablet")])
    tracker = OmadaAutoClientTracker([site], MAC_A, {}, disconnect_timeout=0)
    assert tracker.is_connected
    site.data["all_clients"] = []
    assert not tracker.is_connected
    assert tracker.unique_id == f"{DOMAIN}_{MAC_A}"


async def test_ssid_filter_and_cross_site_duplicates(hass: HomeAssistant) -> None:
    """Only opted-in SSIDs are considered, with one entity per physical MAC."""
    site_a = _site(
        hass,
        "a",
        [_client(MAC_A, "Phone", "Home"), _client(MAC_B, "Printer", None)],
    )
    site_b = _site(
        hass,
        "b",
        [
            _client(MAC_A.replace("-", ":"), "Phone", "Home"),
            _client(MAC_C, "Guest", "Guest"),
        ],
    )
    added: list = []
    await async_setup_entry(
        hass,
        _entry(
            [site_a, site_b],
            {
                CONF_AUTO_DISCOVER_CLIENT_TRACKERS: True,
                CONF_AUTO_DISCOVERY_SSIDS: "Home",
            },
        ),
        added.extend,
    )
    assert len(added) == 1
    assert added[0].unique_id == f"{DOMAIN}_{MAC_A}"


async def test_parent_falls_back_to_site_device(hass: HomeAssistant) -> None:
    """Auto-discovery sets a valid via_device_id using the site registry."""
    site = _site(hass, "a", [_client(MAC_A, "Tablet")])
    site_devices = {"a": SimpleNamespace(id="site-device-1")}
    tracker = OmadaAutoClientTracker([site], MAC_A, site_devices)
    assert tracker.device_info["via_device_id"] == "site-device-1"
    assert tracker.device_info["identifiers"] == {(DOMAIN, MAC_A)}


async def test_no_band_guessing_from_24g_channel(hass: HomeAssistant) -> None:
    """6 GHz radioId=3 remains 6 GHz even when channel is 5."""
    site = _site(hass, "a", [_client(MAC_A, "Laptop")])
    tracker = OmadaAutoClientTracker([site], MAC_A, {})
    assert tracker.extra_state_attributes["channel"] == 5
    assert tracker.extra_state_attributes["band"] == "6 GHz"


async def test_failed_coordinator_is_unavailable_not_falsely_away(
    hass: HomeAssistant,
) -> None:
    """Preserve presence semantics on transient controller fetch failures."""
    site = _site(hass, "a", [_client(MAC_A, "Tablet")])
    tracker = OmadaAutoClientTracker([site], MAC_A, {})
    assert tracker.available
    site.last_update_success = False
    assert not tracker.available


async def test_disabling_auto_discovery_preserves_old_client_registry(
    hass: HomeAssistant,
) -> None:
    """Stale-infra pruning must never remove a historical client device."""
    from custom_components.omada_open_api import _prune_stale_infra_devices

    site = _site(hass, "a", [])
    entry = _entry([site], {})  # Discovery has since been turned off.
    device = SimpleNamespace(
        id="custom-device",
        name="My customized phone",
        identifiers={(DOMAIN, MAC_A)},
    )
    tracker_entity = SimpleNamespace(
        domain="device_tracker", unique_id=f"{DOMAIN}_{MAC_A}"
    )
    with (
        patch("custom_components.omada_open_api.dr.async_get") as get_devices,
        patch(
            "custom_components.omada_open_api.dr.async_entries_for_config_entry",
            return_value=[device],
        ),
        patch("custom_components.omada_open_api.er.async_get"),
        patch(
            "custom_components.omada_open_api.er.async_entries_for_config_entry",
            return_value=[tracker_entity],
        ),
    ):
        _prune_stale_infra_devices(hass, entry)
        get_devices.return_value.async_remove_device.assert_not_called()


async def test_offline_registered_tracker_is_restored_after_restart(
    hass: HomeAssistant,
) -> None:
    """Never drop previously discovered entity IDs when they are now offline."""
    site = _site(hass, "a", [])
    entry = _entry([site], {CONF_AUTO_DISCOVER_CLIENT_TRACKERS: True})
    known = SimpleNamespace(
        domain="device_tracker", unique_id=f"{DOMAIN}_{MAC_A}"
    )
    added: list = []
    with patch(
        "custom_components.omada_open_api.device_tracker.er.async_entries_for_config_entry",
        return_value=[known],
    ):
        await async_setup_entry(hass, entry, added.extend)

    assert len(added) == 1
    restored = added[0]
    assert restored.unique_id == f"{DOMAIN}_{MAC_A}"
    assert restored.is_connected is False
    assert restored.device_info["identifiers"] == {(DOMAIN, MAC_A)}


async def test_new_mac_format_stable_even_if_api_uses_colons(
    hass: HomeAssistant,
) -> None:
    """Normalize newly discovered IDs, preserving existing stored IDs verbatim."""
    site = _site(hass, "a", [_client(MAC_A.replace("-", ":"), "Phone")])
    added: list = []
    await async_setup_entry(
        hass, _entry([site], {CONF_AUTO_DISCOVER_CLIENT_TRACKERS: True}),
        added.extend,
    )
    assert len(added) == 1
    assert added[0].unique_id == f"{DOMAIN}_{MAC_A}"


async def test_failed_optional_client_api_is_unavailable_not_away(
    hass: HomeAssistant,
) -> None:
    """An otherwise successful site refresh must not misreport clients away."""
    site = _site(hass, "a", [_client(MAC_A, "Phone")])
    tracker = OmadaAutoClientTracker([site], MAC_A, {})
    site.data["all_clients"] = []
    site.data["clients_poll_ok"] = False
    assert not tracker.available


async def test_failed_client_poll_does_not_create_new_devices(
    hass: HomeAssistant,
) -> None:
    """Do not create presence devices from failed/stale site client queries."""
    site = _site(hass, "a", [_client(MAC_A, "Tablet")])
    site.data["clients_poll_ok"] = False
    added: list = []
    await async_setup_entry(
        hass,
        _entry([site], {CONF_AUTO_DISCOVER_CLIENT_TRACKERS: True}),
        added.extend,
    )
    assert added == []


async def test_indexed_client_lookup_avoids_full_client_list_scan(
    hass: HomeAssistant,
) -> None:
    """A normalized MAC index is sufficient for presence on large sites."""
    site = _site(hass, "a", [])
    site.data["all_clients"] = None
    site.data["client_index"] = {"1122334455AA": _client(MAC_A, "Tablet")}
    tracker = OmadaAutoClientTracker([site], MAC_A, {})
    assert tracker.is_connected
    assert tracker.name == "Tablet"


async def test_ssid_filter_is_rechecked_when_client_roams(
    hass: HomeAssistant,
) -> None:
    """A tracker goes away after leaving an opted-in SSID."""
    site = _site(hass, "a", [_client(MAC_A, "Phone", "Home")])
    tracker = OmadaAutoClientTracker([site], MAC_A, {}, allowed_ssids={"Home"})
    assert tracker.is_connected
    site.data["all_clients"] = [_client(MAC_A, "Phone", "Guest")]
    assert not tracker.is_connected
    site.data["all_clients"] = [_client(MAC_A, "Phone", "Home")]
    assert tracker.is_connected
