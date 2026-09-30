"""Generic HTTP JSON smart-meter reader with configurable jsonpath fields."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone, timedelta
from typing import Any
from urllib.request import Request, urlopen

from jsonpath import extract_float
from model import Reading
from sources.base import PollingSource

LOG = logging.getLogger("ecotracker-bridge")

_FETCH_HEADERS = {"Accept": "application/json", "User-Agent": "ecotracker-bridge/1.3.2"}
_DEFAULT_TIMEOUT_S = 4.0
_BERLIN = timezone(timedelta(hours=2))


def _berlin_tz():
    try:
        from zoneinfo import ZoneInfo

        return ZoneInfo("Europe/Berlin")
    except Exception:
        return _BERLIN


def berlin_now() -> datetime:
    return datetime.now(_berlin_tz())


class HttpJsonSource(PollingSource):
    type = "http_json"

    def __init__(self, cfg: dict[str, Any]) -> None:
        super().__init__(cfg)
        self.url = str(cfg.get("url") or "").strip()
        if not self.url:
            raise ValueError("http_json: url fehlt")
        self.json_power = str(cfg.get("json_power") or "power")
        self.json_power_l1 = cfg.get("json_power_l1")
        self.json_power_l2 = cfg.get("json_power_l2")
        self.json_power_l3 = cfg.get("json_power_l3")
        self.json_energy_in = cfg.get("json_energy_in")
        self.json_energy_out = cfg.get("json_energy_out")
        self.json_power_avg = cfg.get("json_power_avg")
        self.json_voltage = cfg.get("json_voltage")
        self._timeout_s = float(cfg.get("timeout") or _DEFAULT_TIMEOUT_S)

    def fetch(self) -> Reading:
        req = Request(self.url, headers=_FETCH_HEADERS, method="GET")
        with urlopen(req, timeout=self._timeout_s) as resp:
            body = resp.read()
        data = json.loads(body)
        if not isinstance(data, dict):
            raise ValueError("Antwort ist kein JSON-Objekt")

        power = extract_float(data, self.json_power)
        if power is None:
            raise ValueError(f"json_power Pfad liefert keinen Wert: {self.json_power!r}")

        fetched_at = berlin_now()
        raw = json.dumps(data, separators=(",", ":")).encode("utf-8")
        return Reading(
            power_w=power,
            power_l1_w=extract_float(data, self.json_power_l1) if self.json_power_l1 else None,
            power_l2_w=extract_float(data, self.json_power_l2) if self.json_power_l2 else None,
            power_l3_w=extract_float(data, self.json_power_l3) if self.json_power_l3 else None,
            voltage_v=extract_float(data, self.json_voltage) if self.json_voltage else None,
            energy_import_wh=extract_float(data, self.json_energy_in) if self.json_energy_in else None,
            energy_export_wh=extract_float(data, self.json_energy_out) if self.json_energy_out else None,
            power_avg_w=extract_float(data, self.json_power_avg) if self.json_power_avg else None,
            extra=dict(data),
            source_id=self.id,
            fetched_at=fetched_at,
            raw=raw,
        )
