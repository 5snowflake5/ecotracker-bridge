"""Additional HTTP sources (AMIS, VZLogger, ESPHome, Refoss, ioBroker, Envoy, Shrdzm)."""

from __future__ import annotations

from typing import Any

from jsonpath import extract_float
from sources.base import PollingSource
from sources.http_util import cfg_base_url, fetch_json, watts_reading


class AmisReaderSource(PollingSource):
    type = "amis_reader"

    def __init__(self, cfg: dict[str, Any]) -> None:
        super().__init__(cfg)
        self.url = cfg_base_url(cfg) + "/rest"
        self._timeout = float(cfg.get("timeout") or 4)

    def fetch(self):
        data = fetch_json(self.url, timeout=self._timeout)
        return watts_reading(float(data["saldo"]), source_id=self.id, extra=data)


class VZLoggerSource(PollingSource):
    type = "vzlogger"

    def __init__(self, cfg: dict[str, Any]) -> None:
        super().__init__(cfg)
        ip = str(cfg.get("ip") or cfg.get("host") or "").strip()
        if not ip:
            raise ValueError("vzlogger: ip fehlt")
        port = int(cfg.get("port") or 8080)
        self.base = f"http://{ip}:{port}"
        uuids = str(cfg.get("uuid") or "")
        self.uuids = [u.strip() for u in uuids.split(",") if u.strip()]
        if not self.uuids:
            raise ValueError("vzlogger: uuid fehlt")
        self._timeout = float(cfg.get("timeout") or 4)

    def fetch(self):
        watts = []
        for uuid in self.uuids:
            data = fetch_json(f"{self.base}/{uuid}", timeout=self._timeout)
            watts.append(float(data["data"][0]["tuples"][0][1]))
        l1 = watts[0] if len(watts) > 1 else None
        l2 = watts[1] if len(watts) > 1 else None
        l3 = watts[2] if len(watts) > 2 else None
        return watts_reading(sum(watts), source_id=self.id, l1=l1, l2=l2, l3=l3)


class ESPHomeSource(PollingSource):
    type = "esphome"

    def __init__(self, cfg: dict[str, Any]) -> None:
        super().__init__(cfg)
        ip = str(cfg.get("ip") or cfg.get("host") or "").strip()
        if not ip:
            raise ValueError("esphome: ip fehlt")
        port = int(cfg.get("port") or 80)
        domain = str(cfg.get("domain") or "sensor")
        sensor_id = str(cfg.get("sensor_id") or cfg.get("object_id") or "")
        if not sensor_id:
            raise ValueError("esphome: sensor_id fehlt")
        self.url = f"http://{ip}:{port}/{domain}/{sensor_id}"
        self._timeout = float(cfg.get("timeout") or 4)

    def fetch(self):
        data = fetch_json(self.url, timeout=self._timeout)
        return watts_reading(float(data["value"]), source_id=self.id, extra=data)


class RefossSource(PollingSource):
    type = "refoss"

    def __init__(self, cfg: dict[str, Any]) -> None:
        super().__init__(cfg)
        self.base = cfg_base_url(cfg)
        raw = str(cfg.get("channels") or "1")
        self.channels = [int(p.strip()) for p in raw.split(",") if p.strip()]
        self._timeout = float(cfg.get("timeout") or 4)

    def fetch(self):
        data = fetch_json(f"{self.base}/rpc/Em.Status.Get?id=65535", timeout=self._timeout)
        status = data.get("status")
        if not isinstance(status, list):
            raise ValueError("refoss: status fehlt")
        by_id = {int(e["id"]): float(e["power"]) for e in status if isinstance(e, dict) and "id" in e}
        watts = [by_id[ch] for ch in self.channels]
        l1 = watts[0] if len(watts) > 1 else None
        l2 = watts[1] if len(watts) > 1 else None
        l3 = watts[2] if len(watts) > 2 else None
        return watts_reading(sum(watts), source_id=self.id, l1=l1, l2=l2, l3=l3, extra=data)


class IoBrokerSource(PollingSource):
    type = "iobroker"

    def __init__(self, cfg: dict[str, Any]) -> None:
        super().__init__(cfg)
        ip = str(cfg.get("ip") or cfg.get("host") or "").strip()
        if not ip:
            raise ValueError("iobroker: ip fehlt")
        port = int(cfg.get("port") or 8087)
        self.base = f"http://{ip}:{port}"
        self.alias = str(cfg.get("alias") or cfg.get("json_power") or "")
        if not self.alias:
            raise ValueError("iobroker: alias fehlt")
        self._timeout = float(cfg.get("timeout") or 4)

    def fetch(self):
        from sources.http_util import fetch_bytes

        raw = fetch_bytes(f"{self.base}/getPlainValue/{self.alias}", timeout=self._timeout)
        return watts_reading(float(raw.decode().strip()), source_id=self.id)


class EnvoySource(PollingSource):
    type = "envoy"

    def __init__(self, cfg: dict[str, Any]) -> None:
        super().__init__(cfg)
        host = str(cfg.get("host") or cfg.get("ip") or "").strip().rstrip("/")
        if not host:
            raise ValueError("envoy: host fehlt")
        if not host.startswith("http"):
            host = f"https://{host}"
        self.url = host + "/production.json?details=1"
        self.token = str(cfg.get("token") or "")
        self._timeout = float(cfg.get("timeout") or 6)
        self._headers = {"Authorization": f"Bearer {self.token}"} if self.token else None

    def fetch(self):
        data = fetch_json(self.url, timeout=self._timeout, headers=self._headers, insecure_tls=True)
        cons = None
        for block in data.get("consumption") or []:
            if block.get("measurementType") == "net-consumption" or cons is None:
                cons = block
                if block.get("measurementType") == "net-consumption":
                    break
        if not cons:
            raise ValueError("envoy: kein consumption-Block")
        power = float(cons.get("wNow") or cons.get("whNow") or 0)
        return watts_reading(power, source_id=self.id, extra=cons)


class ShrdzmSource(PollingSource):
    type = "shrdzm"

    def __init__(self, cfg: dict[str, Any]) -> None:
        super().__init__(cfg)
        user = str(cfg.get("user") or "")
        password = str(cfg.get("password") or "")
        self.url = f"{cfg_base_url(cfg)}/getLastData?user={user}&pwd={password}"
        self._timeout = float(cfg.get("timeout") or 4)

    def fetch(self):
        data = fetch_json(self.url, timeout=self._timeout)
        power = extract_float(data, "16.7.0") or extract_float(data, "power") or data.get("1-0:16.7.0")
        if power is None:
            raise ValueError("shrdzm: keine Leistung im JSON")
        return watts_reading(float(power), source_id=self.id, extra=data if isinstance(data, dict) else {})
