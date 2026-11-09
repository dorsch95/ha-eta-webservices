"""Zeitprogramme direkt bearbeiten - für die Dashboard-Karte.

Die Karte "ETA Zeitprogramm" (oberflaeche/eta-zeitprogramm-karte.js) zeigt
die Heizzeiten der Woche als Balken und lässt sie ändern. Home Assistant
lädt sie in jedem Dashboard von selbst; im Kartenwähler steht sie unter
"ETA Zeitprogramm". Sie spricht über zwei Websocket-Befehle mit der
Integration:

- eta_heating_ws/zeitprogramme liest die Zeitfenster aller beschreibbaren
  Zeitprogramme frisch von der Anlage - die Heizzeiten der Heizkreise und
  die Lade- und Bereitschaftszeiten von Puffer und Frischwassermodul -,
  bei Heizzeiten dazu je Tag den "Wert außerhalb der Zeitfenster", die
  Raumtemperatur in der Absenkzeit,
- eta_heating_ws/zeitprogramm_setzen schreibt Fenster und Absenktemperatur
  für einen oder mehrere Tage, liest zur Kontrolle nach und gibt das
  Programm zurück.

Geschrieben wird nur, was sich ändert, mit denselben Regeln wie beim
Zeitplan-Abgleich (zeitplan.tagesfenster). Folgt ein Heizkreis einem
Zeitplan-Helfer, führt der: Die Karte zeigt das Programm dann nur an, und
Schreiben wird abgelehnt - sonst überschriebe der nächste Abgleich die
Änderung wieder. Bei Warmwasser gelten für die Temperaturen
WARMWASSER_GRENZEN bzw. beim Kombi-Puffer KOMBI_GRENZEN statt der des
Thermostats, beim Warmwasserspeicher höchstens "Warmwasserspeicher max.".
Bei den Ladezeiten des Puffers und den Zirkulationszeiten steuern die
Zeiten nur, ob geladen wird bzw. die Pumpe läuft: Die Karte zeigt dort
keine Temperatur, und geschrieben wird keine.
"""

from __future__ import annotations

import asyncio
import logging
import math
from pathlib import Path
from typing import Any

import voluptuous as vol
from homeassistant.components import websocket_api
from homeassistant.components.frontend import add_extra_js_url
from homeassistant.core import HomeAssistant, callback

from .api import ETAApiError, Zeitfenster
from .const import (
    DOMAIN,
    FWM_REGELUNG,
    KARTE_ZEITPROGRAMM,
    THERMOSTAT_SOLL_GRENZEN,
    URL_OBERFLAECHE,
    WARMWASSER_VERBRUEHSCHUTZ,
    WOCHENTAGE,
    ZEITFENSTER_JE_TAG,
)
from .karte import VERSION
from .uri_discovery import WARMWASSER_MAXIMUM
from .zeitplan import Block, als_text, ersatztemperatur, tagesfenster

_LOGGER = logging.getLogger(__name__)

OBERFLAECHE = Path(__file__).parent / "oberflaeche"
"""Der Ordner mit den Dashboard-Karten, ausgeliefert unter URL_OBERFLAECHE."""


def _temperatur(wert: Any) -> float:
    """Eine Temperatur aus der Karte: eine Zahl, aber kein "nan" und kein "inf"."""
    zahl = float(wert)
    if not math.isfinite(zahl):
        raise vol.Invalid("Temperatur ist keine Zahl")
    return zahl


TEMPERATUR = vol.Any(None, vol.All(vol.Coerce(float), _temperatur))


class ZeitprogrammFehler(Exception):
    """Ein Grund, nicht zu schreiben. Der Text erscheint so in der Karte."""


def karte_adresse() -> str:
    """Die Adresse der Karte, mit der Version als Anhang - wie bei den Kachelgrafiken."""
    return f"{URL_OBERFLAECHE}/{KARTE_ZEITPROGRAMM}?v={VERSION}"


@callback
def async_karte_anmelden(hass: HomeAssistant) -> None:
    """Meldet die Websocket-Befehle an und lässt jedes Dashboard die Karte laden."""
    websocket_api.async_register_command(hass, _ws_zeitprogramme)
    websocket_api.async_register_command(hass, _ws_zeitprogramm_setzen)
    if "frontend" in hass.config.components:
        add_extra_js_url(hass, karte_adresse())


