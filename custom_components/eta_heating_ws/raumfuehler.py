"""Schreibt die Temperatur eines Home-Assistant-Thermometers als Raumfühler in die Anlage.

Ziel ist "Raumtemperatur über externe Schnittstellen" eines Heizkreises.
Die Anlage übernimmt den Wert binnen Sekunden als "Raum" und verwirft ihn
wieder, wenn innerhalb der Zeitüberwachung kein neuer kommt - dann meldet
sie "Raumfühler: Keine Verbindung" und regelt ohne Raumeinfluss. Am
24.09.2026 an einer Testanlage so beobachtet.

Deshalb schreibt der Sender regelmäßig, auch wenn sich nichts ändert, und
bei jeder Änderung sofort (höchstens alle MINDESTABSTAND Sekunden). Er
schreibt nie einen Ersatzwert: Ist das Thermometer nicht verfügbar, bleibt
die Anlage sich selbst überlassen und merkt es nach der Zeitüberwachung.
Steht die Zeitüberwachung auf 0, würde die Anlage einen alten Wert
womöglich nie verwerfen - dann schreibt er gar nicht.

Ein Thermometer mit leerer Batterie bleibt in Home Assistant oft auf
seinem letzten Wert stehen. Den schreibt der Sender weiter, aber nach
RAUMFUEHLER_STUMM_NACH ohne Lebenszeichen erscheint ein Hinweis unter
Reparaturen.
"""

from __future__ import annotations

import logging
import time
from datetime import timedelta

from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN, UnitOfTemperature
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers.event import (
    async_track_state_change_event,
    async_track_time_interval,
)

from homeassistant.util import dt as dt_util

from .api import ETAApiError
from .const import RAUMFUEHLER_STUMM_NACH, RAUMFUEHLER_TAKT
from .repairs import async_raumfuehler_pruefen

_LOGGER = logging.getLogger(__name__)

MINDESTABSTAND = 10
"""So viele Sekunden liegen mindestens zwischen zwei Schreibvorgängen."""


def raumwert_roh(state, objekt: dict) -> str | None:
    """Der Rohwert, den die Anlage für diesen Zustand bekommt, oder None.

    None heißt: nicht schreiben - unbekannt, nicht verfügbar, keine Zahl.
    Fahrenheit wird umgerechnet, der Wert auf die Grenzen aus /user/varinfo
    begrenzt und auf eine Nachkommastelle gerundet.
    """
    if state is None or state.state in (STATE_UNKNOWN, STATE_UNAVAILABLE):
        return None
    try:
        grad = float(state.state)
    except (TypeError, ValueError):
        return None
    if state.attributes.get("unit_of_measurement") == UnitOfTemperature.FAHRENHEIT:
        grad = (grad - 32) * 5 / 9
    skala = objekt.get("scale") or 1.0
    roh = round(round(grad, 1) * skala)
    if objekt.get("min_roh") is not None:
        roh = max(roh, round(objekt["min_roh"]))
    if objekt.get("max_roh") is not None:
        roh = min(roh, round(objekt["max_roh"]))
    return str(roh)


def takt(zeitueberwachung: float | None) -> float:
    """Wie oft geschrieben wird: RAUMFUEHLER_TAKT, höchstens die halbe Zeitüberwachung."""
    if not zeitueberwachung:
        return RAUMFUEHLER_TAKT
    return max(MINDESTABSTAND, min(RAUMFUEHLER_TAKT, zeitueberwachung / 2))


