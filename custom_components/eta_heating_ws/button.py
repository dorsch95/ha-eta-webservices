"""Knöpfe am Kessel: Entaschen und den Aschebox-Plan abbrechen.

Beide entstehen nur mit freigegebenem Schreibzugriff, wenn die Anlage die
Entaschentaste als beschreibbar mit genau zwei Zuständen meldet.
"""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import ETAApiError
from .coordinator import ETAConfigEntry, ETADataUpdateCoordinator
from .entitaets_ids import ids_vorschlagen


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ETAConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    entities: list[ButtonEntity] = []
    if coordinator.entaschen_def is not None:
        entities.append(ETAEntaschenKnopf(coordinator))
    if coordinator.aschebox is not None:
        entities.append(ETAAscheboxAbbrechenKnopf(coordinator))
    ids_vorschlagen(coordinator.deutsche_namen, "button", entities)
    async_add_entities(entities)


class ETAEntaschenKnopf(CoordinatorEntity[ETADataUpdateCoordinator], ButtonEntity):
    """Drückt die Entaschentaste des Kessels - wie am Display."""

    _attr_has_entity_name = True
    _attr_translation_key = "kessel_entaschen"
    _attr_icon = "mdi:delete-sweep"

    def __init__(self, coordinator: ETADataUpdateCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"eta_static_{coordinator.config_entry.entry_id}_kessel_entaschen"
        self._attr_device_info = coordinator.device_info

    async def async_press(self) -> None:
        definition = self.coordinator.entaschen_def
        try:
            await self.coordinator.client.async_set_value(definition["uri"], definition["ein_roh"])
        except ETAApiError as err:
            raise HomeAssistantError(f"Die Anlage hat die Entaschentaste nicht angenommen: {err}") from err
        await self.coordinator.async_request_refresh()


class ETAAscheboxAbbrechenKnopf(ButtonEntity):
    """Bricht den Aschebox-Plan ab - nur verfügbar, solange einer läuft."""

    _attr_has_entity_name = True
    _attr_translation_key = "aschebox_plan_abbrechen"
    _attr_icon = "mdi:close-circle-outline"
    _attr_should_poll = False

    def __init__(self, coordinator: ETADataUpdateCoordinator) -> None:
        self._plan = coordinator.aschebox
        self._attr_unique_id = f"eta_static_{coordinator.config_entry.entry_id}_aschebox_plan_abbrechen"
        self._attr_device_info = coordinator.device_info

    @property
    def available(self) -> bool:
        return self._plan.phase != "aus"

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(self._plan.zuhoeren(self._geaendert))

    @callback
    def _geaendert(self) -> None:
        self.async_write_ha_state()

    async def async_press(self) -> None:
        await self._plan.abbrechen()
