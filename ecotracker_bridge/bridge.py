#!/usr/bin/env python3
"""Lightweight everHome EcoTracker + Shelly Pro 3EM proxy for Growatt NOAH.

Serves EcoTracker JSON on port 80 + mDNS `_everhome._tcp`, and optionally
Shelly Gen2 RPC (`/rpc/...`, `/shelly`) + mDNS `_shelly._tcp` from the same process.
Physical meter is fetched on demand when a client hits `/v1/json` or Shelly status RPC.
Optional background poll: if no client has triggered a live fetch for idle_fetch_seconds,
the bridge fetches the physical EcoTracker itself so HA cache stays fresh.
"""

from __future__ import annotations

import json
import logging
import os
import socket
import sys
import threading
import time
from datetime import datetime, timezone, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.error import URLError, HTTPError
from urllib.parse import unquote, urlparse
from urllib.request import Request, urlopen

from zeroconf import IPVersion, ServiceInfo, Zeroconf

import shelly_rpc

BERLIN = timezone(timedelta(hours=2))
OPTIONS_PATHS = ("/data/options.json", "options.json")
VERSION = "1.3.2"
# Shelly/NOAH pollen ~alle 3 s – physischen Tracker nicht jedes Mal neu anfassen.
MIN_SOURCE_REFETCH_S = 2.0
SOURCE_TIMEOUT_S = 4.0
SOURCE_ERROR_LOG_INTERVAL_S = 60.0
_last_source_error_log = 0.0

LOG = logging.getLogger("ecotracker-bridge")


class BerlinFormatter(logging.Formatter):
    """Log-Zeitstempel immer Europe/Berlin, unabhängig von Container-UTC."""

    def formatTime(self, record: logging.LogRecord, datefmt: str | None = None) -> str:  # noqa: N802
        dt = datetime.fromtimestamp(record.created, tz=timezone.utc).astimezone(_berlin_tz())
        if datefmt:
            return dt.strftime(datefmt)
        return dt.isoformat(timespec="seconds")


def _berlin_tz():
    try:
        from zoneinfo import ZoneInfo

        return ZoneInfo("Europe/Berlin")
    except Exception:
        return BERLIN


