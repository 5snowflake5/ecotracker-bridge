#!/usr/bin/env python3
"""Lightweight everHome EcoTracker proxy for Growatt NOAH.

Polls a physical EcoTracker (`GET /v1/json`), serves the same payload on
port 80, and announces `_everhome._tcp` via mDNS so ShinePhone can pair.
"""

from __future__ import annotations

import json
import os
import socket
import threading
import time
from datetime import datetime, timezone, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.error import URLError, HTTPError
from urllib.request import Request, urlopen

from zeroconf import IPVersion, ServiceInfo, Zeroconf

BERLIN = timezone(timedelta(hours=2))  # display only; refreshed via tm
OPTIONS_PATHS = ("/data/options.json", "options.json")


def berlin_now() -> datetime:
    try:
        from zoneinfo import ZoneInfo

        return datetime.now(ZoneInfo("Europe/Berlin"))
    except Exception:
        return datetime.now(BERLIN)


def load_options() -> dict[str, Any]:
    for path in OPTIONS_PATHS:
        if os.path.isfile(path):
            with open(path, encoding="utf-8") as fh:
                return json.load(fh)
    raise SystemExit(f"Keine Optionsdatei gefunden ({', '.join(OPTIONS_PATHS)})")


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


def poll_loop(url: str, interval: float) -> None:
    headers = {"Accept": "application/json", "User-Agent": "ecotracker-bridge/1.0"}
    while True:
        try:
            req = Request(url, headers=headers, method="GET")
            with urlopen(req, timeout=2.5) as resp:
                body = resp.read()
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
        except (URLError, HTTPError, TimeoutError, ValueError, json.JSONDecodeError) as exc:
            with STATE.lock:
                STATE.last_error = str(exc)
                STATE.polls_fail += 1
            print(f"poll fail: {exc}", flush=True)
        time.sleep(interval)


def html_status(snap: dict[str, Any]) -> bytes:
    payload = snap["payload"]
    last_ok = snap["last_ok"]
    last_ok_s = last_ok.strftime("%d.%m.%Y %H:%M:%S") if last_ok else "noch keine Daten"
    err = snap["last_error"] or "—"
    power = payload.get("power") if payload else "—"
    rows = ""
    if payload:
        for key, value in payload.items():
            rows += f"<tr><td>{key}</td><td>{value}</td></tr>"
    else:
        rows = "<tr><td colspan=2>Warte auf den physischen EcoTracker…</td></tr>"

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
  <h1>EcoTracker Bridge</h1>
  <p class="muted">Virtueller EcoTracker für Growatt NOAH. Seite aktualisiert sich selbst.</p>
  <table>
    <tr><th>Leistung</th><td>{power} W</td></tr>
    <tr><th>Letzter erfolgreicher Poll</th><td>{last_ok_s}</td></tr>
    <tr><th>Letzter Fehler</th><td>{err}</td></tr>
    <tr><th>Polls ok / fehl</th><td>{snap["polls_ok"]} / {snap["polls_fail"]}</td></tr>
    <tr><th>Quelle</th><td><code>{META["source_url"]}</code></td></tr>
    <tr><th>mDNS</th><td><code>{META["hostname"]}._everhome._tcp.local</code></td></tr>
    <tr><th>JSON</th><td><a href="/v1/json"><code>/v1/json</code></a></td></tr>
    <tr><th>Angekündigte IP</th><td>{META["announce_ip"]}:{META["port"]}</td></tr>
    <tr><th>Serial / productid</th><td>{META["serial"]} / {META["productid"]}</td></tr>
  </table>
  <h2>Rohdaten</h2>
  <table>{rows}</table>
</body>
</html>
"""
    return html.encode("utf-8")


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt: str, *args: Any) -> None:
        if "/v1/json" in str(args[0] if args else ""):
            return
        print(f"http {args[0] if args else fmt}", flush=True)

    def _send(self, code: int, body: bytes, content_type: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        path = self.path.split("?", 1)[0]
        snap = STATE.snapshot()
        if path in ("/v1/json", "/v1/json/"):
            if snap["raw"] is None:
                msg = json.dumps({"error": "noch keine Daten vom physischen EcoTracker"}).encode()
                self._send(503, msg, "application/json; charset=utf-8")
                return
            self._send(200, snap["raw"], "application/json")
            return
        if path in ("/", "/index.html"):
            self._send(200, html_status(snap), "text/html; charset=utf-8")
            return
        self._send(404, b"not found", "text/plain; charset=utf-8")


def register_mdns(hostname: str, ip: str, port: int, serial: str, productid: str) -> tuple[Zeroconf, ServiceInfo]:
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
    print(
        f"mdns: {hostname}._everhome._tcp.local → {ip}:{port} "
        f"serial={serial} productid={productid}",
        flush=True,
    )
    return zc, info


def main() -> None:
    opts = load_options()
    mac = normalize_mac(str(opts.get("mac", "B43A45A1B2C3")))
    hostname = f"ecotracker-{mac.lower()}"
    serial = str(opts.get("serial", "293d45273261"))
    productid = str(opts.get("productid", "1137"))
    port = int(opts.get("port", 80))
    poll_seconds = float(opts.get("poll_seconds", 1))
    source = source_json_url(str(opts["source_url"]))
    announce_ip = str(opts.get("announce_ip") or "").strip() or detect_ipv4()

    META.update(
        {
            "source_url": source,
            "hostname": hostname,
            "announce_ip": announce_ip,
            "port": port,
            "serial": serial,
            "productid": productid,
        }
    )

    print(f"quelle: {source}", flush=True)
    print(f"listen: 0.0.0.0:{port}  announce: {announce_ip}", flush=True)

    threading.Thread(target=poll_loop, args=(source, poll_seconds), daemon=True).start()

    zc = None
    try:
        zc, _info = register_mdns(hostname, announce_ip, port, serial, productid)
    except Exception as exc:
        print(f"mdns fehlgeschlagen: {exc}", flush=True)
        print(
            "HTTP läuft trotzdem. Growatt NOAH findet den Zähler ohne mDNS nicht.",
            flush=True,
        )

    httpd = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
        if zc is not None:
            zc.unregister_all_services()
            zc.close()


if __name__ == "__main__":
    main()
