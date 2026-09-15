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
    if "lager_vorrat" in coordinator.sensor_defs:
        entities.append(ETALagerBinarySensor(coordinator))
    async_add_entities(entities)


class ETABaseBinarySensor(
    CoordinatorEntity[ETADataUpdateCoordinator], BinarySensorEntity
):
    """Gemeinsame Basis aller binären Melder."""

    _attr_has_entity_name = True
    _attr_device_class = BinarySensorDeviceClass.PROBLEM

    def __init__(self, coordinator: ETADataUpdateCoordinator, key: str) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"eta_static_{coordinator.config_entry.entry_id}_{key}"
        self._attr_device_info = coordinator.device_info

    def _zahl(self, key: str) -> float | None:
        """Der Messwert als Zahl, oder None wenn er fehlt oder Text ist."""
        reading = self.coordinator.data.get(key)
        if reading is None or reading.is_text or reading.value is None:
            return None
        return reading.value


class ETAProblemBinarySensor(ETABaseBinarySensor):
    """Meldet, ob an der Anlage mindestens eine Störung ansteht."""

    _attr_translation_key = "stoerung"

    def __init__(self, coordinator: ETADataUpdateCoordinator) -> None:
        super().__init__(coordinator, "stoerung")

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


class ETAAscheboxBinarySensor(ETABaseBinarySensor):
    """Meldet, wenn die Aschebox geleert werden sollte.

    Verglichen werden zwei Werte der Anlage: die Menge seit der letzten
    Leerung und die dort eingestellte Schwelle. Fehlt einer davon, bleibt
    der Melder aus.
    """

    _attr_translation_key = "aschebox_faellig"
    _attr_icon = "mdi:trash-can-outline"

    def __init__(self, coordinator: ETADataUpdateCoordinator) -> None:
        super().__init__(coordinator, "aschebox_faellig")

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


class ETALagerBinarySensor(ETABaseBinarySensor):
    """Meldet, wenn der Vorrat im Pelletlager zur Neige geht.

    Die Warngrenze stammt aus der Anlage, wo sie auf den eigenen
    Lagerraum eingestellt ist.
    """

    _attr_translation_key = "lager_niedrig"
    _attr_icon = "mdi:silo"

    def __init__(self, coordinator: ETADataUpdateCoordinator) -> None:
        super().__init__(coordinator, "lager_niedrig")

    @property
    def is_on(self) -> bool:
        vorrat = self._zahl("lager_vorrat")
        grenze = self._zahl("lager_warngrenze")
        if vorrat is None or grenze is None or grenze <= 0:
            return False
        return vorrat <= grenze

    @property
    def extra_state_attributes(self) -> dict:
        vorrat = self._zahl("lager_vorrat")
        maximum = self._zahl("lager_maximum")
        fuellstand = None
        if vorrat is not None and maximum:
            fuellstand = round(vorrat / maximum * 100, 1)
        return {
            "vorrat": vorrat,
            "warngrenze": self._zahl("lager_warngrenze"),
            "fuellstand_prozent": fuellstand,
        }
