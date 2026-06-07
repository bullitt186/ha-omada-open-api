"""Tests for Omada Open API coordinators."""

from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock

from homeassistant.util import dt as dt_util

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

from custom_components.omada_open_api.api import OmadaApiError
from custom_components.omada_open_api.const import (
    UPGRADE_COOLDOWN_POLLS,
    UPGRADE_POLL_INTERVAL,
)
from custom_components.omada_open_api.coordinator import (
    OmadaAppTrafficCoordinator,
    OmadaClientCoordinator,
    OmadaSiteCoordinator,
)

from .conftest import (
    SAMPLE_CLIENT_WIRELESS,
    SAMPLE_DEVICE_AP,
    SAMPLE_DEVICE_GATEWAY,
    SAMPLE_DEVICE_SWITCH,
    SAMPLE_POE_PORT_ACTIVE,
    SAMPLE_POE_PORT_INACTIVE,
    SAMPLE_POE_PORT_NOT_SUPPORTED,
    SAMPLE_POE_PORT_SWITCH_NOT_SUPPORTED,
    SAMPLE_POE_USAGE,
    TEST_SITE_ID,
    TEST_SITE_NAME,
)

# ---------------------------------------------------------------------------
# OmadaSiteCoordinator
# ---------------------------------------------------------------------------


async def test_site_coordinator_fetches_devices_and_uplinks(
    hass: HomeAssistant, mock_api_client: MagicMock
) -> None:
    """Test that the site coordinator fetches devices and merges uplink info."""
    coordinator = OmadaSiteCoordinator(
        hass=hass,
        api_client=mock_api_client,
        site_id=TEST_SITE_ID,
        site_name=TEST_SITE_NAME,
    )

    await coordinator.async_refresh()
    assert coordinator.last_update_success is True

    data = coordinator.data
    assert "devices" in data
    assert len(data["devices"]) == 3

    # Verify uplink info was merged into the AP device.
    ap = data["devices"]["AA-BB-CC-DD-EE-01"]
    assert ap["name"] == "Office AP"
    assert ap["uplink_device_name"] == "Core Switch"
    assert ap["link_speed"] == 3

    # Verify gateway has no uplink (not in uplink_info fixture).
    gw = data["devices"]["AA-BB-CC-DD-EE-03"]
    assert gw["name"] == "Main Gateway"


async def test_site_coordinator_handles_uplink_failure_gracefully(
    hass: HomeAssistant, mock_api_client: MagicMock
) -> None:
    """Test that uplink info failure doesn't break the update."""
    mock_api_client.get_device_uplink_info = AsyncMock(
        side_effect=OmadaApiError("Uplink fetch failed")
    )

    coordinator = OmadaSiteCoordinator(
        hass=hass,
        api_client=mock_api_client,
        site_id=TEST_SITE_ID,
        site_name=TEST_SITE_NAME,
    )

    await coordinator.async_refresh()
    # Update should still succeed — uplink info is optional.
    assert coordinator.last_update_success is True
    assert len(coordinator.data["devices"]) == 3


async def test_site_coordinator_raises_on_device_fetch_failure(
    hass: HomeAssistant, mock_api_client: MagicMock
) -> None:
    """Test that device fetch failure raises UpdateFailed."""
    mock_api_client.get_devices = AsyncMock(
        side_effect=OmadaApiError("Connection lost")
    )

    coordinator = OmadaSiteCoordinator(
        hass=hass,
        api_client=mock_api_client,
        site_id=TEST_SITE_ID,
        site_name=TEST_SITE_NAME,
    )

    await coordinator.async_refresh()
    assert coordinator.last_update_success is False


async def test_site_coordinator_handles_device_without_mac(
    hass: HomeAssistant, mock_api_client: MagicMock
) -> None:
    """Test that devices without a MAC are skipped."""
    mock_api_client.get_devices = AsyncMock(
        return_value=[
            SAMPLE_DEVICE_AP,
            {"name": "No MAC Device", "type": "ap"},  # Missing mac
        ]
    )

    coordinator = OmadaSiteCoordinator(
        hass=hass,
        api_client=mock_api_client,
        site_id=TEST_SITE_ID,
        site_name=TEST_SITE_NAME,
    )

    await coordinator.async_refresh()
    assert coordinator.last_update_success is True
    assert len(coordinator.data["devices"]) == 1


async def test_site_coordinator_empty_device_list(
    hass: HomeAssistant, mock_api_client: MagicMock
) -> None:
    """Test that an empty device list is handled correctly."""
    mock_api_client.get_devices = AsyncMock(return_value=[])

    coordinator = OmadaSiteCoordinator(
        hass=hass,
        api_client=mock_api_client,
        site_id=TEST_SITE_ID,
        site_name=TEST_SITE_NAME,
    )

    await coordinator.async_refresh()
    assert coordinator.last_update_success is True
    assert len(coordinator.data["devices"]) == 0
    # Uplink should not be called if there are no devices.
    mock_api_client.get_device_uplink_info.assert_not_called()


