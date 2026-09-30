"""MQTT Home Assistant Discovery – one device per source."""

from __future__ import annotations

import json
import logging
import os
import threading
from typing import Any

from util import VERSION

LOG = logging.getLogger("ecotracker-bridge")

MQTT_SENSOR_DEFS: list[tuple[str, str, str, str, str | None, str]] = [
    ("power", "Power", "power", "W", "power", "measurement"),
    ("powerAvg", "Power average (last minute)", "power_average", "W", "power", "measurement"),
    ("powerPhase1", "Power phase 1", "power_phase_1", "W", "power", "measurement"),
    ("powerPhase2", "Power phase 2", "power_phase_2", "W", "power", "measurement"),
    ("powerPhase3", "Power phase 3", "power_phase_3", "W", "power", "measurement"),
    ("energyCounterIn", "Total grid import", "energy_in", "Wh", "energy", "total_increasing"),
    ("energyCounterOut", "Total grid export", "energy_out", "Wh", "energy", "total_increasing"),
    ("agePower", "Milliseconds since last measurement", "age_power", "ms", None, "measurement"),
]

_MQTT_STALE_OBJECT_SUFFIXES = ("energy_in_t1", "energy_in_t2")

_LEGACY_SOURCE_IDS = frozenset({"grid", "ecotracker"})


def _mqtt_topics(source_id: str) -> tuple[str, str, str]:
    """state_topic, availability_topic, discovery object prefix segment."""
    if source_id in _LEGACY_SOURCE_IDS:
        return "ecotracker_bridge/state", "ecotracker_bridge/status", "ecotracker_bridge"
    base = f"ecotracker_bridge/{source_id}"
    return f"{base}/state", f"{base}/status", base


def _unique_id(source_id: str, object_suffix: str) -> str:
    if source_id in _LEGACY_SOURCE_IDS:
        return f"ecotracker_bridge_{object_suffix}"
    return f"ecotracker_bridge_{source_id}_{object_suffix}"


