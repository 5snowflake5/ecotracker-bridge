"""SMA Energy Meter / SHM2 — UDP Speedwire multicast (host_network)."""

from __future__ import annotations

import logging
import socket
import struct
import threading
from typing import Any

from model import Reading, Source
from sources.http_util import watts_reading
from sources.sma_decode import parse_speedwire
from util import berlin_now

LOG = logging.getLogger("ecotracker-bridge")

DEFAULT_GROUP = "239.12.255.254"
DEFAULT_PORT = 9522


class SmaSource(Source):
    type = "sma"

    def __init__(self, cfg: dict[str, Any]) -> None:
        self.id = str(cfg.get("id") or self.type)
        self.label = str(cfg.get("label") or self.id)
        self.group = str(cfg.get("multicast_group") or DEFAULT_GROUP)
        self.port = int(cfg.get("udp_port") or DEFAULT_PORT)
        serial = cfg.get("serial_number") or cfg.get("serial") or 0
        self.serial = int(serial)
        self._lock = threading.Lock()
        self._last: Reading | None = None
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._sock: socket.socket | None = None

    def start(self) -> None:
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True, name=f"sma-{self.id}")
        self._thread.start()
        LOG.info("SMA Speedwire %s: %s:%s", self.id, self.group, self.port)

    def stop(self) -> None:
        self._stop.set()
        if self._sock is not None:
            try:
                self._sock.close()
            except OSError:
                pass
            self._sock = None

    def _loop(self) -> None:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind(("", self.port))
            mreq = struct.pack("=4s4s", socket.inet_aton(self.group), socket.inet_aton("0.0.0.0"))
            sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
            sock.settimeout(1.0)
        except OSError as exc:
            LOG.error("SMA %s bind fehlgeschlagen: %s", self.id, exc)
            sock.close()
            return
        self._sock = sock
        while not self._stop.is_set():
            try:
                data, _addr = sock.recvfrom(2048)
            except TimeoutError:
                continue
            except OSError:
                if self._stop.is_set():
                    break
                continue
            try:
                parsed = parse_speedwire(data)
            except ValueError:
                continue
            reading = watts_reading(
                parsed["power"],
                source_id=self.id,
                l1=parsed.get("l1"),
                l2=parsed.get("l2"),
                l3=parsed.get("l3"),
            )
            reading.fetched_at = berlin_now()
            with self._lock:
                self._last = reading

    def snapshot(self) -> Reading | None:
        with self._lock:
            return self._last

    def read(self, *, reason: str = "", force: bool = False) -> Reading | None:
        return self.snapshot()

    def stats(self) -> dict[str, Any]:
        last = self.snapshot()
        return {
            "id": self.id,
            "type": self.type,
            "label": self.label,
            "last_ok": last.fetched_at if last else None,
            "last_error": None,
            "polls_ok": 1 if last else 0,
            "polls_fail": 0,
        }