async def test_site_coordinator_fetches_poe_ports(
    hass: HomeAssistant, mock_api_client: MagicMock
) -> None:
    """Test that site coordinator fetches and filters PoE port data."""
    mock_api_client.get_switch_ports_poe = AsyncMock(
        return_value=[
            SAMPLE_POE_PORT_ACTIVE,
            SAMPLE_POE_PORT_INACTIVE,
            SAMPLE_POE_PORT_NOT_SUPPORTED,
            SAMPLE_POE_PORT_SWITCH_NOT_SUPPORTED,
        ]
    )

    coordinator = OmadaSiteCoordinator(
        hass=hass,
        api_client=mock_api_client,
        site_id=TEST_SITE_ID,
        site_name=TEST_SITE_NAME,
    )

    await coordinator.async_refresh()
    assert coordinator.last_update_success is True

    poe_ports = coordinator.data["poe_ports"]
    # Only ports with supportPoe=True AND switchSupportPoe=1 should be included.
    # Port 3 (supportPoe=False) and switch-not-supported port should be excluded.
    assert len(poe_ports) == 2

    key_active = "AA-BB-CC-DD-EE-02_1"
    assert key_active in poe_ports
    assert poe_ports[key_active]["power"] == 12.5
    assert poe_ports[key_active]["poe_enabled"] is True
    assert poe_ports[key_active]["switch_name"] == "Core Switch"
    assert poe_ports[key_active]["port_name"] == "Port 1"
    assert poe_ports[key_active]["voltage"] == 53.2
    assert poe_ports[key_active]["current"] == 235.0
    assert poe_ports[key_active]["pd_class"] == "Class 4"
    assert poe_ports[key_active]["poe_display_type"] == 4

    key_inactive = "AA-BB-CC-DD-EE-02_2"
    assert key_inactive in poe_ports
    assert poe_ports[key_inactive]["power"] == 0.0
    assert poe_ports[key_inactive]["poe_enabled"] is False


async def test_site_coordinator_poe_failure_graceful(
    hass: HomeAssistant, mock_api_client: MagicMock
) -> None:
    """Test that PoE fetch failure doesn't break the update."""
    mock_api_client.get_switch_ports_poe = AsyncMock(
        side_effect=OmadaApiError("PoE endpoint unavailable")
    )

    coordinator = OmadaSiteCoordinator(
        hass=hass,
        api_client=mock_api_client,
        site_id=TEST_SITE_ID,
        site_name=TEST_SITE_NAME,
    )

    await coordinator.async_refresh()
    assert coordinator.last_update_success is True
    # PoE ports should be empty dict, not missing.
    assert coordinator.data["poe_ports"] == {}
    # Devices should still be present.
    assert len(coordinator.data["devices"]) == 3


async def test_site_coordinator_poe_empty_response(
    hass: HomeAssistant, mock_api_client: MagicMock
) -> None:
    """Test that empty PoE response results in empty poe_ports dict."""
    mock_api_client.get_switch_ports_poe = AsyncMock(return_value=[])

    coordinator = OmadaSiteCoordinator(
        hass=hass,
        api_client=mock_api_client,
        site_id=TEST_SITE_ID,
        site_name=TEST_SITE_NAME,
    )

    await coordinator.async_refresh()
    assert coordinator.last_update_success is True
    assert coordinator.data["poe_ports"] == {}


# ---------------------------------------------------------------------------
# OmadaSiteCoordinator - PoE Budget
# ---------------------------------------------------------------------------


async def test_site_coordinator_fetches_poe_budget(
    hass: HomeAssistant, mock_api_client: MagicMock
) -> None:
    """Test that site coordinator fetches and processes PoE budget data."""
    mock_api_client.get_poe_usage = AsyncMock(return_value=[SAMPLE_POE_USAGE])

    coordinator = OmadaSiteCoordinator(
        hass=hass,
        api_client=mock_api_client,
        site_id=TEST_SITE_ID,
        site_name=TEST_SITE_NAME,
    )

    await coordinator.async_refresh()
    assert coordinator.last_update_success is True

    poe_budget = coordinator.data["poe_budget"]
    assert len(poe_budget) == 1

    mac = "AA-BB-CC-DD-EE-02"
    assert mac in poe_budget
    assert poe_budget[mac]["total_power"] == 240
    assert poe_budget[mac]["total_power_used"] == 45
    assert poe_budget[mac]["total_percent_used"] == 18.75
    assert poe_budget[mac]["name"] == "Core Switch"
    assert poe_budget[mac]["port_num"] == 24


async def test_site_coordinator_poe_budget_failure_graceful(
    hass: HomeAssistant, mock_api_client: MagicMock
) -> None:
    """Test that PoE budget fetch failure doesn't break the update."""
    mock_api_client.get_poe_usage = AsyncMock(
        side_effect=OmadaApiError("PoE budget endpoint unavailable")
    )

    coordinator = OmadaSiteCoordinator(
        hass=hass,
        api_client=mock_api_client,
        site_id=TEST_SITE_ID,
        site_name=TEST_SITE_NAME,
    )

    await coordinator.async_refresh()
    assert coordinator.last_update_success is True
    assert coordinator.data["poe_budget"] == {}
    # Devices should still be present.
    assert len(coordinator.data["devices"]) == 3


async def test_site_coordinator_poe_budget_empty(
    hass: HomeAssistant, mock_api_client: MagicMock
) -> None:
    """Test that empty PoE budget response results in empty dict."""
    mock_api_client.get_poe_usage = AsyncMock(return_value=[])

    coordinator = OmadaSiteCoordinator(
        hass=hass,
        api_client=mock_api_client,
        site_id=TEST_SITE_ID,
        site_name=TEST_SITE_NAME,
    )

    await coordinator.async_refresh()
    assert coordinator.last_update_success is True
    assert coordinator.data["poe_budget"] == {}


# ---------------------------------------------------------------------------
# Per-band client stats (Step 2)
# ---------------------------------------------------------------------------


