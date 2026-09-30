from __future__ import annotations

from typing import Any

from model import Emulator

EMULATOR_TYPES = (
    "ecotracker",
    "shelly_pro3em",
    "shelly_emg3",
    "shelly_proem50",
    "chargee_sparky",
)


def create_emulator(cfg: dict[str, Any]) -> Emulator:
    kind = str(cfg.get("type") or "").strip().lower().replace("-", "_")
    if kind == "ecotracker":
        from emulators.ecotracker import EcoTrackerEmulator

        return EcoTrackerEmulator(cfg)
    if kind in (
        "shelly_pro3em",
        "shellypro3em",
        "shelly_emg3",
        "shellyemg3",
        "shelly_em_gen3",
        "shelly_proem50",
        "shellyproem50",
        "shelly_pro_em50",
    ):
        from emulators.shelly_pro3em import ShellyPro3EmEmulator

        return ShellyPro3EmEmulator(cfg)
    if kind in ("chargee_sparky", "sparky", "chargee"):
        from emulators.chargee_sparky import ChargeeSparkyEmulator

        return ChargeeSparkyEmulator(cfg)
    raise ValueError(f"Unbekannter Emulator-Typ: {kind!r} (erlaubt: {', '.join(EMULATOR_TYPES)})")
