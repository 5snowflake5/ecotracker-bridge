"""Shelly Pro 3EM RPC helpers – gleiche Messwerte wie EcoTracker-Cache, anderes Wire-Format."""

from __future__ import annotations

from typing import Any


DEFAULT_VOLTAGE = 230.0
DEFAULT_PF = 1.0
FW_ID = "20250924-062729/1.7.1-gd336f31"
FW_VER = "1.7.1"
MODEL = "SPEM-003CEBEU"


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
    # Mono: Gesamtleistung auf Phase A (wie viele Speicher erwarten).
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
    # EcoTracker: Wh. Shelly EMData: Wh.
    energy_in = float(payload.get("energyCounterIn") or 0)
    energy_out = float(payload.get("energyCounterOut") or 0)
    # Auf Phasen verteilen nur wenn Phasenleistung da – sonst alles auf A.
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


def shelly_get_device_info(mac: str, hostname: str) -> dict[str, Any]:
    mac = mac.upper()
    return {
        "name": None,
        "id": hostname,
        "mac": mac,
        "slot": 0,
        "model": MODEL,
        "gen": 2,
        "fw_id": FW_ID,
        "ver": FW_VER,
        "app": "Pro3EM",
        "auth_en": False,
        "auth_domain": None,
        "profile": "triphase",
    }


def shelly_get_status(payload: dict[str, Any], *, mac: str, ip: str, voltage: float = DEFAULT_VOLTAGE) -> dict[str, Any]:
    em = em_get_status(payload, voltage=voltage)
    emdata = emdata_get_status(payload)
    return {
        "ble": {},
        "cloud": {"connected": False},
        "em:0": em,
        "emdata:0": emdata,
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
    data = payload or {}
    key = method.lower()

    if key in ("shelly.getdeviceinfo",):
        return shelly_get_device_info(mac, hostname)
    if key in ("em.getstatus",):
        return em_get_status(data, voltage=voltage)
    if key in ("emdata.getstatus",):
        return emdata_get_status(data)
    if key in ("shelly.getstatus",):
        return shelly_get_status(data, mac=mac, ip=ip, voltage=voltage)
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
                "EM.GetConfig",
                "EMData.GetStatus",
                "EMData.GetConfig",
                "Cloud.GetStatus",
                "WiFi.GetStatus",
            ]
        }
    return None
