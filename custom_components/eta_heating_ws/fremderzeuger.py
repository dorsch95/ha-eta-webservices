"""Der Fremderzeuger: eine Wärmequelle, die an keiner Stelle an der ETA-Regelung hängt.

Etwa ein Kaminofen mit eigener Regelung. Die Anlage weiß nichts von ihm -
ob er heizt, sagt eine Entität aus Home Assistant, die der Nutzer beim
Einrichten wählt: ein Schalter, ein Helfer oder ein Binärsensor. Damit ist
er das Gegenstück zur Komponente "fremdwaerme", deren Werte die Anlage
selbst führt.

Solange er heizt, hält die Integration die gewählten Kessel gesperrt
(switch.Kesselsperre) und gibt sie danach wieder frei. Bisher kennt die
Integration einen Kessel; die Auswahl ist trotzdem eine Liste, damit
weitere dazukommen können.

Gesperrt und freigegeben wird nach dem Zustand der Entität:
- wenn sie die eingestellte Zeit lang an oder aus ist,
- wenn Home Assistant gestartet ist,
- sobald die Anlage nach einer Unterbrechung wieder erreichbar ist.

Ist der Zustand der Entität unbekannt, bleibt alles, wie es ist. Schaltet
jemand den gesperrten Kessel von Hand ein, bleibt er an, bis einer der
drei Anlässe wieder eintritt.
"""

from __future__ import annotations

import logging
from datetime import timedelta

from homeassistant.const import STATE_OFF, STATE_ON
from homeassistant.core import CALLBACK_TYPE, Event, HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.event import async_call_later, async_track_state_change_event
from homeassistant.helpers.start import async_at_started

_LOGGER = logging.getLogger(__name__)

KESSEL = "kessel"
"""Der Kessel in der Auswahl der sperrbaren Kessel, siehe const.SPERRBARE_KESSEL."""


class Fremderzeuger:
    """Sperrt die gewählten Kessel, solange die Entität des Fremderzeugers an ist."""

    def __init__(
        self,
        hass: HomeAssistant,
        coordinator,
        entitaet: str,
        sperrt: list[str],
        sperren_nach: float,
        freigeben_nach: float,
    ) -> None:
        self.hass = hass
        self.coordinator = coordinator
        self.entitaet = entitaet
        self.sperrt = list(sperrt)
        self._wartezeit = {
            STATE_ON: timedelta(minutes=sperren_nach),
            STATE_OFF: timedelta(minutes=freigeben_nach),
        }
        self._abmelden: list[CALLBACK_TYPE] = []
        self._zeitgeber: CALLBACK_TYPE | None = None
        self._erreichbar = True

    @property
    def heizt(self) -> bool | None:
        """Ob der Fremderzeuger heizt - None, wenn seine Entität es gerade nicht sagt."""
        stand = self.hass.states.get(self.entitaet)
        if stand is None:
            return None
        return {STATE_ON: True, STATE_OFF: False}.get(stand.state)

    @callback
    def starten(self) -> None:
        """Beobachtet die Entität und die Erreichbarkeit der Anlage."""
        self._erreichbar = self.coordinator.last_update_success
        self._abmelden = [
            async_track_state_change_event(self.hass, [self.entitaet], self._geaendert),
            self.coordinator.async_add_listener(self._anlage_gemeldet),
            async_at_started(self.hass, self._gestartet),
        ]

    @callback
    def beenden(self) -> None:
        self._zeitgeber_loeschen()
        for abmelden in self._abmelden:
            abmelden()
        self._abmelden = []

    @callback
    def _zeitgeber_loeschen(self) -> None:
        if self._zeitgeber is not None:
            self._zeitgeber()
            self._zeitgeber = None

    async def _gestartet(self, hass: HomeAssistant) -> None:
        await self.async_abgleichen()

    @callback
    def _geaendert(self, event: Event) -> None:
        """Die Entität hat ihren Zustand gewechselt: Nach der Wartezeit wird abgeglichen.

        Ein neuer Wechsel verwirft die laufende Wartezeit - ein Ofen, der
        kurz aus und wieder an ist, gibt den Kessel nicht frei.
        """
        neu, alt = event.data.get("new_state"), event.data.get("old_state")
        if neu is None or (alt is not None and alt.state == neu.state):
            return
        self._zeitgeber_loeschen()
        wartezeit = self._wartezeit.get(neu.state)
        if wartezeit is not None:
            self._zeitgeber = async_call_later(self.hass, wartezeit, self._zeit_um)

    async def _zeit_um(self, _jetzt) -> None:
        self._zeitgeber = None
        await self.async_abgleichen()

    @callback
    def _anlage_gemeldet(self) -> None:
        """Ist die Anlage nach einer Unterbrechung wieder erreichbar, wird abgeglichen.

        Sonst bliebe der Kessel gesperrt, wenn der Fremderzeuger ausging,
        während die Anlage nicht erreichbar war.
        """
        erreichbar = self.coordinator.last_update_success
        zurueck = erreichbar and not self._erreichbar
        self._erreichbar = erreichbar
        if zurueck and self._zeitgeber is None:
            self.hass.async_create_task(self.async_abgleichen())

    async def async_abgleichen(self) -> None:
        """Sperrt oder gibt frei, wenn die Sperre anders steht, als der Fremderzeuger verlangt."""
        sperre = self.coordinator.kesselsperre
        heizt = self.heizt
        if sperre is None or KESSEL not in self.sperrt or heizt is None:
            return
        if heizt == sperre.gesperrt:
            return
        try:
            if heizt:
                await sperre.async_sperren()
            else:
                await sperre.async_freigeben()
        except HomeAssistantError as err:
            _LOGGER.warning(
                "ETA: Der Fremderzeuger konnte den Kessel nicht %s: %s",
                "sperren" if heizt else "freigeben",
                err,
            )
            return
        await self.coordinator.async_request_refresh()
