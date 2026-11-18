"""Tests for the WAN/VPN logic shared by the sensor and binary sensor platforms.

Unique IDs must keep the formats existing installations registered, so they
are spelled out literally here. Payload fields follow the Omada VPN stats
endpoints (``vpnId``/``id``, ``name``, ``peers``) and the gateway WAN status.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING, Any
from unittest.mock import MagicMock

from homeassistant.helpers import device_registry as dr
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.omada_open_api.binary_sensor import (
    VPN_BINARY_SENSORS,
    VPN_PEER_BINARY_SENSORS,
    WAN_PORT_BINARY_SENSORS,
    OmadaVpnBinarySensor,
    OmadaVpnPeerBinarySensor,
    OmadaWanBinarySensor,
    _build_vpn_binary_sensors,
    _build_vpn_peer_binary_sensors,
)
from custom_components.omada_open_api.const import DOMAIN
from custom_components.omada_open_api.entity import build_linked_infra_device_info
from custom_components.omada_open_api.gateway_entity import (
    new_vpn_peer_entities,
    new_vpn_tunnel_entities,
    new_wan_port_entities,
    vpn_peer_unique_id,
    vpn_tunnel_unique_id,
    wan_port_unique_id,
)
from custom_components.omada_open_api.sensor import (
    VPN_CLIENT_SENSORS,
    VPN_PEER_SENSORS,
    VPN_SENSORS,
    WAN_PORT_SENSORS,
    OmadaVpnPeerSensor,
    OmadaVpnSensor,
    OmadaWanSensor,
    _build_vpn_peer_sensors,
    _build_vpn_sensors,
    _build_wan_sensors,
)

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

GW = "AA-BB-CC-DD-EE-03"
SWITCH = "AA-BB-CC-DD-EE-02"
DEVICES = {GW: {"type": "gateway"}, SWITCH: {"type": "switch"}}
TUNNEL = {
    "id": "row-1",
    "vpnId": "cfg-1",
    "name": "wg0",
    "status": 1,
    "peers": [{"id": 7, "name": "office", "status": 1}],
}
CLIENT_TUNNEL = {"id": "row-2", "name": "to-hq", "status": 0}


def _coordinator(data: dict[str, Any], *, ok: bool = True) -> MagicMock:
    coordinator = MagicMock()
    coordinator.data = data
    coordinator.last_update_success = ok
    return coordinator


def _desc(key: str) -> SimpleNamespace:
    return SimpleNamespace(key=key)


def test_unique_id_formats() -> None:
    """The unique ID formats of existing installations are kept."""
    assert wan_port_unique_id(GW, 1, "wan_status") == f"{GW}_wan1_wan_status"
    assert (
        vpn_tunnel_unique_id(GW, "s2s", "cfg-1", "vpn_connected")
        == f"{GW}_vpn_s2s_cfg-1_vpn_connected"
    )
    assert (
        vpn_peer_unique_id(GW, "server", "cfg-1", "7", "vpn_peer_connected")
        == f"{GW}_vpn_peer_server_cfg-1_7_vpn_peer_connected"
    )


def test_new_vpn_tunnel_entities_once_per_gateway_type_and_description() -> None:
    """Every gateway gets one entity per tunnel and description, only once."""
    vpn_status = {"s2s": [TUNNEL], "server": [], "client": [CLIENT_TUNNEL]}
    known: set[str] = set()

    def descriptions(vpn_type: str) -> tuple[SimpleNamespace, ...]:
        return (_desc(f"d_{vpn_type}"),)

    created = new_vpn_tunnel_entities(
        DEVICES, vpn_status, known, descriptions, lambda *args: args
    )

    assert [(d.key, gw, t, tid, name) for d, gw, t, tid, name in created] == [
        ("d_s2s", GW, "s2s", "cfg-1", "wg0"),
        ("d_client", GW, "client", "row-2", "to-hq"),
    ]
    assert known == {
        f"{GW}_vpn_s2s_cfg-1_d_s2s",
        f"{GW}_vpn_client_row-2_d_client",
    }
    assert (
        new_vpn_tunnel_entities(
            DEVICES, vpn_status, known, descriptions, lambda *args: args
        )
        == []
    )


def test_new_vpn_tunnel_entities_without_gateway_creates_nothing() -> None:
    """Tunnels are attached to gateways only."""
    created = new_vpn_tunnel_entities(
        {SWITCH: {"type": "switch"}},
        {"s2s": [TUNNEL]},
        set(),
        lambda _t: (_desc("d"),),
        lambda *args: args,
    )

    assert created == []


def test_new_vpn_peer_entities_per_peer() -> None:
    """Every peer of every tunnel gets one entity per description."""
    known: set[str] = set()

    created = new_vpn_peer_entities(
        DEVICES,
        {"server": [TUNNEL]},
        known,
        (_desc("a"), _desc("b")),
        lambda *args: args,
    )

    assert [(d.key, *rest) for d, *rest in created] == [
        ("a", GW, "server", "cfg-1", "wg0", "7", "office"),
        ("b", GW, "server", "cfg-1", "wg0", "7", "office"),
    ]
    assert f"{GW}_vpn_peer_server_cfg-1_7_a" in known


def test_new_wan_port_entities_names_ports_and_skips_known_ports() -> None:
    """Ports without a name get "WAN<n>"; a known port gets no new entities."""
    wan_status = {GW: [{"name": "Fiber"}, {}]}
    known = {f"{GW}_wan_0"}

    created = new_wan_port_entities(
        wan_status, known, (_desc("x"),), lambda *args: args
    )

    assert [(d.key, gw, i, name) for d, gw, i, name in created] == [
        ("x", GW, 1, "WAN2")
    ]
    assert known == {f"{GW}_wan_0", f"{GW}_wan_1"}


def test_platform_builders_use_their_descriptions() -> None:
    """Sensor and binary sensor builders differ only in their descriptions."""
    coordinator = _coordinator({})
    vpn_status = {"s2s": [TUNNEL], "server": [], "client": [CLIENT_TUNNEL]}

    sensors = _build_vpn_sensors(coordinator, DEVICES, vpn_status, set())
    binary = _build_vpn_binary_sensors(coordinator, DEVICES, vpn_status, set())

    expected_sensor_keys = [d.key for d in VPN_SENSORS] + [
        d.key for d in VPN_CLIENT_SENSORS
    ]
    assert [e.entity_description.key for e in sensors] == expected_sensor_keys
    assert all(isinstance(e, OmadaVpnSensor) for e in sensors)
    assert [e.entity_description.key for e in binary] == [
        d.key for d in VPN_BINARY_SENSORS
    ] * 2
    assert all(isinstance(e, OmadaVpnBinarySensor) for e in binary)


@pytest.mark.parametrize(
    ("entity_cls", "description"),
    [
        (OmadaVpnSensor, VPN_SENSORS[0]),
        (OmadaVpnBinarySensor, VPN_BINARY_SENSORS[0]),
    ],
)
def test_vpn_tunnel_entity_matches_vpn_id_and_tracks_availability(
    entity_cls: type, description: Any
) -> None:
    """A tunnel is found by vpnId; a removed tunnel makes the entity unavailable."""
    data = {"vpn_status": {"s2s": [TUNNEL]}}
    entity = entity_cls(_coordinator(data), description, GW, "s2s", "cfg-1", "wg0")

    assert entity.unique_id == f"{GW}_vpn_s2s_cfg-1_{description.key}"
    assert entity.translation_placeholders == {"tunnel_name": "wg0"}
    assert entity.device_info == {"identifiers": {(DOMAIN, GW)}}
    assert entity.available is True

    data["vpn_status"]["s2s"] = []
    assert entity.available is False

    data["vpn_status"]["s2s"] = [TUNNEL]
    entity.coordinator.last_update_success = False
    assert entity.available is False


@pytest.mark.parametrize(
    ("entity_cls", "description"),
    [
        (OmadaVpnPeerSensor, VPN_PEER_SENSORS[0]),
        (OmadaVpnPeerBinarySensor, VPN_PEER_BINARY_SENSORS[0]),
    ],
)
def test_vpn_peer_entity_matches_peer_id(entity_cls: type, description: Any) -> None:
    """A peer is found by its ID within the tunnel; a removed peer is unavailable."""
    data = {"vpn_status": {"server": [dict(TUNNEL)]}}
    entity = entity_cls(
        _coordinator(data), description, GW, "server", "cfg-1", "wg0", "7", "office"
    )

    assert entity.unique_id == f"{GW}_vpn_peer_server_cfg-1_7_{description.key}"
    assert entity.translation_placeholders == {
        "peer_name": "office",
        "tunnel_name": "wg0",
    }
    assert entity._get_peer_data() == TUNNEL["peers"][0]

    data["vpn_status"]["server"][0] = {**TUNNEL, "peers": [{"id": 8}]}
    assert entity._get_peer_data() is None
    assert entity.available is False

    data["vpn_status"]["server"] = []
    assert entity.available is False


@pytest.mark.parametrize(
    ("entity_cls", "description"),
    [
        (OmadaWanSensor, WAN_PORT_SENSORS[0]),
        (OmadaWanBinarySensor, WAN_PORT_BINARY_SENSORS[0]),
    ],
)
def test_wan_port_entity_reads_port_by_index(
    entity_cls: type, description: Any
) -> None:
    """A WAN port entity reads its port by index; a missing port is unavailable."""
    port = {"name": "WAN2", "status": 1, "rxRate": 5}
    data = {"wan_status": {GW: [{"name": "WAN1"}, port]}}
    entity = entity_cls(_coordinator(data), description, GW, 1, "WAN2")

    assert entity.unique_id == f"{GW}_wan1_{description.key}"
    assert entity.translation_placeholders == {"port_name": "WAN2"}
    assert entity._get_port_data() is port
    assert entity.available is True

    data["wan_status"][GW] = [{"name": "WAN1"}]
    assert entity._get_port_data() is None
    assert entity.available is False


def test_wan_sensor_respects_description_availability() -> None:
    """The WAN sensor keeps applying its description's available_fn."""
    description = next(d for d in WAN_PORT_SENSORS if d.available_fn({}) is False)
    data = {"wan_status": {GW: [{}]}}
    entity = OmadaWanSensor(_coordinator(data), description, GW, 0, "WAN1")

    assert entity.available is False


