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

Schaltet jemand den Kessel wieder ein, endet der Plan - in jedem Schritt.
Endet er im Schritt "entaschen" vorzeitig, durch Abbrechen oder weil der
Kessel eingeschaltet wurde, steht die Entaschentaste noch auf "Ein". Sie
wird dann wie sonst erst zurückgestellt, wenn die Entaschung durch ist,
siehe AscheboxPlan._taste_nachholen.
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
from .const import ALTE_DOMAIN, ASCHEBOX_AUFSCHLAG, ASCHEBOX_DAUER_ANFANG, DOMAIN

_LOGGER = logging.getLogger(__name__)

EREIGNIS = f"{DOMAIN}_aschebox"
"""Wird bei jedem Schritt ausgelöst - etwa für eine Nachricht aufs Handy."""

ALTES_EREIGNIS = f"{ALTE_DOMAIN}_aschebox"
"""Der Name bis 0.25; kommt zusätzlich, damit Automatisierungen von damals
weiterlaufen."""

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

LAEUFT = ("glutabbrand", "entaschen", "leeren")
"""In diesen Schritten hat der Plan den Kessel ausgeschaltet."""

BLEIBT_GESPERRT = (
    "Der Kessel bleibt aus, weil er gesperrt ist - er geht wieder an, sobald die Sperre endet."
)
"""So endet eine Meldung, wenn der Plan den Kessel der Kesselsperre überlässt."""

TASTE_AUFGEBEN_NACH = timedelta(hours=2)
"""So lange nach dem Drücken wird versucht, die Entaschentaste nachträglich zurückzustellen."""

VERWAIST_HOECHSTENS = timedelta(days=1)
"""So lange wartet ein Plan, der nicht weiterlaufen kann, auf einen Start, bei dem es wieder geht."""

_SPEICHER_VERSION = 1


def _zeit(text: str | None) -> datetime | None:
    return dt_util.parse_datetime(text) if text else None


def _text(zeit: datetime | None) -> str | None:
    return zeit.isoformat() if zeit else None


def speicher(hass: HomeAssistant, entry_id: str, domain: str = DOMAIN) -> Store:
    """Wo sich der Plan über einen Neustart hinweg merkt, was er gelernt hat."""
    return Store(hass, _SPEICHER_VERSION, f"{domain}.aschebox_{entry_id}")


async def verwaisten_plan_melden(hass: HomeAssistant, entry_id: str, endgueltig: bool) -> None:
    """Meldet einen Plan, der den Kessel ausgeschaltet hat und nicht weiterlaufen kann.

    Der Plan läuft nur, wenn Kessel-Schalter und Entaschentaste beim Start
    bestätigt sind. Fehlt das nach einem Neustart mitten im Plan, bliebe
    der Kessel aus, ohne dass es jemand merkt. endgueltig: Der
    Schreibzugriff ist abgeschaltet, der Plan wird verworfen. Sonst bleibt
    er gespeichert und läuft beim nächsten Start weiter, bei dem die Anlage
    wieder antwortet - höchstens VERWAIST_HOECHSTENS lang, danach wird er
    ebenfalls verworfen.
    """
    lager = speicher(hass, entry_id)
    gespeichert = await lager.async_load() or {}
    plan = gespeichert.get("plan") or {}
    if plan.get("phase") not in LAEUFT:
        return
    abgeschaltet = _zeit(plan.get("abgeschaltet_um"))
    if abgeschaltet is None or dt_util.utcnow() - abgeschaltet > VERWAIST_HOECHSTENS:
        endgueltig = True
    nachricht = (
        "Der Aschebox-Plan hat den Kessel ausgeschaltet, kann aber nicht weiterlaufen: "
        + (
            "Kessel-Schalter oder Entaschentaste stehen nicht mehr zur Verfügung. "
            "Der Plan ist beendet."
            if endgueltig
            else "Die Anlage hat Kessel-Schalter oder Entaschentaste beim Start nicht bestätigt."
        )
        + " Bitte den Kessel selbst wieder einschalten."
    )
    _LOGGER.warning("ETA: %s", nachricht)
    persistent_notification.async_create(
        hass, nachricht, title="ETA Heizung: Aschebox", notification_id=f"{DOMAIN}_aschebox_{entry_id}"
    )
    if endgueltig:
        await lager.async_save({**gespeichert, "plan": {"phase": "aus"}})


