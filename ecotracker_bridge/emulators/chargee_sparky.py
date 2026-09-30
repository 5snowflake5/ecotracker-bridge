"""Chargee Sparky / Flint P1 local API + mDNS _chargee_p1._tcp."""

from __future__ import annotations

import json
import logging
import socket
from typing import Any

from emulators.base import should_claim
from model import Emulator
from util import berlin_now

LOG = logging.getLogger("ecotracker-bridge")
_JSON = "application/json; charset=utf-8"


class ChargeeSparkyEmulator(Emulator):
    def __init__(self, cfg: dict[str, Any]) -> None:
        self.id = str(cfg.get("id") or "sparky").strip()
        self.type = "chargee_sparky"
        self.source_id = str(cfg.get("source") or "grid").strip() or "grid"
        serial = str(cfg.get("serial") or "sparky001")
        hostname = str(cfg.get("hostname") or f"sparky-{serial}").strip()
        if hostname.endswith(".local"):
            hostname = hostname[: -len(".local")]
        self.hostnames = [hostname]
        self._hostname = hostname
        self.serial = serial
        self.hub = None

    def mdns_services(self, ip: str, port: int) -> list[Any]:
        from zeroconf import ServiceInfo

        st = "_chargee_p1._tcp.local."
        info = ServiceInfo(
            st,
            f"{self._hostname}.{st}",
            addresses=[socket.inet_aton(ip)],
            port=port,
            properties={"serial": self.serial, "path": "/api"},
            server=f"{self._hostname}.local.",
        )
        return [info]

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
        if http_method != "GET":
            return None
        if path not in ("/api", "/api/", "/api/v1/data", "/api/v1/data/", "/api/v1/identify", "/api/v1/identify/"):
            return None
        if not should_claim(self, hub, headers):
            return None
        if path.rstrip("/").endswith("identify"):
            return 200, b'{"ok":true}', _JSON
        if path.rstrip("/") == "/api":
            obj = {
                "product_type": "sparky",
                "product_name": "Sparky",
                "serial": self.serial,
                "firmware_version": "95",
                "api_version": "v1",
            }
            return 200, json.dumps(obj, separators=(",", ":")).encode(), _JSON
        snap = hub.read_source(self.source_id, reason=f"GET {path} von {client}")
        if snap is None:
            return 503, json.dumps({"error": "no meter data"}).encode(), _JSON
        eco = snap.to_ecotracker()
        last_ok = snap.fetched_at or berlin_now()
        obj = {
            "timestamp": last_ok.isoformat(),
            "power_w": eco.get("power"),
            "power_l1_w": eco.get("powerPhase1"),
            "power_l2_w": eco.get("powerPhase2"),
            "power_l3_w": eco.get("powerPhase3"),
            "energy_import_kwh": (float(eco["energyCounterIn"]) / 1000.0) if eco.get("energyCounterIn") is not None else None,
            "energy_export_kwh": (float(eco["energyCounterOut"]) / 1000.0) if eco.get("energyCounterOut") is not None else None,
        }
        return 200, json.dumps(obj, separators=(",", ":")).encode(), _JSON
