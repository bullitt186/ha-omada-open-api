"""Tests that VPN entity translations and icons exist.

Fixtures use real S2S stats payload keys (see PR #27 WP0 schema capture).
"""

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


def test_vpn_connected_peers_sensor_translation(strings: dict) -> None:
    """vpn_connected_peers sensor has a translation entry."""
    entry = strings["entity"]["sensor"]["vpn_connected_peers"]
    assert "name" in entry


def test_vpn_disconnected_peers_sensor_translation(strings: dict) -> None:
    """vpn_disconnected_peers sensor has a translation entry."""
    entry = strings["entity"]["sensor"]["vpn_disconnected_peers"]
    assert "name" in entry


def test_vpn_total_remote_peers_sensor_translation(strings: dict) -> None:
    """vpn_total_remote_peers sensor has a translation entry."""
    entry = strings["entity"]["sensor"]["vpn_total_remote_peers"]
    assert "name" in entry


def test_vpn_listen_port_sensor_translation(strings: dict) -> None:
    """vpn_listen_port sensor has a translation entry."""
    entry = strings["entity"]["sensor"]["vpn_listen_port"]
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


def test_vpn_connected_peers_translation_has_tunnel_placeholder(strings: dict) -> None:
    """vpn_connected_peers translation uses {tunnel_name} placeholder."""
    name = strings["entity"]["sensor"]["vpn_connected_peers"]["name"]
    assert "{tunnel_name}" in name


def test_vpn_connected_translation_has_tunnel_placeholder(strings: dict) -> None:
    """vpn_connected translation uses {tunnel_name} placeholder."""
    name = strings["entity"]["binary_sensor"]["vpn_connected"]["name"]
    assert "{tunnel_name}" in name


# --- Icons ---


def test_vpn_connected_peers_icon(icons: dict) -> None:
    """vpn_connected_peers has an icon entry."""
    assert (
        "mdi:account-multiple-check"
        in icons["entity"]["sensor"]["vpn_connected_peers"]["default"]
    )


def test_vpn_disconnected_peers_icon(icons: dict) -> None:
    """vpn_disconnected_peers has an icon entry."""
    assert (
        "mdi:account-multiple-remove"
        in icons["entity"]["sensor"]["vpn_disconnected_peers"]["default"]
    )


def test_vpn_total_remote_peers_icon(icons: dict) -> None:
    """vpn_total_remote_peers has an icon entry."""
    assert (
        "mdi:account-multiple"
        in icons["entity"]["sensor"]["vpn_total_remote_peers"]["default"]
    )


def test_vpn_listen_port_icon(icons: dict) -> None:
    """vpn_listen_port has an icon entry."""
    assert (
        "mdi:server-network"
        in icons["entity"]["sensor"]["vpn_listen_port"]["default"]
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
        "vpn_connected_peers",
        "vpn_disconnected_peers",
        "vpn_total_remote_peers",
        "vpn_listen_port",
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
