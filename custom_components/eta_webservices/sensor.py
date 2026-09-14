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
    if coordinator.sensor_defs.get("pellet_gesamtverbrauch", {}).get("uri"):
        entities.append(
            ETAPelletEnergySensor(
                coordinator, "pellet_energie_gesamt", "pellet_gesamtverbrauch"
            )
        )
    else:
        entities.append(
            ETAPelletEnergySensor(coordinator, "pellet_energie", "aschebox_verbrauch")
        )
    if coordinator.enable_errors:
        entities.append(ETAErrorSensor(coordinator))
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
        """Ein Wert, der mehrfach ausbleibt, gilt als nicht erreichbar.

        Der Koordinator behält den letzten bekannten Wert, damit ein
        einzelner Timeout nichts kippt. Bleibt der Wert aber weg, soll
        die Anzeige das sagen, statt wochenlang eine alte Zahl zu
        zeigen.
        """
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

    Die Entität entsteht trotzdem und zeigt dauerhaft "-". Welche Werte
    eine Anlage hat, lässt sich nicht vorhersagen: Restsauerstoff hat
    jeder Kessel, einen Kesseldruck nicht jeder. Eine Entität, die je
    nach Anlage da ist oder fehlt, bricht Dashboards, Automatisierungen
    und Statistiken - "-" sagt dasselbe, ohne etwas kaputtzumachen.

    Einheit, Geräteklasse und Zustandsklasse bleiben leer: Home
    Assistant würde einen Sensor mit numerischer Geräteklasse und dem
    Zustand "-" sonst als fehlerhaft melden, und zwar in jedem
    Abfragezyklus.
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

    picture-elements-Karten können keine zwei Werte zusammenführen, deshalb
    wird die Kombination hier serverseitig gebildet. Die Einheit steckt im
    Text selbst - ein Textwert mit gesetzter unit_of_measurement würde von
    Home Assistant als ungültig behandelt.
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

    Die Meldungen selbst stehen in den Attributen, mit Funktionsblock,
    Priorität und Zeitpunkt - so, wie die Anlage sie unter /user/errors
    ausgibt. Damit lässt sich eine Benachrichtigung bauen, ohne am Kessel
    vorbeizugehen.
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
    """Rechnet den Pelletverbrauch in Energie um.

    Das Energie-Dashboard von Home Assistant nimmt nur Quellen an, die
    Energie in kWh als aufsummierenden Zähler liefern - Kilogramm
    Pellets versteht es nicht.

    Grundlage ist der Gesamtverbrauch der Anlage, wenn ihr Menübaum ihn
    hergibt: Er läuft immer weiter. Sonst bleibt es beim Zähler seit dem
    letzten Leeren der Aschebox; dass der zurückspringt, fängt
    total_increasing ab.

    Beide sind getrennte Entitäten, und es entsteht immer nur eine. Ein
    Wechsel der Grundlage würde sonst im Energie-Dashboard als riesiger
    Verbrauch in einer einzigen Stunde erscheinen - der Sprung von
    "seit der letzten Leerung" auf "seit dem ersten Tag".
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
        self._attr_translation_key = f"komponente_{component}"

    @property
    def available(self) -> bool:
        return True

    @property
    def native_value(self):
        return self._component
