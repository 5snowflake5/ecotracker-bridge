"""Load Home Assistant add-on options and migrate legacy flat config."""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from typing import Any

from util import OPTIONS_PATHS, detect_ipv4, setup_logging

LOG = logging.getLogger("ecotracker-bridge")


def try_load_options() -> dict[str, Any] | None:
    for path in OPTIONS_PATHS:
        if os.path.isfile(path):
            try:
                with open(path, encoding="utf-8") as fh:
                    return json.load(fh)
            except (OSError, json.JSONDecodeError) as exc:
                LOG.error("Options lesen fehlgeschlagen (%s): %s", path, exc)
                return None
    return None


def parse_idle_seconds(raw: Any, fallback: float = 5.0) -> float:
    """Sekunden ohne Trigger, bevor die Bridge selbst holt. 0 = aus."""
    try:
        value = float(raw)
    except (TypeError, ValueError):
        LOG.error("Ungültiges idle_fetch_seconds=%r → Fallback %.0f", raw, fallback)
        return fallback
    if value < 0:
        return 0.0
    return value


def resolve_idle_seconds(opts: dict[str, Any], fallback: float = 5.0) -> float:
    if "idle_fetch_seconds" in opts:
        return parse_idle_seconds(opts.get("idle_fetch_seconds"), fallback)
    if "poll_seconds" in opts:
        return parse_idle_seconds(opts.get("poll_seconds"), fallback)
    return fallback


def _clean_entry(entry: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in entry.items() if value not in (None, "")}


_SOURCE_REQUIRED: dict[str, tuple[str, ...]] = {
    "ecotracker": ("url", "host", "ip"),
    "http_json": ("url",),
    "mqtt": ("mqtt_topic",),
    "homeassistant": ("ha_power_entity", "ha_power_l1_entity"),
    "tasmota": ("host", "url", "ip"),
    "homewizard": ("host", "url", "ip"),
    "fronius": ("host", "url", "ip"),
    "tibber_pulse": ("host", "url", "ip", "password"),
    "shelly": ("host", "url", "ip"),
    "sma": ("id", "serial_number", "serial", "label"),
    "amis_reader": ("host", "url", "ip"),
    "vzlogger": ("host", "ip", "uuid"),
    "esphome": ("host", "ip", "sensor_id"),
    "refoss": ("host", "url", "ip"),
    "iobroker": ("host", "ip", "alias"),
    "envoy": ("host", "url", "ip"),
    "shrdzm": ("host", "url", "ip"),
}


def _has_any(item: dict[str, Any], keys: tuple[str, ...]) -> bool:
    return any(str(item.get(key) or "").strip() for key in keys)


def _source_row_complete(item: dict[str, Any]) -> bool:
    kind = str(item.get("type") or "").strip().lower()
    if not kind:
        return False
    needed = _SOURCE_REQUIRED.get(kind)
    if not needed:
        return bool(item.get("host") or item.get("url") or item.get("ip"))
    if kind == "tibber_pulse":
        return _has_any(item, ("host", "url", "ip")) and bool(item.get("password"))
    if kind == "sma":
        return True
    return _has_any(item, needed)


def _emulator_row_complete(item: dict[str, Any]) -> bool:
    kind = str(item.get("type") or "").strip().lower().replace("-", "_")
    return kind in (
        "ecotracker",
        "shelly_pro3em",
        "shellypro3em",
        "shelly_emg3",
        "shellyemg3",
        "shelly_proem50",
        "shellyproem50",
        "chargee_sparky",
        "sparky",
        "chargee",
    )


_FORM_SOURCE_TYPES: tuple[tuple[str, str], ...] = (
    ("tibber", "tibber_pulse"),
    ("homewizard", "homewizard"),
    ("sma", "sma"),
    ("fronius", "fronius"),
    ("tasmota", "tasmota"),
    ("shelly_source", "shelly"),
    ("http_json", "http_json"),
    ("mqtt_source", "mqtt"),
    ("ha_source", "homeassistant"),
    ("other_meters", "amis_reader"),
)


def _legacy_grid_source(opts: dict[str, Any], idle: float) -> list[dict[str, Any]]:
    source_url = str(opts.get("source_url") or "").strip()
    if not source_url:
        raise SystemExit("source_url fehlt (oder sources-Liste / Zähler-Karten angeben)")
    return [
        {
            "id": "grid",
            "type": "ecotracker",
            "url": source_url,
            "idle_fetch_seconds": idle,
        }
    ]


def _fill_ecotracker_url(item: dict[str, Any], opts: dict[str, Any]) -> dict[str, Any]:
    if str(item.get("type") or "").lower() != "ecotracker":
        return item
    if item.get("url") or item.get("host") or item.get("ip"):
        return item
    source_url = str(opts.get("source_url") or "").strip()
    if source_url:
        item = dict(item)
        item["url"] = source_url
    return item


def _migrate_sources(opts: dict[str, Any], idle: float) -> list[dict[str, Any]]:
    raw = opts.get("sources")
    if isinstance(raw, list):
        entries: list[dict[str, Any]] = []
        for entry in raw:
            if not isinstance(entry, dict):
                continue
            item = _fill_ecotracker_url(_clean_entry(entry), opts)
            if _source_row_complete(item):
                entries.append(item)
        if entries:
            return entries
    extra = _extra_sources(opts)
    if extra:
        return extra
    return _legacy_grid_source(opts, idle)


def _other_meter_type(entry: dict[str, Any]) -> str:
    kind = str(entry.get("meter") or entry.get("type") or "amis_reader").strip().lower()
    if kind in ("", "http_json"):
        return "amis_reader"
    return kind