async def test_linked_device_info_links_uplink_except_for_gateways(
    hass: HomeAssistant,
) -> None:
    """Non-gateway devices link to their registered uplink; gateways never do."""
    entry = MockConfigEntry(domain=DOMAIN)
    entry.add_to_hass(hass)
    uplink = dr.async_get(hass).async_get_or_create(
        config_entry_id=entry.entry_id, identifiers={(DOMAIN, GW)}
    )
    devices = {
        GW: {"type": "gateway", "name": "GW", "uplink_device_mac": SWITCH},
        SWITCH: {"type": "switch", "name": "SW", "uplink_device_mac": GW},
        "AA-BB-CC-DD-EE-09": {"type": "ap", "uplink_device_mac": "unknown"},
    }
    coordinator = SimpleNamespace(
        data={"devices": devices},
        api_client=SimpleNamespace(api_url="https://controller"),
        hass=hass,
        config_entry=entry,
    )

    switch_info = build_linked_infra_device_info(coordinator, SWITCH)
    gateway_info = build_linked_infra_device_info(coordinator, GW)
    ap_info = build_linked_infra_device_info(coordinator, "AA-BB-CC-DD-EE-09")

    assert switch_info["via_device_id"] == uplink.id
    assert switch_info["name"] == "SW"
    assert switch_info["configuration_url"] == "https://controller"
    assert "via_device_id" not in gateway_info
    assert "via_device_id" not in ap_info


