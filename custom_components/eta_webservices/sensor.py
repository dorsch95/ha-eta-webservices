"""Sensor-Entitäten für die ETA-Heizung."""

from __future__ import annotations

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, OPTIONAL_SENSORS
from .coordinator import ETADataUpdateCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Registriert alle Sensoren dieser Anlage."""
    coordinator: ETADataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]

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
    entities.append(ETASystemImageSensor(coordinator))

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


class ETASystemImageSensor(ETABaseSensor):
    """Gibt den Bildschlüssel des gewählten Anlagenschemas aus."""

    _attr_icon = "mdi:image"
    _attr_name = "Anlagenbild Pfad"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: ETADataUpdateCoordinator) -> None:
        super().__init__(coordinator, "image")
        self._attr_unique_id = (
            f"eta_style_{coordinator.config_entry.entry_id}_image"
        )

    @property
    def native_value(self):
        return self.coordinator.system_image_path
