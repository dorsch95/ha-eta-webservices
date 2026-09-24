"""Holt die Daten für die Verbrauchsprognose und rechnet sie stündlich neu.

Die Tageswerte stammen aus der Langzeitstatistik von Home Assistant:
Stundenweise, wie viel der Gesamtverbrauch zugelegt hat und wie warm es
draußen im Mittel war. Die Statistik gibt es seit dem Einrichten der
Integration - die Prognose lernt deshalb sofort aus allem, was seitdem
angefallen ist, und nicht erst ab jetzt. Ist das Puffervolumen bekannt,
kommen die Stundenmittel der Pufferfühler dazu.
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


def lokale_stunde_aus_zeitstempel(zeit: float) -> tuple[date, int]:
    lokal = dt_util.as_local(dt_util.utc_from_timestamp(zeit))
    return lokal.date(), lokal.hour


def lokales_datum_aus_text(text) -> date | None:
    zeit = dt_util.parse_datetime(text) if isinstance(text, str) else None
    return dt_util.as_local(zeit).date() if zeit else None


async def async_stundenwerte(
    hass: HomeAssistant,
    verbrauch_id: str,
    temperatur_id: str,
    heute: date,
    puffer_ids: list[str] | tuple[str, ...] = (),
) -> tuple[list, list, list[list]]:
    """Stündlicher Zuwachs des Gesamtverbrauchs und Stundenmittel draußen.

    Dazu je Pufferfühler seine Stundenmittel, in der Reihenfolge von
    puffer_ids.
    """
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
        {verbrauch_id, temperatur_id, *puffer_ids},
        "hour",
        {"temperature": UnitOfTemperature.CELSIUS, "mass": "kg"},
        {"change", "mean"},
    )
    verbrauch = [(z["start"], z.get("change")) for z in daten.get(verbrauch_id, [])]
    temperatur = [(z["start"], z.get("mean")) for z in daten.get(temperatur_id, [])]
    puffer = [
        [(z["start"], z.get("mean")) for z in daten.get(puffer_id, [])]
        for puffer_id in puffer_ids
    ]
    return verbrauch, temperatur, puffer


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
        puffer_ids: Callable[[], list[str]] = list,
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
        self._puffer_ids = puffer_ids
        self.puffer_tage = 0
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

    def _puffer(self) -> tuple[list[str], float, float]:
        """Statistik-IDs der Pufferfühler, kWh je Grad und kWh je kg Pellets.

        Ohne bekanntes Volumen oder ohne Fühler gibt es nichts
        auszugleichen - dann bleibt die Liste leer.
        """
        volumen = getattr(self.haupt, "puffer_volumen", None)
        ids = [i for i in self._puffer_ids() if i]
        if not volumen or not ids or len(ids) != len(self._puffer_ids()):
            return [], 0.0, 0.0
        kwh_je_kg = (
            getattr(self.haupt, "pellet_kwh_per_kg", 0.0) * prognose.KESSEL_WIRKUNGSGRAD
        )
        return ids, volumen * prognose.WASSER_KWH_JE_LITER_KELVIN, kwh_je_kg

    def _puffer_jetzt(self) -> float | None:
        """Mittlere Puffertemperatur gerade eben, aus den Messwerten der Anlage."""
        schluessel = sorted(
            (k for k in getattr(self.haupt, "sensor_defs", {}) if k.startswith("puffer_fuehler_")),
            key=lambda k: int(k.rsplit("_", 1)[1]),
        )
        werte = prognose.puffer_temperaturen(self.haupt.data, schluessel)
        return sum(werte) / len(werte) if werte else None

    async def _async_update_data(self) -> prognose.Ergebnis:
        heute = dt_util.now().date()
        verbrauch_id, temperatur_id = self._statistik_ids()
        if not verbrauch_id or not temperatur_id:
            return prognose.Ergebnis(status="wartet auf Gesamtverbrauch und Außentemperatur")
        puffer_ids, kwh_je_kelvin, kwh_je_kg = self._puffer()
        try:
            verbrauch, temperatur, puffer = await async_stundenwerte(
                self.hass, verbrauch_id, temperatur_id, heute, puffer_ids
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
        self.puffer_tage = 0
        if puffer_ids and kwh_je_kg > 0:
            enden = prognose.puffer_tagesenden(puffer, lokale_stunde_aus_zeitstempel)
            tage, self.puffer_tage = prognose.puffer_ausgleichen(
                tage, enden, kwh_je_kelvin, kwh_je_kg
            )
            gestern = enden.get(heute - timedelta(days=1))
            jetzt = self._puffer_jetzt()
            if gestern is not None and jetzt is not None:
                heute_schon -= (jetzt - gestern) * kwh_je_kelvin / kwh_je_kg
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