# ---------------------------------------------------------------------------
# Sparse payloads: fields the controller may omit.
# ---------------------------------------------------------------------------


def test_discovery_defaults_for_missing_fields() -> None:
    """Missing names and IDs fall back to empty strings; WAN names to WAN<n>."""
    devices = {SWITCH: {}, GW: {"type": "gateway"}}
    tunnels = new_vpn_tunnel_entities(
        devices,
        {"server": [{"peers": [{}]}]},
        set(),
        lambda _t: (_desc("t"),),
        lambda *args: args,
    )
    peers = new_vpn_peer_entities(
        devices,
        {"server": [{"peers": [{}]}]},
        set(),
        (_desc("p"),),
        lambda *args: args,
    )
    ports = new_wan_port_entities(
        {GW: [{"name": "Fiber"}]}, set(), (_desc("w"),), lambda *args: args
    )

    assert [args[1:] for args in tunnels] == [(GW, "server", "", "")]
    assert [args[1:] for args in peers] == [(GW, "server", "", "", "", "")]
    assert [args[1:] for args in ports] == [(GW, 0, "Fiber")]


def test_discovery_skips_only_known_descriptions() -> None:
    """A known unique ID skips that description, not the following ones."""
    tunnel_known = {f"{GW}_vpn_s2s_cfg-1_a"}
    peer_known = {f"{GW}_vpn_peer_s2s_cfg-1_7_a"}

    tunnels = new_vpn_tunnel_entities(
        DEVICES,
        {"s2s": [TUNNEL]},
        tunnel_known,
        lambda _t: (_desc("a"), _desc("b")),
        lambda *args: args,
    )
    peers = new_vpn_peer_entities(
        DEVICES,
        {"s2s": [TUNNEL]},
        peer_known,
        (_desc("a"), _desc("b")),
        lambda *args: args,
    )

    assert [args[0].key for args in tunnels] == ["b"]
    assert [args[0].key for args in peers] == ["b"]


