"""Der Fremderzeuger: eine Wärmequelle, die an keiner Stelle an der ETA-Regelung hängt.

Etwa ein Kaminofen mit eigener Regelung. Die Anlage weiß nichts von ihm -
ob er heizt, erfährt die Integration aus Home Assistant. Damit ist er das
Gegenstück zur Komponente "fremdwaerme", deren Werte die Anlage selbst
führt.

Wann er als heizend gilt, bestimmen zwei freiwillige Angaben, von denen
mindestens eine da sein muss:
- Nur eine Entität (Schalter, Helfer, Binärsensor): Er heizt, solange sie
  an ist.
- Nur ein Temperaturfühler: Er heizt, sobald der Fühler die
  Sperrtemperatur erreicht hat. An die Stelle der Entität tritt dann ein
  eigener Ein/Aus-Schalter (switch.ETAFremderzeugerSchalter): Aus heißt,
  der Fremderzeuger wird nicht beachtet.
- Beide: Er heizt, wenn die Entität an ist und der Fühler die
  Sperrtemperatur erreicht hat.
Unter die Sperrtemperatur muss der Fühler um
const.FREMDERZEUGER_HYSTERESE fallen, damit der Zustand nicht flattert.

Solange er heizt, hält die Integration die gewählten Kessel gesperrt
(switch.Kesselsperre) und gibt sie danach wieder frei. Bisher kennt die
Integration einen Kessel; die Auswahl ist trotzdem eine Liste, damit
weitere dazukommen können.

Gesperrt wird ohne Fühler nach der Wartezeit "Sperren nach". Mit Fühler
ersetzt die Temperatur die Wartezeit: Gesperrt wird sofort. Freigegeben
wird, wenn er die Wartezeit "Freigeben nach" lang nicht mehr heizt.
Abgeglichen wird außerdem, wenn Home Assistant gestartet ist und sobald
die Anlage nach einer Unterbrechung wieder erreichbar ist. Nimmt die
Anlage das Sperren oder Freigeben nicht an, folgt nach
NEUER_VERSUCH_NACH der nächste Versuch.

Lässt sich nicht mehr sagen, ob er heizt - Entität oder Fühler sind nicht
verfügbar, etwa weil eine Batterie leer ist -, wird der Kessel nach der
Wartezeit "Freigeben nach" freigegeben. Ein Kessel, der unnötig mitläuft,
ist harmlos; ein gesperrter Kessel in einem kalten Haus ist es nicht. Von
sich aus gesperrt wird in dieser Lage nie. Wechselt ein wackeliger Fühler
zwischen "heizt nicht" und "nicht verfügbar", läuft die Wartezeit weiter.

Schaltet jemand den gesperrten Kessel von Hand ein, bleibt er an, bis
einer der Anlässe wieder eintritt.
"""

from __future__ import annotations

import logging
import math
from datetime import timedelta

from homeassistant.components import persistent_notification
from homeassistant.const import ATTR_UNIT_OF_MEASUREMENT, STATE_OFF, STATE_ON, UnitOfTemperature
from homeassistant.core import CALLBACK_TYPE, Event, HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.event import async_call_later, async_track_state_change_event
from homeassistant.helpers.start import async_at_started
from homeassistant.util.unit_conversion import TemperatureConverter

from .const import DEFAULT_FREMDERZEUGER_SCHWELLE, DOMAIN, FREMDERZEUGER_HYSTERESE

_LOGGER = logging.getLogger(__name__)

KESSEL = "kessel"
"""Der Kessel in der Auswahl der sperrbaren Kessel, siehe const.SPERRBARE_KESSEL."""

NEUER_VERSUCH_NACH = timedelta(minutes=1)
"""So lange nach einem gescheiterten Sperren oder Freigeben folgt der nächste Versuch."""

