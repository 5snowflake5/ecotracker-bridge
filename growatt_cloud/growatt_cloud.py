#!/usr/bin/env python3
"""Growatt Cloud → MQTT für Home Assistant.

Ein Login (API-Token), Open API v4:
  - Noah und Nexa (deviceType=noah)
  - MIN-Wechselrichter (Balkon-WR)

Ersetzt die Combo noah-mqtt + Growatt-Server-Integration (Doppel-Login / Sperre).
"""

from __future__ import annotations

import json
import logging
import os
import signal
import sys
import time
from typing import Any

from api import (
    GrowattApiError,
    GrowattCloudApi,
    MIN_INTERVAL_NOAH_S,
    MIN_INTERVAL_OTHER_S,
    normalize_min,
    normalize_storage,
)
from mqtt_ha import HaMqtt

VERSION = "0.1.0"
OPTIONS_PATHS = ("/data/options.json", "options.json")
LOG = logging.getLogger("growatt-cloud")

# Gerätetypen, die wir als Speicher (Noah/Nexa) behandeln
STORAGE_TYPES = {"noah", "nexa"}
# Balkon-/String-WR
INVERTER_TYPES = {"min", "inv", "tlx"}


def setup_logging(level_name: str = "info") -> None:
    level = logging.DEBUG if str(level_name).lower() == "debug" else logging.INFO
    root = logging.getLogger()
    root.handlers.clear()
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
    )
    root.addHandler(handler)
    root.setLevel(level)


def load_options() -> dict[str, Any]:
    for path in OPTIONS_PATHS:
        if os.path.isfile(path):
            with open(path, encoding="utf-8") as fh:
                return json.load(fh)
    return {}


def env_or(opts: dict[str, Any], key: str, default: Any = "") -> Any:
    env_key = f"GROWATT_{key.upper()}"
    if env_key in os.environ and os.environ[env_key] != "":
        return os.environ[env_key]
    return opts.get(key, default)


