"""Tiny dotted-path extractor for JSON meter payloads.

Supports ``emeters.0.power`` and ``emeters[0].power``. Missing paths return None.
"""

from __future__ import annotations

from typing import Any


def extract(obj: Any, path: str | None) -> Any:
    if not path or obj is None:
        return None
    cur: Any = obj
    normalized = path.strip()
    if normalized.startswith("$."):
        normalized = normalized[2:]
    elif normalized == "$":
        return obj
    normalized = normalized.replace("[", ".").replace("]", "")
    for part in normalized.split("."):
        if part == "":
            continue
        if cur is None:
            return None
        if isinstance(cur, list):
            try:
                cur = cur[int(part)]
            except (ValueError, IndexError):
                return None
            continue
        if isinstance(cur, dict):
            if part in cur:
                cur = cur[part]
                continue
            if part.isdigit():
                return None
            return None
        return None
    return cur


def extract_float(obj: Any, path: str | None) -> float | None:
    value = extract(obj, path)
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
