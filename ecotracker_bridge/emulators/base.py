"""Helpers shared by protocol emulators."""

from __future__ import annotations

from typing import Any


def header_host(headers: dict[str, str]) -> str:
    raw = headers.get("Host") or headers.get("host") or ""
    return raw.split(":", 1)[0].strip().lower()


def host_matches(headers: dict[str, str], hostnames: list[str]) -> bool:
    """True if Host is empty (compat) or matches one of the emulator hostnames."""
    if not hostnames:
        return True
    host = header_host(headers)
    if not host:
        return True
    names = {n.lower() for n in hostnames}
    names.update(f"{n}.local".lower() for n in hostnames)
    return host in names


def should_claim(emu: Any, hub: Any, headers: dict[str, str]) -> bool:
    peers = hub.emulators_of_type(emu.type)
    if len(peers) <= 1:
        return True
    host = header_host(headers)
    if not host:
        return peers[0] is emu
    return host_matches(headers, emu.hostnames)