MELDEN_NACH = 5
"""Nach so vielen gescheiterten Versuchen, den Kessel freizugeben, erscheint eine Meldung.

Ein Kessel, der gesperrt bleibt, obwohl der Fremderzeuger aus ist, lässt
das Haus auskühlen. Das soll niemand erst im Protokoll finden.
"""


class Fremderzeuger:
    """Sagt, ob der Fremderzeuger heizt, und sperrt solange die gewählten Kessel."""

    def __init__(
        self,
        hass: HomeAssistant,
        coordinator,
        entitaet: str | None,
        sperrt: list[str],
        sperren_nach: float,
        freigeben_nach: float,
        fuehler: str | None = None,
        schwelle: float = DEFAULT_FREMDERZEUGER_SCHWELLE,
    ) -> None:
        self.hass = hass
        self.coordinator = coordinator
        self.entitaet = entitaet or None
        self.fuehler = fuehler or None
        self.schwelle = float(schwelle)
        self.sperrt = list(sperrt)
        self._sperren_nach = timedelta(minutes=0 if self.fuehler else sperren_nach)
        self._freigeben_nach = timedelta(minutes=freigeben_nach)
        self._abmelden: list[CALLBACK_TYPE] = []
        self._zeitgeber: CALLBACK_TYPE | None = None
        self._erreichbar = True
        self._heizt: bool | None = None
        self._unbekannt_zu_lange = False
        """Ob eine Wartezeit abgelaufen ist, an deren Ende sich nicht sagen ließ, ob er heizt."""
        self._gescheitert = 0
        """Wie oft dasselbe - Sperren oder Freigeben - zuletzt hintereinander gescheitert ist."""
        self._gescheitert_beim_sperren = False
        self._neuer_versuch = False
        """Ob der laufende Zeitgeber nur auf den nächsten Versuch wartet, siehe NEUER_VERSUCH_NACH."""
        self._beobachter: list = []
        self.eingeschaltet = True
        """Der eigene Ein/Aus-Schalter - zählt nur ohne Entität, siehe const.FREMDERZEUGER_SCHALTER."""

    @property
    def an(self) -> bool | None:
        """Was die Entität sagt - None ohne Entität oder ohne verwertbaren Zustand."""
        if not self.entitaet:
            return None
        stand = self.hass.states.get(self.entitaet)
        if stand is None:
            return None
        return {STATE_ON: True, STATE_OFF: False}.get(stand.state)

    @property
    def temperatur(self) -> float | None:
        """Was der Temperaturfühler meldet, in °C - None ohne Fühler oder ohne gültigen Wert.

        Die Sperrtemperatur steht in °C. Ein Fühler in °F oder K wird
        deshalb umgerechnet.
        """
        if not self.fuehler:
            return None
        stand = self.hass.states.get(self.fuehler)
        try:
            wert = float(stand.state) if stand is not None else None
        except (TypeError, ValueError):
            return None
        if wert is None or not math.isfinite(wert):
            return None
        einheit = stand.attributes.get(ATTR_UNIT_OF_MEASUREMENT)
        if einheit in (UnitOfTemperature.FAHRENHEIT, UnitOfTemperature.KELVIN):
            wert = TemperatureConverter.convert(wert, einheit, UnitOfTemperature.CELSIUS)
        return wert

    @property
    def heizt(self) -> bool | None:
        """Ob der Fremderzeuger heizt, wie zuletzt bewertet - None, wenn es sich nicht sagen ließ."""
        return self._heizt

    def bewerten(self) -> bool | None:
        """Ob der Fremderzeuger jetzt heizt - None, wenn es sich gerade nicht sagen lässt.

        Solange er als heizend gilt - oder der Kessel seinetwegen noch
        gesperrt ist, etwa nach einem Neustart -, zählt die Sperrtemperatur
        abzüglich der Hysterese.
        """
        if self.entitaet:
            an = self.an
            if not an:
                return an
            if not self.fuehler:
                return True
        elif not self.eingeschaltet:
            return False
        temperatur = self.temperatur
        if temperatur is None:
            return None
        haelt = self._heizt
        if haelt is None:
            sperre = self.coordinator.kesselsperre
            haelt = sperre is not None and sperre.gesperrt and KESSEL in self.sperrt
        return temperatur >= self.schwelle - (FREMDERZEUGER_HYSTERESE if haelt else 0)

    @callback
    def beobachten(self, rueckruf):
        """Ruft rueckruf, sobald sich ändert, ob er heizt. Gibt die Abmeldung zurück."""
        self._beobachter.append(rueckruf)

        def abmelden() -> None:
            if rueckruf in self._beobachter:
                self._beobachter.remove(rueckruf)

        return abmelden

    @callback
    def starten(self) -> None:
        """Beobachtet Entität, Fühler und die Erreichbarkeit der Anlage."""
        self._erreichbar = self.coordinator.last_update_success
        self._uebernehmen(self.bewerten())
        beobachtet = [entitaet for entitaet in (self.entitaet, self.fuehler) if entitaet]
        self._abmelden = [
            async_track_state_change_event(self.hass, beobachtet, self._geaendert),
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
        self._neuer_versuch = False
        if self._zeitgeber is not None:
            self._zeitgeber()
            self._zeitgeber = None

    async def _gestartet(self, hass: HomeAssistant) -> None:
        """Beim Start gilt, was Entität und Fühler jetzt sagen - ohne Wartezeit.

        Sagen sie noch nichts, läuft die Wartezeit zum Freigeben an.
        """
        self._uebernehmen(self.bewerten())
        if self._heizt is None:
            self._warten(self._freigeben_nach)
            return
        await self.async_abgleichen()

    def _uebernehmen(self, heizt: bool | None) -> bool:
        """Hält die neue Bewertung fest und sagt, ob sie sich geändert hat."""
        if heizt == self._heizt:
            return False
        self._heizt = heizt
        self._unbekannt_zu_lange = False
        for rueckruf in list(self._beobachter):
            rueckruf()
        return True

    @callback
    def _warten(self, wartezeit: timedelta) -> None:
        """Bestellt den Abgleich nach dieser Wartezeit; eine laufende wird verworfen."""
        self._zeitgeber_loeschen()
        self._zeitgeber = async_call_later(self.hass, wartezeit, self._zeit_um)

    @callback
    def _geaendert(self, event: Event | None = None) -> None:
        """Entität, Fühler, Sperrtemperatur oder der eigene Schalter haben sich geändert.

        Heizt der Fremderzeuger jetzt anders als zuvor, läuft die Wartezeit
        an, danach wird abgeglichen. Ein neuer Wechsel verwirft die
        laufende Wartezeit - ein Ofen, der kurz aus und wieder an ist, gibt
        den Kessel nicht frei. Lässt es sich nicht mehr sagen, läuft die
        Wartezeit zum Freigeben.

        Ein Wechsel zwischen "heizt nicht" und "lässt sich nicht sagen"
        lässt eine laufende Wartezeit weiterlaufen: Beides führt zum
        Freigeben, und ein wackeliger Fühler soll es nicht endlos
        hinausschieben.
        """
        vorher = self._heizt
        heizt = self.bewerten()
        if not self._uebernehmen(heizt):
            return
        if not vorher and not heizt and self._zeitgeber is not None:
            return
        self._warten(self._sperren_nach if heizt else self._freigeben_nach)

    @property
    def eigener_schalter(self) -> bool:
        """Ob es den eigenen Ein/Aus-Schalter gibt: nur mit Fühler und ohne Entität."""
        return bool(self.fuehler) and not self.entitaet

    @callback
    def einschalten(self, ein: bool) -> None:
        """Stellt den eigenen Ein/Aus-Schalter und bewertet damit neu."""
        self.eingeschaltet = bool(ein)
        self._geaendert()

    @callback
    def schwelle_setzen(self, grad: float) -> None:
        """Übernimmt eine neue Sperrtemperatur und bewertet damit neu."""
        self.schwelle = float(grad)
        self._geaendert()

    async def _zeit_um(self, _jetzt) -> None:
        self._zeitgeber = None
        self._neuer_versuch = False
        if self._heizt is None:
            self._unbekannt_zu_lange = True
        await self.async_abgleichen()

    @callback
    def _anlage_gemeldet(self) -> None:
        """Ist die Anlage nach einer Unterbrechung wieder erreichbar, wird abgeglichen.

        Sonst bliebe der Kessel gesperrt, wenn der Fremderzeuger ausging,
        während die Anlage nicht erreichbar war. Eine laufende Wartezeit
        bleibt bestehen; nur ein anstehender neuer Versuch wird vorgezogen.
        """
        erreichbar = self.coordinator.last_update_success
        zurueck = erreichbar and not self._erreichbar
        self._erreichbar = erreichbar
        if zurueck and (self._zeitgeber is None or self._neuer_versuch):
            self._zeitgeber_loeschen()
            self.hass.async_create_task(self.async_abgleichen())

    async def async_abgleichen(self) -> None:
        """Sperrt oder gibt frei, wenn die Sperre anders steht, als der Fremderzeuger verlangt.

        Scheitert das, folgt nach NEUER_VERSUCH_NACH der nächste Versuch -
        so lange, bis es gelingt oder sich etwas ändert. Sonst bliebe der
        Kessel nach einem einzigen abgelehnten Befehl gesperrt, bis der
        Fremderzeuger das nächste Mal ausgeht. Gewarnt wird nur beim
        ersten Mal; lässt sich der Kessel MELDEN_NACH Mal nicht freigeben,
        erscheint eine Meldung in Home Assistant.
        """
        sperre = self.coordinator.kesselsperre
        heizt = self._heizt
        if heizt is None and self._unbekannt_zu_lange:
            heizt = False
        if sperre is None or KESSEL not in self.sperrt or heizt is None:
            return
        if heizt == sperre.gesperrt:
            self._gelungen()
            return
        try:
            if heizt:
                await sperre.async_sperren()
            else:
                await sperre.async_freigeben()
        except HomeAssistantError as err:
            if self._gescheitert_beim_sperren != heizt:
                self._gescheitert = 0
            self._gescheitert_beim_sperren = heizt
            (_LOGGER.debug if self._gescheitert else _LOGGER.warning)(
                "ETA: Der Fremderzeuger konnte den Kessel nicht %s, neuer Versuch folgt: %s",
                "sperren" if heizt else "freigeben",
                err,
            )
            self._gescheitert += 1
            if not heizt and self._gescheitert == MELDEN_NACH:
                persistent_notification.async_create(
                    self.hass,
                    "Der Fremderzeuger heizt nicht mehr, aber der Kessel ließ sich nicht "
                    f"freigeben ({err}). Home Assistant versucht es weiter. Soll der Kessel "
                    "gleich laufen, bitte an der Heizung einschalten.",
                    title="ETA Heizung: Fremderzeuger",
                    notification_id=self._meldung_id,
                )
            if self._zeitgeber is None:
                self._warten(NEUER_VERSUCH_NACH)
                self._neuer_versuch = True
            return
        self._gelungen()
        await self.coordinator.async_request_refresh()

    @property
    def _meldung_id(self) -> str:
        return f"{DOMAIN}_fremderzeuger_{self.coordinator.config_entry.entry_id}"

    @callback
    def _gelungen(self) -> None:
        """Die Sperre steht, wie der Fremderzeuger es verlangt - eine Meldung dazu erledigt sich."""
        if self._gescheitert >= MELDEN_NACH and not self._gescheitert_beim_sperren:
            persistent_notification.async_dismiss(self.hass, self._meldung_id)
        self._gescheitert = 0
