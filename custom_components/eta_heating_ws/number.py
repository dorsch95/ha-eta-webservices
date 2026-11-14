"""Zahlen zum Einstellen - bisher das Fassungsvermögen des Pelletlagers.

Welche es gibt, steht in const.ZAHLEN. An die Anlage schreibt ein
Zahlenfeld nur mit freigegebenem Schreibzugriff und nur, wenn sie die
Zahl als beschreibbar meldet, siehe
ETADataUpdateCoordinator._zahlen_pruefen. Das Fassungsvermögen gibt es
auch sonst: Dann merkt es sich seinen Wert in Home Assistant.
"""

from __future__ import annotations

import time

from homeassistant.components.number import NumberDeviceClass, NumberEntity, NumberMode
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import ETAApiError
from .const import ZAHLEN
from .coordinator import ETAConfigEntry, ETADataUpdateCoordinator
from .entitaets_ids import ids_vorschlagen
from .switch import vorwegnahme_pruefen

GERAETEKLASSEN = {"kg": NumberDeviceClass.WEIGHT}
"""Die Geräteklasse zur Einheit einer Zahl."""


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ETAConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Legt für jede bestätigte Zahl ein Zahlenfeld an, sonst das für Home Assistant.

    Beide tragen denselben Schlüssel - es bleibt dieselbe Entität, wenn
    der Schreibzugriff später dazukommt oder wegfällt.
    """
    coordinator = entry.runtime_data
    entities: list[NumberEntity] = [
        ETAZahl(coordinator, key, definition)
        for key, definition in coordinator.zahl_defs.items()
    ]
    entities.extend(
        ETALagerMaximumEigen(coordinator, key, definition)
        for key, definition in ZAHLEN.items()
        if definition.get("sonst_in_home_assistant")
        and definition["component"] in coordinator.components
        and key not in coordinator.zahl_defs
    )
    ids_vorschlagen(coordinator.deutsche_namen, "number", entities)
    async_add_entities(entities)


class ETAZahl(CoordinatorEntity[ETADataUpdateCoordinator], NumberEntity):
    """Eine Zahl an der Anlage: gelesen wie ihr Messwert, geschrieben auf dasselbe Objekt.

    Die Grenzen nennt die Anlage; fehlen sie, gelten die aus const.ZAHLEN.
    Nach dem Schreiben steht der neue Wert sofort da - die Anlage meldet
    ihn erst etwas später, siehe switch.vorwegnahme_pruefen.
    """

    _attr_has_entity_name = True
    _attr_mode = NumberMode.BOX
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator: ETADataUpdateCoordinator, key: str, definition: dict) -> None:
        super().__init__(coordinator)
        self._quelle = definition["quelle"]
        self._uri = definition["uri"]
        self._skala = definition["scale"] or 1.0
        self._attr_translation_key = definition["translation_key"]
        self._attr_icon = definition["icon"]
        self._attr_native_unit_of_measurement = definition["einheit"]
        self._attr_device_class = GERAETEKLASSEN.get(definition["einheit"])
        self._attr_native_step = definition["schritt"]
        untere, obere = definition["grenzen"]
        if definition.get("min_roh") is not None:
            untere = max(untere, definition["min_roh"] / self._skala)
        if definition.get("max_roh") is not None:
            obere = min(obere, definition["max_roh"] / self._skala)
        self._attr_native_min_value = untere
        self._attr_native_max_value = obere
        self._attr_unique_id = f"eta_static_{coordinator.config_entry.entry_id}_{key}"
        self._attr_device_info = coordinator.device_info
        self._erwartet: float | None = None
        self._erwartet_seit = 0.0
        self._widerspruch = 0

    @property
    def native_value(self) -> float | None:
        """Der Wert der Anlage - nach dem Schreiben der neue, bis sie ihn bestätigt."""
        if self._erwartet is not None:
            return self._erwartet
        return self.coordinator.zahl(self._quelle)

    @property
    def extra_state_attributes(self) -> dict[str, str]:
        return {"gespeichert": "Anlage"}

    async def async_set_native_value(self, value: float) -> None:
        """Schreibt die Zahl auf die Anlage, im Rohwert mit ihrer Skalierung."""
        if not self.native_min_value <= value <= self.native_max_value:
            raise HomeAssistantError(
                f"Nur zwischen {self.native_min_value:g} und {self.native_max_value:g} "
                f"{self.native_unit_of_measurement}"
            )
        try:
            await self.coordinator.client.async_set_value(self._uri, str(round(value * self._skala)))
        except ETAApiError as err:
            raise HomeAssistantError(f"Die Anlage hat den Wert nicht angenommen: {err}") from err
        self._erwartet = float(value)
        self._erwartet_seit = time.monotonic()
        self._widerspruch = 0
        if self._quelle == "lager_maximum" and self.coordinator.lager_maximum_eingetragen:
            self.coordinator.lager_maximum_merken(0)
        self.async_write_ha_state()
        await self.coordinator.async_request_refresh()

    @callback
    def _handle_coordinator_update(self) -> None:
        """Gibt die Vorwegnahme auf, sobald die Anlage den Wert meldet."""
        if self._erwartet is not None:
            gemeldet = self.coordinator.zahl(self._quelle)
            if gemeldet is not None and abs(gemeldet - self._erwartet) < 0.5:
                self._erwartet = None
            else:
                self._widerspruch, vorbei = vorwegnahme_pruefen(
                    self.coordinator, self._widerspruch, self._erwartet_seit
                )
                if vorbei:
                    self._erwartet = None
        super()._handle_coordinator_update()


class ETALagerMaximumEigen(CoordinatorEntity[ETADataUpdateCoordinator], NumberEntity):
    """Das Fassungsvermögen des Pelletlagers, wenn es nicht an die Anlage geschrieben werden kann.

    Ohne Schreibzugriff, oder weil die Anlage "Maximaler Vorrat" nicht
    führt oder nicht beschreibbar meldet - ältere Regelungen führen ihn gar
    nicht. Das Feld merkt sich seinen Wert dann in Home Assistant, siehe
    ETADataUpdateCoordinator.lager_maximum_merken; Füllstand und Sensor
    rechnen damit. Solange nichts eingetragen ist, zeigt es den Wert der
    Anlage, falls sie einen meldet. 0 verwirft den eigenen Wert wieder.
    """

    _attr_has_entity_name = True
    _attr_mode = NumberMode.BOX
    _attr_entity_category = EntityCategory.CONFIG
    _attr_native_min_value = 0

    def __init__(self, coordinator: ETADataUpdateCoordinator, key: str, definition: dict) -> None:
        super().__init__(coordinator)
        self._quelle = definition["quelle"]
        self._attr_translation_key = definition["translation_key"]
        self._attr_icon = definition["icon"]
        self._attr_native_unit_of_measurement = definition["einheit"]
        self._attr_device_class = GERAETEKLASSEN.get(definition["einheit"])
        self._attr_native_step = definition["schritt"]
        self._attr_native_max_value = definition["grenzen"][1]
        self._attr_unique_id = f"eta_static_{coordinator.config_entry.entry_id}_{key}"
        self._attr_device_info = coordinator.device_info

    @property
    def native_value(self) -> float | None:
        eigen = self.coordinator.lager_maximum_eigen
        return eigen if eigen is not None else self.coordinator.zahl(self._quelle)

    @property
    def extra_state_attributes(self) -> dict[str, str | float | None]:
        return {
            "gespeichert": "Home Assistant",
            "wert_der_anlage": self.coordinator.zahl(self._quelle),
        }

    async def async_set_native_value(self, value: float) -> None:
        if not self.native_min_value <= value <= self.native_max_value:
            raise HomeAssistantError(
                f"Nur zwischen {self.native_min_value:g} und {self.native_max_value:g} "
                f"{self.native_unit_of_measurement}"
            )
        self.coordinator.lager_maximum_merken(value)
