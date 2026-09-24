"""Wann die Aschebox geleert werden soll - der Auslöser des Aschebox-Plans."""

from __future__ import annotations

from datetime import datetime

from homeassistant.components.datetime import DateTimeEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import ETAConfigEntry, ETADataUpdateCoordinator
from .entitaets_ids import ids_vorschlagen


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ETAConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    if coordinator.aschebox is None:
        return
    entities = [ETAAscheboxZeit(coordinator)]
    ids_vorschlagen(coordinator.deutsche_namen, "datetime", entities)
    async_add_entities(entities)


class ETAAscheboxZeit(DateTimeEntity):
    """Datum und Uhrzeit zum Leeren; ohne Plan leer.

    Wer hier eine Zeit einstellt, startet den Plan - der Kessel geht so
    viel früher aus, dass Glutabbrand und Entaschung bis dahin durch sind.
    """

    _attr_has_entity_name = True
    _attr_translation_key = "aschebox_leeren_um"
    _attr_icon = "mdi:delete-clock"
    _attr_should_poll = False

    def __init__(self, coordinator: ETADataUpdateCoordinator) -> None:
        self._plan = coordinator.aschebox
        self._attr_unique_id = f"eta_static_{coordinator.config_entry.entry_id}_aschebox_leeren_um"
        self._attr_device_info = coordinator.device_info

    @property
    def native_value(self) -> datetime | None:
        return self._plan.ziel if self._plan.phase != "aus" else None

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(self._plan.zuhoeren(self._geaendert))

    @callback
    def _geaendert(self) -> None:
        self.async_write_ha_state()

    async def async_set_value(self, value: datetime) -> None:
        await self._plan.planen(value)
