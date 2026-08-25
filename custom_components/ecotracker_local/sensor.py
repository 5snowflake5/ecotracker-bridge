"""Sensors for EcoTracker Local."""

from __future__ import annotations

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfEnergy, UnitOfPower
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import source_url
from .const import DOMAIN, SENSOR_TYPES

DEVICE_CLASS_MAP = {
    "power": SensorDeviceClass.POWER,
    "energy": SensorDeviceClass.ENERGY,
}
STATE_CLASS_MAP = {
    "measurement": SensorStateClass.MEASUREMENT,
    "total_increasing": SensorStateClass.TOTAL_INCREASING,
}
UNIT_MAP = {
    "W": UnitOfPower.WATT,
    "Wh": UnitOfEnergy.WATT_HOUR,
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator = hass.data[DOMAIN][entry.entry_id]
    entities = [
        EcoTrackerSensor(coordinator, entry, json_key, meta)
        for json_key, meta in SENSOR_TYPES.items()
    ]
    async_add_entities(entities)


class EcoTrackerSensor(CoordinatorEntity, SensorEntity):
    _attr_has_entity_name = True

    def __init__(self, coordinator, entry: ConfigEntry, json_key: str, meta: tuple) -> None:
        super().__init__(coordinator)
        key, unit, device_class, state_class, precision = meta
        self._json_key = json_key
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._attr_translation_key = key
        self._attr_native_unit_of_measurement = UNIT_MAP.get(unit, unit)
        if device_class:
            self._attr_device_class = DEVICE_CLASS_MAP[device_class]
        if state_class:
            self._attr_state_class = STATE_CLASS_MAP[state_class]
        if precision is not None:
            self._attr_suggested_display_precision = precision
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title,
            manufacturer="everHome",
            model="EcoTracker (local API)",
            configuration_url=source_url(str(entry.data.get("host", ""))),
        )

    @property
    def available(self) -> bool:
        if not super().available:
            return False
        data = self.coordinator.data or {}
        return self._json_key in data and data[self._json_key] is not None

    @property
    def native_value(self):
        data = self.coordinator.data or {}
        value = data.get(self._json_key)
        if value is None:
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None
