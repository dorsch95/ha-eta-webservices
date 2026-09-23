"""Holt die Daten für die Verbrauchsprognose und rechnet sie stündlich neu.

Die Tageswerte stammen aus der Langzeitstatistik von Home Assistant:
Stundenweise, wie viel der Gesamtverbrauch zugelegt hat und wie warm es
draußen im Mittel war. Die Statistik gibt es seit dem Einrichten der
Integration - die Prognose lernt deshalb sofort aus allem, was seitdem
angefallen ist, und nicht erst ab jetzt.
"""

from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Callable

from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from . import prognose
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

LERNZEITRAUM = 730
"""So viele Tage zurück werden Werte aus der Statistik geholt."""

AKTUALISIERUNG = timedelta(hours=1)


def einzige_wetter_entitaet(hass: HomeAssistant) -> str | None:
    """Die Wetter-Entität, wenn es genau eine gibt.

    Bei mehreren ist nicht zu erraten, welche für den eigenen Ort gilt.
    """
    wetter = hass.states.async_entity_ids("weather")
    return wetter[0] if len(wetter) == 1 else None


def lokales_datum_aus_zeitstempel(zeit: float) -> date:
    return dt_util.as_local(dt_util.utc_from_timestamp(zeit)).date()


def lokales_datum_aus_text(text) -> date | None:
    zeit = dt_util.parse_datetime(text) if isinstance(text, str) else None
    return dt_util.as_local(zeit).date() if zeit else None


async def async_stundenwerte(
    hass: HomeAssistant, verbrauch_id: str, temperatur_id: str, heute: date
) -> tuple[list[tuple[float, float]], list[tuple[float, float]]]:
    """Stündlicher Zuwachs des Gesamtverbrauchs und Stundenmittel draußen."""
    from homeassistant.components.recorder import get_instance
    from homeassistant.components.recorder.statistics import (
        statistics_during_period,
    )

    beginn = dt_util.start_of_local_day(heute - timedelta(days=LERNZEITRAUM))
    daten = await get_instance(hass).async_add_executor_job(
        statistics_during_period,
        hass,
        beginn,
        None,
        {verbrauch_id, temperatur_id},
        "hour",
        {"temperature": UnitOfTemperature.CELSIUS, "mass": "kg"},
        {"change", "mean"},
    )
    verbrauch = [(z["start"], z.get("change")) for z in daten.get(verbrauch_id, [])]
    temperatur = [(z["start"], z.get("mean")) for z in daten.get(temperatur_id, [])]
    return verbrauch, temperatur


async def async_vorhersage(hass: HomeAssistant, wetter_id: str | None) -> dict[date, float]:
    """Tagesmittel der Wettervorhersage, oder nichts.

    Nimmt die Tagesvorhersage, sonst die für Tag und Nacht, sonst die
    stündliche - je nachdem, was der Wetterdienst anbietet.
    """
    if not wetter_id or hass.states.get(wetter_id) is None:
        return {}
    fahrenheit = hass.config.units.temperature_unit == UnitOfTemperature.FAHRENHEIT
    for art in ("daily", "twice_daily", "hourly"):
        try:
            antwort = await hass.services.async_call(
                "weather",
                "get_forecasts",
                {"entity_id": wetter_id, "type": art},
                blocking=True,
                return_response=True,
            )
        except (HomeAssistantError, ValueError) as err:
            _LOGGER.debug("ETA Prognose: %s-Vorhersage von %s nicht verfügbar: %s", art, wetter_id, err)
            continue
        eintraege = ((antwort or {}).get(wetter_id) or {}).get("forecast") or []
        tage = prognose.tagesmittel_aus_vorhersage(
            eintraege, art, lokales_datum_aus_text, fahrenheit
        )
        if tage:
            return tage
    return {}


class ETAPrognoseKoordinator(DataUpdateCoordinator[prognose.Ergebnis]):
    """Rechnet Verbrauchsprognose und Reichweite des Lagers.

    Scheitert etwas - kein Recorder, keine Vorhersage -, gibt es trotzdem
    ein Ergebnis mit einem verständlichen Status statt eines Fehlers.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        entry,
        haupt,
        wetter_wahl: str | None,
        statistik_ids: Callable[[], tuple[str | None, str | None]],
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_prognose",
            config_entry=entry,
            update_interval=AKTUALISIERUNG,
        )
        self.haupt = haupt
        self.wetter_wahl = wetter_wahl
        self.wetter_id: str | None = None
        self._statistik_ids = statistik_ids
        self._gegenrechnung_bis: date | None = None
        self._gegenrechnung = None
        self.vorhersage_tage = 0

    def _wetter(self) -> str | None:
        """Die gewählte Wetter-Entität; ohne Wahl die einzige, die es gibt.

        Ein leerer Eintrag heißt: bewusst keine Vorhersage.
        """
        if self.wetter_wahl is None:
            return einzige_wetter_entitaet(self.hass)
        return self.wetter_wahl or None

    def _lager(self) -> tuple[float | None, float | None]:
        daten = self.haupt.data or {}

        def zahl(key):
            wert = daten.get(key)
            try:
                return float(wert.value) if wert is not None else None
            except (TypeError, ValueError):
                return None

        return zahl("lager_vorrat"), zahl("lager_warngrenze")

    async def _async_update_data(self) -> prognose.Ergebnis:
        heute = dt_util.now().date()
        verbrauch_id, temperatur_id = self._statistik_ids()
        if not verbrauch_id or not temperatur_id:
            return prognose.Ergebnis(status="wartet auf Gesamtverbrauch und Außentemperatur")
        try:
            verbrauch, temperatur = await async_stundenwerte(
                self.hass, verbrauch_id, temperatur_id, heute
            )
        except (HomeAssistantError, KeyError, ValueError, RuntimeError) as err:
            _LOGGER.warning("ETA Prognose: Verlauf nicht lesbar: %s", err)
            return prognose.Ergebnis(status="Verlauf nicht lesbar")

        tage = prognose.tage_aus_stunden(
            verbrauch, temperatur, lokales_datum_aus_zeitstempel, heute
        )
        heute_schon = sum(
            wert or 0.0
            for zeit, wert in verbrauch
            if lokales_datum_aus_zeitstempel(zeit) == heute
        )
        self.wetter_id = self._wetter()
        vorhersage = await async_vorhersage(self.hass, self.wetter_id)
        self.vorhersage_tage = len(vorhersage)
        vorrat, grenze = self._lager()

        letzter = tage[-1].datum if tage else None
        gegenrechnung = self._gegenrechnung if letzter == self._gegenrechnung_bis else None
        ergebnis = await self.hass.async_add_executor_job(
            prognose.berechnen, tage, heute, vorhersage, vorrat, grenze, heute_schon, gegenrechnung
        )
        if ergebnis.bereit:
            self._gegenrechnung_bis = letzter
            self._gegenrechnung = (
                ergebnis.treffsicherheit,
                ergebnis.verglichene_tage,
                ergebnis.gestern_prognose,
                ergebnis.gestern_tatsaechlich,
            )
        return ergebnis
