"""Shelly Pro 3EM Gen2 RPC emulator."""

from __future__ import annotations

import json
import logging
import socket
from typing import Any

from emulators.base import should_claim
from model import Emulator, Reading

LOG = logging.getLogger("ecotracker-bridge")

DEFAULT_VOLTAGE = 230.0
DEFAULT_PF = 1.0
FW_ID = "20250924-062729/1.7.1-gd336f31"
FW_VER = "1.7.1"
MODEL = "SPEM-003CEBEU"

_JSON_CT = "application/json; charset=utf-8"


def phase_powers(payload: dict[str, Any]) -> tuple[float, float, float, float]:
    total = float(payload.get("power") or 0)
    p1 = payload.get("powerPhase1")
    p2 = payload.get("powerPhase2")
    p3 = payload.get("powerPhase3")
    if p1 is not None or p2 is not None or p3 is not None:
        a = float(p1 or 0)
        b = float(p2 or 0)
        c = float(p3 or 0)
        return a, b, c, a + b + c
    return total, 0.0, 0.0, total


def _phase_block(power: float, voltage: float) -> dict[str, Any]:
    current = abs(power / voltage) if voltage else 0.0
    return {
        "current": round(current, 3),
        "voltage": round(voltage, 1),
        "act_power": round(power, 1),
        "aprt_power": round(abs(power), 1),
        "pf": DEFAULT_PF,
        "freq": 50.0,
    }


def em_get_status(payload: dict[str, Any], *, voltage: float = DEFAULT_VOLTAGE) -> dict[str, Any]:
    a, b, c, total = phase_powers(payload)
    pa = _phase_block(a, voltage)
    pb = _phase_block(b, voltage)
    pc = _phase_block(c, voltage)
    return {
        "id": 0,
        "a_current": pa["current"],
        "a_voltage": pa["voltage"],
        "a_act_power": pa["act_power"],
        "a_aprt_power": pa["aprt_power"],
        "a_pf": pa["pf"],
        "a_freq": pa["freq"],
        "b_current": pb["current"],
        "b_voltage": pb["voltage"],
        "b_act_power": pb["act_power"],
        "b_aprt_power": pb["aprt_power"],
        "b_pf": pb["pf"],
        "b_freq": pb["freq"],
        "c_current": pc["current"],
        "c_voltage": pc["voltage"],
        "c_act_power": pc["act_power"],
        "c_aprt_power": pc["aprt_power"],
        "c_pf": pc["pf"],
        "c_freq": pc["freq"],
        "n_current": None,
        "total_current": round(pa["current"] + pb["current"] + pc["current"], 3),
        "total_act_power": round(total, 1),
        "total_aprt_power": round(abs(a) + abs(b) + abs(c), 1),
        "user_calibrated_phase": [],
    }


def emdata_get_status(payload: dict[str, Any]) -> dict[str, Any]:
    energy_in = float(payload.get("energyCounterIn") or 0)
    energy_out = float(payload.get("energyCounterOut") or 0)
    a, b, c, _ = phase_powers(payload)
    total_abs = abs(a) + abs(b) + abs(c)
    if total_abs > 0:
        share = (abs(a) / total_abs, abs(b) / total_abs, abs(c) / total_abs)
    else:
        share = (1.0, 0.0, 0.0)

    def split(wh: float) -> tuple[float, float, float]:
        return wh * share[0], wh * share[1], wh * share[2]

    ain, bin_, cin = split(energy_in)
    aout, bout, cout = split(energy_out)
    return {
        "id": 0,
        "a_total_act_energy": round(ain, 1),
        "a_total_act_ret_energy": round(aout, 1),
        "b_total_act_energy": round(bin_, 1),
        "b_total_act_ret_energy": round(bout, 1),
        "c_total_act_energy": round(cin, 1),
        "c_total_act_ret_energy": round(cout, 1),
        "total_act": round(energy_in, 1),
        "total_act_ret": round(energy_out, 1),
    }


def em1_get_status(payload: dict[str, Any], *, voltage: float = DEFAULT_VOLTAGE) -> dict[str, Any]:
    _a, _b, _c, total = phase_powers(payload)
    current = abs(total / voltage) if voltage else 0.0
    return {
        "id": 0,
        "current": round(current, 3),
        "voltage": round(voltage, 1),
        "act_power": round(total, 1),
        "aprt_power": round(abs(total), 1),
        "pf": DEFAULT_PF,
        "freq": 50.0,
    }