async def test_site_coordinator_fetches_per_band_client_stats(
    hass: HomeAssistant, mock_api_client: MagicMock
) -> None:
    """Test that per-band client counts are merged into AP device data."""
    mock_api_client.get_device_client_stats = AsyncMock(
        return_value=[
            {
                "mac": "AA-BB-CC-DD-EE-01",
                "clientNum": 12,
                "clientNum2g": 4,
                "clientNum5g": 6,
                "clientNum5g2": 0,
                "clientNum6g": 2,
            }
        ]
    )

    coordinator = OmadaSiteCoordinator(
        hass=hass,
        api_client=mock_api_client,
        site_id=TEST_SITE_ID,
        site_name=TEST_SITE_NAME,
    )

    await coordinator.async_refresh()
    assert coordinator.last_update_success is True

    ap = coordinator.data["devices"]["AA-BB-CC-DD-EE-01"]
    assert ap["client_num"] == 12
    assert ap["client_num_2g"] == 4
    assert ap["client_num_5g"] == 6
    assert ap["client_num_5g2"] == 0
    assert ap["client_num_6g"] == 2

    # Only AP MACs should be sent to the API.
    call_args = mock_api_client.get_device_client_stats.call_args
    assert call_args[0][1] == ["AA-BB-CC-DD-EE-01"]


async def test_site_coordinator_band_stats_failure_graceful(
    hass: HomeAssistant, mock_api_client: MagicMock
) -> None:
    """Test that per-band stats failure doesn't break the update."""
    mock_api_client.get_device_client_stats = AsyncMock(
        side_effect=OmadaApiError("Band stats unavailable")
    )

    coordinator = OmadaSiteCoordinator(
        hass=hass,
        api_client=mock_api_client,
        site_id=TEST_SITE_ID,
        site_name=TEST_SITE_NAME,
    )

    await coordinator.async_refresh()
    assert coordinator.last_update_success is True
    # AP device should still exist, just without band stats.
    ap = coordinator.data["devices"]["AA-BB-CC-DD-EE-01"]
    assert "client_num_2g" not in ap


async def test_band_stat_absent_5g2_leaves_key_absent(
    hass: HomeAssistant, mock_api_client: MagicMock
) -> None:
    """Test that client_num_5g2/6g are absent when API omits them (dual-band AP)."""
    mock_api_client.get_device_client_stats = AsyncMock(
        return_value=[
            {
                "mac": "AA-BB-CC-DD-EE-01",
                "clientNum": 5,
                "clientNum2g": 3,
                "clientNum5g": 2,
                # clientNum5g2 and clientNum6g deliberately absent
            }
        ]
    )
    coordinator = OmadaSiteCoordinator(
        hass=hass,
        api_client=mock_api_client,
        site_id=TEST_SITE_ID,
        site_name=TEST_SITE_NAME,
    )
    await coordinator.async_refresh()
    ap = coordinator.data["devices"]["AA-BB-CC-DD-EE-01"]
    assert ap["client_num_2g"] == 3
    assert ap["client_num_5g"] == 2
    assert "client_num_5g2" not in ap
    assert "client_num_6g" not in ap


async def test_band_stat_zero_5g2_keeps_key_present(
    hass: HomeAssistant, mock_api_client: MagicMock
) -> None:
    """Test that client_num_5g2 == 0 when API returns clientNum5g2: 0 (band exists)."""
    mock_api_client.get_device_client_stats = AsyncMock(
        return_value=[
            {
                "mac": "AA-BB-CC-DD-EE-01",
                "clientNum": 5,
                "clientNum2g": 3,
                "clientNum5g": 2,
                "clientNum5g2": 0,
                "clientNum6g": 0,
            }
        ]
    )
    coordinator = OmadaSiteCoordinator(
        hass=hass,
        api_client=mock_api_client,
        site_id=TEST_SITE_ID,
        site_name=TEST_SITE_NAME,
    )
    await coordinator.async_refresh()
    ap = coordinator.data["devices"]["AA-BB-CC-DD-EE-01"]
    assert ap["client_num_5g2"] == 0
    assert ap["client_num_6g"] == 0


async def test_site_coordinator_no_aps_skips_band_stats(
    hass: HomeAssistant, mock_api_client: MagicMock
) -> None:
    """Test that band stats call is skipped when there are no APs."""
    # Override get_devices to return only a switch.
    mock_api_client.get_devices = AsyncMock(
        return_value=[
            {
                "mac": "AA-BB-CC-DD-EE-02",
                "name": "Core Switch",
                "model": "TL-SG3428X",
                "type": "switch",
                "status": 14,
                "ip": "192.168.1.2",
                "firmwareVersion": "2.0.0",
                "cpuUtil": 5,
                "memUtil": 30,
                "clientNum": 25,
                "uptime": 90000,
                "sn": "SN-SW-001",
                "active": True,
            }
        ]
    )

    coordinator = OmadaSiteCoordinator(
        hass=hass,
        api_client=mock_api_client,
        site_id=TEST_SITE_ID,
        site_name=TEST_SITE_NAME,
    )

    await coordinator.async_refresh()
    assert coordinator.last_update_success is True
    mock_api_client.get_device_client_stats.assert_not_called()


async def test_site_coordinator_ssid_override_error_graceful(
    hass: HomeAssistant, mock_api_client: MagicMock
) -> None:
    """Test that a SSID override fetch error for one AP doesn't block others."""
    mock_api_client.get_ap_ssid_overrides = AsyncMock(
        side_effect=OmadaApiError("timeout")
    )

    coordinator = OmadaSiteCoordinator(
        hass=hass,
        api_client=mock_api_client,
        site_id=TEST_SITE_ID,
        site_name=TEST_SITE_NAME,
    )

    await coordinator.async_refresh()
    # Refresh still succeeds despite SSID override errors.
    assert coordinator.last_update_success is True
    # ap_ssid_overrides should be empty (all failed).
    assert coordinator.data["ap_ssid_overrides"] == {}


