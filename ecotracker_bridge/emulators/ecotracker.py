"""everHome EcoTracker HTTP + mDNS emulator."""

from __future__ import annotations

import json
import logging
import socket
from typing import Any

from emulators.base import should_claim
from model import Emulator, Reading
from util import berlin_now

LOG = logging.getLogger("ecotracker-bridge")

_JSON_CT = "application/json"
_JSON_CT_UTF8 = "application/json; charset=utf-8"


def _normalize_mac(raw: str) -> str:
    mac = "".join(ch for ch in str(raw).upper() if ch.isalnum())
    if len(mac) != 12:
        raise ValueError(f"MAC muss 12 Hex-Zeichen haben, nicht {raw!r}")
    return mac


def cache_payload(reading: Reading | None) -> dict[str, Any] | None:
    """Cache für HA-Sensoren: letzte Werte ohne Live-Abruf."""
    if reading is None:
        return None
    out = reading.to_ecotracker()
    last_ok = reading.fetched_at
    if last_ok is not None:
        age = max(0.0, (berlin_now() - last_ok).total_seconds())
        out["ageSeconds"] = round(age, 1)
        out["lastOk"] = last_ok.isoformat()
    return out


class EcoTrackerEmulator(Emulator):
    def __init__(self, cfg: dict[str, Any]) -> None:
        self.id = str(cfg.get("id") or "ecotracker").strip()
        self.type = "ecotracker"
        mac = _normalize_mac(str(cfg.get("mac") or "B43A45A1B2C3"))
        hostname = str(cfg.get("hostname") or f"ecotracker-{mac.lower()}").strip()
        if hostname.endswith(".local"):
            hostname = hostname[: -len(".local")]
        self.hostnames = [hostname]
        self.source_id = str(cfg.get("source") or "grid").strip() or "grid"
        self.mac = mac
        self.serial = str(cfg.get("serial") or "293d45273261")
        self.productid = str(cfg.get("productid") or "1137")
        self._hostname = hostname

    def mdns_services(self, ip: str, port: int) -> list[Any]:
        from zeroconf import ServiceInfo

        service_type = "_everhome._tcp.local."
        info = ServiceInfo(
            service_type,
            f"{self._hostname}.{service_type}",
            addresses=[socket.inet_aton(ip)],
            port=port,
            properties={
                "ip": ip,
                "serial": self.serial,
                "productid": self.productid,
            },
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
        if path not in ("/v1/json", "/v1/json/", "/v1/cache", "/v1/cache/"):
            return None
        if not should_claim(self, hub, headers):
            return None

        if path in ("/v1/json", "/v1/json/"):
            reading = hub.read_source(
                self.source_id,
                reason=f"GET /v1/json von {client}",
            )
            if reading is None:
                LOG.warning(
                    "GET /v1/json von %s → 503 (keine Daten von Quelle %s)",
                    client,
                    self.source_id,
                )
                msg = json.dumps(
                    {"error": "noch keine Daten vom physischen EcoTracker"},
                    separators=(",", ":"),
                ).encode("utf-8")
                return 503, msg, _JSON_CT_UTF8
            if reading.raw is not None and reading.is_native_ecotracker():
                body_out = reading.raw
            else:
                body_out = json.dumps(
                    reading.to_ecotracker(),
                    separators=(",", ":"),
                    ensure_ascii=False,
                ).encode("utf-8")
            LOG.debug(
                "GET /v1/json von %s → 200 power=%s W (Quelle %s)",
                client,
                reading.power_w,
                self.source_id,
            )
            return 200, body_out, _JSON_CT

        snap = hub.snapshot_source(self.source_id)
        cached = cache_payload(snap)
        if cached is None:
            LOG.debug("GET /v1/cache von %s → 503 (noch kein Cache)", client)
            msg = json.dumps(
                {"error": "noch kein Cache – warte auf Growatt-Abruf von /v1/json"},
                separators=(",", ":"),
            ).encode("utf-8")
            return 503, msg, _JSON_CT_UTF8
        body_out = json.dumps(cached, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        LOG.debug(
            "GET /v1/cache von %s → 200 power=%s W age=%ss",
            client,
            cached.get("power"),
            cached.get("ageSeconds"),
        )
        return 200, body_out, _JSON_CT
