"""Schalter für Kessel und Heizkreise, dazu Kesselsperre und Animationen.

Ein Schalter der Anlage entsteht nur, wenn die Anlage die Variable als
beschreibbar meldet und genau zwei Zustände kennt. Die Rohwerte für Ein
und Aus stammen aus /user/varinfo.

"Kessel sperren" bedient die Ein/Aus-Taste des Kessels und merkt sich,
was er selbst getan hat, siehe ETAKesselSperre.

Der Schalter "Animationen" gehört allein zu Home Assistant: Er schreibt
nichts in die Anlage und entsteht deshalb auch ohne Schreibzugriff.
"""

from __future__ import annotations

import time
from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.const import STATE_OFF, EntityCategory
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import ETAApiError
from .const import (
    KESSEL_GESPERRT_AUSGESCHALTET,
    KESSEL_GESPERRT_WAR_AUS,
    KESSEL_SPERRE,
    KESSEL_TASTE,
)
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


VERWERFEN_FRUEHESTENS = 20
"""So viele Sekunden gilt der erwartete Zustand mindestens.

Bei einem Abfrageintervall von wenigen Sekunden wären VERWERFEN_NACH
Abfragen vorbei, bevor die Anlage den Schaltbefehl in ihre Antworten
übernommen hat. 20 Sekunden sind die Frist, die drei Abfragen beim
früheren kürzesten Intervall von 10 Sekunden ließen.
"""


