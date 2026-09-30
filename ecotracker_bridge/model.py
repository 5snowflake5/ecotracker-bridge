"""Canonical meter model.

Sources produce :class:`Reading`. Emulators consume a Reading and speak a
device protocol (EcoTracker JSON, Shelly RPC, …). One source can feed many
emulators; many sources can run at once.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


def _f(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


@dataclass
class Reading:
    """Signed grid power: positive = import, negative = export."""

    power_w: float = 0.0
    power_l1_w: float | None = None
    power_l2_w: float | None = None
    power_l3_w: float | None = None
    voltage_v: float | None = None
    voltage_l1_v: float | None = None
    voltage_l2_v: float | None = None
    voltage_l3_v: float | None = None
    current_a: float | None = None
    energy_import_wh: float | None = None
    energy_export_wh: float | None = None
    frequency_hz: float | None = None
    power_avg_w: float | None = None
    age_ms: float | None = None
    extra: dict[str, Any] = field(default_factory=dict)
    source_id: str = ""
    fetched_at: datetime | None = None
    error: str | None = None
    raw: bytes | None = None

    def phase_powers(self) -> tuple[float, float, float, float]:
        if self.power_l1_w is not None or self.power_l2_w is not None or self.power_l3_w is not None:
            a = float(self.power_l1_w or 0)
            b = float(self.power_l2_w or 0)
            c = float(self.power_l3_w or 0)
            return a, b, c, a + b + c
        total = float(self.power_w or 0)
        return total, 0.0, 0.0, total

    def is_native_ecotracker(self) -> bool:
        """True when extra is already everHome /v1/json (do not leak foreign JSON)."""
        power = self.extra.get("power") if self.extra else None
        return isinstance(power, (int, float))

    def to_ecotracker(self) -> dict[str, Any]:
        """JSON Growatt NOAH / HA cache expect. Native extra wins, then overlay."""
        out: dict[str, Any] = dict(self.extra) if self.is_native_ecotracker() else {}
        out["power"] = self.power_w
        if self.power_avg_w is not None:
            out["powerAvg"] = self.power_avg_w
        elif "powerAvg" not in out:
            out["powerAvg"] = self.power_w
        a, b, c, _ = self.phase_powers()
        if self.power_l1_w is not None or self.power_l2_w is not None or self.power_l3_w is not None:
            out["powerPhase1"] = a
            out["powerPhase2"] = b
            out["powerPhase3"] = c
        if self.energy_import_wh is not None:
            out["energyCounterIn"] = self.energy_import_wh
        if self.energy_export_wh is not None:
            out["energyCounterOut"] = self.energy_export_wh
        if self.age_ms is not None:
            out["agePower"] = self.age_ms
        return out


def reading_from_ecotracker(payload: dict[str, Any], *, source_id: str = "", fetched_at: datetime | None = None, raw: bytes | None = None) -> Reading:
    """Map everHome EcoTracker /v1/json onto the canonical reading."""
    return Reading(
        power_w=float(payload.get("power") or 0),
        power_l1_w=_f(payload.get("powerPhase1")),
        power_l2_w=_f(payload.get("powerPhase2")),
        power_l3_w=_f(payload.get("powerPhase3")),
        energy_import_wh=_f(payload.get("energyCounterIn")),
        energy_export_wh=_f(payload.get("energyCounterOut")),
        power_avg_w=_f(payload.get("powerAvg")),
        age_ms=_f(payload.get("agePower")),
        extra=dict(payload),
        source_id=source_id,
        fetched_at=fetched_at,
        raw=raw,
    )


class Source(ABC):
    """Reads a physical (or virtual) meter."""

    id: str
    type: str
    label: str = ""

    def start(self) -> None:
        return None

    def stop(self) -> None:
        return None

    @abstractmethod
    def read(self, *, reason: str = "", force: bool = False) -> Reading | None:
        """Live read. Implementations should throttle cheap repeat hits."""

    def snapshot(self) -> Reading | None:
        """Last known reading, no I/O. Override if you cache."""
        return None

    def stats(self) -> dict[str, Any]:
        return {}


class Emulator(ABC):
    """Presents a meter protocol to batteries / HA / other clients."""

    id: str
    type: str
    source_id: str
    hostnames: list[str] = []

    def start(self) -> None:
        return None

    def stop(self) -> None:
        return None

    def mdns_services(self, ip: str, port: int) -> list[Any]:
        """Return zeroconf ServiceInfo instances (may be empty)."""
        return []

    @abstractmethod
    def handle(
        self,
        *,
        http_method: str,
        path: str,
        query: str,
        body: bytes,
        headers: dict[str, str],
        client: str,
        hub: Any,
    ) -> tuple[int, bytes, str] | None:
        """Handle an HTTP request. None = not this emulator's request."""
