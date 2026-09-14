"""Schalter für Kessel und Heizkreise.

Ein Schalter entsteht nur, wenn die Anlage die zugehörige Variable
ausdrücklich als beschreibbar meldet und genau zwei gültige Zustände
kennt. Die Rohwerte für Ein und Aus stammen aus /user/varinfo, werden
also nicht geraten - in eine Heizungssteuerung einen falschen Wert zu
schreiben wäre keine Kleinigkeit.
"""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import ETAApiError
from .coordinator import ETAConfigEntry, ETADataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)



async def async_setup_entry(
    hass: HomeAssistant,
    entry: ETAConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Legt für jede schaltbare Funktion einen Schalter an."""
    coordinator = entry.runtime_data
    async_add_entities(
        ETASwitch(coordinator, key, definition)
        for key, definition in coordinator.switch_defs.items()
    )


class ETASwitch(CoordinatorEntity[ETADataUpdateCoordinator], SwitchEntity):
    """Schaltet eine Funktion der Anlage ein oder aus."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: ETADataUpdateCoordinator,
        key: str,
        definition: dict,
    ) -> None:
        super().__init__(coordinator)
        self._key = key
        self._uri = definition["uri"]
        self._ein_roh = definition["ein_roh"]
        self._aus_roh = definition["aus_roh"]
        self._ein_text = definition["ein_text"]
        self._attr_translation_key = definition["translation_key"]
        self._attr_icon = definition["icon"]
        self._attr_unique_id = (
            f"eta_switch_{coordinator.config_entry.entry_id}_{key}"
        )
        self._attr_device_info = coordinator.device_info
        self._erwartet: bool | None = None

    @property
    def is_on(self) -> bool | None:
        """Der Zustand, den die Anlage meldet.

        Direkt nach dem Schalten steht hier der erwartete Zustand: Home
        Assistant fragt die Anlage erst mit kurzer Verzögerung erneut ab,
        und ohne diese Vorwegnahme würde der Schalter im Dashboard
        zurückspringen und erst Sekunden später umspringen. Sobald echte
        Daten eintreffen, gilt wieder, was die Anlage sagt.
        """
        if self._erwartet is not None:
            return self._erwartet
        reading = self.coordinator.data.get(self._key)
        if reading is None:
            return None
        return reading.text == self._ein_text

    @callback
    def _handle_coordinator_update(self) -> None:
        self._erwartet = None
        super()._handle_coordinator_update()

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._setzen(self._ein_roh, True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._setzen(self._aus_roh, False)

    async def _setzen(self, roh_wert: str, erwartet: bool) -> None:
        """Schreibt den Rohwert und liest danach neu ein.

        Ohne das Nachlesen stünde der Schalter bis zum nächsten
        Abfragezyklus auf dem gewünschten statt auf dem tatsächlichen
        Zustand - und ein von der Anlage abgelehnter Befehl fiele gar
        nicht auf.
        """
        try:
            await self.coordinator.client.async_set_value(self._uri, roh_wert)
        except ETAApiError as err:
            raise HomeAssistantError(
                f"Die Anlage hat den Schaltbefehl nicht angenommen: {err}"
            ) from err
        self._erwartet = erwartet
        self.async_write_ha_state()
        await self.coordinator.async_request_refresh()
