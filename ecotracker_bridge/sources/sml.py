"""Minimal SML scanner for German eHZ OBIS codes (Tibber Pulse binary /data.json)."""

from __future__ import annotations

# 77 07 + 6-byte OBIS
OBIS_POWER = "0100100700ff"
OBIS_L1 = "0100240700ff"
OBIS_L2 = "0100380700ff"
OBIS_L3 = "01004c0700ff"
OBIS_ENERGY_IN = "0100010800ff"
OBIS_ENERGY_OUT = "0100020800ff"


def _sml_value_after(payload: bytes, start: int) -> float | None:
    data = payload[start : start + 48]
    for j, byte in enumerate(data[:-4]):
        if byte != 0x52:
            continue
        scaler = int.from_bytes(bytes([data[j + 1]]), "big", signed=True)
        k = j + 2
        if k >= len(data):
            return None
        tl = data[k]
        length = tl & 0x0F
        n = length - 1
        if n <= 0 or k + 1 + n > len(data):
            continue
        raw = data[k + 1 : k + 1 + n]
        signed = (tl & 0x70) == 0x50
        val = int.from_bytes(raw, "big", signed=signed)
        return float(val) * (10 ** scaler)
    return None


def extract_obis(payload: bytes, obis_hex: str) -> float | None:
    needle = b"\x77\x07" + bytes.fromhex(obis_hex)
    idx = payload.find(needle)
    if idx < 0:
        return None
    return _sml_value_after(payload, idx + len(needle))


def parse_sml_power(payload: bytes, *, power_obis: str = OBIS_POWER) -> dict[str, float | None]:
    l1 = extract_obis(payload, OBIS_L1)
    l2 = extract_obis(payload, OBIS_L2)
    l3 = extract_obis(payload, OBIS_L3)
    power = extract_obis(payload, power_obis)
    if l1 is not None or l2 is not None or l3 is not None:
        total = (l1 or 0) + (l2 or 0) + (l3 or 0)
        if power is None:
            power = total
    energy_in = extract_obis(payload, OBIS_ENERGY_IN)
    energy_out = extract_obis(payload, OBIS_ENERGY_OUT)
    return {
        "power": power,
        "l1": l1,
        "l2": l2,
        "l3": l3,
        "energy_in": energy_in,
        "energy_out": energy_out,
    }