async def test_site_coordinator_inactive_client_filtered(
    hass: HomeAssistant, mock_api_client: MagicMock
) -> None:
    """Test that inactive clients are filtered out from the client list."""
    mock_api_client.get_clients = AsyncMock(
        return_value={
            "data": [
                {"mac": "11-22-33-44-55-66", "active": True, "name": "Active"},
                {"mac": "AA-BB-CC-DD-EE-FF", "active": False, "name": "Inactive"},
            ],
            "totalRows": 2,
            "currentPage": 1,
        }
    )

    coordinator = OmadaSiteCoordinator(
        hass=hass,
        api_client=mock_api_client,
        site_id=TEST_SITE_ID,
        site_name=TEST_SITE_NAME,
    )

    await coordinator.async_refresh()
    assert coordinator.last_update_success is True
    # Only the active client should be present.
    clients = coordinator.data["all_clients"]
    macs = [c["mac"] for c in clients]
    assert "11-22-33-44-55-66" in macs
    assert "AA-BB-CC-DD-EE-FF" not in macs


async def test_site_coordinator_client_fetch_error_graceful(
    hass: HomeAssistant, mock_api_client: MagicMock
) -> None:
    """Test that a client fetch error returns empty list gracefully."""
    mock_api_client.get_clients = AsyncMock(side_effect=OmadaApiError("timeout"))

    coordinator = OmadaSiteCoordinator(
        hass=hass,
        api_client=mock_api_client,
        site_id=TEST_SITE_ID,
        site_name=TEST_SITE_NAME,
    )

    await coordinator.async_refresh()
    assert coordinator.last_update_success is True
    # Client list should be empty but not cause a failure.
    assert coordinator.data["all_clients"] == []


# ---------------------------------------------------------------------------
# Firmware info fetching
# ---------------------------------------------------------------------------


async def test_site_coordinator_fetches_firmware_info(
    hass: HomeAssistant, mock_api_client: MagicMock
) -> None:
    """Test that firmware info is fetched on first refresh."""
    mock_api_client.get_firmware_info = AsyncMock(
        return_value={"curFwVer": "1.0.0", "lastFwVer": "1.1.0", "fwReleaseLog": "Fix"}
    )
    coordinator = OmadaSiteCoordinator(
        hass=hass,
        api_client=mock_api_client,
        site_id=TEST_SITE_ID,
        site_name=TEST_SITE_NAME,
    )

    await coordinator.async_refresh()
    assert coordinator.last_update_success is True
    assert "firmware_info" in coordinator.data

    # Should have fetched firmware info for all 3 devices.
    assert mock_api_client.get_firmware_info.call_count == 3
    for mac in ("AA-BB-CC-DD-EE-01", "AA-BB-CC-DD-EE-02", "AA-BB-CC-DD-EE-03"):
        assert mac in coordinator.data["firmware_info"]
        assert coordinator.data["firmware_info"][mac]["lastFwVer"] == "1.1.0"


async def test_site_coordinator_firmware_info_skips_within_interval(
    hass: HomeAssistant, mock_api_client: MagicMock
) -> None:
    """Test that firmware info is NOT re-fetched within the check interval."""
    mock_api_client.get_firmware_info = AsyncMock(
        return_value={"curFwVer": "1.0.0", "lastFwVer": "1.1.0", "fwReleaseLog": "Fix"}
    )
    coordinator = OmadaSiteCoordinator(
        hass=hass,
        api_client=mock_api_client,
        site_id=TEST_SITE_ID,
        site_name=TEST_SITE_NAME,
    )

    # First refresh — should fetch firmware info.
    await coordinator.async_refresh()
    first_call_count = mock_api_client.get_firmware_info.call_count
    assert first_call_count == 3

    # Second refresh (no time travel) — should NOT re-fetch.
    await coordinator.async_refresh()
    assert mock_api_client.get_firmware_info.call_count == first_call_count


async def test_site_coordinator_firmware_info_refreshes_after_interval(
    hass: HomeAssistant, mock_api_client: MagicMock
) -> None:
    """Test that firmware info is re-fetched after the check interval elapses."""
    mock_api_client.get_firmware_info = AsyncMock(
        return_value={"curFwVer": "1.0.0", "lastFwVer": "1.1.0", "fwReleaseLog": "Fix"}
    )
    coordinator = OmadaSiteCoordinator(
        hass=hass,
        api_client=mock_api_client,
        site_id=TEST_SITE_ID,
        site_name=TEST_SITE_NAME,
    )

    await coordinator.async_refresh()
    assert mock_api_client.get_firmware_info.call_count == 3

    # Move time forward past the 30 min interval.
    coordinator._last_firmware_check -= timedelta(minutes=31)  # noqa: SLF001

    await coordinator.async_refresh()
    # Should have fetched firmware info again for all 3 devices.
    assert mock_api_client.get_firmware_info.call_count == 6


async def test_site_coordinator_firmware_skips_devices_without_need_upgrade(
    hass: HomeAssistant, mock_api_client: MagicMock
) -> None:
    """Test that firmware info is only fetched for devices with needUpgrade."""
    mock_api_client.get_firmware_info = AsyncMock(
        return_value={"curFwVer": "1.0.0", "lastFwVer": "1.1.0", "fwReleaseLog": "Fix"}
    )
    # Only AP needs upgrade; switch and gateway don't.
    ap_with_upgrade = {**SAMPLE_DEVICE_AP, "needUpgrade": True}
    switch_no_upgrade = {**SAMPLE_DEVICE_SWITCH, "needUpgrade": False}
    gateway_no_upgrade = {**SAMPLE_DEVICE_GATEWAY, "needUpgrade": False}
    mock_api_client.get_devices = AsyncMock(
        return_value=[ap_with_upgrade, switch_no_upgrade, gateway_no_upgrade]
    )

    coordinator = OmadaSiteCoordinator(
        hass=hass,
        api_client=mock_api_client,
        site_id=TEST_SITE_ID,
        site_name=TEST_SITE_NAME,
    )

    await coordinator.async_refresh()
    # Only 1 device needs upgrade, so only 1 firmware info fetch.
    assert mock_api_client.get_firmware_info.call_count == 1
    fw = coordinator.data["firmware_info"]
    assert SAMPLE_DEVICE_AP["mac"] in fw
    assert SAMPLE_DEVICE_SWITCH["mac"] not in fw
    assert SAMPLE_DEVICE_GATEWAY["mac"] not in fw


