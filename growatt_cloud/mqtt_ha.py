"""Home Assistant MQTT Discovery + State Publish."""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Any

LOG = logging.getLogger("growatt-cloud.mqtt")


def slug(value: str) -> str:
    text = re.sub(r"[^a-zA-Z0-9_]+", "_", (value or "").strip().lower())
    return text.strip("_") or "device"


class HaMqtt:
    def __init__(
        self,
        host: str,
        port: int,
        username: str = "",
        password: str = "",
        discovery_prefix: str = "homeassistant",
        state_prefix: str = "growatt_cloud",
    ) -> None:
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.discovery_prefix = discovery_prefix.rstrip("/") or "homeassistant"
        self.state_prefix = state_prefix.rstrip("/") or "growatt_cloud"
        self._client = None
        self._discovery_done: set[str] = set()

    def connect(self) -> None:
        import paho.mqtt.client as mqtt

        client = mqtt.Client(client_id=f"growatt-cloud-{os.getpid()}")
        if self.username:
            client.username_pw_set(self.username, self.password or None)

        def on_connect(c, _u, _f, rc, *_a):
            if rc == 0:
                LOG.info("MQTT verbunden (%s:%s)", self.host, self.port)
                self._discovery_done.clear()
            else:
                LOG.error("MQTT Connect rc=%s", rc)

        client.on_connect = on_connect
        client.connect(self.host, self.port, keepalive=60)
        client.loop_start()
        self._client = client

    def stop(self) -> None:
        if self._client:
            self._client.loop_stop()
            self._client.disconnect()
            self._client = None

    def _pub(self, topic: str, payload: str, retain: bool = True) -> None:
        if not self._client:
            return
        self._client.publish(topic, payload, qos=0, retain=retain)

    def _device(self, serial: str, name: str, model: str) -> dict[str, Any]:
        return {
            "identifiers": [f"growatt_cloud_{slug(serial)}"],
            "name": name,
            "manufacturer": "Growatt",
            "model": model,
            "serial_number": serial,
        }

    def ensure_storage_discovery(self, serial: str, label: str) -> None:
        key = f"storage:{serial}"
        if key in self._discovery_done:
            return
        # Geräte-Name = Serial → Entity-IDs wie bei noah-mqtt (sensor.<sn>_soc)
        device = self._device(serial, serial, f"Growatt {label}")
        sensors = [
            ("soc", "SoC", "%", "battery", "measurement"),
            ("solar_power", "Solar Power", "W", "power", "measurement"),
            ("output_power", "Output Power", "W", "power", "measurement"),
            ("charging_power", "Charging Power", "W", "power", "measurement"),
            ("discharge_power", "Discharge Power", "W", "power", "measurement"),
            ("generation_today", "Generation Today", "kWh", "energy", "total_increasing"),
            ("generation_total", "Generation Total", "kWh", "energy", "total_increasing"),
            ("system_temp", "System Temperature", "°C", "temperature", "measurement"),
            ("ct_power", "CT Power", "W", "power", "measurement"),
            ("work_mode", "Work Mode", None, None, "measurement"),
            ("status", "Status", None, None, "measurement"),
        ]
        self._publish_sensor_discovery(serial, device, sensors)
        self._discovery_done.add(key)
        LOG.info("HA-Discovery %s %s", label, serial)

    def ensure_inverter_discovery(self, serial: str) -> None:
        key = f"min:{serial}"
        if key in self._discovery_done:
            return
        device = self._device(serial, serial, "Growatt MIN")
        sensors = [
            ("ac_power", "AC Power", "W", "power", "measurement"),
            ("energy_today", "Energy Today", "kWh", "energy", "total_increasing"),
            ("energy_total", "Energy Total", "kWh", "energy", "total_increasing"),
            ("energy_today_input_1", "Energy Today Input 1", "kWh", "energy", "total_increasing"),
            ("energy_today_input_2", "Energy Today Input 2", "kWh", "energy", "total_increasing"),
            ("ppv", "PV Power", "W", "power", "measurement"),
            ("ppv1", "PV Power Input 1", "W", "power", "measurement"),
            ("ppv2", "PV Power Input 2", "W", "power", "measurement"),
        ]
        self._publish_sensor_discovery(serial, device, sensors)
        self._discovery_done.add(key)
        LOG.info("HA-Discovery Wechselrichter %s", serial)

    def _publish_sensor_discovery(
        self,
        serial: str,
        device: dict[str, Any],
        sensors: list[tuple],
    ) -> None:
        node = slug(serial)
        for object_id, name, unit, device_class, state_class in sensors:
            unique = f"growatt_cloud_{node}_{object_id}"
            topic = f"{self.discovery_prefix}/sensor/{node}/{object_id}/config"
            state_topic = f"{self.state_prefix}/{node}/{object_id}"
            payload: dict[str, Any] = {
                "name": name,
                "unique_id": unique,
                "state_topic": state_topic,
                "device": device,
                "availability_topic": f"{self.state_prefix}/status",
                "payload_available": "online",
                "payload_not_available": "offline",
            }
            if unit:
                payload["unit_of_measurement"] = unit
            if device_class:
                payload["device_class"] = device_class
            if state_class:
                payload["state_class"] = state_class
            if device_class == "energy":
                payload["state_class"] = "total_increasing"
            self._pub(topic, json.dumps(payload), retain=True)

    def publish_states(self, serial: str, values: dict[str, Any]) -> None:
        node = slug(serial)
        for key, value in values.items():
            if key in ("family", "label", "time"):
                continue
            if value is None:
                continue
            self._pub(f"{self.state_prefix}/{node}/{key}", str(value), retain=True)
        self._pub(f"{self.state_prefix}/status", "online", retain=True)
