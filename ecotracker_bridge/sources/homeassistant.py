"""Poll Home Assistant REST API for power/energy entity states."""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone, timedelta
from typing import Any
from urllib.request import Request, urlopen

from model import Reading
from sources.base import PollingSource

LOG = logging.getLogger("ecotracker-bridge")

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


def _default_ha_url() -> str:
    if os.environ.get("SUPERVISOR_TOKEN"):
        return "http://supervisor/core"
    return "http://127.0.0.1:8123"


class HomeAssistantSource(PollingSource):
    type = "homeassistant"

    def __init__(self, cfg: dict[str, Any]) -> None:
        super().__init__(cfg)
        self.ha_url = str(cfg.get("ha_url") or _default_ha_url()).rstrip("/")
        self.ha_token = str(cfg.get("ha_token") or os.environ.get("SUPERVISOR_TOKEN") or "")
        self.ha_power_entity = cfg.get("ha_power_entity")
        self.ha_power_l1_entity = cfg.get("ha_power_l1_entity")
        self.ha_power_l2_entity = cfg.get("ha_power_l2_entity")
        self.ha_power_l3_entity = cfg.get("ha_power_l3_entity")
        self.ha_energy_in_entity = cfg.get("ha_energy_in_entity")
        self.ha_energy_out_entity = cfg.get("ha_energy_out_entity")
        self._timeout_s = float(cfg.get("timeout") or _DEFAULT_TIMEOUT_S)

        three_phase = (
            self.ha_power_l1_entity
            and self.ha_power_l2_entity
            and self.ha_power_l3_entity
        )
        if not self.ha_power_entity and not three_phase:
            raise ValueError("homeassistant: ha_power_entity oder alle drei Phasen-Entitäten nötig")

    def _headers(self) -> dict[str, str]:
        h = {"Accept": "application/json", "User-Agent": "ecotracker-bridge/1.3.2"}
        if self.ha_token:
            h["Authorization"] = f"Bearer {self.ha_token}"
        return h

    def _fetch_entity_state(self, entity_id: str) -> float:
        url = f"{self.ha_url}/api/states/{entity_id}"
        req = Request(url, headers=self._headers(), method="GET")
        with urlopen(req, timeout=self._timeout_s) as resp:
            body = resp.read()
        data = json.loads(body)
        if not isinstance(data, dict):
            raise ValueError(f"HA Antwort für {entity_id!r} ist kein Objekt")
        state = data.get("state")
        if state in ("unavailable", "unknown", None):
            raise ValueError(f"HA Entität {entity_id!r} nicht verfügbar: {state!r}")
        try:
            return float(state)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"HA Entität {entity_id!r} kein numerischer state: {state!r}") from exc

    def fetch(self) -> Reading:
        fetched_at = berlin_now()
        power_w: float
        power_l1: float | None = None
        power_l2: float | None = None
        power_l3: float | None = None

        if self.ha_power_l1_entity and self.ha_power_l2_entity and self.ha_power_l3_entity:
            power_l1 = self._fetch_entity_state(str(self.ha_power_l1_entity))
            power_l2 = self._fetch_entity_state(str(self.ha_power_l2_entity))
            power_l3 = self._fetch_entity_state(str(self.ha_power_l3_entity))
            power_w = power_l1 + power_l2 + power_l3
        else:
            power_w = self._fetch_entity_state(str(self.ha_power_entity))

        energy_in = (
            self._fetch_entity_state(str(self.ha_energy_in_entity))
            if self.ha_energy_in_entity
            else None
        )
        energy_out = (
            self._fetch_entity_state(str(self.ha_energy_out_entity))
            if self.ha_energy_out_entity
            else None
        )

        return Reading(
            power_w=power_w,
            power_l1_w=power_l1,
            power_l2_w=power_l2,
            power_l3_w=power_l3,
            energy_import_wh=energy_in,
            energy_export_wh=energy_out,
            source_id=self.id,
            fetched_at=fetched_at,
        )
