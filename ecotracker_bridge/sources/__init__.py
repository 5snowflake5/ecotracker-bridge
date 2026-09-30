from __future__ import annotations

from typing import Any, Callable

from model import Source

_ALIASES = {
    "json_http": "http_json",
    "ha": "homeassistant",
    "tibber": "tibber_pulse",
    "meross": "refoss",
    "shelly_3em": "shelly",
}


def _load(kind: str) -> Callable[[dict[str, Any]], Source]:
    if kind == "ecotracker":
        from sources.ecotracker import EcoTrackerSource

        return EcoTrackerSource
    if kind == "http_json":
        from sources.http_json import HttpJsonSource

        return HttpJsonSource
    if kind == "mqtt":
        from sources.mqtt_source import MqttSource

        return MqttSource
    if kind == "homeassistant":
        from sources.homeassistant import HomeAssistantSource

        return HomeAssistantSource
    if kind == "tasmota":
        from sources.tasmota import TasmotaSource

        return TasmotaSource
    if kind == "homewizard":
        from sources.homewizard import HomeWizardSource

        return HomeWizardSource
    if kind == "fronius":
        from sources.fronius import FroniusSource

        return FroniusSource
    if kind == "tibber_pulse":
        from sources.tibber_pulse import TibberPulseSource

        return TibberPulseSource
    if kind == "shelly":
        from sources.shelly import ShellySource

        return ShellySource
    if kind == "sma":
        from sources.sma import SmaSource

        return SmaSource
    if kind == "amis_reader":
        from sources.more import AmisReaderSource

        return AmisReaderSource
    if kind == "vzlogger":
        from sources.more import VZLoggerSource

        return VZLoggerSource
    if kind == "esphome":
        from sources.more import ESPHomeSource

        return ESPHomeSource
    if kind == "refoss":
        from sources.more import RefossSource

        return RefossSource
    if kind == "iobroker":
        from sources.more import IoBrokerSource

        return IoBrokerSource
    if kind == "envoy":
        from sources.more import EnvoySource

        return EnvoySource
    if kind == "shrdzm":
        from sources.more import ShrdzmSource

        return ShrdzmSource
    raise ValueError(kind)


SOURCE_TYPES = (
    "ecotracker",
    "http_json",
    "mqtt",
    "homeassistant",
    "tasmota",
    "homewizard",
    "fronius",
    "tibber_pulse",
    "shelly",
    "sma",
    "amis_reader",
    "vzlogger",
    "esphome",
    "refoss",
    "iobroker",
    "envoy",
    "shrdzm",
)


def create_source(cfg: dict[str, Any]) -> Source:
    kind = str(cfg.get("type") or "").strip().lower()
    kind = _ALIASES.get(kind, kind)
    try:
        factory = _load(kind)
    except ValueError:
        raise ValueError(f"Unbekannter Quellentyp: {kind!r} (erlaubt: {', '.join(SOURCE_TYPES)})") from None
    return factory(cfg)
