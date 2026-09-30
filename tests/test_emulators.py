from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from emulators.ecotracker import EcoTrackerEmulator
from model import Emulator, Reading
import shelly_rpc


class FakeHub:
    def __init__(
        self,
        *,
        emulators: list[Emulator] | None = None,
        snapshot: Reading | None = None,
        live: Reading | None = None,
    ) -> None:
        self.emulators = emulators or []
        self.meta: dict[str, Any] = {"announce_ip": "192.168.1.10", "port": 80}
        self._snapshot = snapshot
        self._live = live
        self.read_calls: list[tuple[str, str]] = []
        self.snapshot_calls: list[str] = []

    def read_source(self, source_id: str, *, reason: str = "", force: bool = False) -> Reading | None:
        self.read_calls.append((source_id, reason))
        return self._live

    def snapshot_source(self, source_id: str) -> Reading | None:
        self.snapshot_calls.append(source_id)
        return self._snapshot

    def emulators_of_type(self, type_name: str) -> list[Emulator]:
        t = type_name.strip().lower()
        return [e for e in self.emulators if getattr(e, "type", "").lower() == t]


def test_phase_powers_mono() -> None:
    payload = {"power": 100}
    a, b, c, total = shelly_rpc.phase_powers(payload)
    assert (a, b, c, total) == (100.0, 0.0, 0.0, 100.0)
    em = shelly_rpc.em_get_status(payload)
    assert em["a_act_power"] == 100.0
    assert em["b_act_power"] == 0.0
    assert em["c_act_power"] == 0.0


def test_phase_powers_three_phase() -> None:
    payload = {"power": 999, "powerPhase1": 10, "powerPhase2": 20, "powerPhase3": 30}
    a, b, c, total = shelly_rpc.phase_powers(payload)
    assert (a, b, c, total) == (10.0, 20.0, 30.0, 60.0)
    em = shelly_rpc.em_get_status(payload)
    assert em["total_act_power"] == 60.0


def test_ecotracker_json_calls_read_source() -> None:
    live = Reading(power_w=500, source_id="grid", fetched_at=datetime.now(timezone.utc))
    hub = FakeHub(snapshot=Reading(power_w=1), live=live)
    emu = EcoTrackerEmulator({"id": "et", "mac": "AABBCCDDEEFF", "source": "grid"})
    code, body, _ = emu.handle(
        http_method="GET",
        path="/v1/json",
        query="",
        body=b"",
        headers={},
        client="10.0.0.1",
        hub=hub,
    )
    assert code == 200
    assert hub.read_calls == [("grid", "GET /v1/json von 10.0.0.1")]
    assert hub.snapshot_calls == []
    assert json.loads(body)["power"] == 500


def test_ecotracker_cache_uses_snapshot_only() -> None:
    snap = Reading(
        power_w=42,
        source_id="grid",
        fetched_at=datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
    )
    hub = FakeHub(snapshot=snap, live=Reading(power_w=999))
    emu = EcoTrackerEmulator({"id": "et", "mac": "112233445566", "source": "grid"})
    code, body, _ = emu.handle(
        http_method="GET",
        path="/v1/cache",
        query="",
        body=b"",
        headers={},
        client="10.0.0.2",
        hub=hub,
    )
    assert code == 200
    assert hub.read_calls == []
    assert hub.snapshot_calls == ["grid"]
    data = json.loads(body)
    assert data["power"] == 42
    assert "ageSeconds" in data
    assert "lastOk" in data


def test_host_routing_two_ecotrackers() -> None:
    emu1 = EcoTrackerEmulator(
        {"id": "et1", "mac": "AAAAAAAAAAAA", "hostname": "ecotracker-aaaaaaaaaaaa"}
    )
    emu2 = EcoTrackerEmulator(
        {"id": "et2", "mac": "BBBBBBBBBBBB", "hostname": "ecotracker-bbbbbbbbbbbb"}
    )
    reading = Reading(power_w=77, source_id="grid2", fetched_at=datetime.now(timezone.utc))
    hub = FakeHub(emulators=[emu1, emu2], live=reading)
    hub._live = reading

    def read(source_id: str, *, reason: str = "", force: bool = False) -> Reading | None:
        hub.read_calls.append((source_id, reason))
        return reading if source_id == "grid2" else None

    hub.read_source = read  # type: ignore[method-assign]

    emu2.source_id = "grid2"

    miss = emu1.handle(
        http_method="GET",
        path="/v1/json",
        query="",
        body=b"",
        headers={"Host": "ecotracker-bbbbbbbbbbbb"},
        client="10.0.0.3",
        hub=hub,
    )
    assert miss is None

    hit = emu2.handle(
        http_method="GET",
        path="/v1/json",
        query="",
        body=b"",
        headers={"Host": "ecotracker-bbbbbbbbbbbb"},
        client="10.0.0.3",
        hub=hub,
    )
    assert hit is not None
    assert hit[0] == 200
    assert json.loads(hit[1])["power"] == 77
