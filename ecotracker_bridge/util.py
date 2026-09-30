"""Shared helpers (timezone, logging, network)."""

from __future__ import annotations

import logging
import socket
import sys
from datetime import datetime, timedelta, timezone

VERSION = "1.4.0"

BERLIN = timezone(timedelta(hours=2))
OPTIONS_PATHS = ("/data/options.json", "options.json")


def berlin_tz():
    try:
        from zoneinfo import ZoneInfo

        return ZoneInfo("Europe/Berlin")
    except Exception:
        return BERLIN


class BerlinFormatter(logging.Formatter):
    """Log-Zeitstempel immer Europe/Berlin, unabhängig von Container-UTC."""

    def formatTime(self, record: logging.LogRecord, datefmt: str | None = None) -> str:  # noqa: N802
        dt = datetime.fromtimestamp(record.created, tz=timezone.utc).astimezone(berlin_tz())
        if datefmt:
            return dt.strftime(datefmt)
        return dt.isoformat(timespec="seconds")


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
    return datetime.now(berlin_tz())


def normalize_mac(raw: str) -> str:
    mac = "".join(ch for ch in raw.upper() if ch.isalnum())
    if len(mac) != 12:
        raise SystemExit(f"MAC muss 12 Hex-Zeichen haben, nicht {raw!r}")
    return mac


def detect_ipv4() -> str:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(("1.1.1.1", 80))
        return sock.getsockname()[0]
    except OSError:
        try:
            hostname_ip = socket.gethostbyname(socket.gethostname())
            if hostname_ip and not hostname_ip.startswith("127."):
                return hostname_ip
        except OSError:
            pass
        return "127.0.0.1"
    finally:
        sock.close()