async def test_site_coordinator_firmware_info_error_per_device(
    hass: HomeAssistant, mock_api_client: MagicMock
) -> None:
    """Test that a firmware fetch error for one device doesn't block others."""

    async def _side_effect(site_id: str, mac: str) -> dict:
        if mac == "AA-BB-CC-DD-EE-01":
            raise OmadaApiError("timeout")
        return {"curFwVer": "1.0.0", "lastFwVer": "2.0.0", "fwReleaseLog": "New"}

    mock_api_client.get_firmware_info = AsyncMock(side_effect=_side_effect)

    coordinator = OmadaSiteCoordinator(
        hass=hass,
        api_client=mock_api_client,
        site_id=TEST_SITE_ID,
        site_name=TEST_SITE_NAME,
    )

    await coordinator.async_refresh()
    assert coordinator.last_update_success is True

    fw = coordinator.data["firmware_info"]
    # The failing device should not be present.
    assert "AA-BB-CC-DD-EE-01" not in fw
    # The others should have data.
    assert fw["AA-BB-CC-DD-EE-02"]["lastFwVer"] == "2.0.0"
    assert fw["AA-BB-CC-DD-EE-03"]["lastFwVer"] == "2.0.0"


# ---------------------------------------------------------------------------
# Upgrade polling boost
# ---------------------------------------------------------------------------


async def test_site_coordinator_boosts_polling_during_upgrade(
    hass: HomeAssistant, mock_api_client: MagicMock
) -> None:
    """Test that polling interval is reduced when a device is upgrading."""
    # Start with a device that has detailStatus=12 (Upgrading).
    upgrading_switch = {**SAMPLE_DEVICE_SWITCH, "detailStatus": 12}
    mock_api_client.get_devices = AsyncMock(
        return_value=[SAMPLE_DEVICE_AP, upgrading_switch]
    )

    coordinator = OmadaSiteCoordinator(
        hass=hass,
        api_client=mock_api_client,
        site_id=TEST_SITE_ID,
        site_name=TEST_SITE_NAME,
    )

    await coordinator.async_refresh()
    assert coordinator.last_update_success is True
    assert coordinator.update_interval == timedelta(seconds=UPGRADE_POLL_INTERVAL)
    assert coordinator._upgrade_active is True  # noqa: SLF001


async def test_site_coordinator_restores_polling_after_upgrade(
    hass: HomeAssistant, mock_api_client: MagicMock
) -> None:
    """Test that polling interval is restored after cooldown finishes."""
    # First refresh: device is upgrading.
    upgrading_switch = {**SAMPLE_DEVICE_SWITCH, "detailStatus": 12}
    mock_api_client.get_devices = AsyncMock(
        return_value=[SAMPLE_DEVICE_AP, upgrading_switch]
    )

    coordinator = OmadaSiteCoordinator(
        hass=hass,
        api_client=mock_api_client,
        site_id=TEST_SITE_ID,
        site_name=TEST_SITE_NAME,
        scan_interval=60,
    )

    await coordinator.async_refresh()
    assert coordinator.update_interval == timedelta(seconds=UPGRADE_POLL_INTERVAL)

    # Second refresh: device is back to Connected (14) — cooldown starts.
    normal_switch = {**SAMPLE_DEVICE_SWITCH, "detailStatus": 14}
    mock_api_client.get_devices = AsyncMock(
        return_value=[SAMPLE_DEVICE_AP, normal_switch]
    )

    await coordinator.async_refresh()
    # Still fast polling during cooldown.
    assert coordinator.update_interval == timedelta(seconds=UPGRADE_POLL_INTERVAL)
    assert coordinator._upgrade_active is True  # noqa: SLF001
    assert coordinator._upgrade_cooldown_remaining == UPGRADE_COOLDOWN_POLLS  # noqa: SLF001

    # Subsequent refreshes decrement cooldown.
    for _i in range(UPGRADE_COOLDOWN_POLLS):
        await coordinator.async_refresh()

    # Cooldown finished — normal polling restored.
    assert coordinator.update_interval == timedelta(seconds=60)
    assert coordinator._upgrade_active is False  # noqa: SLF001


async def test_site_coordinator_firmware_cache_reset_after_upgrade(
    hass: HomeAssistant, mock_api_client: MagicMock
) -> None:
    """Test that stale firmware info is cleared when upgrade completes."""
    mock_api_client.get_firmware_info = AsyncMock(
        return_value={"curFwVer": "1.0.0", "lastFwVer": "1.1.0", "fwReleaseLog": "Fix"}
    )

    # First refresh: device upgrading, firmware info fetched (needUpgrade=True).
    upgrading_switch = {**SAMPLE_DEVICE_SWITCH, "detailStatus": 12}
    mock_api_client.get_devices = AsyncMock(
        return_value=[SAMPLE_DEVICE_AP, upgrading_switch]
    )

    coordinator = OmadaSiteCoordinator(
        hass=hass,
        api_client=mock_api_client,
        site_id=TEST_SITE_ID,
        site_name=TEST_SITE_NAME,
    )

    await coordinator.async_refresh()
    first_call_count = mock_api_client.get_firmware_info.call_count
    assert first_call_count == 2  # 2 devices with needUpgrade=True

    # Second refresh: still upgrading — firmware cache NOT bypassed.
    await coordinator.async_refresh()
    assert mock_api_client.get_firmware_info.call_count == first_call_count

    # Third refresh: upgrade finished — needUpgrade is now False for the switch.
    # Cooldown starts, cache reset takes effect in the same cycle.
    normal_switch = {
        **SAMPLE_DEVICE_SWITCH,
        "detailStatus": 14,
        "needUpgrade": False,
    }
    mock_api_client.get_devices = AsyncMock(
        return_value=[SAMPLE_DEVICE_AP, normal_switch]
    )
    await coordinator.async_refresh()
    # Firmware info re-fetched in the SAME cycle due to order swap.
    # Only the AP still needs upgrade, so only 1 new fetch.
    assert mock_api_client.get_firmware_info.call_count > first_call_count
    # The switch's stale firmware_info should be cleared.
    sw_mac = SAMPLE_DEVICE_SWITCH["mac"]
    assert sw_mac not in coordinator.data["firmware_info"]