class AscheboxPlan:
    """Führt den Plan Schritt für Schritt, angestoßen von jeder Abfrage."""

    def __init__(self, hass: HomeAssistant, coordinator) -> None:
        self.hass = hass
        self.coordinator = coordinator
        entry_id = coordinator.config_entry.entry_id
        self._speicher = speicher(hass, entry_id)
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
    def haelt_kessel_aus(self) -> bool:
        """Ob der Plan den Kessel ausgeschaltet hat und ihn an seinem Ende wieder einschaltet."""
        return self.phase in LAEUFT

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
                self._daten = self._aus()
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
            **self._aus(),
            "phase": "geplant",
            "ziel": _text(ziel),
            "abschalten_um": _text(ziel - self.dauer),
        }
        await self._sichern()
        self._zeitgeber_stellen()
        self._melden(f"Aschebox leeren geplant: Der Kessel geht um {self._uhrzeit(self.abschalten_um)} aus.")

    async def abbrechen(self) -> None:
        """Beendet den Plan. Hat er den Kessel ausgeschaltet, geht er vorher wieder an.

        Lässt sich der Kessel gerade nicht einschalten, bleibt der Plan
        bestehen - sonst wäre der Kessel aus und niemand schaltete ihn mehr
        ein. Der Knopf meldet den Fehler und lässt sich erneut drücken.
        Ein gesperrter Kessel bleibt aus, siehe _wieder_einschalten.
        """
        async with self._sperre:
            phase = self.phase
            eingeschaltet = phase in LAEUFT and await self._wieder_einschalten()
            self._zeitgeber_loeschen()
            self._daten = self._aus()
            await self._sichern()
            if eingeschaltet:
                self._melden("Aschebox-Plan abgebrochen, der Kessel ist wieder eingeschaltet.")
            elif phase in LAEUFT:
                self._melden(f"Aschebox-Plan abgebrochen. {BLEIBT_GESPERRT}")
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
                self._daten = self._aus()
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
        """Ein Schritt je voller Abfrage - die schnelle Gruppe treibt den Plan nicht."""
        if (self.phase in LAEUFT or "taste" in self._daten) and self.coordinator.volle_abfrage:
            self.hass.async_create_task(self.weiter())

    async def weiter(self) -> None:
        """Ein Schritt nach jeder Abfrage der Anlage."""
        if self._sperre.locked():
            return
        async with self._sperre:
            zustand = self._kessel_zustand()
            jetzt = dt_util.utcnow()
            if "taste" in self._daten:
                await self._taste_nachholen(zustand, jetzt)
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
        self._daten.pop("taste", None)
        self._daten.update(phase="entaschen", gedrueckt_um=_text(jetzt), entascht=False)
        await self._sichern()
        self._melden("Glutabbrand fertig, der Kessel entascht.")

    async def _nach_entaschen(self, zustand: str | None, jetzt: datetime) -> None:
        if self._von_hand_eingeschaltet():
            await self._beenden("Aschebox-Plan beendet: Der Kessel wurde wieder eingeschaltet.")
            return
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
        if not await self._taste_zuruecksetzen():
            self._daten["taste"] = {"gedrueckt_um": self._daten.get("gedrueckt_um"), "entascht": True}
        abgeschaltet = _zeit(self._daten.get("abgeschaltet_um"))
        if abgeschaltet is not None and self._daten.get("entascht"):
            self._gelernt = (jetzt - abgeschaltet).total_seconds()
        zaehler = self.coordinator.zahl("aschebox_verbrauch")
        self._daten.update(
            phase="leeren", leeren_seit=_text(jetzt), box_raus=False, zaehler=zaehler
        )
        await self._sichern()
        hinweis = "" if self._daten.get("entascht") else " (Die Entaschung war nicht zu sehen.)"
        sperre = self.coordinator.kesselsperre
        danach = (
            "bleibt der Kessel aus, bis seine Sperre endet."
            if sperre is not None and sperre.gesperrt
            else "geht der Kessel wieder an."
        )
        self._melden(
            f"Die Aschebox kann jetzt geleert werden. Ist sie wieder eingesetzt, {danach}{hinweis}"
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
            eingeschaltet = await self._wieder_einschalten()
        except HomeAssistantError as err:
            _LOGGER.warning("ETA: Kessel nicht eingeschaltet, neuer Versuch: %s", err)
            return
        stunden = int(LEEREN_HOECHSTENS.total_seconds() // 3600)
        if zu_lange and not (self._daten.get("box_raus") or zurueckgesetzt):
            if eingeschaltet:
                await self._beenden(
                    "Die Aschebox wurde nicht geleert - der Kessel ist nach "
                    f"{stunden} Stunden wieder eingeschaltet."
                )
            else:
                await self._beenden(
                    f"Die Aschebox wurde in {stunden} Stunden nicht geleert, der Plan ist "
                    f"beendet. {BLEIBT_GESPERRT}"
                )
        elif eingeschaltet:
            await self._beenden("Aschebox geleert, der Kessel ist wieder eingeschaltet.")
        else:
            await self._beenden(f"Aschebox geleert. {BLEIBT_GESPERRT}")

    async def _beenden(self, nachricht: str) -> None:
        self._daten = self._aus()
        await self._sichern()
        self._melden(nachricht)

    def _aus(self) -> dict:
        """Der Plan ohne Vorhaben - samt dem Vermerk, dass die Entaschentaste noch zurückzustellen ist.

        Der Vermerk entsteht, wenn der Plan im Schritt "entaschen" endet,
        und bleibt stehen, bis _taste_nachholen ihn erledigt hat.
        """
        if self.phase == "entaschen":
            return {
                "phase": "aus",
                "taste": {
                    "gedrueckt_um": self._daten.get("gedrueckt_um"),
                    "entascht": bool(self._daten.get("entascht")),
                },
            }
        if "taste" in self._daten:
            return {"phase": "aus", "taste": self._daten["taste"]}
        return {"phase": "aus"}

    async def _taste_nachholen(self, zustand: str | None, jetzt: datetime) -> None:
        """Stellt die Entaschentaste zurück, nachdem der Plan im Schritt "entaschen" geendet hat.

        Wie im Plan selbst erst, wenn die Entaschung durch ist: Der Kessel
        hat sie gezeigt und zeigt sie nicht mehr, oder es sind
        ENTASCHEN_HOECHSTENS vergangen. Mitten in der Entaschung wird die
        Taste nie zurückgestellt - als Entaschung zählt jeder Zustand, der
        davon spricht, und solange der Kessel keinen Zustand meldet, wird
        gewartet. Danach muss er ANLAUFZEIT lang ohne Entaschung bleiben.
        Nimmt die Anlage das Zurückstellen nicht an, folgt bei der nächsten
        Abfrage ein neuer Versuch, bis TASTE_AUFGEBEN_NACH.
        """
        offen = self._daten["taste"]
        gedrueckt = _zeit(offen.get("gedrueckt_um"))
        if gedrueckt is None:
            gedrueckt = jetzt
            offen["gedrueckt_um"] = _text(jetzt)
        zu_alt = jetzt - gedrueckt >= TASTE_AUFGEBEN_NACH
        if zustand is None or zustand in ENTASCHT_GERADE or "entasch" in zustand:
            vorher = dict(offen)
            if zustand is not None:
                offen["entascht"] = True
            offen.pop("ruhig_seit", None)
            if zu_alt:
                self._daten.pop("taste", None)
            if zu_alt or offen != vorher:
                await self._sichern()
            return
        if jetzt - gedrueckt < ANLAUFZEIT:
            return
        if not offen.get("entascht") and jetzt - gedrueckt < ENTASCHEN_HOECHSTENS:
            return
        ruhig_seit = _zeit(offen.get("ruhig_seit"))
        if ruhig_seit is None:
            offen["ruhig_seit"] = _text(jetzt)
            await self._sichern()
            return
        if jetzt - ruhig_seit < ANLAUFZEIT:
            return
        if await self._taste_zuruecksetzen() or zu_alt:
            self._daten.pop("taste", None)
            await self._sichern()

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
        """Schaltet den Kessel und sagt es der Kesselsperre, die dieselbe Taste bedient.

        Die Sperre erfährt es schon vor dem Schreiben: Sperrt sie, während
        der Befehl noch unterwegs ist, rechnet sie mit dem Kessel, wie er
        gleich steht - und schaltet ihn nach dem Einschalten des Plans
        selbst wieder aus, statt ihn für ausgeschaltet zu halten.
        """
        definition = self.coordinator.switch_defs["kessel_schalter"]
        sperre = self.coordinator.kesselsperre
        if sperre is not None:
            sperre.befohlen(ein)
        try:
            await self._senden(definition["uri"], definition["ein_roh" if ein else "aus_roh"])
        except HomeAssistantError:
            if sperre is not None:
                sperre.befehl_verworfen()
            raise
        await self.coordinator.async_request_refresh()

    async def _wieder_einschalten(self) -> bool:
        """Schaltet den Kessel am Ende des Plans wieder ein - außer er ist gesperrt.

        Hält "Kessel sperren" oder der Fremderzeuger ihn gesperrt, bleibt
        er aus, und das Freigeben schaltet ihn ein, siehe
        switch.Kesselsperre. Gibt zurück, ob eingeschaltet wurde.
        """
        sperre = self.coordinator.kesselsperre
        if sperre is not None and sperre.gesperrt:
            sperre.einschalten_uebernehmen()
            return False
        await self._kessel(ein=True)
        return True

    async def _taste(self, roh: str) -> None:
        await self._schreiben(self.coordinator.entaschen_def["uri"], roh)

    async def _taste_zuruecksetzen(self) -> bool:
        """Steht die Entaschentaste noch auf "Ein", zurück auf "Aus".

        Gibt zurück, ob sie danach auf "Aus" steht - also auch dann, wenn
        nichts zu schreiben war.
        """
        definition = self.coordinator.entaschen_def
        wert = (self.coordinator.data or {}).get("kessel_entaschen")
        if wert is None or (wert.text or "").strip() != definition["ein_text"]:
            return True
        try:
            await self._taste(definition["aus_roh"])
        except HomeAssistantError as err:
            _LOGGER.warning("ETA: Entaschentaste nicht zurückgestellt: %s", err)
            return False
        return True

    async def _senden(self, uri: str, roh: str) -> None:
        try:
            await self.coordinator.client.async_set_value(uri, roh)
        except ETAApiError as err:
            raise HomeAssistantError(str(err)) from err

    async def _schreiben(self, uri: str, roh: str) -> None:
        await self._senden(uri, roh)
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
        daten = {
            "phase": self.phase,
            "nachricht": nachricht,
            "ziel": _text(self.ziel),
            "config_entry_id": self.coordinator.config_entry.entry_id,
        }
        for ereignis in (EREIGNIS, ALTES_EREIGNIS):
            self.hass.bus.async_fire(ereignis, daten)
