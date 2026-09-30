"""Shelly Pro 3EM RPC helpers – gleiche Messwerte wie EcoTracker-Cache, anderes Wire-Format.

Compatibility shim: implementations live in emulators.shelly_pro3em.
"""

from __future__ import annotations

from emulators.shelly_pro3em import (
    DEFAULT_PF,
    DEFAULT_VOLTAGE,
    FW_ID,
    FW_VER,
    MODEL,
    dispatch_rpc,
    em_get_config,
    em_get_status,
    em1_get_status,
    emdata_get_status,
    mdns_properties,
    needs_meter_payload,
    phase_powers,
    shelly_get_device_info,
    shelly_get_status,
)

__all__ = [
    "DEFAULT_PF",
    "DEFAULT_VOLTAGE",
    "FW_ID",
    "FW_VER",
    "MODEL",
    "dispatch_rpc",
    "em1_get_status",
    "em_get_config",
    "em_get_status",
    "emdata_get_status",
    "mdns_properties",
    "needs_meter_payload",
    "phase_powers",
    "shelly_get_device_info",
    "shelly_get_status",
]
