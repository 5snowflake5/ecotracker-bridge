"""Fronius Solar API GetMeterRealtimeData."""

from __future__ import annotations

from typing import Any

from sources.base import PollingSource
from sources.http_util import cfg_base_url, fetch_json, watts_reading


class FroniusSource(PollingSource):
    type = "fronius"

    def __init__(self, cfg: dict[str, Any]) -> None:
        super().__init__(cfg)
        self.base = cfg_base_url(cfg)
        self.device_id = str(cfg.get("device_id") or "0")
        self.per_phase = bool(cfg.get("per_phase"))
        self._timeout = float(cfg.get("timeout") or 4)

    def fetch(self):
        url = (
            f"{self.base}/solar_api/v1/GetMeterRealtimeData.cgi"
            f"?Scope=Device&DeviceId={self.device_id}"
        )
        response = fetch_json(url, timeout=self._timeout)
        status = (response.get("Head") or {}).get("Status") or {}
        if int(status.get("Code") or 0) != 0:
            raise ValueError(f"Fronius Status {status.get('Code')}: {status.get('Reason')}")
        data = response["Body"]["Data"]
        if self.per_phase:
            l1 = float(data.get("PowerReal_P_Phase_1") or 0)
            l2 = float(data.get("PowerReal_P_Phase_2") or 0)
            l3 = float(data.get("PowerReal_P_Phase_3") or 0)
            return watts_reading(l1 + l2 + l3, source_id=self.id, l1=l1, l2=l2, l3=l3, extra=data)
        return watts_reading(float(data["PowerReal_P_Sum"]), source_id=self.id, extra=data)
