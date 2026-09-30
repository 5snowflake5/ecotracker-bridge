"""HomeWizard P1 / kWh meter — local HTTP v1, optional v2 Bearer token."""

from __future__ import annotations

from typing import Any

from sources.base import PollingSource
from sources.http_util import cfg_base_url, fetch_json, watts_reading


class HomeWizardSource(PollingSource):
    type = "homewizard"

    def __init__(self, cfg: dict[str, Any]) -> None:
        super().__init__(cfg)
        self.token = str(cfg.get("token") or cfg.get("ha_token") or "")
        self.insecure = bool(cfg.get("insecure_tls") or cfg.get("verify_ssl") is False)
        self._timeout = float(cfg.get("timeout") or 4)
        if self.token:
            host = str(cfg.get("host") or cfg.get("ip") or "").strip().rstrip("/")
            if host.startswith("http"):
                self.url = host.rstrip("/") + "/api/measurement"
            else:
                self.url = f"https://{host}/api/measurement"
            self._headers = {"Authorization": f"Bearer {self.token}"}
        else:
            self.url = cfg_base_url(cfg) + "/api/v1/data"
            self._headers = None

    def fetch(self):
        data = fetch_json(
            self.url,
            timeout=self._timeout,
            headers=self._headers,
            insecure_tls=self.insecure or bool(self.token),
        )
        if not isinstance(data, dict):
            raise ValueError("HomeWizard: Antwort ist kein Objekt")
        power = data.get("active_power_w")
        if power is None:
            power = data.get("power_w")
        if power is None:
            raise ValueError("HomeWizard: kein active_power_w")
        l1 = data.get("active_power_l1_w", data.get("power_l1_w"))
        l2 = data.get("active_power_l2_w", data.get("power_l2_w"))
        l3 = data.get("active_power_l3_w", data.get("power_l3_w"))
        e_in = data.get("total_power_import_kwh")
        e_out = data.get("total_power_export_kwh")
        return watts_reading(
            float(power),
            source_id=self.id,
            l1=float(l1) if l1 is not None else None,
            l2=float(l2) if l2 is not None else None,
            l3=float(l3) if l3 is not None else None,
            energy_in_wh=float(e_in) * 1000.0 if e_in is not None else None,
            energy_out_wh=float(e_out) * 1000.0 if e_out is not None else None,
            extra=data,
        )
