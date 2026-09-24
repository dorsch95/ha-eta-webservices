"""Aschebox-Plan: Kessel rechtzeitig aus, entaschen, danach wieder ein.

Die Aschebox darf nur bei ausgeschaltetem Kessel abgenommen werden. Der
Nutzer wählt, wann er sie leeren will. So viel früher schaltet der Plan
den Kessel über seine Ein/Aus-Taste ab, dass Glutabbrand und Entaschung
bis dahin durch sind:

1. "geplant": Warten auf den Zeitpunkt zum Abschalten.
2. "glutabbrand": Kessel ist aus, die Glut brennt ab. Manche Kessel
   entaschen danach von selbst.
3. "entaschen": Sobald der Kessel "Bereit" oder "Ausgeschaltet" meldet,
   drückt der Plan die Entaschentaste - immer, auch nach einer Entaschung
   von selbst, damit auch der Rest der Asche herauskommt.
4. "leeren": Die Entaschung ist durch, eine Meldung sagt, dass die
   Aschebox geleert werden kann. Wird sie abgenommen und wieder
   eingesetzt, schaltet der Plan den Kessel wieder ein.

Die Dauer vom Abschalten bis zum Ende der Entaschung wird gemessen und
beim nächsten Mal genommen, mit ASCHEBOX_AUFSCHLAG obendrauf. Der Plan
übersteht einen Neustart von Home Assistant.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from datetime import datetime, timedelta

from homeassistant.components import persistent_notification
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.event import async_track_point_in_utc_time
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .api import ETAApiError
from .const import ASCHEBOX_AUFSCHLAG, ASCHEBOX_DAUER_ANFANG, DOMAIN

_LOGGER = logging.getLogger(__name__)

EREIGNIS = f"{DOMAIN}_aschebox"
"""Wird bei jedem Schritt ausgelöst - etwa für eine Nachricht aufs Handy."""

KEIN_FEUER = {"bereit", "ausgeschaltet"}
"""So meldet sich der Kessel, wenn Glutabbrand bzw. Entaschung durch sind."""

ENTASCHT_GERADE = {
    "entaschen",
    "vorbereiten auf entaschung",
    "glutabbrand wegen entaschung",
    "füllen gestoppt wegen entaschung",
}
"""Kessel-Zustände, an denen man sieht, dass die Entaschung läuft."""

BOX_FEHLT = {"aschebox fehlt", "glutabbrand weil aschebox fehlt"}
"""So meldet der Kessel eine abgenommene Aschebox."""

ANLAUFZEIT = timedelta(minutes=1)
"""So lange nach einem Schaltbefehl zählt der gemeldete Zustand noch nicht.

Die Anlage übernimmt einen Befehl nicht sofort in ihre Antworten.
"""

ENTASCHEN_HOECHSTENS = timedelta(minutes=20)
"""Zeigt sich die Entaschung so lange nicht, gilt sie trotzdem als durch."""

LEEREN_HOECHSTENS = timedelta(hours=2)
"""So lange wartet der Plan auf das Leeren, dann geht der Kessel wieder an.

