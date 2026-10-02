"""Shared polling/cache helper for pull-based sources."""

from __future__ import annotations

import logging
import threading
import time
from datetime import datetime
from typing import Any

from model import Reading, Source

LOG = logging.getLogger("ecotracker-bridge")


class PollingSource(Source):
    """Throttle + last-good cache. Subclasses implement :meth:`fetch`."""

    min_refetch_s = 2.0
    error_retry_s = 30.0
    error_log_interval_s = 60.0

    def __init__(self, cfg: dict[str, Any]) -> None:
        self.id = str(cfg.get("id") or self.type)
        self.label = str(cfg.get("label") or self.id)
        self.min_refetch_s = float(cfg.get("min_refetch_s") or self.min_refetch_s)
        self.error_retry_s = float(cfg.get("error_retry_s") or self.error_retry_s)
        self._lock = threading.Lock()
        self._fetch_lock = threading.Lock()
        self._last: Reading | None = None
        self._last_ok: datetime | None = None
        self._last_fetch_mono = 0.0
        self._error_until = 0.0
        self._last_error: str | None = None
        self._polls_ok = 0
        self._polls_fail = 0
        self._last_error_log = 0.0

    def fetch(self) -> Reading:
        raise NotImplementedError

    def snapshot(self) -> Reading | None:
        with self._lock:
            return self._last

    def stats(self) -> dict[str, Any]:
        with self._lock:
            return {
                "id": self.id,
                "type": self.type,
                "label": self.label,
                "last_ok": self._last_ok,
                "last_error": self._last_error,
                "polls_ok": self._polls_ok,
                "polls_fail": self._polls_fail,
            }

    def read(self, *, reason: str = "", force: bool = False) -> Reading | None:
        now = time.monotonic()
        with self._lock:
            last = self._last
            last_mono = self._last_fetch_mono
            error_until = self._error_until
        if not force and error_until and now < error_until:
            LOG.debug(
                "Quelle %s Pause nach Fehler (%s): noch %.0f s",
                self.id,
                reason,
                error_until - now,
            )
            return last
        if not force and last is not None and last_mono > 0:
            age = now - last_mono
            if age < self.min_refetch_s:
                LOG.debug(
                    "Quelle %s übersprungen (%s): Cache %.1f s alt (< %.1f s)",
                    self.id,
                    reason,
                    age,
                    self.min_refetch_s,
                )
                return last
        if not self._fetch_lock.acquire(blocking=False):
            return last
        try:
            return self._do_fetch(reason)
        finally:
            self._fetch_lock.release()

    def _do_fetch(self, reason: str) -> Reading | None:
        try:
            reading = self.fetch()
        except Exception as exc:
            with self._lock:
                self._last_fetch_mono = time.monotonic()
                self._error_until = self._last_fetch_mono + self.error_retry_s
            return self._on_error(exc, reason)
        reading.source_id = self.id
        with self._lock:
            self._last = reading
            self._last_ok = reading.fetched_at
            self._last_fetch_mono = time.monotonic()
            self._error_until = 0.0
            self._last_error = None
            self._polls_ok += 1
            ok_count = self._polls_ok
        LOG.debug(
            "Quelle %s ok (%s) #%s: power=%s W",
            self.id,
            reason,
            ok_count,
            reading.power_w,
        )
        return reading

    def _on_error(self, exc: Exception, reason: str) -> Reading | None:
        now = time.monotonic()
        with self._lock:
            self._last_error = str(exc)
            self._polls_fail += 1
            fail_count = self._polls_fail
            cached = self._last
        if now - self._last_error_log >= self.error_log_interval_s:
            self._last_error_log = now
            LOG.error(
                "Quelle %s fehlgeschlagen (%s) #%s: %s%s",
                self.id,
                reason,
                fail_count,
                exc,
                " – Cache bleibt aktiv" if cached is not None else "",
            )
        else:
            LOG.debug(
                "Quelle %s fehlgeschlagen (%s) #%s: %s",
                self.id,
                reason,
                fail_count,
                exc,
            )
        return cached
