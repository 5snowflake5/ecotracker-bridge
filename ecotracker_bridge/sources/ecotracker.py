"""Pull readings from a physical everHome EcoTracker /v1/json endpoint."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone, timedelta
from typing import Any
from urllib.request import Request, urlopen

from model import reading_from_ecotracker
from sources.base import PollingSource

LOG = logging.getLogger("ecotracker-bridge")

_VERSION = "1.3.2"
_FETCH_HEADERS = {"Accept": "application/json", "User-Agent": f"ecotracker-bridge/{_VERSION}"}
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


def normalize_ecotracker_url(raw: str) -> str:
    url = str(raw or "").strip().rstrip("/")
    if not url.endswith("/v1/json"):
        url = f"{url}/v1/json"
    return url


class EcoTrackerSource(PollingSource):
    type = "ecotracker"

    def __init__(self, cfg: dict[str, Any]) -> None:
        super().__init__(cfg)
        raw_url = cfg.get("url") or cfg.get("source_url") or ""
        self.url = normalize_ecotracker_url(str(raw_url))
        self._timeout_s = float(cfg.get("timeout") or _DEFAULT_TIMEOUT_S)

    def fetch(self):
        req = Request(self.url, headers=_FETCH_HEADERS, method="GET")
        with urlopen(req, timeout=self._timeout_s) as resp:
            body = resp.read()
        data = json.loads(body)
        if not isinstance(data, dict):
            raise ValueError("Antwort ist kein JSON-Objekt")
        raw = json.dumps(data, separators=(",", ":")).encode("utf-8")
        fetched_at = berlin_now()
        return reading_from_ecotracker(
            data,
            source_id=self.id,
            fetched_at=fetched_at,
            raw=raw,
        )
