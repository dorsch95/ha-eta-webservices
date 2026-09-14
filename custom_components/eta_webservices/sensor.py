"""Sensor-Entitäten für die ETA-Heizung."""

from __future__ import annotations

from homeassistant.components.sensor import SensorEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import COMPONENTS, OPTIONAL_SENSORS
from .coordinator import ETAConfigEntry, ETADataUpdateCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ETAConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Registriert alle Sensoren dieser Anlage."""
    coordinator = entry.runtime_data

    entities: list[SensorEntity] = [
        ETAMeasurementSensor(coordinator, key, info)
        for key, info in coordinator.sensor_defs.items()
        if key not in OPTIONAL_SENSORS
    ]

    entities.extend(
        ETAOptionalSensor(coordinator, key, coordinator.sensor_defs[key])
        for key in OPTIONAL_SENSORS
        if key in coordinator.sensor_defs
    )

    entities.append(ETAAscheboxStatusSensor(coordinator))
    entities.extend(
        ETAComponentMarkerSensor(coordinator, key) for key in coordinator.components
    )

    async_add_entities(entities)


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

    Die Einheit wird bewusst fest aus der Sensordefinition genommen und nicht
    aus der XML-Antwort: eine zwischendurch wechselnde Einheit lässt Home
    Assistant die Langzeitstatistik einer Entität verwerfen.
    """

    _missing_value = None

    def __init__(
        self,
        coordinator: ETADataUpdateCoordinator,
        key: str,
        info: dict,
    ) -> None:
        super().__init__(coordinator, key)
        self._attr_name = info["name"]
        self._attr_icon = info["icon"]
        self._attr_device_class = info.get("device_class")
        self._attr_state_class = info.get("state_class")

        if not info.get("is_string"):
            self._attr_native_unit_of_measurement = info.get("default_unit")
            self._attr_suggested_display_precision = 1

        if position := info.get("position"):
            self._attr_extra_state_attributes = {"position": position}

    @property
    def native_value(self):
        reading = self.coordinator.data.get(self._key)
        if reading is None:
            return self._missing_value
        return reading.value


class ETAOptionalSensor(ETAMeasurementSensor):
    """Messwert, den nicht jede Anlage hat (z.B. FWM-Zirkulation).

    Existiert immer, damit eine Dashboard-Karte ihn gefahrlos referenzieren
    kann, und zeigt "-" statt eines "Entität nicht gefunden"-Fehlers, wenn
    der Wert an dieser Anlage nicht vorhanden ist.

    Einheit und Präzision werden dynamisch geliefert: solange der Wert der
    Platzhalter "-" ist, darf keine numerische Einheit gesetzt sein, sonst
    behandelt Home Assistant die Entität als ungültig.
    """

    _missing_value = "-"

    def __init__(
        self,
        coordinator: ETADataUpdateCoordinator,
        key: str,
        info: dict,
    ) -> None:
        super().__init__(coordinator, key, info)
        self._optional_unit = info.get("default_unit")
        self._attr_native_unit_of_measurement = None
        self._attr_suggested_display_precision = None

    @property
    def native_value(self):
        reading = self.coordinator.data.get(self._key)
        if reading is None:
            return self._missing_value
        if isinstance(reading.value, float):
            return round(reading.value, 1)
        return reading.value

    @property
    def native_unit_of_measurement(self):
        if self.coordinator.data.get(self._key) is None:
            return None
        return self._optional_unit


class ETAAscheboxStatusSensor(ETABaseSensor):
    """Kombinierte Anzeige "Verbrauch/Schwellwert", z.B. "459/1000kg".

    picture-elements-Karten können keine zwei Werte zusammenführen, deshalb
    wird die Kombination hier serverseitig gebildet. Die Einheit steckt im
    Text selbst - ein Textwert mit gesetzter unit_of_measurement würde von
    Home Assistant als ungültig behandelt.
    """

    _attr_icon = "mdi:trash-can"
    _attr_name = "Aschebox Status"

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


class ETAComponentMarkerSensor(ETABaseSensor):
    """Meldet, dass eine Anlagenkomponente eingerichtet ist.

    Dashboard-Karten blenden ihre Komponenten über diese Entität ein. Eine
    Bedingung auf einen echten Messwert taugt dafür nicht: Home Assistant
    wertet eine gar nicht existierende Entität als "unknown" aus - denselben
    Zustand, den ein vorhandener Messwert kurz nach dem Start hat. Dieser
    Marker liefert stattdessen konstant den Komponentenschlüssel und bleibt
    auch bei einer gestörten Abfrage verfügbar, damit die Komponente nicht
    bei jedem Aussetzer aus dem Dashboard verschwindet.
    """

    _attr_icon = "mdi:puzzle-outline"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: ETADataUpdateCoordinator, component: str) -> None:
        super().__init__(coordinator, f"komponente_{component}")
        self._component = component
        self._attr_name = f"Komponente {COMPONENTS[component]['name']}"

    @property
    def available(self) -> bool:
        return True

    @property
    def native_value(self):
        return self._component
