"""SMA Energy Meter / Sunny Home Manager Speedwire (UDP multicast)."""

from __future__ import annotations

# After the SMA header: 2-byte ident + 2-byte type (0x0400 = uint32) + value.
# Values are 0.1 W (divide by 10).
IDENT_P_IN = 0x0001
IDENT_P_OUT = 0x0002
IDENT_L1_IN = 0x0015
IDENT_L1_OUT = 0x0016
IDENT_L2_IN = 0x0029
IDENT_L2_OUT = 0x002A
IDENT_L3_IN = 0x003D
IDENT_L3_OUT = 0x003E


def parse_speedwire(datagram: bytes) -> dict[str, float]:
    if len(datagram) < 24 or datagram[0:3] != b"SMA":
        raise ValueError("Kein SMA-Speedwire-Paket")
    fields: dict[int, float] = {}
    i = 16
    end = len(datagram) - 4
    while i + 8 <= end:
        ident = int.from_bytes(datagram[i : i + 2], "big")
        typ = int.from_bytes(datagram[i + 2 : i + 4], "big")
        if typ == 0x0400:
            raw = int.from_bytes(datagram[i + 4 : i + 8], "big")
            fields[ident] = raw / 10.0
            i += 8
            continue
        if typ == 0x0800 and i + 12 <= end:
            raw = int.from_bytes(datagram[i + 4 : i + 12], "big")
            fields[ident] = raw / 10.0
            i += 12
            continue
        i += 2
    p_in = fields.get(IDENT_P_IN, 0.0)
    p_out = fields.get(IDENT_P_OUT, 0.0)
    l1 = fields.get(IDENT_L1_IN, 0.0) - fields.get(IDENT_L1_OUT, 0.0)
    l2 = fields.get(IDENT_L2_IN, 0.0) - fields.get(IDENT_L2_OUT, 0.0)
    l3 = fields.get(IDENT_L3_IN, 0.0) - fields.get(IDENT_L3_OUT, 0.0)
    return {
        "power": p_in - p_out,
        "l1": l1,
        "l2": l2,
        "l3": l3,
    }
