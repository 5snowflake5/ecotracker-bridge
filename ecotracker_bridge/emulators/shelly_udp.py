"""Shelly Gen2-style JSON-RPC over UDP (Marstek B2500 / Venus / Jupiter)."""

from __future__ import annotations

import json
import logging
import socket
import threading
from typing import Any

LOG = logging.getLogger("ecotracker-bridge")


def parse_udp_ports(raw: Any) -> list[int]:
    if raw is None or raw == "" or raw is False:
        return []
    if isinstance(raw, str) and raw.strip().lower() in ("off", "none", "-", "0"):
        return []
    if isinstance(raw, (int, float)):
        if int(raw) <= 0:
            return []
        return [int(raw)]
    if isinstance(raw, list):
        return [int(x) for x in raw]
    return [int(p.strip()) for p in str(raw).split(",") if p.strip()]


class ShellyUdpServer:
    def __init__(self, emu: Any, ports: list[int]) -> None:
        self._emu = emu
        self._ports = ports
        self._stop = threading.Event()
        self._socks: list[socket.socket] = []
        self._threads: list[threading.Thread] = []

    def start(self) -> None:
        for port in self._ports:
            t = threading.Thread(target=self._loop, args=(port,), daemon=True, name=f"shelly-udp-{port}")
            t.start()
            self._threads.append(t)

    def stop(self) -> None:
        self._stop.set()
        for sock in self._socks:
            try:
                sock.close()
            except OSError:
                pass
        self._socks.clear()

    def _loop(self, port: int) -> None:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind(("0.0.0.0", port))
            sock.settimeout(0.5)
        except OSError as exc:
            LOG.error("Shelly UDP Port %s: %s", port, exc)
            sock.close()
            return
        self._socks.append(sock)
        LOG.info("Shelly UDP %s auf Port %s", getattr(self._emu, "id", "?"), port)
        while not self._stop.is_set():
            try:
                data, addr = sock.recvfrom(4096)
            except TimeoutError:
                continue
            except OSError:
                break
            reply = self._reply(data, addr)
            if reply:
                try:
                    sock.sendto(reply, addr)
                except OSError:
                    pass

    def _reply(self, data: bytes, addr: tuple[str, int]) -> bytes | None:
        try:
            req = json.loads(data.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return None
        if not isinstance(req, dict):
            return None
        method = str(req.get("method") or "")
        if method not in ("EM.GetStatus", "EM1.GetStatus"):
            return None
        params = req.get("params") or {}
        if not isinstance(params, dict) or not isinstance(params.get("id"), int):
            return None
        hub = getattr(self._emu, "hub", None)
        if hub is None:
            return None
        reading = hub.read_source(
            self._emu.source_id,
            reason=f"Shelly UDP {method} von {addr[0]}",
        )
        if reading is None:
            return None
        payload = reading.to_ecotracker()
        from emulators.shelly_pro3em import em1_get_status, em_get_status

        rpc_id = req.get("id")
        src = getattr(self._emu, "_hostname", "shelly")
        if method == "EM1.GetStatus" or getattr(self._emu, "em_kind", "EM") == "EM1":
            result = em1_get_status(payload)
        else:
            result = em_get_status(payload)
        frame = {"id": rpc_id, "src": src, "dst": "unknown", "result": result}
        LOG.debug("Shelly UDP %s → %s power=%s", method, addr[0], payload.get("power"))
        return json.dumps(frame, separators=(",", ":")).encode("utf-8")