def _extra_sources(opts: dict[str, Any]) -> list[dict[str, Any]]:
    """Form cards (tibber, homewizard, …) when the expert sources list is empty."""
    out: list[dict[str, Any]] = []
    for key, kind in _FORM_SOURCE_TYPES:
        entries = opts.get(key)
        if not isinstance(entries, list):
            continue
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            item = _clean_entry(entry)
            if not item:
                continue
            if key == "other_meters":
                item.pop("meter", None)
                item["type"] = _other_meter_type(entry)
            else:
                item["type"] = kind
            if not str(item.get("id") or "").strip():
                item["id"] = str(item.get("type") or kind)
            if not _source_row_complete(item):
                LOG.warning("Zähler-Karte %s ignoriert (unvollständig)", key)
                continue
            out.append(item)
    return out


def _migrate_emulators(opts: dict[str, Any], sources: list[dict[str, Any]]) -> list[dict[str, Any]]:
    raw = opts.get("emulators")
    if isinstance(raw, list):
        entries = [
            item
            for item in (_clean_entry(entry) for entry in raw if isinstance(entry, dict))
            if _emulator_row_complete(item)
        ]
        if entries:
            return entries
    extra = _extra_emulators(opts)
    if extra:
        return extra
    source_id = "grid"
    if sources:
        source_id = str(sources[0].get("id") or "grid")
    emulators: list[dict[str, Any]] = [
        {
            "id": "ecotracker",
            "type": "ecotracker",
            "source": source_id,
            "mac": str(opts.get("mac", "B43A45A1B2C3")),
            "serial": str(opts.get("serial", "293d45273261")),
            "productid": str(opts.get("productid", "1137")),
        }
    ]
    if bool(opts.get("shelly_enabled", True)):
        emulators.append(
            {
                "id": "shelly",
                "type": "shelly_pro3em",
                "source": source_id,
                "mac": str(opts.get("shelly_mac", "C8C9A3B43A45")),
            }
        )
    return emulators


def _extra_emulators(opts: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for key in ("outputs", "expert_emulators"):
        entries = opts.get(key)
        if not isinstance(entries, list):
            continue
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            item = _clean_entry(entry)
            if not _emulator_row_complete(item):
                continue
            if not str(item.get("id") or "").strip():
                item["id"] = str(item.get("type") or "output")
            out.append(item)
    return out


@dataclass
class HubConfig:
    log_level: str
    port: int
    announce_ip: str
    idle_fetch_seconds: float
    mqtt_enabled: bool
    mqtt_host: str
    mqtt_port: int
    mqtt_user: str
    mqtt_password: str
    mqtt_discovery_prefix: str
    sources: list[dict[str, Any]] = field(default_factory=list)
    emulators: list[dict[str, Any]] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)


def load_config() -> HubConfig:
    data = try_load_options()
    if data is None:
        raise SystemExit(f"Keine Optionsdatei gefunden ({', '.join(OPTIONS_PATHS)})")
    for path in OPTIONS_PATHS:
        if os.path.isfile(path):
            LOG.info("Konfiguration geladen aus %s", path)
            break

    idle = resolve_idle_seconds(data, 5.0)
    log_level = str(data.get("log_level", "info")).lower()
    if log_level not in ("info", "debug"):
        log_level = "info"

    port = int(data.get("port", 80))
    announce_ip = str(data.get("announce_ip") or "").strip() or detect_ipv4()
    sources = _migrate_sources(data, idle)

    return HubConfig(
        log_level=log_level,
        port=port,
        announce_ip=announce_ip,
        idle_fetch_seconds=idle,
        mqtt_enabled=bool(data.get("mqtt_enabled", True)),
        mqtt_host=str(data.get("mqtt_host") or "core-mosquitto").strip(),
        mqtt_port=int(data.get("mqtt_port") or 1883),
        mqtt_user=str(data.get("mqtt_user") or ""),
        mqtt_password=str(data.get("mqtt_password") or ""),
        mqtt_discovery_prefix=str(data.get("mqtt_discovery_prefix") or "homeassistant").strip()
        or "homeassistant",
        sources=sources,
        emulators=_migrate_emulators(data, sources),
        raw=data,
    )


def apply_runtime_options(hub: Any, opts: dict[str, Any], mqtt: Any) -> None:
    """Live-Reload: Log-Level, MQTT, legacy source_url, globales Idle."""
    level = str(opts.get("log_level", hub.meta.get("log_level", "info"))).lower()
    if level not in ("info", "debug"):
        level = "info"
    if level != hub.meta.get("log_level"):
        setup_logging(level)
        hub.meta["log_level"] = level
        LOG.info("Log-Level: %s", level.upper())

    legacy_url = str(opts.get("source_url") or "").strip()
    if legacy_url:
        src = hub.get_source("grid")
        if src is not None and getattr(src, "type", "") == "ecotracker" and hasattr(src, "url"):
            from sources.ecotracker import normalize_ecotracker_url

            wanted = normalize_ecotracker_url(legacy_url)
            current = str(getattr(src, "url") or "")
            if wanted != current:
                LOG.info("source_url geändert: %s → %s", current, wanted)
                src.url = wanted

    idle = resolve_idle_seconds(opts, float(hub.meta.get("idle_fetch_seconds", 5) or 5))
    if idle != hub.meta.get("idle_fetch_seconds"):
        LOG.info("idle_fetch_seconds geändert: %s → %.0f", hub.meta.get("idle_fetch_seconds"), idle)
        hub.meta["idle_fetch_seconds"] = idle

    mqtt.configure(opts)