async def test_site_coordinator_no_boost_without_upgrade(
    hass: HomeAssistant, mock_api_client: MagicMock
) -> None:
    """Test that normal polling is kept when no device is upgrading."""
    coordinator = OmadaSiteCoordinator(
        hass=hass,
        api_client=mock_api_client,
        site_id=TEST_SITE_ID,
        site_name=TEST_SITE_NAME,
        scan_interval=60,
    )

    await coordinator.async_refresh()
    assert coordinator.update_interval == timedelta(seconds=60)
    assert coordinator._upgrade_active is False  # noqa: SLF001


async def test_start_upgrade_polling_activates_fast_polling(
    hass: HomeAssistant, mock_api_client: MagicMock
) -> None:
    """Test start_upgrade_polling switches to fast interval immediately."""
    coordinator = OmadaSiteCoordinator(
        hass=hass,
        api_client=mock_api_client,
        site_id=TEST_SITE_ID,
        site_name=TEST_SITE_NAME,
        scan_interval=60,
    )

    assert coordinator._upgrade_active is False  # noqa: SLF001
    assert coordinator.update_interval == timedelta(seconds=60)

    coordinator.start_upgrade_polling()

    assert coordinator._upgrade_active is True  # noqa: SLF001
    assert coordinator.update_interval == timedelta(seconds=UPGRADE_POLL_INTERVAL)


async def test_start_upgrade_polling_idempotent(
    hass: HomeAssistant, mock_api_client: MagicMock
) -> None:
    """Test start_upgrade_polling is a no-op when already active."""
    coordinator = OmadaSiteCoordinator(
        hass=hass,
        api_client=mock_api_client,
        site_id=TEST_SITE_ID,
        site_name=TEST_SITE_NAME,
        scan_interval=60,
    )

    coordinator.start_upgrade_polling()
    assert coordinator._upgrade_active is True  # noqa: SLF001

    # Calling again should not error or change state.
    coordinator.start_upgrade_polling()
    assert coordinator._upgrade_active is True  # noqa: SLF001
    assert coordinator.update_interval == timedelta(seconds=UPGRADE_POLL_INTERVAL)


async def test_upgrade_cooldown_keeps_fast_polling(
    hass: HomeAssistant, mock_api_client: MagicMock
) -> None:
    """Test that fast polling continues during the cooldown period."""
    upgrading_switch = {**SAMPLE_DEVICE_SWITCH, "detailStatus": 12}
    mock_api_client.get_devices = AsyncMock(
        return_value=[SAMPLE_DEVICE_AP, upgrading_switch]
    )

    coordinator = OmadaSiteCoordinator(
        hass=hass,
        api_client=mock_api_client,
        site_id=TEST_SITE_ID,
        site_name=TEST_SITE_NAME,
        scan_interval=60,
    )

    await coordinator.async_refresh()
    assert coordinator._upgrade_active is True  # noqa: SLF001

    # Upgrade finishes — cooldown starts.
    normal_switch = {**SAMPLE_DEVICE_SWITCH, "detailStatus": 14}
    mock_api_client.get_devices = AsyncMock(
        return_value=[SAMPLE_DEVICE_AP, normal_switch]
    )

    await coordinator.async_refresh()
    # Fast polling persists during cooldown.
    assert coordinator.update_interval == timedelta(seconds=UPGRADE_POLL_INTERVAL)
    assert coordinator._upgrade_cooldown_remaining == UPGRADE_COOLDOWN_POLLS  # noqa: SLF001

    # Each subsequent poll decrements cooldown but keeps fast interval.
    await coordinator.async_refresh()
    assert coordinator.update_interval == timedelta(seconds=UPGRADE_POLL_INTERVAL)
    assert coordinator._upgrade_cooldown_remaining == UPGRADE_COOLDOWN_POLLS - 1  # noqa: SLF001


async def test_upgrade_cooldown_resets_if_upgrade_resumes(
    hass: HomeAssistant, mock_api_client: MagicMock
) -> None:
    """Test that a new upgrade during cooldown resets the cooldown counter."""
    upgrading_switch = {**SAMPLE_DEVICE_SWITCH, "detailStatus": 12}
    mock_api_client.get_devices = AsyncMock(
        return_value=[SAMPLE_DEVICE_AP, upgrading_switch]
    )

    coordinator = OmadaSiteCoordinator(
        hass=hass,
        api_client=mock_api_client,
        site_id=TEST_SITE_ID,
        site_name=TEST_SITE_NAME,
        scan_interval=60,
    )

    await coordinator.async_refresh()

    # Upgrade finishes — cooldown starts.
    normal_switch = {**SAMPLE_DEVICE_SWITCH, "detailStatus": 14}
    mock_api_client.get_devices = AsyncMock(
        return_value=[SAMPLE_DEVICE_AP, normal_switch]
    )
    await coordinator.async_refresh()
    assert coordinator._upgrade_cooldown_remaining == UPGRADE_COOLDOWN_POLLS  # noqa: SLF001

    # Another device starts upgrading during cooldown.
    mock_api_client.get_devices = AsyncMock(
        return_value=[SAMPLE_DEVICE_AP, upgrading_switch]
    )
    await coordinator.async_refresh()
    # Cooldown reset, upgrade active.
    assert coordinator._upgrade_cooldown_remaining == 0  # noqa: SLF001
    assert coordinator._upgrade_active is True  # noqa: SLF001


