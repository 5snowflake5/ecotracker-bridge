"""Central registry: sources, emulators, idle watchdog."""

from __future__ import annotations

import logging
import threading
import time
from typing import Any

from config import HubConfig, apply_runtime_options, try_load_options
from emulators import create_emulator
from model import Emulator, Reading, Source
from sources import create_source
from util import VERSION, berlin_now

LOG = logging.getLogger("ecotracker-bridge")


class Hub:
    def __init__(self, cfg: HubConfig, mqtt: Any) -> None:
        self.sources: dict[str, Source] = {}
        self.emulators: list[Emulator] = []
        self.meta: dict[str, Any] = {
            "port": cfg.port,
            "announce_ip": cfg.announce_ip,
            "version": VERSION,
            "log_level": cfg.log_level,
            "idle_fetch_seconds": cfg.idle_fetch_seconds,
            "mqtt_enabled": cfg.mqtt_enabled,
            "default_voltage": 230.0,
        }
        self._mqtt = mqtt
        self._last_idle_attempt: dict[str, float] = {}
        self._source_cfg: dict[str, dict[str, Any]] = {}
        self._status_html_cache: bytes = b""
        self._status_html_lock = threading.Lock()

        for entry in cfg.sources:
            sid = str(entry.get("id") or "").strip()
            if not sid:
                raise SystemExit("Quelle ohne id in sources")
            try:
                src = create_source(entry)
            except ValueError as exc:
                raise SystemExit(str(exc)) from exc
            self.sources[sid] = src
            self._source_cfg[sid] = dict(entry)

        for entry in cfg.emulators:
            if entry.get("enabled") is False:
                LOG.info("Emulator %s deaktiviert (enabled=false)", entry.get("id"))
                continue
            eid = str(entry.get("id") or "").strip()
            source_id = str(entry.get("source") or "").strip()
            if source_id and source_id not in self.sources:
                if len(self.sources) == 1:
                    only = next(iter(self.sources))
                    LOG.info("Emulator %s: Quelle %r fehlt → %s", eid, source_id, only)
                    source_id = only
                else:
                    raise SystemExit(f"Emulator {eid!r}: unbekannte Quelle {source_id!r}")
            if not source_id and len(self.sources) == 1:
                source_id = next(iter(self.sources))
            if source_id:
                entry = dict(entry)
                entry["source"] = source_id
            try:
                emu = create_emulator(entry)
            except ValueError as exc:
                raise SystemExit(str(exc)) from exc
            self.emulators.append(emu)

        for src in self.sources.values():
            src.start()
        for emu in self.emulators:
            emu.hub = self
            emu.start()

        mqtt.set_hub(self, list(self.sources.keys()))

    def get_source(self, source_id: str) -> Source | None:
        return self.sources.get(source_id)

    def snapshot_source(self, source_id: str) -> Reading | None:
        src = self.get_source(source_id)
        if src is None:
            return None
        return src.snapshot()

    def read_source(self, source_id: str, *, reason: str = "", force: bool = False) -> Reading | None:
        src = self.get_source(source_id)
        if src is None:
            return None
        reading = src.read(reason=reason, force=force)
        if reading is not None:
            self._mqtt.publish_state(source_id, reading.to_ecotracker())
        return reading

    def emulators_of_type(self, type_name: str) -> list[Emulator]:
        t = type_name.strip().lower()
        return [e for e in self.emulators if getattr(e, "type", "").lower() == t]

    def set_status_html_cache(self, body: bytes) -> None:
        with self._status_html_lock:
            self._status_html_cache = body

    def get_status_html_cache(self) -> bytes:
        with self._status_html_lock:
            return self._status_html_cache

    def refresh_status_html_cache(self, builder: Any) -> None:
        self.set_status_html_cache(builder(self))

    def idle_watchdog_loop(self) -> None:
        while True:
            opts = try_load_options()
            if opts is not None:
                apply_runtime_options(self, opts, self._mqtt)

            global_idle = float(self.meta.get("idle_fetch_seconds") or 0)
            now_mono = time.monotonic()

            for sid, src in self.sources.items():
                if getattr(src, "type", "") in ("mqtt", "sma"):
                    continue
                scfg = self._source_cfg.get(sid, {})
                if scfg.get("idle_fetch_seconds") is not None:
                    try:
                        idle = float(scfg.get("idle_fetch_seconds"))
                    except (TypeError, ValueError):
                        idle = global_idle
                else:
                    idle = global_idle
                if idle <= 0:
                    continue

                snap = src.snapshot()
                stats = src.stats()
                last_ok = stats.get("last_ok") or (snap.fetched_at if snap else None)
                if last_ok is None:
                    age = float("inf")
                else:
                    age = max(0.0, (berlin_now() - last_ok).total_seconds())

                last_attempt = self._last_idle_attempt.get(sid, 0.0)
                if age >= idle and (now_mono - last_attempt) >= idle:
                    self._last_idle_attempt[sid] = now_mono
                    LOG.debug(
                        "Idle-Watchdog %s: kein frischer Trigger seit %.1f s (≥ %.0f s) → selbst holen",
                        sid,
                        age if age != float("inf") else -1,
                        idle,
                    )
                    self.read_source(sid, reason=f"idle-watchdog (age≥{idle:.0f}s)")

            try:
                from status import html_status

                self.refresh_status_html_cache(html_status)
            except Exception:
                pass

            time.sleep(0.5)

    def stop(self) -> None:
        for src in self.sources.values():
            src.stop()
        for emu in self.emulators:
            emu.stop()
