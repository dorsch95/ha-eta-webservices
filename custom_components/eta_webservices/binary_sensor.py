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
    """Legt Störungsmelder und Wartungserinnerung an."""
    coordinator = entry.runtime_data
    entities: list[BinarySensorEntity] = []
    if coordinator.enable_errors:
        entities.append(ETAProblemBinarySensor(coordinator))
    if "aschebox_verbrauch" in coordinator.sensor_defs:
        entities.append(ETAAscheboxBinarySensor(coordinator))
    async_add_entities(entities)


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


class ETAAscheboxBinarySensor(
    CoordinatorEntity[ETADataUpdateCoordinator], BinarySensorEntity
):
    """Meldet, wenn die Aschebox geleert werden sollte.

    Die Anlage führt beides selbst: wie viel seit der letzten Leerung
    verbrannt wurde und ab welcher Menge sie geleert werden soll. Hier
    wird nur verglichen - eine eigene Schwelle einzuführen wäre geraten,
    denn sie hängt an der Boxgröße und steht an der Steuerung.

    Der Melder bleibt aus, solange einer der beiden Werte fehlt. Ein
    Vergleich mit einem unbekannten Wert wäre schlimmer als keine
    Erinnerung.
    """

    _attr_has_entity_name = True
    _attr_translation_key = "aschebox_faellig"
    _attr_device_class = BinarySensorDeviceClass.PROBLEM
    _attr_icon = "mdi:trash-can-outline"

    def __init__(self, coordinator: ETADataUpdateCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = (
            f"eta_static_{coordinator.config_entry.entry_id}_aschebox_faellig"
        )
        self._attr_device_info = coordinator.device_info

    def _zahl(self, key: str) -> float | None:
        reading = self.coordinator.data.get(key)
        if reading is None or reading.is_text or reading.value is None:
            return None
        return reading.value

    @property
    def is_on(self) -> bool:
        verbrauch = self._zahl("aschebox_verbrauch")
        schwelle = self._zahl("aschebox_schwelle")
        if verbrauch is None or schwelle is None or schwelle <= 0:
            return False
        return verbrauch >= schwelle

    @property
    def extra_state_attributes(self) -> dict:
        return {
            "verbrauch": self._zahl("aschebox_verbrauch"),
            "schwelle": self._zahl("aschebox_schwelle"),
        }