# ---------------------------------------------------------------------------
# OmadaClientCoordinator
# ---------------------------------------------------------------------------


async def test_client_coordinator_filters_selected_clients(
    hass: HomeAssistant, mock_api_client: MagicMock
) -> None:
    """Test that only selected clients are returned."""
    coordinator = OmadaClientCoordinator(
        hass=hass,
        api_client=mock_api_client,
        site_id=TEST_SITE_ID,
        site_name=TEST_SITE_NAME,
        selected_client_macs=["11-22-33-44-55-AA"],
    )

    await coordinator.async_refresh()
    assert coordinator.last_update_success is True

    data = coordinator.data
    assert "11-22-33-44-55-AA" in data
    assert "11-22-33-44-55-BB" not in data
    assert data["11-22-33-44-55-AA"]["name"] == "Phone"


async def test_client_coordinator_handles_all_selected(
    hass: HomeAssistant, mock_api_client: MagicMock
) -> None:
    """Test with all clients selected."""
    coordinator = OmadaClientCoordinator(
        hass=hass,
        api_client=mock_api_client,
        site_id=TEST_SITE_ID,
        site_name=TEST_SITE_NAME,
        selected_client_macs=["11-22-33-44-55-AA", "11-22-33-44-55-BB"],
    )

    await coordinator.async_refresh()
    assert coordinator.last_update_success is True
    assert len(coordinator.data) == 2


async def test_client_coordinator_selected_client_not_online(
    hass: HomeAssistant, mock_api_client: MagicMock
) -> None:
    """Test that missing (offline) selected clients are simply absent from data."""
    mock_api_client.get_clients = AsyncMock(
        return_value={"data": [], "totalRows": 0, "currentPage": 1}
    )

    coordinator = OmadaClientCoordinator(
        hass=hass,
        api_client=mock_api_client,
        site_id=TEST_SITE_ID,
        site_name=TEST_SITE_NAME,
        selected_client_macs=["11-22-33-44-55-AA"],
    )

    await coordinator.async_refresh()
    assert coordinator.last_update_success is True
    assert len(coordinator.data) == 0


async def test_client_coordinator_api_failure(
    hass: HomeAssistant, mock_api_client: MagicMock
) -> None:
    """Test that API failure raises UpdateFailed."""
    mock_api_client.get_clients = AsyncMock(
        side_effect=OmadaApiError("API unreachable")
    )

    coordinator = OmadaClientCoordinator(
        hass=hass,
        api_client=mock_api_client,
        site_id=TEST_SITE_ID,
        site_name=TEST_SITE_NAME,
        selected_client_macs=["11-22-33-44-55-AA"],
    )

    await coordinator.async_refresh()
    assert coordinator.last_update_success is False


async def test_client_coordinator_blocked_client_remains_in_data(
    hass: HomeAssistant, mock_api_client: MagicMock
) -> None:
    """Test that blocked clients remain in coordinator data (scope=0).

    This ensures the switch entity stays available when a client is blocked,
    allowing users to unblock via the UI (GitHub issue #4).
    """
    blocked_client = dict(SAMPLE_CLIENT_WIRELESS)
    blocked_client["blocked"] = True
    blocked_client["active"] = False

    mock_api_client.get_clients = AsyncMock(
        return_value={
            "data": [blocked_client],
            "totalRows": 1,
            "currentPage": 1,
        }
    )

    coordinator = OmadaClientCoordinator(
        hass=hass,
        api_client=mock_api_client,
        site_id=TEST_SITE_ID,
        site_name=TEST_SITE_NAME,
        selected_client_macs=["11-22-33-44-55-AA"],
    )

    await coordinator.async_refresh()
    assert coordinator.last_update_success is True
    # Blocked client should still be present in data.
    assert "11-22-33-44-55-AA" in coordinator.data
    assert coordinator.data["11-22-33-44-55-AA"]["blocked"] is True


async def test_client_coordinator_uses_scope_all(
    hass: HomeAssistant, mock_api_client: MagicMock
) -> None:
    """Test that coordinator fetches all clients (scope=0), not just online."""
    coordinator = OmadaClientCoordinator(
        hass=hass,
        api_client=mock_api_client,
        site_id=TEST_SITE_ID,
        site_name=TEST_SITE_NAME,
        selected_client_macs=["11-22-33-44-55-AA"],
    )

    await coordinator.async_refresh()

    # Verify scope=0 was passed to get_clients.
    mock_api_client.get_clients.assert_called_once_with(
        TEST_SITE_ID, page=1, page_size=1000, scope=0
    )


# ---------------------------------------------------------------------------
# OmadaAppTrafficCoordinator
# ---------------------------------------------------------------------------


async def test_app_traffic_coordinator_fetches_data(
    hass: HomeAssistant, mock_api_client: MagicMock
) -> None:
    """Test that app traffic coordinator fetches and filters data."""
    mock_api_client.get_client_app_traffic = AsyncMock(
        return_value=[
            {
                "applicationId": 100,
                "applicationName": "Netflix",
                "upload": 1024,
                "download": 2048,
                "traffic": 3072,
            },
            {
                "applicationId": 200,
                "applicationName": "YouTube",
                "upload": 512,
                "download": 1024,
                "traffic": 1536,
            },
            {
                "applicationId": 999,
                "applicationName": "Unselected App",
                "upload": 0,
                "download": 0,
                "traffic": 0,
            },
        ]
    )

    coordinator = OmadaAppTrafficCoordinator(
        hass=hass,
        api_client=mock_api_client,
        site_id=TEST_SITE_ID,
        site_name=TEST_SITE_NAME,
        selected_client_macs=["11-22-33-44-55-AA"],
        selected_app_ids=["100", "200"],
    )

    await coordinator.async_refresh()
    assert coordinator.last_update_success is True

    data = coordinator.data
    assert "11-22-33-44-55-AA" in data
    client_apps = data["11-22-33-44-55-AA"]
    assert "100" in client_apps
    assert "200" in client_apps
    assert "999" not in client_apps  # Not selected
    assert client_apps["100"]["download"] == 2048


