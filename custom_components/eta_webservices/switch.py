"""Schalter für Kessel und Heizkreise, dazu der Schalter für die Animationen.

Ein Schalter der Anlage entsteht nur, wenn die Anlage die Variable als
beschreibbar meldet und genau zwei Zustände kennt. Die Rohwerte für Ein
und Aus stammen aus /user/varinfo.

Der Schalter "Animationen" gehört allein zu Home Assistant: Er schreibt
nichts in die Anlage und entsteht deshalb auch ohne Schreibzugriff.
"""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.const import STATE_OFF, EntityCategory
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import ETAApiError
from .coordinator import ETAConfigEntry, ETADataUpdateCoordinator
from .entitaets_ids import ids_vorschlagen

VERWERFEN_NACH = 3
"""So oft darf die Anlage dem erwarteten Zustand widersprechen.

Ein Schaltbefehl steht nicht sofort in den Antworten der Anlage - je nach
Gerät dauert es mehrere Sekunden. Solange gilt der erwartete Zustand,
sonst springt der Schalter im Dashboard auf den alten zurück, obwohl der
Befehl angekommen ist. Widerspricht die Anlage dauerhaft, hat sie recht:
dann wurde der Befehl nicht ausgeführt.
"""


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ETAConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Legt für jede schaltbare Funktion einen Schalter an.

    Ausgenommen sind die Ein/Aus-Tasten der Heizkreise: Dort gibt es
    stattdessen die Betriebsart-Auswahl, in der "Aus" einer von vier
    Einträgen ist.
    """
    coordinator = entry.runtime_data
    entities: list[SwitchEntity] = [
        ETASwitch(coordinator, key, definition)
        for key, definition in coordinator.switch_defs.items()
        if not definition.get("nur_fuer_auswahl")
    ]
    entities.append(ETAAnimationenSwitch(coordinator))
    ids_vorschlagen(coordinator.deutsche_namen, "switch", entities)
    async_add_entities(entities)


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
        self._widerspruch = 0

    def _gemeldet(self) -> bool | None:
        """Der Zustand, den die Anlage zuletzt gemeldet hat."""
        reading = self.coordinator.data.get(self._key)
        if reading is None:
            return None
        return reading.text == self._ein_text

    @property
    def is_on(self) -> bool | None:
        """Der Zustand, den die Anlage meldet.

        Nach dem Schalten steht hier der erwartete Zustand, bis die Anlage
        ihn bestätigt - sonst springt der Schalter zurück, solange sie noch
        den alten meldet.
        """
        if self._erwartet is not None:
            return self._erwartet
        return self._gemeldet()

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

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._setzen(self._ein_roh, True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._setzen(self._aus_roh, False)

    async def _setzen(self, roh_wert: str, erwartet: bool) -> None:
        """Schreibt den Rohwert und liest danach neu ein."""
        try:
            await self.coordinator.client.async_set_value(self._uri, roh_wert)
        except ETAApiError as err:
            raise HomeAssistantError(
                f"Die Anlage hat den Schaltbefehl nicht angenommen: {err}"
            ) from err
        self._erwartet = erwartet
        self._widerspruch = 0
        self.async_write_ha_state()
        await self.coordinator.async_request_refresh()


class ETAAnimationenSwitch(SwitchEntity, RestoreEntity):
    """Bewegte oder stehende Bilder auf der Dashboard-Karte.

    Die Karte fragt diesen Schalter ab: An zeigt sie Flamme, Funken,
    Schnecke und Fluss in Bewegung, aus je ein Standbild mit derselben
    Aussage - etwa für ein Wandtablet, das sparsam laufen soll. Nach einem
    Neustart gilt die letzte Einstellung, anfangs an.
    """

    _attr_has_entity_name = True
    _attr_translation_key = "animationen"
    _attr_entity_category = EntityCategory.CONFIG
    _attr_should_poll = False

    def __init__(self, coordinator: ETADataUpdateCoordinator) -> None:
        self._attr_unique_id = (
            f"eta_switch_{coordinator.config_entry.entry_id}_animationen"
        )
        self._attr_device_info = coordinator.device_info
        self._attr_is_on = True

    @property
    def icon(self) -> str:
        return "mdi:animation-play" if self.is_on else "mdi:image-outline"

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        letzter = await self.async_get_last_state()
        if letzter is not None:
            self._attr_is_on = letzter.state != STATE_OFF

    async def async_turn_on(self, **kwargs: Any) -> None:
        self._attr_is_on = True
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        self._attr_is_on = False
        self.async_write_ha_state()