def vorwegnahme_pruefen(
    coordinator: ETADataUpdateCoordinator, widerspruch: int, seit: float
) -> tuple[int, bool]:
    """Zählt einen Widerspruch der Anlage und sagt, ob die Vorwegnahme damit endet.

    Gezählt wird nur bei einer vollen Abfrage: Die schnelle Gruppe meldet
    sich öfter, als die Anlage für einen Schaltbefehl braucht. seit ist der
    Zeitpunkt des Schreibens nach time.monotonic().
    """
    if coordinator.volle_abfrage:
        widerspruch += 1
    abgelaufen = time.monotonic() - seit >= VERWERFEN_FRUEHESTENS
    return widerspruch, widerspruch >= VERWERFEN_NACH and abgelaufen


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ETAConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Legt für jede schaltbare Funktion einen Schalter an.

    Ausgenommen sind die Ein/Aus-Tasten der Heizkreise: Dort gibt es
    stattdessen die Betriebsart-Auswahl, in der "Aus" einer von vier
    Einträgen ist.

    "Kessel sperren" entsteht, wenn er in den Einstellungen angekreuzt ist
    und die Ein/Aus-Taste des Kessels sich schalten lässt.
    """
    coordinator = entry.runtime_data
    entities: list[SwitchEntity] = [
        ETASwitch(coordinator, key, definition)
        for key, definition in coordinator.switch_defs.items()
        if not definition.get("nur_fuer_auswahl")
    ]
    taste = coordinator.switch_defs.get(KESSEL_TASTE)
    if coordinator.kessel_sperre and taste:
        entities.append(ETAKesselSperre(coordinator, taste))
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
        self._erwartet_seit = 0.0
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

        Bestätigt sie nicht, bekommt sie VERWERFEN_NACH Abfragen Zeit,
        siehe vorwegnahme_pruefen. Danach zählt wieder, was sie meldet.
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
        self._erwartet_seit = time.monotonic()
        self._widerspruch = 0
        self.async_write_ha_state()
        await self.coordinator.async_request_refresh()


class ETAKesselSperre(CoordinatorEntity[ETADataUpdateCoordinator], SwitchEntity):
    """Sperrt den Kessel über seine Ein/Aus-Taste, siehe const.CONF_KESSEL_SPERRE.

    Ein schaltet den Kessel aus. Aus schaltet ihn wieder ein - aber nur,
    wenn dieser Schalter ihn ausgeschaltet hat: War der Kessel beim Sperren
    schon aus, bleibt er es beim Freigeben, und ohne Sperre schreibt Aus
    gar nichts. So schaltet eine Automatisierung nie einen Kessel ein, den
    jemand von Hand ausgeschaltet hat.

    Was gilt, steht in den Optionen der Einrichtung
    (const.CONF_KESSEL_GESPERRT) und übersteht einen Neustart. Schaltet
    jemand den gesperrten Kessel an der Heizung oder über den Schalter
    "Kessel" wieder ein, ist die Sperre damit aufgehoben; geschrieben wird
    dann nichts.
    """

    _attr_has_entity_name = True

    def __init__(self, coordinator: ETADataUpdateCoordinator, taste: dict) -> None:
        super().__init__(coordinator)
        self._uri = taste["uri"]
        self._ein_roh = taste["ein_roh"]
        self._aus_roh = taste["aus_roh"]
        self._ein_text = taste["ein_text"]
        self._attr_translation_key = KESSEL_SPERRE["translation_key"]
        self._attr_icon = KESSEL_SPERRE["icon"]
        self._attr_unique_id = (
            f"eta_switch_{coordinator.config_entry.entry_id}_{KESSEL_SPERRE['translation_key']}"
        )
        self._attr_device_info = coordinator.device_info
        self._erwartet: bool | None = None
        self._erwartet_seit = 0.0
        self._widerspruch = 0

    def _gemeldet(self) -> bool | None:
        """Ob die Anlage den Kessel zuletzt als eingeschaltet gemeldet hat."""
        reading = (self.coordinator.data or {}).get(KESSEL_TASTE)
        if reading is None:
            return None
        return reading.text == self._ein_text

    def _kessel_ein(self) -> bool | None:
        """Ob der Kessel eingeschaltet ist.

        Kurz nach dem eigenen Schalten gilt der Befehl, bis die Anlage ihn
        in ihre Antworten übernommen hat - wie bei ETASwitch.
        """
        if self._erwartet is not None:
            return self._erwartet
        return self._gemeldet()

    @property
    def is_on(self) -> bool:
        """Ein, solange Home Assistant den Kessel gesperrt hält."""
        return self.coordinator.kessel_gesperrt is not None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Sagt, ob das Freigeben den Kessel wieder einschaltet."""
        return {
            "schaltet_kessel_wieder_ein": (
                self.coordinator.kessel_gesperrt == KESSEL_GESPERRT_AUSGESCHALTET
            )
        }

    @callback
    def _handle_coordinator_update(self) -> None:
        """Hebt die Sperre auf, wenn der Kessel trotz Sperre eingeschaltet ist.

        Dann hat ihn jemand eingeschaltet - oder die Anlage hat das
        Ausschalten nicht ausgeführt. Wie lange ihr dafür Zeit bleibt,
        bestimmt vorwegnahme_pruefen.
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
        if self.coordinator.kessel_gesperrt and self._kessel_ein():
            self.coordinator.kessel_gesperrt_merken(None)
        super()._handle_coordinator_update()

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Sperrt den Kessel und merkt sich, ob er dafür ausgeschaltet wurde."""
        if self.coordinator.kessel_gesperrt:
            return
        ein = self._kessel_ein()
        if ein is None:
            raise HomeAssistantError(
                "Die Anlage meldet gerade nicht, ob der Kessel ein- oder ausgeschaltet ist. "
                "Gesperrt wurde nichts."
            )
        if ein:
            await self._schalten(self._aus_roh, False)
            self.coordinator.kessel_gesperrt_merken(KESSEL_GESPERRT_AUSGESCHALTET)
        else:
            self.coordinator.kessel_gesperrt_merken(KESSEL_GESPERRT_WAR_AUS)
        self.async_write_ha_state()
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Gibt den Kessel frei und schaltet ihn ein, wenn die Sperre ihn ausgeschaltet hat."""
        gemerkt = self.coordinator.kessel_gesperrt
        if gemerkt is None:
            return
        if gemerkt == KESSEL_GESPERRT_AUSGESCHALTET:
            await self._schalten(self._ein_roh, True)
        self.coordinator.kessel_gesperrt_merken(None)
        self.async_write_ha_state()
        await self.coordinator.async_request_refresh()

    async def _schalten(self, roh_wert: str, erwartet: bool) -> None:
        """Schreibt die Ein/Aus-Taste des Kessels."""
        try:
            await self.coordinator.client.async_set_value(self._uri, roh_wert)
        except ETAApiError as err:
            raise HomeAssistantError(
                f"Die Anlage hat den Schaltbefehl nicht angenommen: {err}"
            ) from err
        self._erwartet = erwartet
        self._erwartet_seit = time.monotonic()
        self._widerspruch = 0


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
