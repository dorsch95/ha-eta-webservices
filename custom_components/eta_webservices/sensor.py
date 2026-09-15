"""Sensor-Entitäten für die ETA-Heizung."""

from __future__ import annotations

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .coordinator import ETAConfigEntry, ETADataUpdateCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ETAConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Registriert alle Sensoren dieser Anlage."""
    coordinator = entry.runtime_data

    entities: list[SensorEntity] = [
        (ETAMeasurementSensor if info.get("uri") else ETAPlaceholderSensor)(
            coordinator, key, info
        )
        for key, info in coordinator.sensor_defs.items()
        if "platform" not in info
    ]

    entities.append(ETAAscheboxStatusSensor(coordinator))
    entities.append(_pellet_energie(coordinator))
    if coordinator.enable_errors:
        entities.append(ETAErrorSensor(coordinator))
    entities.extend(
        ETAComponentMarkerSensor(coordinator, key) for key in coordinator.components
    )

    async_add_entities(entities)


def _pellet_energie(coordinator: ETADataUpdateCoordinator) -> SensorEntity:
    """Baut den Energiewert aus dem Gesamtverbrauch der Anlage.

    Führt eine Anlage den Gesamtverbrauch nicht - Hackgut- und
    Stückholzkessel messen ihren Verbrauch nicht -, entsteht ein
    Platzhalter mit "-", der sich dem Energie-Dashboard nicht anbietet.
    """
    if coordinator.sensor_defs.get("pellet_gesamtverbrauch", {}).get("uri"):
        return ETAPelletEnergySensor(
            coordinator, "pellet_energie_gesamt", "pellet_gesamtverbrauch"
        )
    return ETAPlaceholderSensor(
        coordinator,
        "pellet_energie_gesamt",
        {"translation_key": "pellet_energie_gesamt", "icon": "mdi:lightning-bolt"},
    )


class ETABaseSensor(CoordinatorEntity[ETADataUpdateCoordinator], SensorEntity):
    """Gemeinsame Basis aller ETA-Sensoren."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: ETADataUpdateCoordinator, key: str) -> None:
        super().__init__(coordinator)
        self._key = key
        self._attr_unique_id = f"eta_static_{coordinator.config_entry.entry_id}_{key}"
        self._attr_device_info = coordinator.device_info


class ETAMeasurementSensor(ETABaseSensor):
    """Ein von der Anlage gelesener Messwert.

    Die Einheit stammt fest aus der Sensordefinition, nicht aus der
    XML-Antwort: eine wechselnde Einheit verwirft die Langzeitstatistik.
    """

    _missing_value = None

    def __init__(
        self,
        coordinator: ETADataUpdateCoordinator,
        key: str,
        info: dict,
    ) -> None:
        super().__init__(coordinator, key)
        self._attr_translation_key = info["translation_key"]
        self._attr_icon = info["icon"]
        self._attr_device_class = info.get("device_class")
        self._attr_state_class = info.get("state_class")

        if not info.get("is_string"):
            self._attr_native_unit_of_measurement = info.get("default_unit")
            self._attr_suggested_display_precision = 1

        self._position = info.get("position")

    @property
    def available(self) -> bool:
        """Ein Wert, der mehrfach ausbleibt, gilt als nicht erreichbar."""
        if not super().available:
            return False
        return self.coordinator.sensor_status(self._key) != "nicht_erreichbar"

    @property
    def extra_state_attributes(self) -> dict:
        attribute = {"status": self.coordinator.sensor_status(self._key)}
        if self._position:
            attribute["position"] = self._position
        return attribute

    @property
    def native_value(self):
        reading = self.coordinator.data.get(self._key)
        if reading is None:
            return self._missing_value
        return reading.display


