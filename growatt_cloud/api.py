"""Growatt Open API (token) – v4 new-api. Noah und Nexa teilen deviceType=noah."""

from __future__ import annotations

import json
import logging
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

LOG = logging.getLogger("growatt-cloud.api")

DEFAULT_SERVER = "https://openapi.growatt.com"

# Offizielle Limits (Showdoc / growatt-public-api):
# Noah/Nexa energy: 1/min · andere Geräte energy: 1/5min · Device-Liste: 1/5s
MIN_INTERVAL_NOAH_S = 60
MIN_INTERVAL_OTHER_S = 300
MIN_INTERVAL_LIST_S = 5


class GrowattApiError(RuntimeError):
    def __init__(self, message: str, code: int | None = None):
        super().__init__(message)
        self.code = code


class GrowattCloudApi:
    def __init__(self, token: str, server_url: str = DEFAULT_SERVER) -> None:
        self.token = (token or "").strip()
        self.server_url = (server_url or DEFAULT_SERVER).rstrip("/")
        if not self.token:
            raise ValueError("Growatt API-Token fehlt")
        self._last_list = 0.0
        self._last_energy: dict[str, float] = {}

    def _request(
        self,
        method: str,
        path: str,
        params: dict[str, Any] | None = None,
        data: dict[str, Any] | None = None,
        timeout: float = 30.0,
    ) -> dict[str, Any]:
        # Session der Lib nutzt base .../v4 + endpoint; beides funktioniert.
        url = f"{self.server_url}/v4/{path.lstrip('/')}"
        if params:
            url = f"{url}?{urllib.parse.urlencode(params)}"
        body = None
        headers = {"token": self.token, "Accept": "application/json"}
        if data is not None:
            body = urllib.parse.urlencode(data).encode("utf-8")
            headers["Content-Type"] = "application/x-www-form-urlencoded"
        req = urllib.request.Request(url, data=body, headers=headers, method=method.upper())
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode("utf-8", errors="replace")
            raise GrowattApiError(f"HTTP {exc.code}: {raw[:300]}", code=exc.code) from exc
        except urllib.error.URLError as exc:
            raise GrowattApiError(f"Netzwerk: {exc.reason}") from exc

        if "<html" in raw.lower() and "login" in raw.lower():
            raise GrowattApiError("Growatt zeigt Login-Seite (Token ungültig oder Server falsch)")

        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise GrowattApiError(f"Keine JSON-Antwort: {raw[:200]}") from exc

        code = payload.get("error_code")
        if code is None:
            code = payload.get("code")
        if code not in (None, 0, "0", ""):
            msg = payload.get("error_msg") or payload.get("message") or "API-Fehler"
            raise GrowattApiError(f"{msg} (code={code})", code=int(code) if str(code).lstrip("-").isdigit() else None)
        return payload

    def list_devices(self, page: int = 1) -> list[dict[str, Any]]:
        now = time.monotonic()
        wait = MIN_INTERVAL_LIST_S - (now - self._last_list)
        if wait > 0:
            time.sleep(wait)
        payload = self._request("POST", "new-api/queryDeviceList", params={"page": page})
        self._last_list = time.monotonic()
        data = payload.get("data") or {}
        rows = data.get("data") or []
        if not isinstance(rows, list):
            return []
        return [r for r in rows if isinstance(r, dict)]

    def query_last_data(self, device_sn: str, device_type: str) -> dict[str, Any]:
        """Rohdaten von queryLastData. device_type z.B. noah | min | inv."""
        dtype = (device_type or "").strip().lower()
        # Nexa erscheint in der Geräteliste als type=noah
        if dtype in ("nexa", "noah/nexa"):
            dtype = "noah"
        key = f"{dtype}:{device_sn}"
        min_interval = MIN_INTERVAL_NOAH_S if dtype == "noah" else MIN_INTERVAL_OTHER_S
        now = time.monotonic()
        last = self._last_energy.get(key, 0.0)
        wait = min_interval - (now - last)
        if wait > 0:
            time.sleep(wait)

        payload = self._request(
            "POST",
            "new-api/queryLastData",
            params={"deviceSn": device_sn, "deviceType": dtype},
        )
        self._last_energy[key] = time.monotonic()

        block = (payload.get("data") or {}).get(dtype)
        if isinstance(block, list) and block:
            return block[0] if isinstance(block[0], dict) else {}
        if isinstance(block, dict):
            return block
        # manchmals Key "noah" auch für Nexa; Fallback: erstes Dict in data
        data = payload.get("data") or {}
        if isinstance(data, dict):
            for value in data.values():
                if isinstance(value, list) and value and isinstance(value[0], dict):
                    return value[0]
                if isinstance(value, dict) and ("deviceSn" in value or "device_sn" in value or "ppv" in value):
                    return value
        return {}


