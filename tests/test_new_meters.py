from __future__ import annotations

import json
from datetime import datetime, timezone
from unittest.mock import patch

from emulators import create_emulator
from emulators.chargee_sparky import ChargeeSparkyEmulator
from emulators.shelly_pro3em import ShellyPro3EmEmulator
from emulators.shelly_udp import ShellyUdpServer, parse_udp_ports
from model import Reading
from sources import create_source
from sources.fronius import FroniusSource
from sources.homewizard import HomeWizardSource
from sources.sml import parse_sml_power
from sources.sma_decode import parse_speedwire
from sources.tasmota import TasmotaSource
from sources.tibber_pulse import TibberPulseSource


class FakeHub:
    def __init__(self, live: Reading, emulators=None) -> None:
        self.emulators = emulators or []
        self.meta = {"announce_ip": "192.168.1.10", "port": 80}
        self._live = live
        self.read_calls: list[str] = []

    def read_source(self, source_id: str, *, reason: str = "", force: bool = False):
        self.read_calls.append(reason)
        return self._live

    def snapshot_source(self, source_id: str):
        return self._live

    def emulators_of_type(self, type_name: str):
        t = type_name.strip().lower()
        return [e for e in self.emulators if getattr(e, "type", "").lower() == t]


def _sml_value(obis_hex: str, value: int, *, scaler: int = 0, width: int = 4) -> bytes:
    tl = 0x50 | (width + 1)
    return (
        b"\x77\x07"
        + bytes.fromhex(obis_hex)
        + bytes([0x52, scaler & 0xFF, tl])
        + int(value).to_bytes(width, "big", signed=True)
    )


def test_sml_power_and_phases() -> None:
    payload = (
        _sml_value("0100100700ff", 1500)
        + _sml_value("0100240700ff", 400)
        + _sml_value("0100380700ff", 500)
        + _sml_value("01004c0700ff", 600)
        + _sml_value("0100010800ff", 12345000)
    )
    parsed = parse_sml_power(payload)
    assert parsed["power"] == 1500.0
    assert parsed["l1"] == 400.0
    assert parsed["l2"] == 500.0
    assert parsed["l3"] == 600.0
    assert parsed["energy_in"] == 12345000.0


def test_sma_speedwire_signed_power() -> None:
    header = b"SMA" + bytes(13)
    p_in = (0x0001).to_bytes(2, "big") + (0x0400).to_bytes(2, "big") + int(12000).to_bytes(4, "big")
    p_out = (0x0002).to_bytes(2, "big") + (0x0400).to_bytes(2, "big") + int(2000).to_bytes(4, "big")
    datagram = header + p_in + p_out + bytes(4)
    parsed = parse_speedwire(datagram)
    assert parsed["power"] == 1000.0


def test_tasmota_status10() -> None:
    src = TasmotaSource({"id": "tas", "host": "192.168.1.20"})
    body = {"StatusSNS": {"ENERGY": {"Power": 321, "Power_1": 100, "Power_2": 121, "Power_3": 100}}}
    with patch("sources.tasmota.fetch_json", return_value=body):
        reading = src.fetch()
    assert reading.power_w == 321.0
    assert reading.power_l1_w is None


def test_tasmota_three_labels() -> None:
    src = TasmotaSource({"id": "tas", "host": "192.168.1.20", "json_power": "Power_1,Power_2,Power_3"})
    body = {"StatusSNS": {"ENERGY": {"Power_1": 10, "Power_2": 20, "Power_3": 30}}}
    with patch("sources.tasmota.fetch_json", return_value=body):
        reading = src.fetch()
    assert reading.power_w == 60.0
    assert reading.power_l1_w == 10.0
    assert reading.power_l3_w == 30.0


def test_homewizard_v1() -> None:
    src = HomeWizardSource({"id": "hw", "host": "192.168.1.30"})
    assert src.url.endswith("/api/v1/data")
    body = {
        "active_power_w": -250.5,
        "active_power_l1_w": -80,
        "total_power_import_kwh": 12.3,
        "total_power_export_kwh": 4.0,
    }
    with patch("sources.homewizard.fetch_json", return_value=body):
        reading = src.fetch()
    assert reading.power_w == -250.5
    assert reading.energy_import_wh == 12300.0
    assert reading.energy_export_wh == 4000.0


def test_homewizard_v2_token_url() -> None:
    src = HomeWizardSource({"id": "hw", "host": "p1.local", "token": "abc"})
    assert src.url == "https://p1.local/api/measurement"
    assert src._headers["Authorization"] == "Bearer abc"


