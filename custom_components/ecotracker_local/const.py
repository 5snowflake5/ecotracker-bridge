"""Constants for EcoTracker Local."""

DOMAIN = "ecotracker_local"
DEFAULT_NAME = "EcoTracker"
DEFAULT_SCAN_INTERVAL = 5
CONF_HOST = "host"
CONF_SCAN_INTERVAL = "scan_interval"

# JSON key → (translation key / sensor key, unit, device_class, state_class, precision)
SENSOR_TYPES: dict[str, tuple[str, str | None, str | None, str | None, int | None]] = {
    "power": ("power", "W", "power", "measurement", 0),
    "powerAvg": ("power_avg", "W", "power", "measurement", 0),
    "powerPhase1": ("power_phase_1", "W", "power", "measurement", 0),
    "powerPhase2": ("power_phase_2", "W", "power", "measurement", 0),
    "powerPhase3": ("power_phase_3", "W", "power", "measurement", 0),
    "energyCounterIn": ("energy_in", "Wh", "energy", "total_increasing", 0),
    "energyCounterInT1": ("energy_in_t1", "Wh", "energy", "total_increasing", 0),
    "energyCounterInT2": ("energy_in_t2", "Wh", "energy", "total_increasing", 0),
    "energyCounterOut": ("energy_out", "Wh", "energy", "total_increasing", 0),
}