Im Winter soll das Haus nicht auskühlen, nur weil niemand zur Aschebox
kam. Solange die Anlage "Aschebox fehlt" meldet, wartet er weiter.
"""

VERWERFEN_NACH = timedelta(hours=1)
"""Lag die gewünschte Zeit beim Neustart schon so lange zurück, entfällt der Plan."""

_SPEICHER_VERSION = 1


def _zeit(text: str | None) -> datetime | None:
    return dt_util.parse_datetime(text) if text else None


def _text(zeit: datetime | None) -> str | None:
    return zeit.isoformat() if zeit else None


class AscheboxPlan:
    """Führt den Plan Schritt für Schritt, angestoßen von jeder Abfrage."""

    def __init__(self, hass: HomeAssistant, coordinator) -> None:
        self.hass = hass
        self.coordinator = coordinator
        entry_id = coordinator.config_entry.entry_id
        self._speicher = Store(hass, _SPEICHER_VERSION, f"{DOMAIN}.aschebox_{entry_id}")
        self._meldung_id = f"{DOMAIN}_aschebox_{entry_id}"
        self._daten: dict = {"phase": "aus"}
        self._gelernt: float | None = None
        self._zuhoerer: list[Callable[[], None]] = []
        self._abbestellen: list[Callable[[], None]] = []
        self._zeitgeber: Callable[[], None] | None = None
        self._sperre = asyncio.Lock()

    @property
    def phase(self) -> str:
        return self._daten.get("phase", "aus")

    @property
    def ziel(self) -> datetime | None:
        """Wann der Nutzer die Aschebox leeren will."""
        return _zeit(self._daten.get("ziel"))

    @property
    def abschalten_um(self) -> datetime | None:
        return _zeit(self._daten.get("abschalten_um"))

    @property
    def dauer(self) -> timedelta:
        """Wie lange vor der gewünschten Zeit der Kessel ausgeht."""
        if self._gelernt is None:
            return timedelta(seconds=ASCHEBOX_DAUER_ANFANG)
        return timedelta(seconds=self._gelernt + ASCHEBOX_AUFSCHLAG)

    @property
    def gelernt(self) -> timedelta | None:
        """Wie lange Glutabbrand und Entaschung zuletzt gedauert haben."""
        return None if self._gelernt is None else timedelta(seconds=self._gelernt)

    def zuhoeren(self, rueckruf: Callable[[], None]) -> Callable[[], None]:
        """Meldet jede Änderung des Plans, etwa an die Entitäten."""
        self._zuhoerer.append(rueckruf)
        return lambda: self._zuhoerer.remove(rueckruf)

    async def laden(self) -> None:
        """Holt Plan und gelernte Dauer aus dem Speicher."""
        gespeichert = await self._speicher.async_load() or {}
        self._gelernt = gespeichert.get("gelernt")
        self._daten = gespeichert.get("plan") or {"phase": "aus"}
        if self.phase == "geplant":
            ziel = self.ziel
            if ziel is None or ziel + VERWERFEN_NACH < dt_util.utcnow():
                _LOGGER.info("ETA: Aschebox-Plan für %s ist abgelaufen, verworfen", ziel)
                self._daten = {"phase": "aus"}
                await self._sichern()

    def starten(self) -> None:
        """Hört auf jede Abfrage und plant den Zeitpunkt zum Abschalten."""
        self._abbestellen.append(self.coordinator.async_add_listener(self._abgefragt))
        if self.phase == "geplant":
            self._zeitgeber_stellen()

    def stoppen(self) -> None:
        for abbestellen in self._abbestellen:
            abbestellen()
        self._abbestellen.clear()
        self._zeitgeber_loeschen()

    async def planen(self, ziel: datetime) -> None:
        """Legt fest, wann die Aschebox geleert werden soll.

        Solange der Kessel noch nicht ausgeschaltet wurde, lässt sich die
        Zeit ändern. Liegt der Zeitpunkt zum Abschalten schon zurück, geht
        der Kessel sofort aus - leeren lässt sich dann etwas später.
        """
        if self.phase not in ("aus", "geplant"):
            raise HomeAssistantError(
                "Der Aschebox-Plan läuft schon - erst abbrechen, dann neu planen"
            )
        ziel = dt_util.as_utc(ziel)
        if ziel <= dt_util.utcnow():
            raise HomeAssistantError("Die Zeit zum Leeren muss in der Zukunft liegen")
        self._daten = {
            "phase": "geplant",
            "ziel": _text(ziel),
            "abschalten_um": _text(ziel - self.dauer),
        }
        await self._sichern()
        self._zeitgeber_stellen()
        self._melden(f"Aschebox leeren geplant: Der Kessel geht um {self._uhrzeit(self.abschalten_um)} aus.")

    async def abbrechen(self) -> None:
        """Beendet den Plan. Hat er den Kessel ausgeschaltet, geht er wieder an."""
        async with self._sperre:
            phase = self.phase
            self._zeitgeber_loeschen()
            self._daten = {"phase": "aus"}
            await self._sichern()
            if phase in ("glutabbrand", "entaschen", "leeren"):
                await self._kessel(ein=True)
                self._melden("Aschebox-Plan abgebrochen, der Kessel ist wieder eingeschaltet.")
            else:
                self._melden("Aschebox-Plan abgebrochen.")

    def _zeitgeber_stellen(self) -> None:
        self._zeitgeber_loeschen()
        zeitpunkt = self.abschalten_um
        if zeitpunkt is None:
            return
        if zeitpunkt <= dt_util.utcnow():
            self.hass.async_create_task(self._abschalten())
            return
        self._zeitgeber = async_track_point_in_utc_time(
            self.hass, self._zeit_erreicht, zeitpunkt
        )

    def _zeitgeber_loeschen(self) -> None:
        if self._zeitgeber is not None:
            self._zeitgeber()
            self._zeitgeber = None

    @callback
    def _zeit_erreicht(self, _jetzt: datetime) -> None:
        self._zeitgeber = None
        self.hass.async_create_task(self._abschalten())

    async def _abschalten(self) -> None:
        async with self._sperre:
            if self.phase != "geplant":
                return
            try:
                await self._kessel(ein=False)
            except HomeAssistantError as err:
                self._daten = {"phase": "aus"}
                await self._sichern()
                self._melden(f"Aschebox-Plan abgebrochen: Kessel ließ sich nicht ausschalten ({err}).")
                return
            self._daten.update(
                phase="glutabbrand", abgeschaltet_um=_text(dt_util.utcnow())
            )
            await self._sichern()
            self._melden("Kessel ausgeschaltet, die Glut brennt ab. Danach wird entascht.")

    @callback
    def _abgefragt(self) -> None:
        if self.phase in ("glutabbrand", "entaschen", "leeren"):
            self.hass.async_create_task(self.weiter())

    async def weiter(self) -> None:
        """Ein Schritt nach jeder Abfrage der Anlage."""
        if self._sperre.locked():
            return
        async with self._sperre:
            zustand = self._kessel_zustand()
            jetzt = dt_util.utcnow()
            if self.phase == "glutabbrand":
                await self._nach_glutabbrand(zustand, jetzt)
            elif self.phase == "entaschen":
                await self._nach_entaschen(zustand, jetzt)
            elif self.phase == "leeren":
                await self._nach_leeren(zustand, jetzt)

    async def _nach_glutabbrand(self, zustand: str | None, jetzt: datetime) -> None:
        abgeschaltet = _zeit(self._daten.get("abgeschaltet_um")) or jetzt
        if jetzt - abgeschaltet < ANLAUFZEIT:
            return
        if self._von_hand_eingeschaltet():
            await self._beenden("Aschebox-Plan beendet: Der Kessel wurde wieder eingeschaltet.")
            return
        if zustand not in KEIN_FEUER:
            return
        try:
            await self._taste(self.coordinator.entaschen_def["ein_roh"])
        except HomeAssistantError as err:
            _LOGGER.warning("ETA: Entaschentaste nicht gedrückt, neuer Versuch: %s", err)
            return
        self._daten.update(phase="entaschen", gedrueckt_um=_text(jetzt), entascht=False)
        await self._sichern()
        self._melden("Glutabbrand fertig, der Kessel entascht.")

    async def _nach_entaschen(self, zustand: str | None, jetzt: datetime) -> None:
        if zustand in ENTASCHT_GERADE:
            if not self._daten.get("entascht"):
                self._daten["entascht"] = True
                await self._sichern()
            return
        gedrueckt = _zeit(self._daten.get("gedrueckt_um")) or jetzt
        if jetzt - gedrueckt < ANLAUFZEIT or zustand not in KEIN_FEUER:
            return
        if not self._daten.get("entascht") and jetzt - gedrueckt < ENTASCHEN_HOECHSTENS:
            return
        await self._taste_zuruecksetzen()
        abgeschaltet = _zeit(self._daten.get("abgeschaltet_um"))
        if abgeschaltet is not None and self._daten.get("entascht"):
            self._gelernt = (jetzt - abgeschaltet).total_seconds()
        zaehler = self.coordinator.zahl("aschebox_verbrauch")
        self._daten.update(
            phase="leeren", leeren_seit=_text(jetzt), box_raus=False, zaehler=zaehler
        )
        await self._sichern()
        hinweis = "" if self._daten.get("entascht") else " (Die Entaschung war nicht zu sehen.)"
        self._melden(
            "Die Aschebox kann jetzt geleert werden. Ist sie wieder eingesetzt, "
            f"geht der Kessel wieder an.{hinweis}"
        )

    async def _nach_leeren(self, zustand: str | None, jetzt: datetime) -> None:
        if self._von_hand_eingeschaltet():
            await self._beenden("Aschebox-Plan beendet: Der Kessel wurde wieder eingeschaltet.")
            return
        if zustand in BOX_FEHLT:
            if not self._daten.get("box_raus"):
                self._daten["box_raus"] = True
                await self._sichern()
            return
        vorher = self._daten.get("zaehler")
        jetzt_zaehler = self.coordinator.zahl("aschebox_verbrauch")
        zurueckgesetzt = bool(vorher) and jetzt_zaehler is not None and jetzt_zaehler < vorher / 2
        seit = _zeit(self._daten.get("leeren_seit")) or jetzt
        zu_lange = jetzt - seit >= LEEREN_HOECHSTENS
        if not (self._daten.get("box_raus") or zurueckgesetzt or zu_lange):
            return
        try:
            await self._kessel(ein=True)
        except HomeAssistantError as err:
            _LOGGER.warning("ETA: Kessel nicht eingeschaltet, neuer Versuch: %s", err)
            return
        if zu_lange and not (self._daten.get("box_raus") or zurueckgesetzt):
            await self._beenden(
                "Die Aschebox wurde nicht geleert - der Kessel ist nach "
                f"{int(LEEREN_HOECHSTENS.total_seconds() // 3600)} Stunden wieder eingeschaltet."
            )
        else:
            await self._beenden("Aschebox geleert, der Kessel ist wieder eingeschaltet.")

    async def _beenden(self, nachricht: str) -> None:
        self._daten = {"phase": "aus"}
        await self._sichern()
        self._melden(nachricht)

    def _kessel_zustand(self) -> str | None:
        wert = (self.coordinator.data or {}).get("kessel_zustand")
        if wert is None or not wert.text:
            return None
        return wert.text.strip().casefold()

    def _von_hand_eingeschaltet(self) -> bool:
        """Meldet die Anlage den Kessel an, hat ihn jemand eingeschaltet."""
        definition = self.coordinator.switch_defs.get("kessel_schalter")
        wert = (self.coordinator.data or {}).get("kessel_schalter")
        if definition is None or wert is None or not wert.text:
            return False
        return wert.text.strip() == definition["ein_text"]

    async def _kessel(self, ein: bool) -> None:
        definition = self.coordinator.switch_defs["kessel_schalter"]
        await self._schreiben(definition["uri"], definition["ein_roh" if ein else "aus_roh"])

    async def _taste(self, roh: str) -> None:
        await self._schreiben(self.coordinator.entaschen_def["uri"], roh)

    async def _taste_zuruecksetzen(self) -> None:
        """Steht die Entaschentaste noch auf "Ein", zurück auf "Aus"."""
        definition = self.coordinator.entaschen_def
        wert = (self.coordinator.data or {}).get("kessel_entaschen")
        if wert is None or (wert.text or "").strip() != definition["ein_text"]:
            return
        try:
            await self._taste(definition["aus_roh"])
        except HomeAssistantError as err:
            _LOGGER.warning("ETA: Entaschentaste nicht zurückgestellt: %s", err)

    async def _schreiben(self, uri: str, roh: str) -> None:
        try:
            await self.coordinator.client.async_set_value(uri, roh)
        except ETAApiError as err:
            raise HomeAssistantError(str(err)) from err
        await self.coordinator.async_request_refresh()

    async def _sichern(self) -> None:
        await self._speicher.async_save({"gelernt": self._gelernt, "plan": self._daten})
        for rueckruf in list(self._zuhoerer):
            rueckruf()

    def _uhrzeit(self, zeit: datetime | None) -> str:
        return dt_util.as_local(zeit).strftime("%H:%M") if zeit else "?"

    def _melden(self, nachricht: str) -> None:
        """Meldung in Home Assistant und ein Ereignis für Automatisierungen."""
        _LOGGER.info("ETA: %s", nachricht)
        persistent_notification.async_create(
            self.hass, nachricht, title="ETA Heizung: Aschebox", notification_id=self._meldung_id
        )
        self.hass.bus.async_fire(
            EREIGNIS,
            {
                "phase": self.phase,
                "nachricht": nachricht,
                "ziel": _text(self.ziel),
                "config_entry_id": self.coordinator.config_entry.entry_id,
            },
        )