async def bestand_lesen(coordinator, programm: str) -> dict[tuple[str, int], Zeitfenster]:
    """Alle Zeitfenster der Woche, frisch von der Anlage."""
    defs = coordinator.zeitprogramm_defs[programm]
    fenster = list(defs)
    gelesen = await asyncio.gather(
        *(coordinator.client.async_get_zeitfenster(defs[f]["uri"]) for f in fenster)
    )
    return dict(zip(fenster, gelesen))


async def absenkung_lesen(coordinator, programm: str) -> dict[str, float | None] | None:
    """Je Tag der Wert außerhalb der Zeitfenster in °C - None, wenn er sich nicht einstellen lässt.

    Ein Tag, der gerade nicht antwortet, steht auf None; deshalb bleibt
    das ganze Programm nicht unlesbar.
    """
    defs = coordinator.zeitprogramm_absenkung.get(programm)
    if defs is None:
        return None
    gelesen = await asyncio.gather(
        *(coordinator.client.async_get_value(defs[tag]["uri"]) for tag in defs),
        return_exceptions=True,
    )
    return {
        tag: None
        if isinstance(wert, Exception) or wert.value is None
        else round(wert.value, 1)
        for tag, wert in zip(defs, gelesen)
    }


def temperaturgrenzen(defs: dict) -> tuple[float, float]:
    """In diesem Bereich nimmt die Karte eine Temperatur an.

    Die Grenzen des Programms - bei Warmwasser WARMWASSER_GRENZEN, sonst
    die des Thermostats -, enger, wenn die Anlage für einen Wert engere
    meldet.
    """
    untere, obere = next(
        (info["grenzen"] for info in defs.values() if info.get("grenzen")),
        THERMOSTAT_SOLL_GRENZEN,
    )
    for info in defs.values():
        if info.get("min_roh") is not None:
            untere = max(untere, info["min_roh"] / info["skala"])
        if info.get("max_roh") is not None:
            obere = min(obere, info["max_roh"] / info["skala"])
    return untere, obere


OHNE_TEMPERATUR = ("puffer", "zirkulation")
"""Bei diesen Zeitprogrammen steuern die Zeiten nur, ob geladen wird bzw. die Pumpe läuft."""


async def obergrenze_lesen(coordinator, programm: str) -> float | None:
    """Bei einem Warmwasserspeicher "Warmwasserspeicher max." in °C, frisch von der Anlage.

    None, wenn es den Wert nicht gibt oder er gerade nicht lesbar ist - dann
    gelten nur die übrigen Grenzen. Liegt er nicht über der unteren Grenze,
    etwa 0 bei einem nicht eingestellten Speicher, wird er ebenso übergangen;
    sonst würde jede Temperatur auf ihn gesetzt.
    """
    uri = coordinator.zeitprogramm_maximum_uri(programm)
    if uri is None:
        return None
    try:
        wert = await coordinator.client.async_get_value(uri)
    except ETAApiError:
        return None
    return wert.value


def kopf(eintrag, programm: str, obergrenze: float | None = None) -> dict[str, Any]:
    """Was die Karte über ein Zeitprogramm wissen muss, auch wenn es nicht lesbar ist.

    obergrenze: "Warmwasserspeicher max." - liegt sie unter den übrigen
    Grenzen, gilt sie, und die Karte nennt sie beim Fehlerhinweis.
    """
    coordinator = eintrag.runtime_data
    defs = coordinator.zeitprogramm_defs[programm]
    absenk_defs = coordinator.zeitprogramm_absenkung.get(programm)
    abgleich = coordinator.zeitplan_abgleiche.get(programm)
    art = coordinator.zeitprogramm_art(programm)
    untere, obere = temperaturgrenzen(defs)
    grund = None
    if obergrenze is not None and untere < obergrenze < obere:
        obere = round(obergrenze, 1)
        grund = WARMWASSER_MAXIMUM
    absenk_untere, absenk_obere = temperaturgrenzen(absenk_defs or {})
    return {
        "eintrag": eintrag.entry_id,
        "anlage": eintrag.title,
        "programm": programm,
        "name": coordinator.zeitprogramm_name(programm),
        "art": art,
        "mit_temperatur": art not in OHNE_TEMPERATUR
        and all(info["mit_wert"] for info in defs.values()),
        "hinweise": (
            {
                "verbruehschutz": WARMWASSER_VERBRUEHSCHUTZ,
                "regelung": FWM_REGELUNG if coordinator.zeitprogramm_fwm(programm) else None,
            }
            if art == "warmwasser"
            else None
        ),
        "temperatur_min": untere,
        "temperatur_max": obere,
        "temperatur_max_grund": grund,
        "temperatur_vorgabe": _vorgabe(defs),
        "mit_absenkung": absenk_defs is not None,
        "absenkung_min": absenk_untere,
        "absenkung_max": absenk_obere,
        "zeitplan": abgleich.entity_id if abgleich is not None else None,
    }


