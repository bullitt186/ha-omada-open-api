"""Tests for configurable disconnect timeout for client device trackers (Issue #10)."""

from __future__ import annotations

import datetime as dt
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock

from custom_components.omada_open_api.coordinator import OmadaClientCoordinator
from custom_components.omada_open_api.device_tracker import OmadaClientTracker

from .conftest import TEST_SITE_ID, TEST_SITE_NAME

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

CLIENT_MAC = "AA-BB-CC-DD-EE-01"
CLIENT_DATA_ACTIVE = {
    "mac": CLIENT_MAC,
    "name": "Phone",
    "active": True,
    "wireless": True,
    "ip": "192.168.1.100",
}
CLIENT_DATA_INACTIVE = {
    **CLIENT_DATA_ACTIVE,
    "active": False,
}


def _make_coordinator(
    hass: HomeAssistant,
    data: dict,
    disconnect_timeout: int = 0,
) -> OmadaClientCoordinator:
    """Build coordinator with optional disconnect timeout."""
    coord = OmadaClientCoordinator(
        hass=hass,
        api_client=MagicMock(),
        site_id=TEST_SITE_ID,
        site_name=TEST_SITE_NAME,
        selected_client_macs=[CLIENT_MAC],
        disconnect_timeout=disconnect_timeout,
    )
    coord.data = data
    return coord


def _make_tracker(
    hass: HomeAssistant,
    data: dict,
    disconnect_timeout: int = 0,
) -> OmadaClientTracker:
    """Build OmadaClientTracker with given coordinator data."""
    coord = _make_coordinator(hass, data, disconnect_timeout)
    return OmadaClientTracker(coordinator=coord, client_mac=CLIENT_MAC)


# ---------------------------------------------------------------------------
# OmadaClientTracker — immediate disconnect (timeout=0, default behavior)
# ---------------------------------------------------------------------------


async def test_tracker_connected_when_active(hass: HomeAssistant) -> None:
    """Tracker reports connected when client is active."""
    tracker = _make_tracker(
        hass, {CLIENT_MAC: CLIENT_DATA_ACTIVE}, disconnect_timeout=0
    )
    assert tracker.is_connected is True


async def test_tracker_disconnected_immediately_with_timeout_zero(
    hass: HomeAssistant,
) -> None:
    """With timeout=0, tracker disconnects immediately when client goes inactive."""
    tracker = _make_tracker(
        hass, {CLIENT_MAC: CLIENT_DATA_INACTIVE}, disconnect_timeout=0
    )
    assert tracker.is_connected is False


async def test_tracker_disconnected_when_absent_from_coordinator(
    hass: HomeAssistant,
) -> None:
    """Tracker is disconnected when MAC absent from coordinator data."""
    tracker = _make_tracker(hass, {}, disconnect_timeout=0)
    assert tracker.is_connected is False


# ---------------------------------------------------------------------------
# OmadaClientTracker — grace period (timeout > 0)
# ---------------------------------------------------------------------------


async def test_tracker_stays_connected_during_grace_period(
    hass: HomeAssistant,
) -> None:
    """Tracker stays connected during grace period after client goes absent."""
    coord = _make_coordinator(
        hass, {CLIENT_MAC: CLIENT_DATA_ACTIVE}, disconnect_timeout=5
    )

    # Seed last_seen to 30 seconds ago (within 5-minute grace)
    now = dt.datetime.now(dt.UTC)
    coord.last_seen[CLIENT_MAC] = now - dt.timedelta(seconds=30)

    # Remove client from coordinator data (client disappeared from API)
    coord.data = {}

    tracker = OmadaClientTracker(coordinator=coord, client_mac=CLIENT_MAC)
    assert tracker.is_connected is True


async def test_tracker_disconnects_after_timeout_expires(hass: HomeAssistant) -> None:
    """Tracker disconnects when grace period has fully elapsed."""
    coord = _make_coordinator(hass, {}, disconnect_timeout=5)

    # Seed last_seen to 6 minutes ago (beyond 5-minute grace)
    now = dt.datetime.now(dt.UTC)
    coord.last_seen[CLIENT_MAC] = now - dt.timedelta(minutes=6)

    tracker = OmadaClientTracker(coordinator=coord, client_mac=CLIENT_MAC)
    assert tracker.is_connected is False