def shelly_get_device_info(
    mac: str, hostname: str, *, model: str = MODEL, app: str = "Pro3EM", profile: str = "triphase"
) -> dict[str, Any]:
    mac = mac.upper()
    return {
        "name": None,
        "id": hostname,
        "mac": mac,
        "slot": 0,
        "model": model,
        "gen": 2,
        "fw_id": FW_ID,
        "ver": FW_VER,
        "app": app,
        "auth_en": False,
        "auth_domain": None,
        "profile": profile,
    }


def shelly_get_status(
    payload: dict[str, Any],
    *,
    mac: str,
    ip: str,
    voltage: float = DEFAULT_VOLTAGE,
    em_kind: str = "EM",
) -> dict[str, Any]:
    emdata = emdata_get_status(payload)
    meter: dict[str, Any]
    if em_kind == "EM1":
        meter = {"em1:0": em1_get_status(payload, voltage=voltage), "emdata:0": emdata}
    else:
        meter = {"em:0": em_get_status(payload, voltage=voltage), "emdata:0": emdata}
    return {
        "ble": {},
        "cloud": {"connected": False},
        **meter,
        "eth": {"ip": ip},
        "modbus": {},
        "mqtt": {"connected": False},
        "sys": {
            "mac": mac.upper(),
            "restart_required": False,
            "uptime": 3600,
            "ram_size": 262144,
            "ram_free": 120000,
            "fs_size": 524288,
            "fs_free": 200000,
            "cfg_rev": 1,
            "kvs_rev": 0,
            "schedule_rev": 0,
            "webhook_rev": 0,
            "available_updates": {},
        },
        "wifi": {
            "sta_ip": ip,
            "status": "got ip",
            "ssid": "bridge",
            "rssi": -60,
        },
        "ws": {"connected": False},
    }


def mdns_properties(hostname: str) -> dict[str, str]:
    return {
        "id": hostname,
        "arch": "esp8266",
        "gen": "2",
        "fw_id": FW_ID,
    }


def needs_meter_payload(method: str) -> bool:
    key = method.strip().lower()
    return key in (
        "em.getstatus",
        "em1.getstatus",
        "emdata.getstatus",
        "shelly.getstatus",
    )


def em_get_config() -> dict[str, Any]:
    return {
        "id": 0,
        "name": None,
        "blink_mode_selector": "active_energy",
        "phase_selector": "a",
        "monitor_phase_sequence": True,
        "reverse": {"a": None, "b": None, "c": None},
        "ct_type": "120A",
    }


def dispatch_rpc(method: str, payload: dict[str, Any] | None, meta: dict[str, Any]) -> dict[str, Any] | None:
    """Bekannte Shelly-RPC-Methoden. Unbekannt → None."""
    method = method.strip()
    mac = str(meta.get("shelly_mac") or "C8C9A3B43A45")
    hostname = str(meta.get("shelly_hostname") or f"shellypro3em-{mac.lower()}")
    ip = str(meta.get("announce_ip") or "0.0.0.0")
    voltage = float(meta.get("default_voltage") or DEFAULT_VOLTAGE)
    model = str(meta.get("shelly_model") or MODEL)
    app = str(meta.get("shelly_app") or "Pro3EM")
    em_kind = str(meta.get("shelly_em") or "EM")
    data = payload or {}
    key = method.lower()

    if key in ("shelly.getdeviceinfo",):
        return shelly_get_device_info(
            mac,
            hostname,
            model=model,
            app=app,
            profile=str(meta.get("shelly_profile") or "triphase"),
        )
    if key in ("em.getstatus",):
        return em_get_status(data, voltage=voltage)
    if key in ("em1.getstatus",):
        return em1_get_status(data, voltage=voltage)
    if key in ("emdata.getstatus",):
        return emdata_get_status(data)
    if key in ("shelly.getstatus",):
        return shelly_get_status(data, mac=mac, ip=ip, voltage=voltage, em_kind=em_kind)
    if key in ("em.getconfig",):
        return em_get_config()
    if key in ("emdata.getconfig",):
        return {}
    if key in ("cloud.getstatus",):
        return {"connected": False}
    if key in ("wifi.getstatus",):
        return {"sta_ip": ip, "status": "got ip", "ssid": "bridge", "rssi": -60}
    if key in ("shelly.listmethods",):
        return {
            "methods": [
                "Shelly.GetDeviceInfo",
                "Shelly.GetStatus",
                "Shelly.ListMethods",
                "EM.GetStatus",
                "EM1.GetStatus",
                "EM.GetConfig",
                "EMData.GetStatus",
                "EMData.GetConfig",
                "Cloud.GetStatus",
                "WiFi.GetStatus",
            ]
        }
    return None