class MqttHaPublisher:
    """Veröffentlicht Cache-Werte per MQTT Home Assistant Discovery."""

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.client = None
        self.enabled = False
        self.host = "core-mosquitto"
        self.port = 1883
        self.username = ""
        self.password = ""
        self.prefix = "homeassistant"
        self._discovery_done: set[str] = set()
        self._last_error = ""
        self._hub: Any = None
        self._source_ids: list[str] = []

    def set_hub(self, hub: Any, source_ids: list[str]) -> None:
        self._hub = hub
        self._source_ids = list(source_ids)

    def configure(self, opts: dict[str, Any]) -> None:
        enabled = bool(opts.get("mqtt_enabled", True))
        host = str(opts.get("mqtt_host") or "core-mosquitto").strip()
        port = int(opts.get("mqtt_port") or 1883)
        username = str(opts.get("mqtt_user") or "")
        password = str(opts.get("mqtt_password") or "")
        prefix = str(opts.get("mqtt_discovery_prefix") or "homeassistant").strip() or "homeassistant"
        changed = (
            enabled != self.enabled
            or host != self.host
            or port != self.port
            or username != self.username
            or password != self.password
            or prefix != self.prefix
        )
        self.enabled = enabled
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.prefix = prefix
        if not enabled:
            self._disconnect()
            return
        if changed or self.client is None:
            self._connect()

    def _disconnect(self) -> None:
        with self.lock:
            if self.client is not None:
                try:
                    self.client.loop_stop()
                    self.client.disconnect()
                except Exception:
                    pass
                self.client = None
            self._discovery_done.clear()

    def _connect(self) -> None:
        self._disconnect()
        try:
            import paho.mqtt.client as mqtt
        except ImportError:
            LOG.error("MQTT: paho-mqtt nicht installiert")
            return
        client = mqtt.Client(client_id=f"ecotracker-bridge-{os.getpid()}")

        if self.username:
            client.username_pw_set(self.username, self.password or None)

        def on_connect(client, userdata, flags, rc, properties=None):  # noqa: ARG001
            if rc == 0:
                LOG.info("MQTT verbunden: %s:%s", self.host, self.port)
                self._discovery_done.clear()
                for sid in self._source_ids:
                    self.publish_discovery(sid)
                    self._publish_snapshot_state(sid)
            else:
                LOG.error("MQTT connect rc=%s (%s:%s)", rc, self.host, self.port)

        client.on_connect = on_connect
        try:
            client.connect_async(self.host, self.port, keepalive=60)
            client.loop_start()
            with self.lock:
                self.client = client
            self._last_error = ""
        except Exception as exc:
            self._last_error = str(exc)
            LOG.error("MQTT Verbindung fehlgeschlagen (%s:%s): %s", self.host, self.port, exc)

    def _publish_snapshot_state(self, source_id: str) -> None:
        if self._hub is None:
            return
        reading = self._hub.snapshot_source(source_id)
        if reading is not None:
            self.publish_state(source_id, reading.to_ecotracker())

    def publish_discovery(self, source_id: str) -> None:
        with self.lock:
            client = self.client
            if client is None or not self.enabled:
                return
            state_topic, avail_topic, obj_prefix = _mqtt_topics(source_id)
            device_name = "Meter Bridge" if source_id in _LEGACY_SOURCE_IDS else f"Meter Bridge ({source_id})"
            device_id = "ecotracker_bridge" if source_id in _LEGACY_SOURCE_IDS else f"ecotracker_bridge_{source_id}"
            device = {
                "identifiers": [device_id],
                "name": device_name,
                "manufacturer": "everHome",
                "model": "EcoTracker (via Bridge)",
                "sw_version": VERSION,
            }
            if source_id in _LEGACY_SOURCE_IDS:
                for stale in _MQTT_STALE_OBJECT_SUFFIXES:
                    topic = f"{self.prefix}/sensor/ecotracker_bridge/{stale}/config"
                    client.publish(topic, "", retain=True)
            for json_key, name, object_suffix, unit, device_class, state_class in MQTT_SENSOR_DEFS:
                uid = _unique_id(source_id, object_suffix)
                oid = f"ecotracker_{object_suffix}" if source_id in _LEGACY_SOURCE_IDS else f"ecotracker_{source_id}_{object_suffix}"
                cfg: dict[str, Any] = {
                    "name": name,
                    "object_id": oid,
                    "unique_id": uid,
                    "state_topic": state_topic,
                    "availability_topic": avail_topic,
                    "payload_available": "online",
                    "payload_not_available": "offline",
                    "value_template": f"{{{{ value_json.{json_key} | default(none, true) }}}}",
                    "unit_of_measurement": unit,
                    "state_class": state_class,
                    "device": device,
                    "force_update": True,
                }
                if device_class:
                    cfg["device_class"] = device_class
                topic = f"{self.prefix}/sensor/{obj_prefix}/{object_suffix}/config"
                client.publish(topic, json.dumps(cfg), retain=True)
            client.publish(avail_topic, "online", retain=True)
            self._discovery_done.add(source_id)
            LOG.info(
                "MQTT HA-Discovery für Quelle %s (%s Sensoren)",
                source_id,
                len(MQTT_SENSOR_DEFS),
            )

    def publish_state(self, source_id: str, payload: dict[str, Any]) -> None:
        with self.lock:
            client = self.client
            if client is None or not self.enabled:
                return
            body = {k: payload.get(k) for k, *_ in MQTT_SENSOR_DEFS if k in payload and payload.get(k) is not None}
            if not body:
                return
            state_topic, _, _ = _mqtt_topics(source_id)
            client.publish(state_topic, json.dumps(body), retain=True)
            LOG.debug("MQTT State [%s]: power=%s", source_id, body.get("power"))


MQTT = MqttHaPublisher()
