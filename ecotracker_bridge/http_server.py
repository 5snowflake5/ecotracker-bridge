"""HTTP dispatcher: hub routes + emulator delegation."""

from __future__ import annotations

import json
import logging
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import unquote, urlparse

from status import api_status, html_status

LOG = logging.getLogger("ecotracker-bridge")


def create_server(hub: Any, port: int) -> ThreadingHTTPServer:
    handler_cls = _make_handler(hub)
    return ThreadingHTTPServer(("0.0.0.0", port), handler_cls)


def _make_handler(hub: Any) -> type[BaseHTTPRequestHandler]:
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
            self._send(code, body, "application/json; charset=utf-8")

        def _dispatch_emulators(
            self, *, http_method: str, path: str, query: str, body: bytes
        ) -> tuple[int, bytes, str] | None:
            headers = {k: v for k, v in self.headers.items()}
            client = self._client()
            for emu in hub.emulators:
                result = emu.handle(
                    http_method=http_method,
                    path=path,
                    query=query,
                    body=body,
                    headers=headers,
                    client=client,
                    hub=hub,
                )
                if result is not None:
                    return result
            return None

        def _handle_hub_routes(self, path: str) -> bool:
            client = self._client()
            if path in ("/", "/index.html"):
                # Statusseite nur Cache – sonst würde meta refresh die Hardware killen.
                cached = hub.get_status_html_cache()
                if not cached:
                    cached = html_status(hub)
                    hub.set_status_html_cache(cached)
                LOG.debug("GET / von %s → 200 Statusseite (Cache)", client)
                self._send(200, cached, "text/html; charset=utf-8")
                return True
            if path == "/api/status":
                LOG.debug("GET /api/status von %s", client)
                self._send_json(200, api_status(hub))
                return True
            return False

        def do_GET(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            path = unquote(parsed.path)
            query = parsed.query or ""
            if self._handle_hub_routes(path):
                return
            result = self._dispatch_emulators(
                http_method="GET", path=path, query=query, body=b""
            )
            if result is not None:
                code, body, ctype = result
                self._send(code, body, ctype)
                return
            LOG.debug("GET %s von %s → 404", path, self._client())
            self._send(404, b"not found", "text/plain; charset=utf-8")

        def do_POST(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            path = unquote(parsed.path)
            query = parsed.query or ""
            length = int(self.headers.get("Content-Length") or 0)
            body = self.rfile.read(length) if length > 0 else b""
            result = self._dispatch_emulators(
                http_method="POST", path=path, query=query, body=body
            )
            if result is not None:
                code, resp_body, ctype = result
                self._send(code, resp_body, ctype)
                return
            LOG.warning("POST %s von %s → 404", path, self._client())
            self._send(404, b"not found", "text/plain; charset=utf-8")

    return Handler