def setup_logging(level_name: str = "info") -> None:
    """Stdout = App-Log im Home Assistant Supervisor."""
    level = logging.DEBUG if str(level_name).lower() == "debug" else logging.INFO
    root = logging.getLogger()
    root.handlers.clear()
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        BerlinFormatter(
            "%(asctime)s %(levelname)s %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )
    root.addHandler(handler)
    root.setLevel(level)
    logging.getLogger("zeroconf").setLevel(logging.WARNING)


def berlin_now() -> datetime:
    return datetime.now(_berlin_tz())


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
    """Sekunden ohne Trigger, bevor die Bridge selbst den physischen Tracker holt. 0 = aus."""
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
    # Kompatibilität zu älteren Optionen (poll_seconds).
    if "poll_seconds" in opts:
        return parse_idle_seconds(opts.get("poll_seconds"), fallback)
    return fallback


def apply_runtime_options(opts: dict[str, Any]) -> None:
    level = str(opts.get("log_level", META.get("log_level", "info"))).lower()
    if level not in ("info", "debug"):
        level = "info"
    if level != META.get("log_level"):
        setup_logging(level)
        META["log_level"] = level
        LOG.info("Log-Level: %s", level.upper())
    source = source_json_url(str(opts.get("source_url", META.get("source_url", ""))))
    if source and source != META.get("source_url"):
        LOG.info("source_url geändert: %s → %s", META.get("source_url"), source)
        META["source_url"] = source
    idle = resolve_idle_seconds(opts, float(META.get("idle_fetch_seconds", 5) or 5))
    if idle != META.get("idle_fetch_seconds"):
        LOG.info("idle_fetch_seconds geändert: %s → %.0f", META.get("idle_fetch_seconds"), idle)
        META["idle_fetch_seconds"] = idle
    shelly_on = bool(opts.get("shelly_enabled", META.get("shelly_enabled", True)))
    if shelly_on != META.get("shelly_enabled"):
        LOG.info("shelly_enabled geändert: %s → %s", META.get("shelly_enabled"), shelly_on)
        META["shelly_enabled"] = shelly_on
    MQTT.configure(opts)


def load_options() -> dict[str, Any]:
    data = try_load_options()
    if data is None:
        raise SystemExit(f"Keine Optionsdatei gefunden ({', '.join(OPTIONS_PATHS)})")
    for path in OPTIONS_PATHS:
        if os.path.isfile(path):
            LOG.info("Konfiguration geladen aus %s", path)
            break
    return data


def normalize_mac(raw: str) -> str:
    mac = "".join(ch for ch in raw.upper() if ch.isalnum())
    if len(mac) != 12:
        raise SystemExit(f"MAC muss 12 Hex-Zeichen haben, nicht {raw!r}")
    return mac


def source_json_url(source_url: str) -> str:
    url = source_url.rstrip("/")
    if url.endswith("/v1/json"):
        return url
    return f"{url}/v1/json"


def detect_ipv4() -> str:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(("1.1.1.1", 80))
        return sock.getsockname()[0]
    finally:
        sock.close()


class MeterState:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.payload: dict[str, Any] | None = None
        self.raw: bytes | None = None
        self.last_ok: datetime | None = None
        self.last_error: str | None = None
        self.polls_ok = 0
        self.polls_fail = 0

    def snapshot(self) -> dict[str, Any]:
        with self.lock:
            return {
                "payload": None if self.payload is None else dict(self.payload),
                "raw": self.raw,
                "last_ok": self.last_ok,
                "last_error": self.last_error,
                "polls_ok": self.polls_ok,
                "polls_fail": self.polls_fail,
            }


STATE = MeterState()
META: dict[str, Any] = {}
FETCH_HEADERS = {"Accept": "application/json", "User-Agent": f"ecotracker-bridge/{VERSION}"}


class ClientPollStats:
    """Misst Client-Intervalle für /v1/json (nur Debug-Log)."""

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.last_at: dict[str, float] = {}
        self.count: dict[str, int] = {}
        self.sum_delta: dict[str, float] = {}
        self.last_summary_at = 0.0

    def record(self, client: str) -> tuple[int, float | None, float | None]:
        now = time.monotonic()
        with self.lock:
            prev = self.last_at.get(client)
            delta = None if prev is None else now - prev
            self.last_at[client] = now
            n = self.count.get(client, 0) + 1
            self.count[client] = n
            avg = None
            if delta is not None:
                self.sum_delta[client] = self.sum_delta.get(client, 0.0) + delta
                avg = self.sum_delta[client] / max(1, n - 1)
            return n, delta, avg

    def maybe_summary(self, every_seconds: float = 60.0) -> None:
        if not LOG.isEnabledFor(logging.DEBUG):
            return
        now = time.monotonic()
        with self.lock:
            if now - self.last_summary_at < every_seconds:
                return
            if not self.count:
                return
            self.last_summary_at = now
            lines = []
            for client, n in sorted(self.count.items(), key=lambda x: -x[1]):
                if n < 2:
                    lines.append(f"{client}: {n} Hit(s)")
                    continue
                avg = self.sum_delta.get(client, 0.0) / (n - 1)
                lines.append(f"{client}: {n} Hits, Ø {avg:.1f} s")
        LOG.debug("Client-Poll-Zusammenfassung: %s", " | ".join(lines))


CLIENT_STATS = ClientPollStats()

# HA MQTT Discovery – Namen wie stefanseeger/ecotracker (everHome Plugin).
# (json_key, name, object_id_suffix, unit, device_class|None, state_class)
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

# Alte Discovery-Topics (Tarifzähler – viele Meter liefern die Felder nicht → HA-Log-Spam)
_MQTT_STALE_OBJECT_SUFFIXES = ("energy_in_t1", "energy_in_t2")


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
        self.device_id = "ecotracker"
        self._discovery_done = False
        self._last_error = ""

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
            self._discovery_done = False

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
                self._discovery_done = False
                self.publish_discovery()
                snap = STATE.snapshot()
                if snap.get("payload"):
                    self.publish_state(snap["payload"])
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

    def publish_discovery(self) -> None:
        with self.lock:
            client = self.client
            if client is None or not self.enabled:
                return
            device = {
                "identifiers": ["ecotracker_bridge"],
                "name": "Ecotracker",
                "manufacturer": "everHome",
                "model": "EcoTracker (via Bridge)",
                "sw_version": VERSION,
            }
            state_topic = f"ecotracker_bridge/state"
            avail_topic = f"ecotracker_bridge/status"
            for stale in _MQTT_STALE_OBJECT_SUFFIXES:
                topic = f"{self.prefix}/sensor/ecotracker_bridge/{stale}/config"
                client.publish(topic, "", retain=True)
            for json_key, name, object_suffix, unit, device_class, state_class in MQTT_SENSOR_DEFS:
                uid = f"ecotracker_bridge_{object_suffix}"
                cfg: dict[str, Any] = {
                    "name": name,
                    "object_id": f"ecotracker_{object_suffix}",
                    "unique_id": uid,
                    "state_topic": state_topic,
                    "availability_topic": avail_topic,
                    "payload_available": "online",
                    "payload_not_available": "offline",
                    # default(none) → kein Template-Spam wenn Feld fehlt; State wird unavailable
                    "value_template": (
                        f"{{{{ value_json.{json_key} | default(none, true) }}}}"
                    ),
                    "unit_of_measurement": unit,
                    "state_class": state_class,
                    "device": device,
                    "force_update": True,
                }
                if device_class:
                    cfg["device_class"] = device_class
                topic = f"{self.prefix}/sensor/ecotracker_bridge/{object_suffix}/config"
                client.publish(topic, json.dumps(cfg), retain=True)
            client.publish(avail_topic, "online", retain=True)
            self._discovery_done = True
            LOG.info("MQTT HA-Discovery veröffentlicht (%s Sensoren, Namen wie Ecotracker-Plugin)", len(MQTT_SENSOR_DEFS))

    def publish_state(self, payload: dict[str, Any]) -> None:
        with self.lock:
            client = self.client
            if client is None or not self.enabled:
                return
            body = {k: payload.get(k) for k, *_ in MQTT_SENSOR_DEFS if k in payload and payload.get(k) is not None}
            if not body:
                return
            client.publish("ecotracker_bridge/state", json.dumps(body), retain=True)
            LOG.debug("MQTT State: power=%s", body.get("power"))


MQTT = MqttHaPublisher()


def fetch_source(url: str, *, reason: str, force: bool = False) -> dict[str, Any] | None:
    """Holt frisch vom physischen EcoTracker und aktualisiert den Cache."""
    global _last_source_error_log
    if not force:
        snap = STATE.snapshot()
        last_ok = snap.get("last_ok")
        if last_ok is not None:
            age = max(0.0, (berlin_now() - last_ok).total_seconds())
            if age < MIN_SOURCE_REFETCH_S and isinstance(snap.get("payload"), dict):
                LOG.debug(
                    "Quelle übersprungen (%s): Cache %.1f s alt (< %.1f s)",
                    reason,
                    age,
                    MIN_SOURCE_REFETCH_S,
                )
                return snap["payload"]

    started = time.perf_counter()
    try:
        req = Request(url, headers=FETCH_HEADERS, method="GET")
        with urlopen(req, timeout=SOURCE_TIMEOUT_S) as resp:
            body = resp.read()
        elapsed_ms = (time.perf_counter() - started) * 1000.0
        data = json.loads(body)
        if not isinstance(data, dict):
            raise ValueError("Antwort ist kein JSON-Objekt")
        raw = json.dumps(data, separators=(",", ":")).encode("utf-8")
        with STATE.lock:
            STATE.payload = data
            STATE.raw = raw
            STATE.last_ok = berlin_now()
            STATE.last_error = None
            STATE.polls_ok += 1
            ok_count = STATE.polls_ok
        LOG.debug(
            "Quelle ok (%s) #%s: power=%s W (avg=%s) ecotracker=%.0f ms",
            reason,
            ok_count,
            data.get("power"),
            data.get("powerAvg"),
            elapsed_ms,
        )
        MQTT.publish_state(data)
        return data
    except (URLError, HTTPError, TimeoutError, ValueError, json.JSONDecodeError, OSError) as exc:
        elapsed_ms = (time.perf_counter() - started) * 1000.0
        with STATE.lock:
            STATE.last_error = str(exc)
            STATE.polls_fail += 1
            fail_count = STATE.polls_fail
            cached = STATE.payload
        now = time.monotonic()
        if now - _last_source_error_log >= SOURCE_ERROR_LOG_INTERVAL_S:
            _last_source_error_log = now
            LOG.error(
                "Quelle fehlgeschlagen (%s) #%s nach %.0f ms: %s%s",
                reason,
                fail_count,
                elapsed_ms,
                exc,
                " – Cache bleibt aktiv" if isinstance(cached, dict) else "",
            )
        else:
            LOG.debug(
                "Quelle fehlgeschlagen (%s) #%s nach %.0f ms: %s",
                reason,
                fail_count,
                elapsed_ms,
                exc,
            )
        return cached if isinstance(cached, dict) else None


def poll_loop() -> None:
    """Idle-Watchdog: holt selbst, wenn länger kein /v1/json-Trigger kam."""
    last_attempt = 0.0
    while True:
        opts = try_load_options()
        if opts is not None:
            apply_runtime_options(opts)
        idle = float(META.get("idle_fetch_seconds") or 0)
        url = str(META.get("source_url") or "")
        if idle <= 0 or not url:
            time.sleep(1)
            continue

        snap = STATE.snapshot()
        if snap["last_ok"] is None:
            age = float("inf")
        else:
            age = max(0.0, (berlin_now() - snap["last_ok"]).total_seconds())

        now = time.monotonic()
        # Nur triggern, wenn Cache älter als idle UND seit letztem Versuch mind. idle.
        if age >= idle and (now - last_attempt) >= idle:
            last_attempt = now
            LOG.debug(
                "Idle-Watchdog: kein frischer Trigger seit %.1f s (≥ %.0f s) → selbst holen",
                age if age != float("inf") else -1,
                idle,
            )
            fetch_source(url, reason=f"idle-watchdog (age≥{idle:.0f}s)")
        time.sleep(0.5)


def html_status(snap: dict[str, Any]) -> bytes:
    payload = snap["payload"]
    last_ok = snap["last_ok"]
    last_ok_s = last_ok.strftime("%d.%m.%Y %H:%M:%S") if last_ok else "noch keine Daten"
    err = snap["last_error"] or "—"
    power = payload.get("power") if payload else "—"
    idle = META.get("idle_fetch_seconds", 5)
    idle_txt = "aus" if not idle else f"nach {idle:.0f} s ohne Live-Trigger"
    if META.get("shelly_enabled"):
        shelly_mdns = f"<code>{META.get('shelly_hostname')}._shelly._tcp.local</code>"
    else:
        shelly_mdns = "aus"
    rows = ""
    if payload:
        for key, value in payload.items():
            rows += f"<tr><td>{key}</td><td>{value}</td></tr>"
    else:
        rows = "<tr><td colspan=2>Warte auf Abruf vom Growatt NOAH (oder öffne /v1/json)…</td></tr>"

    html = f"""<!DOCTYPE html>
<html lang="de">
<head>
  <meta charset="utf-8">
  <meta http-equiv="refresh" content="5">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>EcoTracker Bridge</title>
  <style>
    body {{ font-family: system-ui, sans-serif; margin: 1.5rem; color: #1a1a1a; }}
    h1 {{ font-size: 1.25rem; }}
    table {{ border-collapse: collapse; width: 100%; max-width: 36rem; }}
    td, th {{ border-bottom: 1px solid #ddd; padding: 0.35rem 0.5rem; text-align: left; }}
    .muted {{ color: #555; }}
    code {{ background: #f4f4f4; padding: 0.1rem 0.3rem; }}
  </style>
</head>
<body>
  <h1>EcoTracker Bridge {VERSION}</h1>
  <p class="muted">Virtueller EcoTracker + optional Shelly Pro 3EM. Live-Fetch bei /v1/json und Shelly-Status-RPC.</p>
  <table>
    <tr><th>Leistung</th><td>{power} W</td></tr>
    <tr><th>Letzter erfolgreicher Abruf</th><td>{last_ok_s}</td></tr>
    <tr><th>Letzter Fehler</th><td>{err}</td></tr>
    <tr><th>Abrufe ok / fehl</th><td>{snap["polls_ok"]} / {snap["polls_fail"]}</td></tr>
    <tr><th>Idle-Fetch</th><td>{idle_txt}</td></tr>
    <tr><th>Log-Level</th><td>{META.get("log_level", "info")}</td></tr>
    <tr><th>Quelle</th><td><code>{META["source_url"]}</code></td></tr>
    <tr><th>mDNS EcoTracker</th><td><code>{META["hostname"]}._everhome._tcp.local</code></td></tr>
    <tr><th>mDNS Shelly</th><td>{shelly_mdns}</td></tr>
    <tr><th>JSON live (NOAH)</th><td><a href="/v1/json"><code>/v1/json</code></a></td></tr>
    <tr><th>JSON Cache (HA)</th><td><a href="/v1/cache"><code>/v1/cache</code></a></td></tr>
    <tr><th>Shelly RPC</th><td><a href="/rpc/EM.GetStatus?id=0"><code>/rpc/EM.GetStatus</code></a></td></tr>
    <tr><th>Angekündigte IP</th><td>{META["announce_ip"]}:{META["port"]}</td></tr>
    <tr><th>Serial / productid</th><td>{META["serial"]} / {META["productid"]}</td></tr>
  </table>
  <h2>Rohdaten</h2>
  <table>{rows}</table>
</body>
</html>
"""
    return html.encode("utf-8")


def cache_payload(snap: dict[str, Any]) -> dict[str, Any] | None:
    """Cache für HA-Sensoren: letzte NOAH-Werte, ohne physischen EcoTracker anzufassen."""
    payload = snap.get("payload")
    if not isinstance(payload, dict):
        return None
    out = dict(payload)
    last_ok = snap.get("last_ok")
    age = None
    if last_ok is not None:
        age = max(0.0, (berlin_now() - last_ok).total_seconds())
        out["ageSeconds"] = round(age, 1)
        out["lastOk"] = last_ok.isoformat()
    return out


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt: str, *args: Any) -> None:
        return

    def _client(self) -> str:
        return self.client_address[0] if self.client_address else "?"

    def _send(self, code: int, body: bytes, content_type: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(body)

    def _send_json(self, code: int, obj: Any) -> None:
        body = json.dumps(obj, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        self._send(code, body, "application/json")

    def _meter_payload_for_rpc(self, method: str, client: str) -> dict[str, Any] | None:
        """Status-RPC: live vom physischen Tracker; Info/Config: Cache reicht."""
        if shelly_rpc.needs_meter_payload(method):
            source = META.get("source_url")
            if source:
                n, delta, avg = CLIENT_STATS.record(f"shelly:{client}")
                if delta is None:
                    interval_txt = "erster Hit"
                else:
                    avg_txt = f", Ø {avg:.1f} s" if avg is not None else ""
                    interval_txt = f"Δ={delta:.1f} s{avg_txt}"
                fetch_source(
                    source,
                    reason=f"Shelly {method} von {client} ({interval_txt})",
                )
                CLIENT_STATS.maybe_summary()
        snap = STATE.snapshot()
        payload = snap.get("payload")
        return payload if isinstance(payload, dict) else None

    def _handle_shelly_rpc(self, method: str, *, rpc_id: Any = None, src: str | None = None) -> None:
        client = self._client()
        if not META.get("shelly_enabled", True):
            self._send(404, b"shelly disabled", "text/plain; charset=utf-8")
            return
        payload = self._meter_payload_for_rpc(method, client)
        if shelly_rpc.needs_meter_payload(method) and payload is None:
            LOG.warning("Shelly %s von %s → 503 (keine Meter-Daten)", method, client)
            err = {"code": -104, "message": "no meter data yet"}
            if rpc_id is not None:
                self._send_json(
                    200,
                    {
                        "id": rpc_id,
                        "src": META.get("shelly_hostname"),
                        "dst": src,
                        "error": err,
                    },
                )
            else:
                self._send_json(503, {"error": "noch keine Daten vom physischen EcoTracker"})
            return
        result = shelly_rpc.dispatch_rpc(method, payload, META)
        if result is None:
            LOG.warning("Shelly unbekannte Methode %s von %s", method, client)
            err = {"code": -114, "message": f"Method '{method}' not found"}
            if rpc_id is not None:
                self._send_json(
                    200,
                    {
                        "id": rpc_id,
                        "src": META.get("shelly_hostname"),
                        "dst": src,
                        "error": err,
                    },
                )
            else:
                self._send_json(404, err)
            return
        power = (payload or {}).get("power") if payload else None
        LOG.debug("Shelly %s von %s → 200 power=%s W", method, client, power)
        if rpc_id is not None:
            frame: dict[str, Any] = {
                "id": rpc_id,
                "src": META.get("shelly_hostname"),
                "result": result,
            }
            if src:
                frame["dst"] = src
            self._send_json(200, frame)
        else:
            self._send_json(200, result)

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        path = unquote(parsed.path)
        client = self._client()
        if path in ("/v1/json", "/v1/json/"):
            n, delta, avg = CLIENT_STATS.record(client)
            if delta is None:
                interval_txt = "erster Hit"
            else:
                avg_txt = f", Ø {avg:.1f} s" if avg is not None else ""
                interval_txt = f"Δ={delta:.1f} s{avg_txt}"
            source = META.get("source_url")
            if source:
                fetch_source(source, reason=f"GET /v1/json von {client} ({interval_txt})")
            snap = STATE.snapshot()
            if snap["raw"] is None:
                LOG.warning(
                    "GET /v1/json von %s → 503 (keine Daten vom physischen EcoTracker)",
                    client,
                )
                msg = json.dumps({"error": "noch keine Daten vom physischen EcoTracker"}).encode()
                self._send(503, msg, "application/json; charset=utf-8")
                CLIENT_STATS.maybe_summary()
                return
            power = (snap["payload"] or {}).get("power")
            LOG.debug(
                "GET /v1/json von %s → 200 power=%s W [%s, Hit #%s]",
                client,
                power,
                interval_txt,
                n,
            )
            self._send(200, snap["raw"], "application/json")
            CLIENT_STATS.maybe_summary()
            return
        if path in ("/v1/cache", "/v1/cache/"):
            # HA-Sensoren: nur Speicher, kein Call zum physischen EcoTracker.
            snap = STATE.snapshot()
            cached = cache_payload(snap)
            if cached is None:
                LOG.debug("GET /v1/cache von %s → 503 (noch kein Cache)", client)
                msg = json.dumps(
                    {"error": "noch kein Cache – warte auf Growatt-Abruf von /v1/json"}
                ).encode()
                self._send(503, msg, "application/json; charset=utf-8")
                return
            body = json.dumps(cached, separators=(",", ":")).encode("utf-8")
            LOG.debug(
                "GET /v1/cache von %s → 200 power=%s W age=%ss",
                client,
                cached.get("power"),
                cached.get("ageSeconds"),
            )
            self._send(200, body, "application/json")
            return
        if path in ("/shelly", "/shelly/"):
            self._handle_shelly_rpc("Shelly.GetDeviceInfo")
            return
        if path.startswith("/rpc/") or path in ("/rpc", "/rpc/"):
            method = path[len("/rpc/") :].strip("/") if path.startswith("/rpc/") else ""
            if method:
                self._handle_shelly_rpc(method)
                return
            # HA/Clients prüfen manchmal nur GET /rpc ohne Methode.
            LOG.debug("GET /rpc von %s → ListMethods", client)
            self._handle_shelly_rpc("Shelly.ListMethods")
            return
        if path in ("/", "/index.html"):
            # Statusseite nur Cache – sonst würde meta refresh den physischen Tracker killen.
            snap = STATE.snapshot()
            LOG.debug("GET / von %s → 200 Statusseite (Cache)", client)
            self._send(200, html_status(snap), "text/html; charset=utf-8")
            return
        LOG.debug("GET %s von %s → 404", path, client)
        self._send(404, b"not found", "text/plain; charset=utf-8")

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        path = unquote(parsed.path)
        client = self._client()
        if path not in ("/rpc", "/rpc/"):
            LOG.warning("POST %s von %s → 404", path, client)
            self._send(404, b"not found", "text/plain; charset=utf-8")
            return
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length > 0 else b"{}"
        try:
            req = json.loads(raw.decode("utf-8") or "{}")
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            LOG.warning("POST /rpc von %s → ungültiges JSON: %s", client, exc)
            self._send_json(400, {"error": "invalid json"})
            return
        if not isinstance(req, dict):
            self._send_json(400, {"error": "rpc body must be object"})
            return
        method = str(req.get("method") or "")
        if not method:
            self._send_json(400, {"error": "missing method"})
            return
        rpc_id = req.get("id", 0)
        src = req.get("src")
        self._handle_shelly_rpc(method, rpc_id=rpc_id, src=str(src) if src else None)


def register_mdns(hostname: str, ip: str, port: int, serial: str, productid: str) -> tuple[Zeroconf, list[ServiceInfo]]:
    infos: list[ServiceInfo] = []
    service_type = "_everhome._tcp.local."
    info = ServiceInfo(
        service_type,
        f"{hostname}.{service_type}",
        addresses=[socket.inet_aton(ip)],
        port=port,
        properties={
            "ip": ip,
            "serial": serial,
            "productid": productid,
        },
        server=f"{hostname}.local.",
    )
    zc = Zeroconf(ip_version=IPVersion.V4Only)
    zc.register_service(info, cooperating_responders=True)
    infos.append(info)
    LOG.info(
        "mDNS EcoTracker: %s._everhome._tcp.local → %s:%s (serial=%s productid=%s)",
        hostname,
        ip,
        port,
        serial,
        productid,
    )
    return zc, infos


def register_shelly_mdns(zc: Zeroconf, hostname: str, ip: str, port: int) -> list[ServiceInfo]:
    """Shelly Gen2: _shelly._tcp (+ _http._tcp wie uni-meter)."""
    infos: list[ServiceInfo] = []
    props = shelly_rpc.mdns_properties(hostname)
    for service_type in ("_shelly._tcp.local.", "_http._tcp.local."):
        info = ServiceInfo(
            service_type,
            f"{hostname}.{service_type}",
            addresses=[socket.inet_aton(ip)],
            port=port,
            properties=props,
            server=f"{hostname}.local.",
        )
        zc.register_service(info, cooperating_responders=True)
        infos.append(info)
        LOG.info("mDNS Shelly: %s.%s → %s:%s", hostname, service_type.rstrip("."), ip, port)
    return infos


def main() -> None:
    setup_logging("info")
    LOG.info("EcoTracker Bridge %s startet", VERSION)

    opts = load_options()
    LOG.debug("Rohe Options: %s", json.dumps(opts, ensure_ascii=False, sort_keys=True))
    mac = normalize_mac(str(opts.get("mac", "B43A45A1B2C3")))
    hostname = f"ecotracker-{mac.lower()}"
    serial = str(opts.get("serial", "293d45273261"))
    productid = str(opts.get("productid", "1137"))
    port = int(opts.get("port", 80))
    idle_fetch_seconds = resolve_idle_seconds(opts, 5.0)
    log_level = str(opts.get("log_level", "info")).lower()
    if log_level not in ("info", "debug"):
        log_level = "info"
    setup_logging(log_level)
    source = source_json_url(str(opts["source_url"]))
    announce_ip = str(opts.get("announce_ip") or "").strip() or detect_ipv4()
    shelly_enabled = bool(opts.get("shelly_enabled", True))
    shelly_mac = normalize_mac(str(opts.get("shelly_mac", "C8C9A3B43A45")))
    shelly_hostname = f"shellypro3em-{shelly_mac.lower()}"

    META.update(
        {
            "source_url": source,
            "hostname": hostname,
            "announce_ip": announce_ip,
            "port": port,
            "serial": serial,
            "productid": productid,
            "idle_fetch_seconds": idle_fetch_seconds,
            "log_level": log_level,
            "version": VERSION,
            "shelly_enabled": shelly_enabled,
            "shelly_mac": shelly_mac,
            "shelly_hostname": shelly_hostname,
            "default_voltage": 230.0,
        }
    )

    LOG.info("Quelle:        %s", source)
    LOG.info("HTTP-Listen:   0.0.0.0:%s", port)
    LOG.info("mDNS-Announce: %s (%s)", announce_ip, hostname)
    if idle_fetch_seconds > 0:
        LOG.info(
            "Idle-Fetch:    nach %.0f s ohne Live-Trigger (NOAH/Shelly ~3 s → meist unnötig)",
            idle_fetch_seconds,
        )
    else:
        LOG.info("Idle-Fetch:    aus")
    LOG.info("Log-Level:     %s", log_level.upper())
    LOG.info("MAC/Serial:    %s / %s / productid=%s", mac, serial, productid)
    if shelly_enabled:
        LOG.info("Shelly Pro 3EM: an → %s (MAC %s)", shelly_hostname, shelly_mac)
    else:
        LOG.info("Shelly Pro 3EM: aus")

    MQTT.configure(opts)
    if bool(opts.get("mqtt_enabled", True)):
        LOG.info(
            "MQTT Sensoren: an → %s:%s (Discovery unter homeassistant/)",
            opts.get("mqtt_host") or "core-mosquitto",
            opts.get("mqtt_port") or 1883,
        )
    else:
        LOG.info("MQTT Sensoren: aus")

    threading.Thread(target=poll_loop, daemon=True, name="poll").start()

    zc = None
    try:
        zc, _infos = register_mdns(hostname, announce_ip, port, serial, productid)
        if shelly_enabled:
            register_shelly_mdns(zc, shelly_hostname, announce_ip, port)
    except Exception as exc:
        LOG.error("mDNS fehlgeschlagen: %s", exc)
        LOG.error("HTTP läuft trotzdem. Growatt NOAH findet den Zähler ohne mDNS nicht.")

    try:
        httpd = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    except OSError as exc:
        LOG.error("HTTP-Server startet nicht auf Port %s: %s", port, exc)
        raise SystemExit(1) from exc

    LOG.info(
        "HTTP bereit auf Port %s (EcoTracker: /v1/json  Shelly: /rpc/EM.GetStatus)",
        port,
    )
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        LOG.info("Stop angefordert")
    finally:
        httpd.server_close()
        if zc is not None:
            zc.unregister_all_services()
            zc.close()
        MQTT._disconnect()
        LOG.info("EcoTracker Bridge beendet")


if __name__ == "__main__":
    main()