def test_fronius_sum() -> None:
    src = FroniusSource({"id": "fr", "host": "192.168.1.40"})
    body = {
        "Head": {"Status": {"Code": 0}},
        "Body": {"Data": {"PowerReal_P_Sum": -420.0, "PowerReal_P_Phase_1": -100}},
    }
    with patch("sources.fronius.fetch_json", return_value=body):
        reading = src.fetch()
    assert reading.power_w == -420.0
    assert reading.power_l1_w is None


def test_tibber_sml_fetch() -> None:
    src = TibberPulseSource({"id": "tb", "host": "192.168.1.50", "password": "secret"})
    blob = _sml_value("0100100700ff", 88)
    with patch("sources.tibber_pulse.fetch_bytes", return_value=blob):
        reading = src.fetch()
    assert reading.power_w == 88.0


def test_factory_aliases() -> None:
    src = create_source({"id": "x", "type": "tibber", "host": "1.2.3.4", "password": "p"})
    assert src.type == "tibber_pulse"
    emu = create_emulator({"id": "s", "type": "sparky", "source": "x", "serial": "abc"})
    assert emu.type == "chargee_sparky"


def test_shelly_emg3_hostname_and_udp_defaults() -> None:
    emu = ShellyPro3EmEmulator({"id": "g3", "type": "shelly_emg3", "mac": "AABBCCDDEEFF"})
    assert emu.type == "shelly_emg3"
    assert emu.hostnames == ["shellyemg3-aabbccddeeff"]
    assert emu.udp_ports == [1010, 2220]
    assert emu.em_kind == "EM"
    assert emu.shelly_app == "EMG3"


def test_shelly_proem50_em1_http() -> None:
    live = Reading(power_w=123, source_id="grid", fetched_at=datetime.now(timezone.utc))
    emu = ShellyPro3EmEmulator({"id": "em50", "type": "shelly_proem50", "mac": "112233445566"})
    assert emu.hostnames == ["shellyproem50-112233445566"]
    assert emu.udp_ports == [2223]
    assert emu.em_kind == "EM1"
    hub = FakeHub(live, emulators=[emu])
    code, body, _ = emu.handle(
        http_method="GET",
        path="/rpc/EM1.GetStatus",
        query="id=0",
        body=b"",
        headers={},
        client="10.0.0.9",
        hub=hub,
    )
    assert code == 200
    data = json.loads(body)
    assert data["act_power"] == 123.0
    info_code, info_body, _ = emu.handle(
        http_method="GET",
        path="/shelly",
        query="",
        body=b"",
        headers={},
        client="10.0.0.9",
        hub=hub,
    )
    assert info_code == 200
    info = json.loads(info_body)
    assert info["id"] == "shellyproem50-112233445566"
    assert info["app"] == "ProEM"
    assert info["profile"] == "monophase"


def test_udp_ports_off() -> None:
    emu = ShellyPro3EmEmulator({"id": "g3", "type": "shelly_emg3", "udp_ports": "off"})
    assert emu.udp_ports == []
    assert parse_udp_ports("1010,2220") == [1010, 2220]


def test_udp_em1_reply_frame() -> None:
    live = Reading(power_w=50, source_id="grid", fetched_at=datetime.now(timezone.utc))
    emu = ShellyPro3EmEmulator({"id": "em50", "type": "shelly_proem50", "udp_ports": "off"})
    hub = FakeHub(live, emulators=[emu])
    emu.hub = hub
    server = ShellyUdpServer(emu, [])
    req = json.dumps({"id": 7, "method": "EM1.GetStatus", "params": {"id": 0}}).encode()
    reply = server._reply(req, ("10.0.0.8", 1234))
    assert reply is not None
    frame = json.loads(reply)
    assert frame["id"] == 7
    assert frame["result"]["act_power"] == 50.0


def test_sparky_api() -> None:
    live = Reading(
        power_w=-12,
        power_l1_w=-4,
        energy_import_wh=5000,
        source_id="grid",
        fetched_at=datetime.now(timezone.utc),
    )
    emu = ChargeeSparkyEmulator({"id": "sp", "source": "grid", "serial": "unit1"})
    hub = FakeHub(live, emulators=[emu])
    code, body, _ = emu.handle(
        http_method="GET",
        path="/api",
        query="",
        body=b"",
        headers={},
        client="10.0.0.1",
        hub=hub,
    )
    assert code == 200
    assert json.loads(body)["product_type"] == "sparky"
    data_code, data_body, _ = emu.handle(
        http_method="GET",
        path="/api/v1/data",
        query="",
        body=b"",
        headers={},
        client="10.0.0.1",
        hub=hub,
    )
    assert data_code == 200
    payload = json.loads(data_body)
    assert payload["power_w"] == -12
    assert payload["energy_import_kwh"] == 5.0