async def test_app_traffic_coordinator_per_client_error_resilience(
    hass: HomeAssistant, mock_api_client: MagicMock
) -> None:
    """Test that one client failing doesn't affect others."""
    call_count = 0

    async def _side_effect(site_id, mac, start, end):
        nonlocal call_count
        call_count += 1
        if mac == "11-22-33-44-55-AA":
            raise OmadaApiError("Timeout for this client")
        return [
            {
                "applicationId": 100,
                "applicationName": "Netflix",
                "upload": 100,
                "download": 200,
                "traffic": 300,
            },
        ]

    mock_api_client.get_client_app_traffic = AsyncMock(side_effect=_side_effect)

    coordinator = OmadaAppTrafficCoordinator(
        hass=hass,
        api_client=mock_api_client,
        site_id=TEST_SITE_ID,
        site_name=TEST_SITE_NAME,
        selected_client_macs=["11-22-33-44-55-AA", "11-22-33-44-55-BB"],
        selected_app_ids=["100"],
    )

    await coordinator.async_refresh()
    assert coordinator.last_update_success is True

    # First client failed, second succeeded.
    data = coordinator.data
    assert "11-22-33-44-55-AA" not in data
    assert "11-22-33-44-55-BB" in data


async def test_app_traffic_coordinator_midnight_reset(
    hass: HomeAssistant, mock_api_client: MagicMock, freezer
) -> None:
    """Test that the coordinator resets its tracking at midnight."""
    mock_api_client.get_client_app_traffic = AsyncMock(return_value=[])

    coordinator = OmadaAppTrafficCoordinator(
        hass=hass,
        api_client=mock_api_client,
        site_id=TEST_SITE_ID,
        site_name=TEST_SITE_NAME,
        selected_client_macs=["11-22-33-44-55-AA"],
        selected_app_ids=["100"],
    )

    # First fetch sets _last_reset.
    await coordinator.async_refresh()
    assert coordinator._last_reset is not None  # noqa: SLF001
    first_reset = coordinator._last_reset  # noqa: SLF001

    # Advance time by 1 day.
    freezer.move_to(dt_util.now() + timedelta(days=1, hours=1))

    await coordinator.async_refresh()
    second_reset = coordinator._last_reset  # noqa: SLF001
    assert second_reset > first_reset


async def test_app_traffic_coordinator_no_selected_apps_returns_empty(
    hass: HomeAssistant, mock_api_client: MagicMock
) -> None:
    """Test coordinator with no apps returns empty data for each client."""
    mock_api_client.get_client_app_traffic = AsyncMock(
        return_value=[
            {
                "applicationId": 100,
                "applicationName": "Netflix",
                "upload": 1024,
                "download": 2048,
                "traffic": 3072,
            },
        ]
    )

    coordinator = OmadaAppTrafficCoordinator(
        hass=hass,
        api_client=mock_api_client,
        site_id=TEST_SITE_ID,
        site_name=TEST_SITE_NAME,
        selected_client_macs=["11-22-33-44-55-AA"],
        selected_app_ids=[],  # No apps selected
    )

    await coordinator.async_refresh()
    assert coordinator.last_update_success is True
    # No matching apps → client not in data.
    assert len(coordinator.data) == 0


# ---------------------------------------------------------------------------
# Configurable scan intervals
# ---------------------------------------------------------------------------


async def test_site_coordinator_default_interval(
    hass: HomeAssistant, mock_api_client: MagicMock
) -> None:
    """Test site coordinator uses default 60s interval when none specified."""
    coordinator = OmadaSiteCoordinator(
        hass=hass,
        api_client=mock_api_client,
        site_id=TEST_SITE_ID,
        site_name=TEST_SITE_NAME,
    )
    assert coordinator.update_interval == timedelta(seconds=60)


async def test_site_coordinator_custom_interval(
    hass: HomeAssistant, mock_api_client: MagicMock
) -> None:
    """Test site coordinator uses custom scan interval."""
    coordinator = OmadaSiteCoordinator(
        hass=hass,
        api_client=mock_api_client,
        site_id=TEST_SITE_ID,
        site_name=TEST_SITE_NAME,
        scan_interval=120,
    )
    assert coordinator.update_interval == timedelta(seconds=120)


async def test_client_coordinator_custom_interval(
    hass: HomeAssistant, mock_api_client: MagicMock
) -> None:
    """Test client coordinator uses custom scan interval."""
    coordinator = OmadaClientCoordinator(
        hass=hass,
        api_client=mock_api_client,
        site_id=TEST_SITE_ID,
        site_name=TEST_SITE_NAME,
        selected_client_macs=[],
        scan_interval=15,
    )
    assert coordinator.update_interval == timedelta(seconds=15)


async def test_app_traffic_coordinator_custom_interval(
    hass: HomeAssistant, mock_api_client: MagicMock
) -> None:
    """Test app traffic coordinator uses custom scan interval."""
    coordinator = OmadaAppTrafficCoordinator(
        hass=hass,
        api_client=mock_api_client,
        site_id=TEST_SITE_ID,
        site_name=TEST_SITE_NAME,
        selected_client_macs=[],
        selected_app_ids=[],
        scan_interval=600,
    )
    assert coordinator.update_interval == timedelta(seconds=600)
