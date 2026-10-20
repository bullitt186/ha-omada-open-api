"""Regression tests for opt-in presence-only client discovery (GH #88)."""

from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

from homeassistant.components.device_tracker import SourceType

from custom_components.omada_open_api.const import (
    CONF_AUTO_DISCOVER_CLIENT_TRACKERS,
    CONF_AUTO_DISCOVERY_EXCLUDE_GUESTS,
    CONF_AUTO_DISCOVERY_EXCLUDE_LOCAL_MACS,
    CONF_AUTO_DISCOVERY_EXCLUDED_CLIENTS,
    CONF_AUTO_DISCOVERY_INCLUDE_WIRED,
    CONF_AUTO_DISCOVERY_REQUIRE_NAME,
    CONF_AUTO_DISCOVERY_SIGNAL_ATTRIBUTES,
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
    entry.entry_id = "auto-discovery-entry"
    entry.options = options
    entry.async_on_unload.side_effect = lambda unsubscribe: unsubscribe()
    entry.runtime_data = SimpleNamespace(
        coordinators={s.site_id: s for s in sites},
        site_devices={},
        client_coordinators=[],
    )
    return entry


async def test_existing_installations_stay_opted_out(hass: HomeAssistant) -> None:
    """Upgrading must not automatically register hundreds of clients."""
    site = _site(hass, "office", [_client(MAC_A, "Phone")])
    added: list = []
    await async_setup_entry(hass, _entry([site], {}), added.extend)
    assert added == []


async def test_explicit_user_opt_out_disables_auto_discovery(
    hass: HomeAssistant,
) -> None:
    """An explicitly disabled installation creates no auto trackers."""
    site = _site(hass, "office", [_client(MAC_A, "Phone")])
    added: list = []
    await async_setup_entry(
        hass, _entry([site], {CONF_AUTO_DISCOVER_CLIENT_TRACKERS: False}), added.extend
    )
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
                CONF_AUTO_DISCOVERY_INCLUDE_WIRED: False,
            },
        ),
        added.extend,
    )
    assert len(added) == 1
    assert added[0].unique_id == f"{DOMAIN}_{MAC_A}"


async def test_auto_discovery_safe_filter_defaults(hass: HomeAssistant) -> None:
    """Defaults include wired/private clients but exclude guest clients."""
    guest = _client(MAC_A, "Guest phone")
    guest["guest"] = True
    wired = _client(MAC_B, "Printer", None)
    private = _client("12-22-33-44-55-CC", "Private phone")
    site = _site(hass, "a", [guest, wired, private])
    added: list = []

    await async_setup_entry(
        hass,
        _entry([site], {CONF_AUTO_DISCOVER_CLIENT_TRACKERS: True}),
        added.extend,
    )

    assert {entity.unique_id for entity in added} == {
        f"{DOMAIN}_{MAC_B}",
        f"{DOMAIN}_12-22-33-44-55-CC",
    }


async def test_auto_discovery_applies_all_optional_filters(
    hass: HomeAssistant,
) -> None:
    """Wired, guest, private, and unnamed clients can all be excluded."""
    guest = _client(MAC_A, "Guest phone")
    guest["guest"] = True
    wired = _client(MAC_B, "Printer", None)
    private = _client("12-22-33-44-55-CC", "Private phone")
    unnamed = _client("10-22-33-44-55-DD", "")
    unnamed["host_name"] = ""
    allowed = _client("10-22-33-44-55-EE", "Laptop")
    site = _site(hass, "a", [guest, wired, private, unnamed, allowed])
    added: list = []

    await async_setup_entry(
        hass,
        _entry(
            [site],
            {
                CONF_AUTO_DISCOVER_CLIENT_TRACKERS: True,
                CONF_AUTO_DISCOVERY_INCLUDE_WIRED: False,
                CONF_AUTO_DISCOVERY_EXCLUDE_GUESTS: True,
                CONF_AUTO_DISCOVERY_EXCLUDE_LOCAL_MACS: True,
                CONF_AUTO_DISCOVERY_REQUIRE_NAME: True,
            },
        ),
        added.extend,
    )

    assert [entity.unique_id for entity in added] == [f"{DOMAIN}_10-22-33-44-55-EE"]