def _vorgabe(defs: dict) -> float | None:
    """Der Werkswert der Anlage für die Temperatur eines Fensters, in °C."""
    info = next(iter(defs.values()))
    if info.get("vorgabe_roh") is None or not info.get("mit_wert"):
        return None
    return round(info["vorgabe_roh"] / info["skala"], 1)


def programm_daten(
    eintrag,
    programm: str,
    bestand: dict[tuple[str, int], Zeitfenster],
    absenkung: dict[str, float | None] | None,
    obergrenze: float | None = None,
) -> dict:
    """Das Zeitprogramm für die Karte: je Tag die belegten Fenster, nach Beginn sortiert.

    Beginn und Ende in Viertelstunden ab Mitternacht, die Temperatur in °C
    oder None. Dazu je Tag der Wert außerhalb der Zeitfenster, falls er
    sich einstellen lässt.
    """
    angaben = kopf(eintrag, programm, obergrenze)
    defs = eintrag.runtime_data.zeitprogramm_defs[programm]
    tage = {}
    for tag in WOCHENTAGE:
        belegt = []
        for nummer in range(1, ZEITFENSTER_JE_TAG + 1):
            fenster = bestand[(tag, nummer)]
            if fenster.leer:
                continue
            temperatur = None
            if angaben["mit_temperatur"] and fenster.wert is not None:
                temperatur = round(fenster.wert / defs[(tag, nummer)]["skala"], 1)
            belegt.append(
                {"beginn": fenster.beginn, "ende": fenster.ende, "temperatur": temperatur}
            )
        tage[tag] = sorted(belegt, key=lambda f: f["beginn"])
    return {**angaben, "tage": tage, "absenkung": absenkung, "fehler": None}


def _absenk_roh(grad: float, info: dict, bisher: float | None) -> int:
    """Der Wert außerhalb der Zeitfenster als Rohwert, in den Grenzen der Karte.

    Wie bei den Fenstern: Ist es der Wert, der schon dasteht, bleibt er,
    auch außerhalb der Grenzen.
    """
    gewuenscht = round(grad * info["skala"])
    if bisher is not None and gewuenscht == round(bisher * info["skala"]):
        return gewuenscht
    untere, obere = temperaturgrenzen({"wert": info})
    return round(min(max(grad, untere), obere) * info["skala"])


def bloecke_pruefen(fenster: list[dict]) -> list[Block]:
    """Die Fenster aus der Karte als Blöcke, nach Beginn sortiert.

    Jedes muss nach seinem Beginn enden, und keine zwei dürfen sich
    überschneiden.
    """
    bloecke = sorted(
        ((f["beginn"], f["ende"], f.get("temperatur")) for f in fenster),
        key=lambda block: block[:2],
    )
    if any(ende <= beginn for beginn, ende, _ in bloecke):
        raise ZeitprogrammFehler("Ein Zeitfenster endet nicht nach seinem Beginn.")
    if any(nachher[0] < vorher[1] for vorher, nachher in zip(bloecke, bloecke[1:])):
        raise ZeitprogrammFehler("Zeitfenster dürfen sich nicht überschneiden.")
    return bloecke