async def test_tracker_reconnects_immediately_within_grace(hass: HomeAssistant) -> None:
    """When client reappears within grace period, tracker returns to connected."""
    coord = _make_coordinator(
        hass, {CLIENT_MAC: CLIENT_DATA_ACTIVE}, disconnect_timeout=5
    )
    coord.last_seen[CLIENT_MAC] = dt.datetime.now(dt.UTC) - dt.timedelta(seconds=30)

    tracker = OmadaClientTracker(coordinator=coord, client_mac=CLIENT_MAC)
    assert tracker.is_connected is True


async def test_two_clients_independent_grace_periods(hass: HomeAssistant) -> None:
    """Each client's grace period is tracked independently."""
    client2_mac = "AA-BB-CC-DD-EE-02"
    coord = OmadaClientCoordinator(
        hass=hass,
        api_client=MagicMock(),
        site_id=TEST_SITE_ID,
        site_name=TEST_SITE_NAME,
        selected_client_macs=[CLIENT_MAC, client2_mac],
        disconnect_timeout=5,
    )

    now = dt.datetime.now(dt.UTC)
    # Client 1 last seen 30s ago (still within grace)
    coord.last_seen[CLIENT_MAC] = now - dt.timedelta(seconds=30)
    # Client 2 last seen 10 minutes ago (beyond grace)
    coord.last_seen[client2_mac] = now - dt.timedelta(minutes=10)

    # Both absent from coordinator data
    coord.data = {}

    tracker1 = OmadaClientTracker(coordinator=coord, client_mac=CLIENT_MAC)
    tracker2 = OmadaClientTracker(coordinator=coord, client_mac=client2_mac)

    assert tracker1.is_connected is True
    assert tracker2.is_connected is False


# ---------------------------------------------------------------------------
# OmadaClientCoordinator — disconnect_timeout parameter
# ---------------------------------------------------------------------------


def test_coordinator_accepts_disconnect_timeout_parameter(hass: HomeAssistant) -> None:
    """OmadaClientCoordinator accepts disconnect_timeout parameter."""
    coord = OmadaClientCoordinator(
        hass=hass,
        api_client=MagicMock(),
        site_id=TEST_SITE_ID,
        site_name=TEST_SITE_NAME,
        selected_client_macs=[CLIENT_MAC],
        disconnect_timeout=3,
    )
    assert coord.disconnect_timeout == 3


def test_coordinator_defaults_to_zero_disconnect_timeout(hass: HomeAssistant) -> None:
    """OmadaClientCoordinator defaults disconnect_timeout to 0."""
    coord = OmadaClientCoordinator(
        hass=hass,
        api_client=MagicMock(),
        site_id=TEST_SITE_ID,
        site_name=TEST_SITE_NAME,
        selected_client_macs=[CLIENT_MAC],
    )
    assert coord.disconnect_timeout == 0


async def test_coordinator_updates_last_seen_on_data_fetch(hass: HomeAssistant) -> None:
    """Coordinator updates _last_seen timestamps for active clients on each update."""

    mock_api = MagicMock()
    mock_api.get_clients = AsyncMock(
        return_value={
            "data": [
                {
                    "mac": CLIENT_MAC,
                    "name": "Phone",
                    "active": True,
                    "wireless": True,
                }
            ],
            "totalRows": 1,
        }
    )

    coord = OmadaClientCoordinator(
        hass=hass,
        api_client=mock_api,
        site_id=TEST_SITE_ID,
        site_name=TEST_SITE_NAME,
        selected_client_macs=[CLIENT_MAC],
        disconnect_timeout=5,
    )

    before = dt.datetime.now(dt.UTC)
    await coord._async_update_data()
    after = dt.datetime.now(dt.UTC)

    assert CLIENT_MAC in coord.last_seen
    last_seen = coord.last_seen[CLIENT_MAC]
    assert before <= last_seen <= after