class Bridge:
    def __init__(self, opts: dict[str, Any]) -> None:
        self.opts = opts
        self.stop = False
        token = str(env_or(opts, "api_token", "")).strip()
        server = str(env_or(opts, "server_url", "https://openapi.growatt.com")).strip()
        self.api = GrowattCloudApi(token=token, server_url=server)

        self.poll_storage_s = max(
            MIN_INTERVAL_NOAH_S,
            int(env_or(opts, "poll_storage_seconds", MIN_INTERVAL_NOAH_S)),
        )
        self.poll_inverter_s = max(
            MIN_INTERVAL_OTHER_S,
            int(env_or(opts, "poll_inverter_seconds", MIN_INTERVAL_OTHER_S)),
        )
        self.poll_devices_s = max(300, int(env_or(opts, "poll_devices_seconds", 3600)))

        sn_storage = str(env_or(opts, "storage_sn", "")).strip()
        sn_inverter = str(env_or(opts, "inverter_sn", "")).strip()
        self.force_storage_sn = sn_storage or None
        self.force_inverter_sn = sn_inverter or None
        self.storage_family = str(env_or(opts, "storage_family", "auto")).strip().lower() or "auto"

        self.mqtt = HaMqtt(
            host=str(env_or(opts, "mqtt_host", "core-mosquitto")),
            port=int(env_or(opts, "mqtt_port", 1883)),
            username=str(env_or(opts, "mqtt_user", "")),
            password=str(env_or(opts, "mqtt_password", "")),
            discovery_prefix=str(env_or(opts, "mqtt_discovery_prefix", "homeassistant")),
            state_prefix=str(env_or(opts, "mqtt_state_prefix", "growatt_cloud")),
        )

        self.devices: list[dict[str, Any]] = []
        self._last_devices = 0.0
        self._last_storage: dict[str, float] = {}
        self._last_inverter: dict[str, float] = {}

    def request_stop(self, *_args) -> None:
        self.stop = True

    def refresh_devices(self, force: bool = False) -> None:
        now = time.monotonic()
        if not force and self.devices and (now - self._last_devices) < self.poll_devices_s:
            return
        rows = self.api.list_devices()
        self.devices = rows
        self._last_devices = now
        for row in rows:
            LOG.info(
                "Gerät: sn=%s type=%s",
                row.get("deviceSn") or row.get("device_sn"),
                row.get("deviceType") or row.get("device_type"),
            )

    def storage_targets(self) -> list[tuple[str, str]]:
        """[(sn, api_type)] – api_type immer noah für Open API."""
        if self.force_storage_sn:
            return [(self.force_storage_sn, "noah")]
        out: list[tuple[str, str]] = []
        for row in self.devices:
            sn = str(row.get("deviceSn") or row.get("device_sn") or "").strip()
            dtype = str(row.get("deviceType") or row.get("device_type") or "").strip().lower()
            if sn and dtype in STORAGE_TYPES:
                out.append((sn, "noah"))
        return out

    def inverter_targets(self) -> list[tuple[str, str]]:
        if self.force_inverter_sn:
            return [(self.force_inverter_sn, "min")]
        out: list[tuple[str, str]] = []
        for row in self.devices:
            sn = str(row.get("deviceSn") or row.get("device_sn") or "").strip()
            dtype = str(row.get("deviceType") or row.get("device_type") or "").strip().lower()
            if sn and dtype in INVERTER_TYPES:
                # BZP… typisch MIN
                api_type = "min" if dtype in ("min", "tlx") else dtype
                if api_type == "inv":
                    api_type = "min"
                out.append((sn, api_type))
        return out

    def poll_storage(self) -> None:
        now = time.monotonic()
        for sn, api_type in self.storage_targets():
            last = self._last_storage.get(sn, 0.0)
            if now - last < self.poll_storage_s:
                continue
            try:
                raw = self.api.query_last_data(sn, api_type)
                if self.storage_family in ("noah", "nexa"):
                    family = self.storage_family
                else:
                    blob = json.dumps(raw).lower()
                    family = "nexa" if "nexa" in blob else "noah"
                values = normalize_storage(raw, family=family)
                self.mqtt.ensure_storage_discovery(sn, values["label"])
                self.mqtt.publish_states(sn, values)
                self._last_storage[sn] = time.monotonic()
                LOG.info(
                    "%s %s SoC=%s%% PV=%.0fW Out=%.0fW Today=%.2fkWh",
                    values["label"],
                    sn,
                    values["soc"],
                    values["solar_power"],
                    values["output_power"],
                    values["generation_today"],
                )
            except GrowattApiError as exc:
                LOG.error("Speicher %s: %s", sn, exc)
                # bei Rate-Limit länger warten
                if exc.code in (100, 102, 10012):
                    self._last_storage[sn] = time.monotonic()

    def poll_inverter(self) -> None:
        now = time.monotonic()
        for sn, api_type in self.inverter_targets():
            last = self._last_inverter.get(sn, 0.0)
            if now - last < self.poll_inverter_s:
                continue
            try:
                raw = self.api.query_last_data(sn, api_type)
                values = normalize_min(raw)
                self.mqtt.ensure_inverter_discovery(sn)
                self.mqtt.publish_states(sn, values)
                self._last_inverter[sn] = time.monotonic()
                LOG.info(
                    "WR %s AC=%.0fW Today=%.2fkWh In1=%.2f In2=%.2f",
                    sn,
                    values["ac_power"],
                    values["energy_today"],
                    values["energy_today_input_1"],
                    values["energy_today_input_2"],
                )
            except GrowattApiError as exc:
                LOG.error("WR %s: %s", sn, exc)
                if exc.code in (100, 102, 10012):
                    self._last_inverter[sn] = time.monotonic()

    def run(self) -> None:
        LOG.info("growatt_cloud %s start", VERSION)
        self.mqtt.connect()
        while not self.stop:
            try:
                self.refresh_devices()
                if not self.storage_targets() and not self.inverter_targets():
                    LOG.warning("Keine Noah/Nexa/MIN-Geräte gefunden – Token/Plant prüfen")
                self.poll_storage()
                self.poll_inverter()
            except GrowattApiError as exc:
                LOG.error("API: %s", exc)
            except Exception:
                LOG.exception("Unerwarteter Fehler")
            # kurze Schleife; echte Intervalle stecken in poll_*
            for _ in range(10):
                if self.stop:
                    break
                time.sleep(1)
        self.mqtt.stop()
        LOG.info("stopped")


def main() -> None:
    opts = load_options()
    setup_logging(str(opts.get("log_level") or "info"))
    if not str(opts.get("api_token") or os.environ.get("GROWATT_API_TOKEN") or "").strip():
        LOG.error("api_token fehlt – in der App-Config den Growatt Open-API-Token eintragen")
        sys.exit(1)
    bridge = Bridge(opts)
    signal.signal(signal.SIGTERM, bridge.request_stop)
    signal.signal(signal.SIGINT, bridge.request_stop)
    bridge.run()


if __name__ == "__main__":
    main()
