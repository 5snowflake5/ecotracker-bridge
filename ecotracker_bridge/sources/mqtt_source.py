"""MQTT push source: last message on topic becomes the reading."""

from __future__ import annotations

import json
import logging
import os
import threading
from datetime import datetime, timezone, timedelta
from typing import Any

from jsonpath import extract_float
from model import Reading, Source

LOG = logging.getLogger("ecotracker-bridge")

_BERLIN = timezone(timedelta(hours=2))


def _berlin_tz():
    try:
        from zoneinfo import ZoneInfo

        return ZoneInfo("Europe/Berlin")
    except Exception:
        return _BERLIN


def berlin_now() -> datetime:
    return datetime.now(_berlin_tz())


class MqttSource(Source):
    type = "mqtt"

    def __init__(self, cfg: dict[str, Any]) -> None:
        self.id = str(cfg.get("id") or self.type)
        self.label = str(cfg.get("label") or self.id)
        self.mqtt_host = str(cfg.get("mqtt_host") or "core-mosquitto")
        self.mqtt_port = int(cfg.get("mqtt_port") or 1883)
        self.mqtt_user = cfg.get("mqtt_user")
        self.mqtt_password = cfg.get("mqtt_password")
        topic = cfg.get("mqtt_topic")
        if not topic:
            raise ValueError("mqtt: mqtt_topic fehlt")
        self.mqtt_topic = str(topic)
        self.json_power = cfg.get("json_power")
        self.json_power_l1 = cfg.get("json_power_l1")
        self.json_power_l2 = cfg.get("json_power_l2")
        self.json_power_l3 = cfg.get("json_power_l3")
        self.json_energy_in = cfg.get("json_energy_in")
        self.json_energy_out = cfg.get("json_energy_out")
        self._lock = threading.Lock()
        self._last: Reading | None = None
        self._client: Any = None

    def start(self) -> None:
        try:
            import paho.mqtt.client as mqtt
        except ImportError:
            LOG.error("MQTT: paho-mqtt nicht installiert")
            return

        client = mqtt.Client(client_id=f"ecotracker-bridge-src-{os.getpid()}-{self.id}")
        if self.mqtt_user:
            client.username_pw_set(str(self.mqtt_user), self.mqtt_password or None)

        source_id = self.id

        def on_connect(client, userdata, flags, rc, properties=None):  # noqa: ARG001
            if rc == 0:
                LOG.info("MQTT Quelle %s verbunden: %s:%s", source_id, self.mqtt_host, self.mqtt_port)
                client.subscribe(self.mqtt_topic)
            else:
                LOG.error(
                    "MQTT Quelle %s connect rc=%s (%s:%s)",
                    source_id,
                    rc,
                    self.mqtt_host,
                    self.mqtt_port,
                )

        def on_message(client, userdata, msg):  # noqa: ARG001
            try:
                reading = self._parse_payload(msg.payload)
            except Exception as exc:
                LOG.debug("MQTT Quelle %s Nachricht ungültig: %s", source_id, exc)
                return
            reading.source_id = source_id
            with self._lock:
                self._last = reading
            LOG.debug("MQTT Quelle %s: power=%s W", source_id, reading.power_w)

        client.on_connect = on_connect
        client.on_message = on_message
        try:
            client.connect_async(self.mqtt_host, self.mqtt_port, keepalive=60)
            client.loop_start()
            self._client = client
        except Exception as exc:
            LOG.error(
                "MQTT Quelle %s Verbindung fehlgeschlagen (%s:%s): %s",
                self.id,
                self.mqtt_host,
                self.mqtt_port,
                exc,
            )

    def stop(self) -> None:
        client = self._client
        self._client = None
        if client is None:
            return
        try:
            client.loop_stop()
            client.disconnect()
        except Exception:
            pass

    def _parse_payload(self, payload: bytes) -> Reading:
        fetched_at = berlin_now()
        text = payload.decode("utf-8", errors="replace").strip()
        if self.json_power:
            data = json.loads(text)
            if not isinstance(data, dict):
                raise ValueError("JSON-Payload ist kein Objekt")
            power = extract_float(data, self.json_power)
            if power is None:
                raise ValueError(f"json_power Pfad liefert keinen Wert: {self.json_power!r}")
            raw = json.dumps(data, separators=(",", ":")).encode("utf-8")
            return Reading(
                power_w=power,
                power_l1_w=extract_float(data, self.json_power_l1) if self.json_power_l1 else None,
                power_l2_w=extract_float(data, self.json_power_l2) if self.json_power_l2 else None,
                power_l3_w=extract_float(data, self.json_power_l3) if self.json_power_l3 else None,
                energy_import_wh=extract_float(data, self.json_energy_in) if self.json_energy_in else None,
                energy_export_wh=extract_float(data, self.json_energy_out) if self.json_energy_out else None,
                extra=dict(data),
                fetched_at=fetched_at,
                raw=raw,
            )
        power = float(text)
        return Reading(power_w=power, fetched_at=fetched_at, raw=payload)

    def snapshot(self) -> Reading | None:
        with self._lock:
            return self._last

    def stats(self) -> dict[str, Any]:
        with self._lock:
            last = self._last
        return {
            "id": self.id,
            "type": self.type,
            "label": self.label,
            "last_ok": last.fetched_at if last else None,
            "last_error": None,
            "polls_ok": 1 if last else 0,
            "polls_fail": 0,
        }

    def read(self, *, reason: str = "", force: bool = False) -> Reading | None:
        return self.snapshot()
