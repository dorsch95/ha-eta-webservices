"""Überträgt einen Zeitplan aus Home Assistant in das Zeitprogramm eines Heizkreises.

Das Zeitprogramm der Anlage hat je Wochentag drei Zeitfenster. Jedes hat
Beginn und Ende in Viertelstunden und - an den meisten Anlagen - eine
eigene Raumtemperatur; außerhalb der Fenster gilt die Absenkung. Der
Zeitplan-Helfer von Home Assistant hat Blöcke je Wochentag, und jeder Block
darf zusätzliche Daten tragen.

Home Assistant führt: Ändert sich der Zeitplan, schreibt die Integration
die Fenster, die davon abweichen, in die Anlage - ebenso beim Start. Was
jemand am Display ändert, gilt bis dahin.

Eine Temperatur schreibt sie nur, wenn der Block eine mitbringt
(temperatur: 21). Sonst behält jedes Fenster seine, ein neu belegtes
übernimmt die des ersten belegten Fensters der Woche. So passt es auch
für Heizkreise, an denen nur Tag und Absenkung zählen.

Nie geschrieben wird
- ohne lesbaren Zeitplan, etwa wenn der Helfer gelöscht wurde,
- eine Woche ganz ohne Blöcke - das hieße Dauerabsenkung und ist eher ein
  Versehen; dafür gibt es die Betriebsart ECO,
- ein Tag mit mehr Blöcken, als die Anlage Fenster hat. Dafür gibt es einen
  Reparaturhinweis, die übrigen Tage werden übertragen.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import time, timedelta
from typing import Any

from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.event import (
    async_track_state_change_event,
    async_track_state_report_event,
    async_track_time_interval,
)

from .api import ETAApiError, Zeitfenster
from .const import (
    THERMOSTAT_SOLL_GRENZEN,
    WOCHENTAGE,
    ZEITFENSTER_JE_TAG,
    ZEITPLAN_TAKT,
    ZEITPLAN_TEMPERATUR,
)
from .repairs import async_zeitplan_pruefen

_LOGGER = logging.getLogger(__name__)

Block = tuple[int, int, float | None]
"""Ein Block des Zeitplans: Beginn und Ende in Viertelstunden, dazu die Temperatur oder None."""

Wochenplan = dict[str, list[Block]]


def viertelstunde(zeit: Any) -> int:
    """Eine Uhrzeit in Viertelstunden ab Mitternacht, auf die nächste gerundet.

    Der Zeitplan-Helfer liefert datetime.time, für 24:00 time.max; über die
    Weboberfläche kommen dieselben Zeiten als Text.
    """
    if isinstance(zeit, str):
        stunden, minuten, *_ = (int(teil) for teil in zeit.split(":"))
        return min(96, round((stunden * 60 + minuten) / 15))
    if zeit == time.max:
        return 96
    return min(96, round((zeit.hour * 60 + zeit.minute + zeit.second / 60) / 15))


def temperatur(block: dict) -> float | None:
    """Die Raumtemperatur, die ein Block mitbringt, oder None."""
    daten = block.get("data") or {}
    for name in ZEITPLAN_TEMPERATUR:
        if name in daten:
            try:
                return float(daten[name])
            except (TypeError, ValueError):
                return None
    return None


def bloecke(tagesplan: list[dict]) -> list[Block]:
    """Die Blöcke eines Tages in Viertelstunden, sortiert.

    Ein Block, der nach dem Runden keine Viertelstunde mehr lang ist,
    entfällt. Blöcke, die aneinanderstoßen und dieselbe Temperatur haben,
    werden einer - das spart Fenster. Überlappen sich zwei erst durch das
    Runden, beginnt der spätere, wo der frühere endet.
    """
    ergebnis: list[Block] = []
    for beginn, ende, grad in sorted(
        (viertelstunde(b["from"]), viertelstunde(b["to"]), temperatur(b)) for b in tagesplan
    ):
        if ergebnis and beginn <= ergebnis[-1][1]:
            vorher = ergebnis[-1]
            if grad == vorher[2]:
                ergebnis[-1] = (vorher[0], max(ende, vorher[1]), grad)
                continue
            beginn = vorher[1]
        if ende > beginn:
            ergebnis.append((beginn, ende, grad))
    return ergebnis


def _rohwert(grad: float, info: dict) -> int:
    """Die Temperatur als Rohwert, in den Grenzen des Thermostats und des Fensters."""
    untere, obere = THERMOSTAT_SOLL_GRENZEN
    roh = round(min(max(grad, untere), obere) * info["skala"])
    if info.get("min_roh") is not None:
        roh = max(roh, round(info["min_roh"]))
    if info.get("max_roh") is not None:
        roh = min(roh, round(info["max_roh"]))
    return roh


def tagesfenster(
    tag: list[Block],
    bestand: list[Zeitfenster],
    infos: list[dict],
    ersatz_roh: int | None,
) -> list[Zeitfenster] | None:
    """Die Fenster eines Tages für seine Blöcke, oder None, wenn es zu viele Blöcke sind.

    Ohne Temperatur im Block behält ein belegtes Fenster seine und ein bis
    dahin leeres bekommt ersatz_roh. Leere Fenster behalten ihren Wert,
    damit nur geschrieben wird, was sich wirklich ändert.
    """
    if len(tag) > ZEITFENSTER_JE_TAG:
        return None
    neu = []
    for nummer, (alt, info) in enumerate(zip(bestand, infos)):
        if not info["mit_wert"]:
            wert = None
        elif nummer < len(tag) and tag[nummer][2] is not None:
            wert = _rohwert(tag[nummer][2], info)
        elif nummer < len(tag) and alt.leer:
            wert = ersatz_roh if ersatz_roh is not None else alt.wert
        else:
            wert = alt.wert
        if wert is None and info["mit_wert"]:
            wert = round(info["vorgabe_roh"]) if info.get("vorgabe_roh") is not None else 0
        beginn, ende = tag[nummer][:2] if nummer < len(tag) else (0, 0)
        neu.append(Zeitfenster(beginn, ende, wert))
    return neu


def ersatztemperatur(bestand: dict[tuple[str, int], Zeitfenster]) -> int | None:
    """Die Temperatur des ersten belegten Fensters der Woche, als Rohwert."""
    for tag in WOCHENTAGE:
        for nummer in range(1, ZEITFENSTER_JE_TAG + 1):
            fenster = bestand[(tag, nummer)]
            if not fenster.leer and fenster.wert:
                return fenster.wert
    return None


def aenderungen(
    plan: Wochenplan,
    bestand: dict[tuple[str, int], Zeitfenster],
    defs: dict[tuple[str, int], dict],
) -> tuple[dict[tuple[str, int], Zeitfenster], list[str]]:
    """Welche Fenster neu geschrieben werden müssen, und welche Tage zu viele Blöcke haben."""
    ersatz = ersatztemperatur(bestand)
    zu_schreiben: dict[tuple[str, int], Zeitfenster] = {}
    zu_voll = []
    for tag in WOCHENTAGE:
        nummern = range(1, ZEITFENSTER_JE_TAG + 1)
        neu = tagesfenster(
            plan.get(tag, []),
            [bestand[(tag, n)] for n in nummern],
            [defs[(tag, n)] for n in nummern],
            ersatz,
        )
        if neu is None:
            zu_voll.append(tag)
            continue
        for nummer, fenster in zip(nummern, neu):
            if not fenster.gleich(bestand[(tag, nummer)]):
                zu_schreiben[(tag, nummer)] = fenster
    return zu_schreiben, zu_voll


def als_text(fenster: Zeitfenster, skala: float) -> str:
    """Ein Fenster so, wie das Display es zeigt - für Protokoll und Diagnose."""
    if fenster.leer:
        return "-"
    text = (
        f"{fenster.beginn // 4:02d}:{fenster.beginn % 4 * 15:02d} - "
        f"{fenster.ende // 4:02d}:{fenster.ende % 4 * 15:02d}"
    )
    if fenster.wert is not None:
        text += f" {fenster.wert / skala:.1f}".replace(".", ",")
    return text


class ZeitplanAbgleich:
    """Hält das Zeitprogramm eines Heizkreises auf dem Stand eines Zeitplan-Helfers."""

    def __init__(self, hass: HomeAssistant, coordinator, heizkreis: str, entity_id: str) -> None:
        self.hass = hass
        self.coordinator = coordinator
        self.heizkreis = heizkreis
        self.entity_id = entity_id
        self._defs = coordinator.zeitprogramm_defs[heizkreis]
        self._uebertragen: Wochenplan | None = None
        self._sperre = asyncio.Lock()
        self._abmelden: list = []
        self._gewarnt: str | None = None
        self.bestand: dict[tuple[str, int], Zeitfenster] = {}
        """Die Fenster, wie die Anlage sie zuletzt gemeldet hat - für die Diagnose."""

    def starten(self) -> None:
        """Gleicht beim Start ab, bei jeder Änderung des Helfers und im festen Takt.

        Ändert jemand den Zeitplan, schreibt der Helfer seinen Zustand neu.
        Bleibt der dabei gleich - etwa weil nur ein anderer Tag geändert
        wurde -, meldet Home Assistant das als "reported" statt "changed".
        Auf beides wird gehört.
        """
        self._abmelden.append(
            async_track_state_change_event(self.hass, [self.entity_id], self._geaendert)
        )
        self._abmelden.append(
            async_track_state_report_event(self.hass, [self.entity_id], self._geaendert)
        )
        self._abmelden.append(
            async_track_time_interval(
                self.hass, self._im_takt, timedelta(seconds=ZEITPLAN_TAKT)
            )
        )
        self.hass.async_create_task(self.abgleichen())

    def stoppen(self) -> None:
        for abmelden in self._abmelden:
            abmelden()
        self._abmelden.clear()

    @callback
    def _geaendert(self, _event: Event) -> None:
        self.hass.async_create_task(self.abgleichen())

    async def _im_takt(self, _jetzt) -> None:
        await self.abgleichen()

    def _warnen(self, grund: str, *args) -> None:
        """Meldet einen Grund, nicht zu schreiben, nur beim ersten Mal."""
        if self._gewarnt != grund:
            _LOGGER.warning(grund, *args)
            self._gewarnt = grund

    async def plan_lesen(self) -> Wochenplan | None:
        """Der Zeitplan des Helfers in Viertelstunden, oder None, wenn er nicht lesbar ist."""
        zustand = self.hass.states.get(self.entity_id)
        if zustand is None or zustand.state not in ("on", "off"):
            return None
        try:
            antwort = await self.hass.services.async_call(
                "schedule",
                "get_schedule",
                {"entity_id": self.entity_id},
                blocking=True,
                return_response=True,
            )
        except (HomeAssistantError, ValueError) as err:
            self._warnen("ETA: Zeitplan %s nicht lesbar: %s", self.entity_id, err)
            return None
        tage = (antwort or {}).get(self.entity_id)
        if not isinstance(tage, dict):
            return None
        return {tag: bloecke(tage.get(tag) or []) for tag in WOCHENTAGE}

    async def _bestand_lesen(self) -> dict[tuple[str, int], Zeitfenster]:
        fenster = list(self._defs)
        gelesen = await asyncio.gather(
            *(self.coordinator.client.async_get_zeitfenster(self._defs[f]["uri"]) for f in fenster)
        )
        return dict(zip(fenster, gelesen))

    async def abgleichen(self) -> bool:
        """Schreibt die Fenster, die vom Zeitplan abweichen. True, wenn danach alles stimmt."""
        async with self._sperre:
            plan = await self.plan_lesen()
            if plan is None or plan == self._uebertragen:
                return plan is not None
            if not any(plan.values()):
                self._warnen(
                    "ETA: Zeitplan %s hat keinen einzigen Block - das Zeitprogramm "
                    "von %s bleibt, wie es ist",
                    self.entity_id,
                    self.heizkreis,
                )
                return False
            try:
                self.bestand = await self._bestand_lesen()
                zu_schreiben, zu_voll = aenderungen(plan, self.bestand, self._defs)
                async_zeitplan_pruefen(
                    self.hass,
                    self.coordinator.config_entry.entry_id,
                    self.heizkreis,
                    self.entity_id,
                    [WOCHENTAGE[tag] for tag in zu_voll],
                )
                for fenster, neu in zu_schreiben.items():
                    await self.coordinator.client.async_set_zeitfenster(
                        self._defs[fenster]["uri"], neu
                    )
                    _LOGGER.info(
                        "ETA: %s %s Zeitfenster %d: %s -> %s",
                        self.heizkreis,
                        WOCHENTAGE[fenster[0]],
                        fenster[1],
                        als_text(self.bestand[fenster], self._defs[fenster]["skala"]),
                        als_text(neu, self._defs[fenster]["skala"]),
                    )
                if zu_schreiben:
                    self.bestand = await self._bestand_lesen()
            except ETAApiError as err:
                self._warnen("ETA: Zeitprogramm von %s nicht übertragen: %s", self.heizkreis, err)
                return False
            abweichend = [
                fenster
                for fenster, neu in zu_schreiben.items()
                if not neu.gleich(self.bestand[fenster])
            ]
            if abweichend:
                self._warnen(
                    "ETA: Die Anlage meldet für %s nach dem Schreiben andere Zeitfenster (%s)",
                    self.heizkreis,
                    ", ".join(f"{WOCHENTAGE[t]} {n}" for t, n in abweichend),
                )
                return False
            self._uebertragen = plan
            self._gewarnt = None
            return not zu_voll