async def test_auto_discovery_ssid_list_and_explicit_exclusions(
    hass: HomeAssistant,
) -> None:
    """List-valued SSIDs and excluded MACs are applied after normalization."""
    site = _site(
        hass,
        "a",
        [
            _client(MAC_A, "Excluded", "Home"),
            _client(MAC_B, "Allowed", "Home"),
            _client(MAC_C, "Other", "IoT"),
        ],
    )
    added: list = []

    await async_setup_entry(
        hass,
        _entry(
            [site],
            {
                CONF_AUTO_DISCOVER_CLIENT_TRACKERS: True,
                CONF_AUTO_DISCOVERY_SSIDS: ["Home"],
                CONF_AUTO_DISCOVERY_EXCLUDED_CLIENTS: [MAC_A.replace("-", ":").lower()],
            },
        ),
        added.extend,
    )

    assert [entity.unique_id for entity in added] == [f"{DOMAIN}_{MAC_B}"]


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
    added: list = []
    with patch(
        "custom_components.omada_open_api.auto_discovery.Store.async_load",
        return_value={
            "1122334455AA": {
                "entity_unique_id": f"{DOMAIN}_{MAC_A}",
                "last_seen": "2026-01-01T00:00:00+00:00",
            }
        },
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
        hass,
        _entry([site], {CONF_AUTO_DISCOVER_CLIENT_TRACKERS: True}),
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


async def test_cleanup_waits_for_every_site_client_poll(
    hass: HomeAssistant,
) -> None:
    """An expired record survives while any relevant site poll has failed."""
    good = _site(hass, "good", [])
    failed = _site(hass, "failed", [])
    failed.data["clients_poll_ok"] = False
    entry = _entry(
        [good, failed],
        {CONF_AUTO_DISCOVER_CLIENT_TRACKERS: True},
    )
    stored = {
        "1122334455AA": {
            "entity_unique_id": f"{DOMAIN}_{MAC_A}",
            "last_seen": "2020-01-01T00:00:00+00:00",
        }
    }
    added: list = []

    with (
        patch(
            "custom_components.omada_open_api.auto_discovery.Store.async_load",
            return_value=stored,
        ),
        patch("custom_components.omada_open_api.auto_discovery.Store.async_delay_save"),
    ):
        await async_setup_entry(hass, entry, added.extend)
        await hass.async_block_till_done()

    assert MAC_A.replace("-", "") in entry.runtime_data.auto_client_manager.records


async def test_expired_client_can_be_rediscovered_after_cleanup(
    hass: HomeAssistant,
) -> None:
    """Cleanup releases ownership so a later sighting creates a fresh tracker."""
    site = _site(hass, "a", [])
    listeners: list = []
    site.async_add_listener.side_effect = lambda listener: (
        listeners.append(listener) or (lambda: None)
    )
    entry = _entry([site], {CONF_AUTO_DISCOVER_CLIENT_TRACKERS: True})
    stored = {
        "1122334455AA": {
            "entity_unique_id": f"{DOMAIN}_{MAC_A}",
            "last_seen": "2020-01-01T00:00:00+00:00",
        }
    }
    added: list = []

    with (
        patch(
            "custom_components.omada_open_api.auto_discovery.Store.async_load",
            return_value=stored,
        ),
        patch("custom_components.omada_open_api.auto_discovery.Store.async_delay_save"),
    ):
        await async_setup_entry(hass, entry, added.extend)
        await hass.async_block_till_done()
        assert entry.runtime_data.auto_client_manager.records == {}
        site.data["all_clients"] = [_client(MAC_A, "Returned")]
        for listener in listeners:
            listener()

    assert [entity.unique_id for entity in added] == [
        f"{DOMAIN}_{MAC_A}",
        f"{DOMAIN}_{MAC_A}",
    ]


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


async def test_invalid_and_selected_client_macs_are_not_auto_created(
    hass: HomeAssistant,
) -> None:
    """Skip missing/malformed MACs and never duplicate a selected client."""
    site = _site(
        hass,
        "a",
        [
            {"name": "No MAC", "active": True},
            _client("not-a-mac", "Bad device"),
            _client(MAC_B, "Selected phone"),
        ],
    )
    added: list = []
    await async_setup_entry(
        hass,
        _entry(
            [site],
            {
                CONF_AUTO_DISCOVER_CLIENT_TRACKERS: True,
                CONF_SELECTED_CLIENTS: [MAC_B],
            },
        ),
        added.extend,
    )
    assert added == []


async def test_registry_restore_ignores_invalid_selected_and_duplicate_ids(
    hass: HomeAssistant,
) -> None:
    """Skip malformed and selected IDs during reboot restoration."""
    site = _site(hass, "a", [])
    last_seen = "2026-01-01T00:00:00+00:00"
    stored = {
        "bad": {"entity_unique_id": f"{DOMAIN}_bad", "last_seen": last_seen},
        MAC_B: {"entity_unique_id": f"{DOMAIN}_{MAC_B}", "last_seen": last_seen},
        MAC_A: {"entity_unique_id": f"{DOMAIN}_{MAC_A}", "last_seen": last_seen},
    }
    entry = _entry(
        [site],
        {
            CONF_AUTO_DISCOVER_CLIENT_TRACKERS: True,
            CONF_SELECTED_CLIENTS: [MAC_B],
        },
    )
    added: list = []
    with patch(
        "custom_components.omada_open_api.auto_discovery.Store.async_load",
        return_value=stored,
    ):
        await async_setup_entry(hass, entry, added.extend)
    assert len(added) == 1
    assert added[0].unique_id == f"{DOMAIN}_{MAC_A}"


async def test_disconnected_grace_and_missing_host_details(
    hass: HomeAssistant,
) -> None:
    """Preserve short disconnect grace and clear stale network attributes."""
    import datetime as dt

    site = _site(hass, "a", [_client(MAC_A, "Tablet", None)])
    tracker = OmadaAutoClientTracker([site], MAC_A, {}, disconnect_timeout=2)
    assert tracker.extra_state_attributes["connection_type"] == "wired"
    assert "band" not in tracker.extra_state_attributes
    assert tracker.hostname == "laptop.local"
    site.data["all_clients"] = []
    assert tracker.is_connected
    assert tracker.ip_address is None
    assert tracker.hostname is None
    assert tracker.extra_state_attributes == {}
    tracker._last_seen = dt.datetime.now(dt.UTC) - dt.timedelta(minutes=3)
    assert not tracker.is_connected


async def test_tracker_update_keeps_name_in_sync_without_recreating_entity(
    hass: HomeAssistant,
) -> None:
    """A coordinator update writes state but retains its stable identity."""
    site = _site(hass, "a", [_client(MAC_A, "First name")])
    tracker = OmadaAutoClientTracker([site], MAC_A, {})
    assert tracker.unique_id == f"{DOMAIN}_{MAC_A}"
    site.data["all_clients"] = [_client(MAC_A, "New name")]
    with patch.object(tracker, "async_write_ha_state") as write_state:
        tracker._handle_site_update()
        write_state.assert_called_once_with()
    assert tracker.name == "New name"
    assert tracker.unique_id == f"{DOMAIN}_{MAC_A}"


async def test_signal_values_are_attributes_without_new_sensor_entities(
    hass: HomeAssistant,
) -> None:
    """Controller RSSI/SNR/quality are attached to one tracker for a client."""
    phone = _client(MAC_A, "Phone", "Home")
    phone.update({"rssi": -63, "snr": 29, "signal_level": 81})
    site = _site(hass, "a", [phone])
    added: list = []
    await async_setup_entry(
        hass, _entry([site], {CONF_AUTO_DISCOVER_CLIENT_TRACKERS: True}), added.extend
    )
    assert len(added) == 1
    tracker = added[0]
    assert tracker.unique_id == f"{DOMAIN}_{MAC_A}"
    assert tracker.extra_state_attributes["ssid"] == "Home"
    assert tracker.extra_state_attributes["rssi_dbm"] == -63
    assert tracker.extra_state_attributes["snr_db"] == 29
    assert tracker.extra_state_attributes["signal_strength_percent"] == 81


async def test_wifi_roaming_updates_existing_tracker_without_creating_another(
    hass: HomeAssistant,
) -> None:
    """One MAC remains one device across SSIDs, APs and selected Omada sites."""
    initial = _client(MAC_A, "Phone", "Home")
    initial.update({"rssi": -74, "snr": 20, "signal_level": 51})
    home = _site(hass, "home", [initial])
    guest = _site(hass, "guest", [])
    added: list = []
    await async_setup_entry(
        hass,
        _entry([home, guest], {CONF_AUTO_DISCOVER_CLIENT_TRACKERS: True}),
        added.extend,
    )
    assert len(added) == 1
    tracker = added[0]
    device_id = tracker.unique_id
    assert tracker.extra_state_attributes["rssi_dbm"] == -74
    # Move the same MAC to another SSID and another site, changing MAC notation.
    next_link = _client(MAC_A.replace("-", ":"), "Phone", "Guest")
    next_link.update({"rssi": -48, "snr": 38, "signal_level": 95})
    home.data["all_clients"] = []
    guest.data["all_clients"] = [next_link]
    tracker._refresh_metadata()
    for site in (home, guest):
        for listener in site.async_add_listener.call_args_list:
            listener.args[0]()
    assert len(added) == 1
    assert tracker.unique_id == device_id
    assert tracker.extra_state_attributes["ssid"] == "Guest"
    assert tracker.extra_state_attributes["rssi_dbm"] == -48
    assert tracker.extra_state_attributes["snr_db"] == 38


async def test_missing_or_wired_signal_data_is_never_invented(
    hass: HomeAssistant,
) -> None:
    """Missing measurement keys do not become guessed or zero values."""
    site = _site(hass, "home", [_client(MAC_A, "Phone")])
    tracker = OmadaAutoClientTracker([site], MAC_A, {})
    assert "rssi_dbm" not in tracker.extra_state_attributes
    assert "snr_db" not in tracker.extra_state_attributes
    wired = _client(MAC_A, "Printer", None)
    wired.update({"rssi": -44, "snr": 21, "signal_level": 70})
    site.data["all_clients"] = [wired]
    assert "rssi_dbm" not in tracker.extra_state_attributes
    assert "snr_db" not in tracker.extra_state_attributes


async def test_signal_attributes_toggle_defaults_on_and_can_be_disabled(
    hass: HomeAssistant,
) -> None:
    """Disable metrics without removing or replacing the presence entity."""
    device = _client(MAC_A, "Phone")
    device.update({"rssi": -52, "snr": 35, "signal_level": 88})
    site = _site(hass, "home", [device])
    tracker = OmadaAutoClientTracker([site], MAC_A, {})
    assert tracker.extra_state_attributes["rssi_dbm"] == -52
    tracker_off = OmadaAutoClientTracker([site], MAC_A, {}, signal_attributes=False)
    assert tracker_off.unique_id == tracker.unique_id
    assert "rssi_dbm" not in tracker_off.extra_state_attributes
    assert tracker_off.is_connected

    added: list = []
    await async_setup_entry(
        hass,
        _entry(
            [site],
            {
                CONF_AUTO_DISCOVER_CLIENT_TRACKERS: True,
                CONF_AUTO_DISCOVERY_SIGNAL_ATTRIBUTES: False,
            },
        ),
        added.extend,
    )
    assert len(added) == 1
    assert "rssi_dbm" not in added[0].extra_state_attributes
