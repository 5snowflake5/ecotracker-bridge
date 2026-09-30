#!/usr/bin/env python3
"""Meter Bridge hub – thin entry point."""

from __future__ import annotations

import json
import logging
import threading

from config import load_config
from http_server import create_server
from hub import Hub
from mdns import register_emulators, unregister_all
from mqtt_ha import MQTT
from status import html_status
from util import VERSION, setup_logging

LOG = logging.getLogger("ecotracker-bridge")


def main() -> None:
    setup_logging("info")
    LOG.info("Meter Bridge %s startet", VERSION)

    cfg = load_config()
    LOG.debug("Rohe Options: %s", json.dumps(cfg.raw, ensure_ascii=False, sort_keys=True))
    setup_logging(cfg.log_level)

    hub = Hub(cfg, MQTT)
    hub.set_status_html_cache(html_status(hub))

    LOG.info("Quellen:       %s", ", ".join(hub.sources.keys()) or "—")
    LOG.info("Emulatoren:    %s", ", ".join(getattr(e, "id", "?") for e in hub.emulators) or "—")
    LOG.info("HTTP-Listen:   0.0.0.0:%s", cfg.port)
    LOG.info("mDNS-Announce: %s", cfg.announce_ip)
    if cfg.idle_fetch_seconds > 0:
        LOG.info(
            "Idle-Fetch:    nach %.0f s ohne Live-Trigger",
            cfg.idle_fetch_seconds,
        )
    else:
        LOG.info("Idle-Fetch:    aus")
    LOG.info("Log-Level:     %s", cfg.log_level.upper())

    MQTT.configure(cfg.raw)
    if cfg.mqtt_enabled:
        LOG.info(
            "MQTT Sensoren: an → %s:%s (Discovery unter homeassistant/)",
            cfg.mqtt_host,
            cfg.mqtt_port,
        )
    else:
        LOG.info("MQTT Sensoren: aus")

    threading.Thread(target=hub.idle_watchdog_loop, daemon=True, name="idle-watchdog").start()

    zc = None
    try:
        zc, _infos = register_emulators(hub)
    except Exception as exc:
        LOG.error("mDNS fehlgeschlagen: %s", exc)
        LOG.error("HTTP läuft trotzdem. Clients finden den Zähler ohne mDNS nicht.")

    try:
        httpd = create_server(hub, cfg.port)
    except OSError as exc:
        LOG.error("HTTP-Server startet nicht auf Port %s: %s", cfg.port, exc)
        raise SystemExit(1) from exc

    LOG.info("HTTP bereit auf Port %s", cfg.port)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        LOG.info("Stop angefordert")
    finally:
        httpd.server_close()
        unregister_all(zc)
        hub.stop()
        MQTT._disconnect()
        LOG.info("Meter Bridge beendet")


if __name__ == "__main__":
    main()