def test_tunnel_lookup_falls_back_to_row_id_and_tolerates_missing_data() -> None:
    """Tunnels without vpnId match on id; missing data means unavailable."""
    data: dict[str, Any] = {"vpn_status": {"client": [CLIENT_TUNNEL]}}
    tunnel = OmadaVpnSensor(
        _coordinator(data), VPN_CLIENT_SENSORS[0], GW, "client", "row-2", "to-hq"
    )
    peer = OmadaVpnPeerSensor(
        _coordinator(data), VPN_PEER_SENSORS[0], GW, "client", "row-2", "", "7", ""
    )
    port = OmadaWanSensor(_coordinator(data), WAN_PORT_SENSORS[0], GW, 0, "WAN1")

    assert tunnel._get_tunnel_data() is CLIENT_TUNNEL
    assert peer._get_peer_data() is None
    assert port._get_port_data() is None

    data.clear()
    assert tunnel._get_tunnel_data() is None
    assert port._get_port_data() is None


def test_platform_builders_pass_their_coordinator() -> None:
    """Every builder creates entities bound to the given coordinator."""
    coordinator = _coordinator({})
    vpn_status = {"s2s": [TUNNEL]}

    built = [
        *_build_wan_sensors(coordinator, {GW: [{"name": "WAN1"}]}, set()),
        *_build_vpn_sensors(coordinator, DEVICES, vpn_status, set()),
        *_build_vpn_peer_sensors(coordinator, DEVICES, vpn_status, set()),
        *_build_vpn_binary_sensors(coordinator, DEVICES, vpn_status, set()),
        *_build_vpn_peer_binary_sensors(coordinator, DEVICES, vpn_status, set()),
    ]

    assert built
    assert all(entity.coordinator is coordinator for entity in built)
    assert any(isinstance(e, OmadaVpnPeerBinarySensor) for e in built)


async def test_linked_device_info_skips_routers_and_unknown_devices(
    hass: HomeAssistant,
) -> None:
    """Gateways and routers are never linked; unknown devices get plain info."""
    entry = MockConfigEntry(domain=DOMAIN)
    entry.add_to_hass(hass)
    uplink = dr.async_get(hass).async_get_or_create(
        config_entry_id=entry.entry_id, identifiers={(DOMAIN, SWITCH)}
    )
    devices = {
        "AA-BB-CC-DD-EE-10": {"type": "Router", "uplink_device_mac": SWITCH},
        "AA-BB-CC-DD-EE-11": {"type": "AP", "uplink_device_mac": SWITCH},
        "AA-BB-CC-DD-EE-12": {"uplink_device_mac": SWITCH},
        "AA-BB-CC-DD-EE-13": {"type": "gateway", "uplink_device_mac": SWITCH},
    }
    coordinator = SimpleNamespace(
        data={"devices": devices},
        api_client=SimpleNamespace(api_url="https://controller"),
        hass=hass,
        config_entry=entry,
    )

    router = build_linked_infra_device_info(coordinator, "AA-BB-CC-DD-EE-10")
    gateway = build_linked_infra_device_info(coordinator, "AA-BB-CC-DD-EE-13")
    ap = build_linked_infra_device_info(coordinator, "AA-BB-CC-DD-EE-11")
    untyped = build_linked_infra_device_info(coordinator, "AA-BB-CC-DD-EE-12")
    unknown = build_linked_infra_device_info(coordinator, "AA-BB-CC-DD-EE-99")
    empty = build_linked_infra_device_info(
        SimpleNamespace(
            data={},
            api_client=coordinator.api_client,
            hass=hass,
            config_entry=entry,
        ),
        "AA-BB-CC-DD-EE-99",
    )

    assert "via_device_id" not in router
    assert "via_device_id" not in gateway
    assert ap["via_device_id"] == uplink.id
    assert untyped["via_device_id"] == uplink.id
    assert unknown["name"] == "Unknown Device"
    assert "via_device_id" not in unknown
    assert empty["identifiers"] == {(DOMAIN, "AA-BB-CC-DD-EE-99")}
