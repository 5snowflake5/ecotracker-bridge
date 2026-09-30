"""HTTP GET JSON helper for pull sources."""

from __future__ import annotations

import json
import ssl
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from util import VERSION, berlin_now

FETCH_HEADERS = {"Accept": "application/json", "User-Agent": f"ecotracker-bridge/{VERSION}"}


def cfg_host(cfg: dict[str, Any]) -> str:
    raw = cfg.get("url") or cfg.get("host") or cfg.get("ip") or cfg.get("source_url") or ""
    host = str(raw).strip().rstrip("/")
    if host.startswith("http://") or host.startswith("https://"):
        # strip scheme for callers that build their own path
        return host
    return host


def cfg_base_url(cfg: dict[str, Any], *, default_scheme: str = "http") -> str:
    host = str(cfg.get("url") or cfg.get("host") or cfg.get("ip") or "").strip().rstrip("/")
    if not host:
        raise ValueError("url/host/ip fehlt")
    if host.startswith("http://") or host.startswith("https://"):
        return host
    return f"{default_scheme}://{host}"


def fetch_bytes(
    url: str,
    *,
    timeout: float = 4.0,
    user: str | None = None,
    password: str | None = None,
    headers: dict[str, str] | None = None,
    insecure_tls: bool = False,
) -> bytes:
    hdrs = dict(FETCH_HEADERS)
    if headers:
        hdrs.update(headers)
    if user:
        import base64

        token = base64.b64encode(f"{user}:{password or ''}".encode()).decode("ascii")
        hdrs["Authorization"] = f"Basic {token}"
    req = Request(url, headers=hdrs, method="GET")
    ctx = None
    if url.startswith("https://") and insecure_tls:
        ctx = ssl._create_unverified_context()
    try:
        with urlopen(req, timeout=timeout, context=ctx) as resp:
            return resp.read()
    except HTTPError as exc:
        body = exc.read() if exc.fp else b""
        raise ValueError(f"HTTP {exc.code} für {url}: {body[:200]!r}") from exc
    except (URLError, TimeoutError, OSError) as exc:
        raise ValueError(f"Abruf fehlgeschlagen ({url}): {exc}") from exc


def fetch_json(url: str, **kwargs: Any) -> Any:
    raw = fetch_bytes(url, **kwargs)
    try:
        data = json.loads(raw.decode("utf-8", errors="replace"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Keine JSON-Antwort von {url}") from exc
    return data


def watts_reading(
    power_w: float,
    *,
    source_id: str = "",
    l1: float | None = None,
    l2: float | None = None,
    l3: float | None = None,
    energy_in_wh: float | None = None,
    energy_out_wh: float | None = None,
    extra: dict[str, Any] | None = None,
):
    from model import Reading

    return Reading(
        power_w=float(power_w),
        power_l1_w=l1,
        power_l2_w=l2,
        power_l3_w=l3,
        energy_import_wh=energy_in_wh,
        energy_export_wh=energy_out_wh,
        extra=dict(extra or {}),
        source_id=source_id,
        fetched_at=berlin_now(),
    )
