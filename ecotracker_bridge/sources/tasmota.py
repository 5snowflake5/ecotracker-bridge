"""Tasmota Status 10 / MQTT JSON energy sensors."""

from __future__ import annotations

from typing import Any
from urllib.parse import urlencode

from sources.base import PollingSource
from sources.http_util import cfg_base_url, fetch_json, watts_reading


class TasmotaSource(PollingSource):
    type = "tasmota"

    def __init__(self, cfg: dict[str, Any]) -> None:
        super().__init__(cfg)
        self.base = cfg_base_url(cfg)
        self.user = str(cfg.get("user") or cfg.get("mqtt_user") or "")
        self.password = str(cfg.get("password") or cfg.get("mqtt_password") or "")
        self.json_status = str(cfg.get("json_status") or "StatusSNS")
        self.prefix = str(cfg.get("json_prefix") or cfg.get("mqtt_prefix") or "ENERGY")
        labels = str(cfg.get("json_power") or cfg.get("json_label") or "Power")
        self.labels = [p.strip() for p in labels.split(",") if p.strip()] or ["Power"]
        self.calculate = bool(cfg.get("power_calculate"))
        self.in_labels = [p.strip() for p in str(cfg.get("json_power_in") or "").split(",") if p.strip()]
        self.out_labels = [p.strip() for p in str(cfg.get("json_power_out") or "").split(",") if p.strip()]
        self._timeout = float(cfg.get("timeout") or 4)

    def fetch(self):
        if self.user:
            qs = urlencode({"user": self.user, "password": self.password, "cmnd": "status 10"})
        else:
            qs = "cmnd=status%2010"
        data = fetch_json(f"{self.base}/cm?{qs}", timeout=self._timeout)
        block = data[self.json_status][self.prefix]
        if self.calculate:
            if len(self.in_labels) != len(self.out_labels) or not self.in_labels:
                raise ValueError("tasmota: json_power_in/out nötig bei power_calculate")
            watts = [float(block[a]) - float(block[b]) for a, b in zip(self.in_labels, self.out_labels)]
        else:
            watts = [float(block[label]) for label in self.labels]
        l1 = watts[0] if len(watts) > 0 else None
        l2 = watts[1] if len(watts) > 1 else None
        l3 = watts[2] if len(watts) > 2 else None
        total = sum(watts)
        return watts_reading(total, source_id=self.id, l1=l1 if len(watts) > 1 else None, l2=l2, l3=l3, extra=block)