class RaumfuehlerSender:
    """Hält die Raumtemperatur eines Heizkreises an der Anlage aktuell."""

    def __init__(self, hass: HomeAssistant, coordinator, heizkreis: str, entity_id: str) -> None:
        self.hass = hass
        self.coordinator = coordinator
        self.heizkreis = heizkreis
        self.entity_id = entity_id
        self._definition = coordinator.thermostat_defs[heizkreis]
        self._zuletzt = 0.0
        self._abmelden: list = []
        self._gewarnt: str | None = None
        self._stumm: bool | None = None
        """Ob der Hinweis zum stummen Thermometer gerade ansteht; None bis zur ersten Prüfung."""

    def _lebenszeichen_pruefen(self, state) -> None:
        """Legt den Hinweis an oder nimmt ihn zurück, wenn sich etwas geändert hat.

        Stumm heißt: Das Thermometer zeigt einen Wert, hat sich aber seit
        RAUMFUEHLER_STUMM_NACH nicht gemeldet - auch nicht mit demselben
        Wert. Ein Raum mit gleichbleibender Temperatur löst also nichts
        aus, solange das Thermometer weiter sendet. Ist es nicht verfügbar,
        merkt die Anlage das selbst über ihre Zeitüberwachung.
        """
        gemeldet = getattr(state, "last_reported", None)
        stumm = (
            gemeldet is not None
            and state.state not in (STATE_UNKNOWN, STATE_UNAVAILABLE)
            and (dt_util.utcnow() - gemeldet).total_seconds() > RAUMFUEHLER_STUMM_NACH
        )
        if stumm == self._stumm:
            return
        self._stumm = stumm
        async_raumfuehler_pruefen(
            self.hass, self.coordinator.config_entry.entry_id, self.heizkreis, self.entity_id, stumm
        )
        if stumm:
            _LOGGER.warning(
                "ETA: %s hat sich seit %d Stunden nicht gemeldet - für %s wird weiter "
                "der letzte Wert geschrieben",
                self.entity_id,
                RAUMFUEHLER_STUMM_NACH // 3600,
                self.heizkreis,
            )

    @property
    def _zeitueberwachung(self) -> float | None:
        return self.coordinator.zahl(f"{self._definition['praefix']}_zeitueberwachung")

    def starten(self) -> None:
        """Schreibt bei jeder Änderung des Thermometers und im festen Takt."""
        self._abmelden.append(
            async_track_state_change_event(self.hass, [self.entity_id], self._geaendert)
        )
        self._abmelden.append(
            async_track_time_interval(
                self.hass, self._im_takt, timedelta(seconds=takt(self._zeitueberwachung))
            )
        )
        self.hass.async_create_task(self.schreiben())

    def stoppen(self) -> None:
        for abmelden in self._abmelden:
            abmelden()
        self._abmelden.clear()

    @callback
    def _geaendert(self, _event: Event) -> None:
        if time.monotonic() - self._zuletzt >= MINDESTABSTAND:
            self.hass.async_create_task(self.schreiben())

    async def _im_takt(self, _jetzt) -> None:
        await self.schreiben()

    def _warnen(self, grund: str, *args) -> None:
        """Meldet einen Grund, nicht zu schreiben, nur beim ersten Mal."""
        if self._gewarnt != grund:
            _LOGGER.warning(grund, *args)
            self._gewarnt = grund

    async def schreiben(self) -> bool:
        """Schreibt den aktuellen Wert, falls es einen gültigen gibt."""
        state = self.hass.states.get(self.entity_id)
        self._lebenszeichen_pruefen(state)
        if self._zeitueberwachung == 0:
            self._warnen(
                "ETA: Zeitüberwachung von %s steht auf 0 - die Raumtemperatur "
                "wird nicht geschrieben, sonst behielte die Anlage einen alten "
                "Wert womöglich für immer",
                self.heizkreis,
            )
            return False
        roh = raumwert_roh(state, self._definition["raum_extern"])
        if roh is None:
            self._warnen(
                "ETA: %s liefert keine Temperatur - für %s wird nichts geschrieben",
                self.entity_id,
                self.heizkreis,
            )
            return False
        try:
            await self.coordinator.client.async_set_value(self._definition["raum_extern"]["uri"], roh)
        except ETAApiError as err:
            self._warnen("ETA: Raumtemperatur für %s nicht geschrieben: %s", self.heizkreis, err)
            return False
        self._zuletzt = time.monotonic()
        self._gewarnt = None
        return True
