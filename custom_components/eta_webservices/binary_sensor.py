"""Binäre Zustände der ETA-Heizung."""

from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .coordinator import ETAConfigEntry, ETADataUpdateCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ETAConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Legt den Störungsmelder an, sofern Störungen gelesen werden."""
    coordinator = entry.runtime_data
    if coordinator.enable_errors:
        async_add_entities([ETAProblemBinarySensor(coordinator)])


class ETAProblemBinarySensor(
    CoordinatorEntity[ETADataUpdateCoordinator], BinarySensorEntity
):
    """Meldet, ob an der Anlage eine Störung ansteht.

    Den Zähler gibt es schon als Sensor. Der hier ist an, sobald
    mindestens eine Störung anliegt - damit reicht in einer
    Automatisierung ein Gerätetrigger, statt einen Zahlenwert mit Null
    zu vergleichen.
    """

    _attr_has_entity_name = True
    _attr_translation_key = "stoerung"
    _attr_device_class = BinarySensorDeviceClass.PROBLEM

    def __init__(self, coordinator: ETADataUpdateCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = (
            f"eta_static_{coordinator.config_entry.entry_id}_stoerung"
        )
        self._attr_device_info = coordinator.device_info

    @property
    def is_on(self) -> bool:
        return bool(self.coordinator.errors)

    @property
    def extra_state_attributes(self) -> dict:
        """Dieselben Meldungen wie am Zähler, damit beides zusammenpasst."""
        return {
            "anzahl": len(self.coordinator.errors),
            "fehler": [fehler.as_dict() for fehler in self.coordinator.errors],
        }
