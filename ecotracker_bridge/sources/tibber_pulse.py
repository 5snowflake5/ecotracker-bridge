"""Tibber Pulse Bridge — local /data.json (binary SML) with Basic auth."""

from __future__ import annotations

from typing import Any

from sources.base import PollingSource
from sources.http_util import cfg_base_url, fetch_bytes, watts_reading
from sources.sml import parse_sml_power


class TibberPulseSource(PollingSource):
    type = "tibber_pulse"

    def __init__(self, cfg: dict[str, Any]) -> None:
        super().__init__(cfg)
        self.base = cfg_base_url(cfg)
        self.user = str(cfg.get("user") or "admin")
        self.password = str(cfg.get("password") or "")
        if not self.password:
            raise ValueError("tibber_pulse: password (Aufdruck der Bridge) fehlt")
        self.node_id = str(cfg.get("node_id") or "1")
        self._timeout = float(cfg.get("timeout") or 8)
        self.power_obis = str(cfg.get("obis_power") or "0100100700ff")

    def fetch(self):
        last_err = None
        for path in (f"/node_data.json?node_id={self.node_id}", f"/data.json?node_id={self.node_id}"):
            try:
                raw = fetch_bytes(
                    f"{self.base}{path}",
                    timeout=self._timeout,
                    user=self.user,
                    password=self.password,
                )
                break
            except ValueError as exc:
                last_err = exc
                raw = None
        else:
            raise last_err or ValueError("tibber_pulse: kein data.json")
        if raw is None:
            raise last_err or ValueError("tibber_pulse: leer")
        parsed = parse_sml_power(raw, power_obis=self.power_obis)
        if parsed.get("power") is None:
            raise ValueError("tibber_pulse: keine Wirkleistung im SML (webserver-force-enable?)")
        return watts_reading(
            float(parsed["power"]),
            source_id=self.id,
            l1=parsed.get("l1"),
            l2=parsed.get("l2"),
            l3=parsed.get("l3"),
            energy_in_wh=parsed.get("energy_in"),
            energy_out_wh=parsed.get("energy_out"),
        )
