"""Tests that VPN entity translations and icons exist."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

COMP_DIR = (
    Path(__file__).resolve().parent.parent / "custom_components" / "omada_open_api"
)


@pytest.fixture
def strings() -> dict:
    """Load strings.json."""
    return json.loads((COMP_DIR / "strings.json").read_text())


@pytest.fixture
def translations_en() -> dict:
    """Load translations/en.json."""
    return json.loads((COMP_DIR / "translations" / "en.json").read_text())


@pytest.fixture
def icons() -> dict:
    """Load icons.json."""
    return json.loads((COMP_DIR / "icons.json").read_text())


# --- Sensor translations ---


def test_vpn_uptime_sensor_translation(strings: dict) -> None:
    """vpn_uptime sensor has a translation entry."""
    entry = strings["entity"]["sensor"]["vpn_uptime"]
    assert "name" in entry


def test_vpn_download_sensor_translation(strings: dict) -> None:
    """vpn_download sensor has a translation entry."""
    entry = strings["entity"]["sensor"]["vpn_download"]
    assert "name" in entry


def test_vpn_upload_sensor_translation(strings: dict) -> None:
    """vpn_upload sensor has a translation entry."""
    entry = strings["entity"]["sensor"]["vpn_upload"]
    assert "name" in entry


def test_vpn_remote_peer_sensor_translation(strings: dict) -> None:
    """vpn_remote_peer sensor has a translation entry."""
    entry = strings["entity"]["sensor"]["vpn_remote_peer"]
    assert "name" in entry


# --- Binary sensor translations ---


def test_vpn_connected_binary_sensor_translation(strings: dict) -> None:
    """vpn_connected binary sensor has a translation entry."""
    entry = strings["entity"]["binary_sensor"]["vpn_connected"]
    assert "name" in entry
    assert "state" in entry


def test_vpn_connected_binary_sensor_states(strings: dict) -> None:
    """vpn_connected binary sensor has on/off state translations."""
    state = strings["entity"]["binary_sensor"]["vpn_connected"]["state"]
    assert "on" in state
    assert "off" in state


# --- Translation placeholders ---


def test_vpn_uptime_translation_has_tunnel_placeholder(strings: dict) -> None:
    """vpn_uptime translation uses {tunnel_name} placeholder."""
    name = strings["entity"]["sensor"]["vpn_uptime"]["name"]
    assert "{tunnel_name}" in name


def test_vpn_connected_translation_has_tunnel_placeholder(strings: dict) -> None:
    """vpn_connected translation uses {tunnel_name} placeholder."""
    name = strings["entity"]["binary_sensor"]["vpn_connected"]["name"]
    assert "{tunnel_name}" in name


# --- Icons ---


def test_vpn_uptime_icon(icons: dict) -> None:
    """vpn_uptime has an icon entry."""
    assert "mdi:clock-outline" in icons["entity"]["sensor"]["vpn_uptime"]["default"]


def test_vpn_download_icon(icons: dict) -> None:
    """vpn_download has an icon entry."""
    assert "mdi:download" in icons["entity"]["sensor"]["vpn_download"]["default"]


def test_vpn_upload_icon(icons: dict) -> None:
    """vpn_upload has an icon entry."""
    assert "mdi:upload" in icons["entity"]["sensor"]["vpn_upload"]["default"]


def test_vpn_remote_peer_icon(icons: dict) -> None:
    """vpn_remote_peer has an icon entry."""
    assert (
        "mdi:server-network" in icons["entity"]["sensor"]["vpn_remote_peer"]["default"]
    )


def test_vpn_connected_icon(icons: dict) -> None:
    """vpn_connected has icon entries with state overrides."""
    entry = icons["entity"]["binary_sensor"]["vpn_connected"]
    assert entry["default"] == "mdi:vpn"
    assert "state" in entry
    assert "off" in entry["state"]
    assert entry["state"]["off"] == "mdi:vpn-off"


# --- Translation / en.json sync ---


def test_strings_and_translations_in_sync() -> None:
    """strings.json and translations/en.json have the same VPN entity keys."""
    strings = json.loads((COMP_DIR / "strings.json").read_text())
    translations = json.loads((COMP_DIR / "translations" / "en.json").read_text())

    vpn_sensor_keys = [
        "vpn_uptime",
        "vpn_download",
        "vpn_upload",
        "vpn_remote_peer",
    ]
    for key in vpn_sensor_keys:
        assert key in strings["entity"]["sensor"], f"Missing {key} in strings.json"
        assert key in translations["entity"]["sensor"], f"Missing {key} in en.json"

    vpn_binary_keys = ["vpn_connected"]
    for key in vpn_binary_keys:
        assert key in strings["entity"]["binary_sensor"], (
            f"Missing {key} in strings.json"
        )
        assert key in translations["entity"]["binary_sensor"], (
            f"Missing {key} in en.json"
        )