async def zeitprogramm_setzen(
    eintrag,
    programm: str,
    tage: list[str],
    fenster: list[dict],
    absenkung: float | None = None,
) -> dict:
    """Schreibt dieselben Fenster an jeden der Tage und gibt das neue Programm zurück.

    Eine Temperatur von None heißt: wie beim Zeitplan-Abgleich - ein
    belegtes Fenster behält seine, ein neu belegtes übernimmt die des
    ersten belegten Fensters der Woche. absenkung ist der Wert außerhalb
    der Zeitfenster für diese Tage, None lässt ihn, wie er ist.
    """
    coordinator = eintrag.runtime_data
    defs = coordinator.zeitprogramm_defs.get(programm)
    if defs is None:
        raise ZeitprogrammFehler("Dieses Zeitprogramm lässt sich nicht beschreiben.")
    absenk_defs = coordinator.zeitprogramm_absenkung.get(programm)
    if absenkung is not None and absenk_defs is None:
        raise ZeitprogrammFehler(
            "Den Wert außerhalb der Zeitfenster meldet die Heizung nicht als einstellbar."
        )
    abgleich = coordinator.zeitplan_abgleiche.get(programm)
    if abgleich is not None:
        raise ZeitprogrammFehler(
            f"Das Zeitprogramm folgt dem Zeitplan {abgleich.entity_id}. "
            "Änderungen bitte dort vornehmen."
        )
    if coordinator.zeitprogramm_art(programm) in OHNE_TEMPERATUR:
        fenster = [{**f, "temperatur": None} for f in fenster]
    bloecke = bloecke_pruefen(fenster)
    nummern = range(1, ZEITFENSTER_JE_TAG + 1)

    async with coordinator.zeitprogramm_sperre:
        bestand = await bestand_lesen(coordinator, programm)
        absenk_bestand = await absenkung_lesen(coordinator, programm)
        obergrenze = await obergrenze_lesen(coordinator, programm)
        if obergrenze is not None and obergrenze > temperaturgrenzen(defs)[0]:
            defs = {
                fenster: {**info, "grenzen": (info["grenzen"][0], min(info["grenzen"][1], obergrenze))}
                for fenster, info in defs.items()
            }
        ersatz = ersatztemperatur(bestand)
        absenk_neu: dict[str, int] = {}
        if absenkung is not None:
            for tag in WOCHENTAGE:
                if tag not in tage:
                    continue
                alt = absenk_bestand[tag]
                roh = _absenk_roh(absenkung, absenk_defs[tag], alt)
                if alt is None or round(alt * absenk_defs[tag]["skala"]) != roh:
                    absenk_neu[tag] = roh
        zu_schreiben: dict[tuple[str, int], Zeitfenster] = {}
        for tag in WOCHENTAGE:
            if tag not in tage:
                continue
            neu = tagesfenster(
                bloecke,
                [bestand[(tag, n)] for n in nummern],
                [defs[(tag, n)] for n in nummern],
                ersatz,
            )
            for nummer, neues in zip(nummern, neu):
                if not neues.gleich(bestand[(tag, nummer)]):
                    zu_schreiben[(tag, nummer)] = neues

        for (tag, nummer), neues in zu_schreiben.items():
            await coordinator.client.async_set_zeitfenster(defs[(tag, nummer)]["uri"], neues)
            _LOGGER.info(
                "ETA: %s %s Zeitfenster %d: %s -> %s (Dashboard-Karte)",
                programm,
                WOCHENTAGE[tag],
                nummer,
                als_text(bestand[(tag, nummer)], defs[(tag, nummer)]["skala"]),
                als_text(neues, defs[(tag, nummer)]["skala"]),
            )
        for tag, roh in absenk_neu.items():
            await coordinator.client.async_set_value(absenk_defs[tag]["uri"], str(roh))
            _LOGGER.info(
                "ETA: %s %s Wert außerhalb der Zeitfenster: %s -> %s (Dashboard-Karte)",
                programm,
                WOCHENTAGE[tag],
                absenk_bestand[tag],
                roh / absenk_defs[tag]["skala"],
            )
        if not zu_schreiben and not absenk_neu:
            return programm_daten(eintrag, programm, bestand, absenk_bestand, obergrenze)
        try:
            bestand = await bestand_lesen(coordinator, programm)
        except ETAApiError as err:
            await coordinator.async_request_refresh()
            raise ZeitprogrammFehler(
                "Gespeichert, aber die Heizung hat zum Nachlesen nicht geantwortet "
                f"({err}). Bitte neu lesen."
            ) from err
        absenk_bestand = await absenkung_lesen(coordinator, programm)

    await coordinator.async_request_refresh()
    abweichend = [
        f"{WOCHENTAGE[tag]} {nummer}"
        for (tag, nummer), neues in zu_schreiben.items()
        if not neues.gleich(bestand[(tag, nummer)])
    ] + [
        f"{WOCHENTAGE[tag]} außerhalb"
        for tag, roh in absenk_neu.items()
        if absenk_bestand[tag] is not None
        and round(absenk_bestand[tag] * absenk_defs[tag]["skala"]) != roh
    ]
    if abweichend:
        raise ZeitprogrammFehler(
            "Die Heizung meldet nach dem Speichern andere Werte "
            f"({', '.join(abweichend)}). Bitte am Display nachsehen."
        )
    return programm_daten(eintrag, programm, bestand, absenk_bestand, obergrenze)


def _eintrag(hass: HomeAssistant, entry_id: str):
    for eintrag in hass.config_entries.async_loaded_entries(DOMAIN):
        if eintrag.entry_id == entry_id:
            return eintrag
    return None


