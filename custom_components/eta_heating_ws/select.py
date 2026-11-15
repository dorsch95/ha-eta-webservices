"""Betriebsart der Heizkreise und die Bilder von Brenner und Fremdwärme."""

from __future__ import annotations

import time

from homeassistant.components.select import SelectEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import ETAApiError
from .const import BETRIEBSART_AUS, BILD_AUSWAHLEN
from .coordinator import ETAConfigEntry, ETADataUpdateCoordinator
from .entitaets_ids import ids_vorschlagen
from .karte import ERZEUGER_BILDER
from .switch import vorwegnahme_pruefen


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ETAConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Legt je erkanntem Heizkreis eine Betriebsart-Auswahl an, dazu die Bildauswahlen."""
    coordinator = entry.runtime_data
    entities: list[SelectEntity] = [
        ETABetriebsartSelect(coordinator, key, definition)
        for key, definition in coordinator.select_defs.items()
    ]
    coordinator.betriebsart_auswahl.update({e.schluessel: e for e in entities})
    entities.extend(
        ETABildAuswahl(coordinator, key, definition)
        for key, definition in BILD_AUSWAHLEN.items()
        if definition["component"] in coordinator.components
    )
    ids_vorschlagen(coordinator.deutsche_namen, "select", entities)
    async_add_entities(entities)


class ETABildAuswahl(SelectEntity, RestoreEntity):
    """Welches Bild die Dashboard-Karten für Brenner oder Fremdwärme zeigen.

    Die Anlage sagt nicht, was hinter dem Funktionsblock steht - der Nutzer
    wählt es hier, siehe karte.ERZEUGER_BILDER. Beide Karten fragen diese
    Auswahl ab. An der Anlage ändert sie nichts, deshalb gibt es sie auch
    ohne Schreibzugriff. Nach einem Neustart gilt die letzte Wahl, anfangs
    die Vorgabe aus const.BILD_AUSWAHLEN.
    """

    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.CONFIG
    _attr_should_poll = False

    def __init__(
        self, coordinator: ETADataUpdateCoordinator, key: str, definition: dict
    ) -> None:
        self._attr_translation_key = definition["translation_key"]
        self._attr_icon = definition["icon"]
        self._attr_options = list(ERZEUGER_BILDER)
        self._attr_current_option = definition["vorgabe"]
        self._attr_unique_id = f"eta_static_{coordinator.config_entry.entry_id}_{key}"
        self._attr_device_info = coordinator.device_info

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        letzter = await self.async_get_last_state()
        if letzter is not None and letzter.state in self._attr_options:
            self._attr_current_option = letzter.state

    async def async_select_option(self, option: str) -> None:
        self._attr_current_option = option
        self.async_write_ha_state()


class ETABetriebsartSelect(
    CoordinatorEntity[ETADataUpdateCoordinator], SelectEntity
):
    """Automatik, Heizen, Absenken oder Aus - für einen Heizkreis.

    An der Anlage sind das drei Tasten plus die Ein/Aus-Taste: Läuft der
    Heizkreis, steht genau eine der drei auf "Ein".
    """

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: ETADataUpdateCoordinator,
        key: str,
        definition: dict,
    ) -> None:
        super().__init__(coordinator)
        self._key = key
        self.schluessel = key
        self._tasten = definition["tasten"]
        self._schalter = definition["schalter"]
        self._attr_translation_key = definition["translation_key"]
        self._attr_icon = definition["icon"]
        self._attr_unique_id = f"eta_static_{coordinator.config_entry.entry_id}_{key}"
        self._attr_device_info = coordinator.device_info
        self._attr_options = [BETRIEBSART_AUS, *self._tasten]
        self._erwartet: str | None = None
        self._erwartet_seit = 0.0
        self._widerspruch = 0

    def _gemeldet(self) -> str | None:
        """Die Betriebsart, die die Anlage zuletzt gemeldet hat."""
        return self.coordinator.betriebsart_gemeldet(self._key)

    @property
    def current_option(self) -> str | None:
        """Die gewählte Betriebsart.

        Nach dem Umschalten steht hier die erwartete, bis die Anlage sie
        bestätigt - sie übernimmt einen Tastendruck nicht sofort in ihre
        Antworten.
        """
        if self._erwartet is not None:
            return self._erwartet
        return self._gemeldet()

    async def async_select_option(self, option: str) -> None:
        """Schaltet die gewünschte Betriebsart an der Anlage.

        "Aus" geht über die Ein/Aus-Taste. Steht der Heizkreis auf "Aus",
        wird er vor dem Setzen einer Betriebsart eingeschaltet.
        """
        if option not in self.options:
            raise HomeAssistantError(f"Unbekannte Betriebsart: {option}")

        try:
            if option == BETRIEBSART_AUS:
                await self._schalter_setzen(ein=False)
            else:
                if self.current_option == BETRIEBSART_AUS:
                    await self._schalter_setzen(ein=True)
                taste = self._tasten[option]
                await self.coordinator.client.async_set_value(
                    taste["uri"], taste["ein_roh"]
                )
        except ETAApiError as err:
            raise HomeAssistantError(
                f"Betriebsart konnte nicht gesetzt werden: {err}"
            ) from err

        self._erwartet = option
        self._erwartet_seit = time.monotonic()
        self._widerspruch = 0
        self.async_write_ha_state()
        await self.coordinator.async_request_refresh()

    async def _schalter_setzen(self, ein: bool) -> None:
        """Legt die Ein/Aus-Taste des Heizkreises um."""
        schalter = self.coordinator.switch_defs[self._schalter]
        await self.coordinator.client.async_set_value(
            schalter["uri"], schalter["ein_roh"] if ein else schalter["aus_roh"]
        )

    @callback
    def _handle_coordinator_update(self) -> None:
        """Gibt die Vorwegnahme auf, sobald die Anlage bestätigt hat.

        Bestätigt sie nicht, bekommt sie VERWERFEN_NACH Abfragen Zeit,
        siehe switch.vorwegnahme_pruefen. Danach zählt wieder, was sie meldet.
        """
        if self._erwartet is not None:
            if self._gemeldet() == self._erwartet:
                self._erwartet = None
            else:
                self._widerspruch, vorbei = vorwegnahme_pruefen(
                    self.coordinator, self._widerspruch, self._erwartet_seit
                )
                if vorbei:
                    self._erwartet = None
        super()._handle_coordinator_update()