def _num(data: dict[str, Any], *keys: str, default: float = 0.0) -> float:
    for key in keys:
        if key in data and data[key] not in (None, ""):
            try:
                return float(data[key])
            except (TypeError, ValueError):
                continue
    return default


def _int(data: dict[str, Any], *keys: str, default: int = 0) -> int:
    return int(_num(data, *keys, default=float(default)))


def normalize_storage(raw: dict[str, Any], family: str = "noah") -> dict[str, Any]:
    """Noah/Nexa Live-Werte → einheitliche Sensor-Map."""
    bat = _num(raw, "totalBatteryPackChargingPower", "total_battery_pack_charging_power")
    status = _int(raw, "totalBatteryPackChargingStatus", "total_battery_pack_charging_status")
    if status == 1:
        charge_w, discharge_w = abs(bat), 0.0
    elif status == 2:
        charge_w, discharge_w = 0.0, abs(bat)
    else:
        charge_w = max(bat, 0.0)
        discharge_w = abs(min(bat, 0.0))

    model = str(raw.get("model") or raw.get("modelName") or raw.get("alias") or family).strip()
    label = "Nexa" if "nexa" in model.lower() or family.lower() == "nexa" else "Noah"

    return {
        "family": label.lower(),
        "label": label,
        "soc": _num(raw, "totalBatteryPackSoc", "total_battery_pack_soc"),
        "solar_power": _num(raw, "ppv"),
        "output_power": abs(_num(raw, "pac")),
        "charging_power": charge_w,
        "discharge_power": discharge_w,
        "generation_today": _num(raw, "eacToday", "eac_today"),
        "generation_total": _num(raw, "eacTotal", "eac_total"),
        "system_temp": _num(raw, "systemTemp", "system_temp"),
        "work_mode": _int(raw, "workMode", "work_mode"),
        "status": _int(raw, "status"),
        "ct_power": _num(raw, "ctSelfPower", "ct_self_power"),
        "time": raw.get("timeStr") or raw.get("time_str") or raw.get("time"),
    }


def normalize_min(raw: dict[str, Any]) -> dict[str, Any]:
    """MIN/Wechselrichter (Balkon-WR) → Sensor-Map."""
    return {
        "family": "min",
        "label": "Wechselrichter",
        "ac_power": _num(raw, "pac"),
        "energy_today": _num(raw, "eacToday", "eac_today", "powerToday", "power_today"),
        "energy_total": _num(raw, "eacTotal", "eac_total", "powerTotal", "power_total"),
        "energy_today_input_1": _num(raw, "epv1Today", "epv1_today"),
        "energy_today_input_2": _num(raw, "epv2Today", "epv2_today"),
        "ppv": _num(raw, "ppv"),
        "ppv1": _num(raw, "ppv1"),
        "ppv2": _num(raw, "ppv2"),
        "status": raw.get("statusText") or raw.get("status_text") or raw.get("status"),
        "time": raw.get("time") or raw.get("timeStr") or raw.get("time_str"),
    }