class ETAPlaceholderSensor(ETAMeasurementSensor):
    """Ein Messwert, den der Menübaum dieser Anlage nicht hergibt.

    Die Entität entsteht trotzdem und zeigt dauerhaft "-", damit
    Dashboards und Automatisierungen nicht je nach Anlage ins Leere
    zeigen. Einheit, Geräte- und Zustandsklasse bleiben leer - Home
    Assistant lehnt einen Sensor mit numerischer Geräteklasse und dem
    Zustand "-" sonst ab.
    """

    _attr_device_class = None
    _attr_state_class = None
    _attr_native_unit_of_measurement = None
    _attr_suggested_display_precision = None

    def __init__(
        self,
        coordinator: ETADataUpdateCoordinator,
        key: str,
        info: dict,
    ) -> None:
        super().__init__(coordinator, key, info)
        self._attr_device_class = None
        self._attr_state_class = None
        self._attr_native_unit_of_measurement = None
        self._attr_suggested_display_precision = None

    @property
    def native_value(self) -> str:
        return "-"


class ETAAscheboxStatusSensor(ETABaseSensor):
    """Kombinierte Anzeige "Verbrauch/Schwellwert", z.B. "459/1000kg".

    picture-elements-Karten können keine zwei Werte zusammenführen. Die
    Einheit steckt im Text selbst, weil ein Textwert keine
    unit_of_measurement tragen darf.
    """

    _attr_icon = "mdi:trash-can"
    _attr_translation_key = "aschebox_status"

    def __init__(self, coordinator: ETADataUpdateCoordinator) -> None:
        super().__init__(coordinator, "aschebox_status")

    @property
    def native_value(self):
        verbrauch = self.coordinator.data.get("aschebox_verbrauch")
        schwelle = self.coordinator.data.get("aschebox_schwelle")
        if verbrauch is None or schwelle is None:
            return None
        try:
            return f"{float(verbrauch.value):.0f}/{float(schwelle.value):.0f}kg"
        except (TypeError, ValueError):
            return None


class ETAErrorSensor(ETABaseSensor):
    """Zeigt, wie viele Fehler an der Anlage anstehen.

    Die Meldungen stehen in den Attributen, mit Funktionsblock, Priorität
    und Zeitpunkt.
    """

    _attr_translation_key = "aktive_fehler"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator: ETADataUpdateCoordinator) -> None:
        super().__init__(coordinator, "aktive_fehler")

    @property
    def icon(self) -> str:
        return "mdi:alert-circle" if self.coordinator.errors else "mdi:check-circle"

    @property
    def native_value(self) -> int:
        return len(self.coordinator.errors)

    @property
    def extra_state_attributes(self) -> dict:
        return {"fehler": [fehler.as_dict() for fehler in self.coordinator.errors]}


class ETAPelletEnergySensor(ETABaseSensor):
    """Rechnet den Gesamtverbrauch in Kilogramm in Energie um.

    Das Energie-Dashboard nimmt nur Quellen an, die Energie in kWh als
    aufsummierenden Zähler liefern.
    """

    _attr_icon = "mdi:lightning-bolt"
    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_native_unit_of_measurement = "kWh"
    _attr_suggested_display_precision = 0

    def __init__(
        self, coordinator: ETADataUpdateCoordinator, key: str, quelle: str
    ) -> None:
        super().__init__(coordinator, key)
        self._attr_translation_key = key
        self._quelle = quelle

    @property
    def native_value(self):
        verbrauch = self.coordinator.data.get(self._quelle)
        if verbrauch is None:
            return None
        try:
            return float(verbrauch.value) * self.coordinator.pellet_kwh_per_kg
        except (TypeError, ValueError):
            return None


class ETAComponentMarkerSensor(ETABaseSensor):
    """Meldet, dass eine Anlagenkomponente eingerichtet ist.

    Dashboard-Karten blenden ihre Kacheln darüber ein. Der Marker liefert
    konstant den Komponentenschlüssel und bleibt auch bei gestörter
    Abfrage verfügbar.
    """

    _attr_icon = "mdi:puzzle-outline"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: ETADataUpdateCoordinator, component: str) -> None:
        super().__init__(coordinator, f"komponente_{component}")
        self._component = component
        self._attr_translation_key = f"komponente_{component}"

    @property
    def available(self) -> bool:
        return True

    @property
    def native_value(self):
        return self._component