def _json_response(code: int, obj: Any) -> tuple[int, bytes, str]:
    body = json.dumps(obj, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return code, body, _JSON_CT


SHELLY_PROFILES: dict[str, dict[str, Any]] = {
    "shelly_pro3em": {
        "type": "shelly_pro3em",
        "prefix": "shellypro3em",
        "model": MODEL,
        "app": "Pro3EM",
        "em": "EM",
        "profile": "triphase",
        "udp": [],
    },
    "shelly_emg3": {
        "type": "shelly_emg3",
        "prefix": "shellyemg3",
        "model": "S3EM-002CXCEU",
        "app": "EMG3",
        "em": "EM",
        "profile": "triphase",
        "udp": [1010, 2220],
    },
    "shelly_proem50": {
        "type": "shelly_proem50",
        "prefix": "shellyproem50",
        "model": "SPEM-002CEBEU50",
        "app": "ProEM",
        "em": "EM1",
        "profile": "monophase",
        "udp": [2223],
    },
}


class ShellyPro3EmEmulator(Emulator):
    def __init__(self, cfg: dict[str, Any]) -> None:
        kind = str(cfg.get("type") or "shelly_pro3em").strip().lower().replace("-", "_")
        if kind == "shellypro3em":
            kind = "shelly_pro3em"
        if kind in ("shellyemg3", "shelly_em_gen3"):
            kind = "shelly_emg3"
        if kind in ("shellyproem50", "shelly_pro_em50"):
            kind = "shelly_proem50"
        profile = dict(SHELLY_PROFILES.get(kind) or SHELLY_PROFILES["shelly_pro3em"])
        self.id = str(cfg.get("id") or "shelly").strip()
        self.type = str(profile["type"])
        mac_raw = str(cfg.get("mac") or "C8C9A3B43A45")
        mac = "".join(ch for ch in mac_raw.upper() if ch.isalnum())
        if len(mac) != 12:
            mac = "C8C9A3B43A45"
        self.mac = mac
        hostname = str(cfg.get("hostname") or f"{profile['prefix']}-{mac.lower()}").strip()
        if hostname.endswith(".local"):
            hostname = hostname[: -len(".local")]
        self.hostnames = [hostname]
        self.source_id = str(cfg.get("source") or "grid").strip() or "grid"
        self._hostname = hostname
        self._default_voltage = float(cfg.get("default_voltage") or DEFAULT_VOLTAGE)
        self.em_kind = str(profile["em"])
        self.shelly_model = str(profile["model"])
        self.shelly_app = str(profile["app"])
        self.shelly_profile = str(profile["profile"])
        from emulators.shelly_udp import parse_udp_ports

        if "udp_ports" in cfg:
            self.udp_ports = parse_udp_ports(cfg.get("udp_ports"))
        else:
            self.udp_ports = list(profile["udp"])
        self.hub = None
        self._udp = None

    def start(self) -> None:
        if not self.udp_ports:
            return
        from emulators.shelly_udp import ShellyUdpServer

        self._udp = ShellyUdpServer(self, self.udp_ports)
        self._udp.start()

    def stop(self) -> None:
        if self._udp is not None:
            self._udp.stop()
            self._udp = None

    def _rpc_meta(self, hub: Any) -> dict[str, Any]:
        return {
            "shelly_mac": self.mac,
            "shelly_hostname": self._hostname,
            "announce_ip": str(hub.meta.get("announce_ip") or "0.0.0.0"),
            "default_voltage": float(
                hub.meta.get("default_voltage") or self._default_voltage or DEFAULT_VOLTAGE
            ),
            "shelly_model": self.shelly_model,
            "shelly_app": self.shelly_app,
            "shelly_profile": self.shelly_profile,
            "shelly_em": self.em_kind,
        }

    def _meter_payload(self, hub: Any, method: str, client: str) -> dict[str, Any] | None:
        reading: Reading | None
        if needs_meter_payload(method):
            reading = hub.read_source(
                self.source_id,
                reason=f"Shelly {method} von {client}",
            )
        else:
            reading = hub.snapshot_source(self.source_id)
        if reading is None:
            return None
        return reading.to_ecotracker()

    def mdns_services(self, ip: str, port: int) -> list[Any]:
        from zeroconf import ServiceInfo

        props = mdns_properties(self._hostname)
        infos: list[Any] = []
        for service_type in ("_shelly._tcp.local.", "_http._tcp.local."):
            info = ServiceInfo(
                service_type,
                f"{self._hostname}.{service_type}",
                addresses=[socket.inet_aton(ip)],
                port=port,
                properties=props,
                server=f"{self._hostname}.local.",
            )
            infos.append(info)
        return infos

    def _handle_rpc(
        self,
        method: str,
        *,
        client: str,
        hub: Any,
        rpc_id: Any = None,
        src: str | None = None,
    ) -> tuple[int, bytes, str]:
        payload = self._meter_payload(hub, method, client)
        meta = self._rpc_meta(hub)
        if needs_meter_payload(method) and payload is None:
            LOG.warning("Shelly %s von %s → 503 (keine Meter-Daten)", method, client)
            err = {"code": -104, "message": "no meter data yet"}
            if rpc_id is not None:
                frame: dict[str, Any] = {
                    "id": rpc_id,
                    "src": self._hostname,
                    "error": err,
                }
                if src:
                    frame["dst"] = src
                return _json_response(200, frame)
            return _json_response(503, {"error": "noch keine Daten vom physischen EcoTracker"})

        result = dispatch_rpc(method, payload, meta)
        if result is None:
            LOG.warning("Shelly unbekannte Methode %s von %s", method, client)
            err = {"code": -114, "message": f"Method '{method}' not found"}
            if rpc_id is not None:
                frame = {
                    "id": rpc_id,
                    "src": self._hostname,
                    "error": err,
                }
                if src:
                    frame["dst"] = src
                return _json_response(200, frame)
            return _json_response(404, err)

        power = (payload or {}).get("power") if payload else None
        LOG.debug("Shelly %s von %s → 200 power=%s W", method, client, power)
        if rpc_id is not None:
            frame = {
                "id": rpc_id,
                "src": self._hostname,
                "result": result,
            }
            if src:
                frame["dst"] = src
            return _json_response(200, frame)
        return _json_response(200, result)

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
        shelly_paths = (
            path in ("/shelly", "/shelly/", "/rpc", "/rpc/")
            or path.startswith("/rpc/")
        )
        if not shelly_paths and http_method != "POST":
            return None
        if http_method == "POST" and path not in ("/rpc", "/rpc/"):
            return None
        if not shelly_paths and http_method == "POST":
            return None
        if not should_claim(self, hub, headers):
            return None

        if path in ("/shelly", "/shelly/"):
            return self._handle_rpc("Shelly.GetDeviceInfo", client=client, hub=hub)

        if http_method == "GET":
            if path.startswith("/rpc/") or path in ("/rpc", "/rpc/"):
                method = path[len("/rpc/") :].strip("/") if path.startswith("/rpc/") else ""
                if method:
                    return self._handle_rpc(method, client=client, hub=hub)
                LOG.debug("GET /rpc von %s → ListMethods", client)
                return self._handle_rpc("Shelly.ListMethods", client=client, hub=hub)

        if http_method == "POST" and path in ("/rpc", "/rpc/"):
            try:
                req = json.loads(body.decode("utf-8") or "{}")
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                LOG.warning("POST /rpc von %s → ungültiges JSON: %s", client, exc)
                return _json_response(400, {"error": "invalid json"})
            if not isinstance(req, dict):
                return _json_response(400, {"error": "rpc body must be object"})
            method = str(req.get("method") or "")
            if not method:
                return _json_response(400, {"error": "missing method"})
            rpc_id = req.get("id")
            src = req.get("src")
            return self._handle_rpc(
                method,
                client=client,
                hub=hub,
                rpc_id=rpc_id,
                src=str(src) if src else None,
            )

        return None