def gewuenscht(coordinator, programm: str, arten: list[str] | None, heizkreis: str | None) -> bool:
    """Zeigt die Karte dieses Programm? Wie ihre Auswahl: Arten, bei Heizzeiten ein Heizkreis.

    Ohne Angaben alle - so fragen die Einstellungen der Karte.
    """
    art = coordinator.zeitprogramm_art(programm)
    if arten and art not in arten:
        return False
    gesucht = (heizkreis or "").casefold()
    if art != "heizzeiten" or not gesucht:
        return True
    return gesucht in (programm.casefold(), coordinator.zeitprogramm_name(programm).casefold())


async def _programm_lesen(eintrag, programm: str) -> dict:
    """Ein Programm für die Karte, frisch von der Anlage - oder mit dem Fehler, warum nicht."""
    coordinator = eintrag.runtime_data
    try:
        bestand, absenkung, obergrenze = await asyncio.gather(
            bestand_lesen(coordinator, programm),
            absenkung_lesen(coordinator, programm),
            obergrenze_lesen(coordinator, programm),
        )
    except ETAApiError as err:
        return {**kopf(eintrag, programm), "tage": None, "absenkung": None, "fehler": str(err)}
    return programm_daten(eintrag, programm, bestand, absenkung, obergrenze)


@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{DOMAIN}/zeitprogramme",
        vol.Optional("ohne_zeiten", default=False): bool,
        vol.Optional("arten"): [str],
        vol.Optional("heizkreis"): vol.Any(None, str),
    }
)
@websocket_api.async_response
async def _ws_zeitprogramme(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict
) -> None:
    """Die beschreibbaren Zeitprogramme aller geladenen Anlagen.

    Haben beim Start nicht alle Zeitfenster geantwortet, wird vorher
    nachgeprüft - so erscheint das Programm ohne Neustart. ohne_zeiten:
    nur, welche Programme es gibt, ohne die Heizung nach ihren Zeiten zu
    fragen - für die Einstellungen der Karte. arten und heizkreis: nur,
    was die Karte zeigt, siehe gewuenscht. Jedes Programm kostet rund 30
    Anfragen, und die Steuerung beantwortet sie nacheinander.
    """
    auswahl = []
    for eintrag in hass.config_entries.async_loaded_entries(DOMAIN):
        await eintrag.runtime_data.zeitprogramme_nachpruefen()
        auswahl += [
            (eintrag, programm)
            for programm in list(eintrag.runtime_data.zeitprogramm_defs)
            if gewuenscht(eintrag.runtime_data, programm, msg.get("arten"), msg.get("heizkreis"))
        ]
    if msg.get("ohne_zeiten"):
        programme = [kopf(eintrag, programm) for eintrag, programm in auswahl]
    else:
        programme = list(
            await asyncio.gather(*(_programm_lesen(eintrag, programm) for eintrag, programm in auswahl))
        )
    connection.send_result(msg["id"], {"programme": programme})


@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{DOMAIN}/zeitprogramm_setzen",
        vol.Required("eintrag"): str,
        vol.Required("programm"): str,
        vol.Required("tage"): vol.All([vol.In(list(WOCHENTAGE))], vol.Length(min=1)),
        vol.Required("fenster"): vol.All(
            [
                {
                    vol.Required("beginn"): vol.All(int, vol.Range(min=0, max=96)),
                    vol.Required("ende"): vol.All(int, vol.Range(min=0, max=96)),
                    vol.Optional("temperatur"): TEMPERATUR,
                }
            ],
            vol.Length(max=ZEITFENSTER_JE_TAG),
        ),
        vol.Optional("absenkung"): TEMPERATUR,
    }
)
@websocket_api.async_response
async def _ws_zeitprogramm_setzen(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict
) -> None:
    """Schreibt die Fenster eines Tages, auf Wunsch an mehrere Tage."""
    eintrag = _eintrag(hass, msg["eintrag"])
    if eintrag is None:
        connection.send_error(
            msg["id"], "nicht_geladen", "Diese ETA-Heizung ist gerade nicht geladen."
        )
        return
    await eintrag.runtime_data.zeitprogramme_bereit()
    try:
        ergebnis = await zeitprogramm_setzen(
            eintrag, msg["programm"], msg["tage"], msg["fenster"], msg.get("absenkung")
        )
    except ZeitprogrammFehler as err:
        connection.send_error(msg["id"], "abgelehnt", str(err))
        return
    except ETAApiError as err:
        connection.send_error(
            msg["id"], "anlage", f"Die Heizung hat nicht geantwortet: {err}"
        )
        return
    connection.send_result(msg["id"], ergebnis)
