"""Betriebsart der Heizkreise."""

from __future__ import annotations


from homeassistant.components.select import SelectEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import ETAApiError
from .const import BETRIEBSART_AUS
from .coordinator import ETAConfigEntry, ETADataUpdateCoordinator
from .switch import VERWERFEN_NACH


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ETAConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Legt je erkanntem Heizkreis eine Betriebsart-Auswahl an."""
    coordinator = entry.runtime_data
    async_add_entities(
        ETABetriebsartSelect(coordinator, key, definition)
        for key, definition in coordinator.select_defs.items()
    )


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
        self._tasten = definition["tasten"]
        self._schalter = definition["schalter"]
        self._attr_translation_key = definition["translation_key"]
        self._attr_icon = definition["icon"]
        self._attr_unique_id = f"eta_static_{coordinator.config_entry.entry_id}_{key}"
        self._attr_device_info = coordinator.device_info
        self._attr_options = [BETRIEBSART_AUS, *self._tasten]
        self._erwartet: str | None = None
        self._widerspruch = 0

    def _steht_auf_ein(self, modus: str) -> bool | None:
        """Sagt, ob eine der drei Tasten gerade auf "Ein" steht."""
        reading = self.coordinator.data.get(f"{self._key}_{modus}")
        if reading is None or not reading.text:
            return None
        return reading.text.strip().casefold() == (
            self._tasten[modus]["ein_text"].strip().casefold()
        )

    def _gemeldet(self) -> str | None:
        """Die Betriebsart, die die Anlage zuletzt gemeldet hat."""
        zustaende = {modus: self._steht_auf_ein(modus) for modus in self._tasten}
        if all(zustand is None for zustand in zustaende.values()):
            return None
        for modus, zustand in zustaende.items():
            if zustand:
                return modus
        return BETRIEBSART_AUS

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

        Bestätigt sie nicht, bekommt sie VERWERFEN_NACH Abfragen Zeit.
        Danach zählt wieder, was sie meldet.
        """
        if self._erwartet is not None:
            if self._gemeldet() == self._erwartet:
                self._erwartet = None
            else:
                self._widerspruch += 1
                if self._widerspruch >= VERWERFEN_NACH:
                    self._erwartet = None
        super()._handle_coordinator_update()
