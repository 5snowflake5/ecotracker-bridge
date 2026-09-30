"""Physical Shelly energy meters (1PM / EM / 3EM / Pro 3EM)."""

from __future__ import annotations

from typing import Any

from sources.base import PollingSource
from sources.http_util import cfg_base_url, fetch_json, watts_reading


class ShellySource(PollingSource):
    type = "shelly"

    def __init__(self, cfg: dict[str, Any]) -> None:
        super().__init__(cfg)
        self.base = cfg_base_url(cfg)
        self.model = str(cfg.get("shelly_model") or cfg.get("model") or "3empro").lower()
        self.user = str(cfg.get("user") or "") or None
        self.password = str(cfg.get("password") or "") or None
        self.index = str(cfg.get("meter_index") or "")
        self._timeout = float(cfg.get("timeout") or 4)

    def fetch(self):
        kw = {"timeout": self._timeout, "user": self.user, "password": self.password}
        if self.model in ("3empro", "pro3em", "3em_pro"):
            data = fetch_json(f"{self.base}/rpc/EM.GetStatus?id=0", **kw)
            l1 = float(data.get("a_act_power") or 0)
            l2 = float(data.get("b_act_power") or 0)
            l3 = float(data.get("c_act_power") or 0)
            total = float(data.get("total_act_power") if data.get("total_act_power") is not None else l1 + l2 + l3)
            return watts_reading(total, source_id=self.id, l1=l1, l2=l2, l3=l3, extra=data)
        if self.model in ("plus1pm", "1pm_plus"):
            data = fetch_json(f"{self.base}/rpc/Switch.GetStatus?id=0", **kw)
            return watts_reading(float(data["apower"]), source_id=self.id, extra=data)
        if self.model in ("1pm",):
            if self.index:
                data = fetch_json(f"{self.base}/meter/{self.index}", **kw)
                return watts_reading(float(data["power"]), source_id=self.id, extra=data)
            data = fetch_json(f"{self.base}/status", **kw)
            meters = data.get("meters") or []
            watts = [float(m.get("power") or 0) for m in meters]
            return watts_reading(sum(watts) if watts else 0, source_id=self.id, extra=data)
        # EM / 3EM gen1
        if self.index:
            data = fetch_json(f"{self.base}/emeter/{self.index}", **kw)
            return watts_reading(float(data["power"]), source_id=self.id, extra=data)
        data = fetch_json(f"{self.base}/status", **kw)
        emeters = data.get("emeters") or []
        watts = [float(m.get("power") or 0) for m in emeters]
        l1 = watts[0] if len(watts) > 0 else None
        l2 = watts[1] if len(watts) > 1 else None
        l3 = watts[2] if len(watts) > 2 else None
        return watts_reading(sum(watts), source_id=self.id, l1=l1, l2=l2, l3=l3, extra=data)
