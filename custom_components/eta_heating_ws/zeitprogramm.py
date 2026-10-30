"""Das Zeitprogramm eines Heizkreises direkt bearbeiten - für die Dashboard-Karte.

Die Karte "ETA Zeitprogramm" (oberflaeche/eta-zeitprogramm-karte.js) zeigt
die Heizzeiten der Woche als Balken und lässt sie ändern. Home Assistant
lädt sie in jedem Dashboard von selbst; im Kartenwähler steht sie unter
"ETA Zeitprogramm". Sie spricht über zwei Websocket-Befehle mit der
Integration:

- eta_heating_ws/zeitprogramme liest die Zeitfenster aller Heizkreise mit
  beschreibbarem Zeitprogramm frisch von der Anlage, dazu je Tag den "Wert
  außerhalb der Zeitfenster" - die Raumtemperatur in der Absenkzeit,
- eta_heating_ws/zeitprogramm_setzen schreibt Fenster und Absenktemperatur
  für einen oder mehrere Tage, liest zur Kontrolle nach und gibt das
  Programm zurück.

Geschrieben wird nur, was sich ändert, mit denselben Regeln wie beim
Zeitplan-Abgleich (zeitplan.tagesfenster). Folgt ein Heizkreis einem
Zeitplan-Helfer, führt der: Die Karte zeigt das Programm dann nur an, und
Schreiben wird abgelehnt - sonst überschriebe der nächste Abgleich die
Änderung wieder.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any

import voluptuous as vol
from homeassistant.components import websocket_api
from homeassistant.components.frontend import add_extra_js_url
from homeassistant.core import HomeAssistant, callback

from .api import ETAApiError, Zeitfenster
from .const import (
    DOMAIN,
    KARTE_ZEITPROGRAMM,
    THERMOSTAT_SOLL_GRENZEN,
    URL_OBERFLAECHE,
    WOCHENTAGE,
    ZEITFENSTER_JE_TAG,
)
from .karte import VERSION
from .zeitplan import Block, als_text, ersatztemperatur, tagesfenster

_LOGGER = logging.getLogger(__name__)

OBERFLAECHE = Path(__file__).parent / "oberflaeche"
"""Der Ordner mit den Dashboard-Karten, ausgeliefert unter URL_OBERFLAECHE."""


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


async def bestand_lesen(coordinator, heizkreis: str) -> dict[tuple[str, int], Zeitfenster]:
    """Alle Zeitfenster der Woche, frisch von der Anlage."""
    defs = coordinator.zeitprogramm_defs[heizkreis]
    fenster = list(defs)
    gelesen = await asyncio.gather(
        *(coordinator.client.async_get_zeitfenster(defs[f]["uri"]) for f in fenster)
    )
    return dict(zip(fenster, gelesen))


async def absenkung_lesen(coordinator, heizkreis: str) -> dict[str, float | None] | None:
    """Je Tag der Wert außerhalb der Zeitfenster in °C - None, wenn er sich nicht einstellen lässt."""
    defs = coordinator.zeitprogramm_absenkung.get(heizkreis)
    if defs is None:
        return None
    gelesen = await asyncio.gather(
        *(coordinator.client.async_get_value(defs[tag]["uri"]) for tag in defs)
    )
    return {
        tag: None if wert.value is None else round(wert.value, 1)
        for tag, wert in zip(defs, gelesen)
    }


def temperaturgrenzen(defs: dict) -> tuple[float, float]:
    """In diesem Bereich nimmt die Karte eine Temperatur an.

    Die Grenzen des Thermostats, enger, wenn die Anlage für einen Wert
    engere meldet.
    """
    untere, obere = THERMOSTAT_SOLL_GRENZEN
    for info in defs.values():
        if info.get("min_roh") is not None:
            untere = max(untere, info["min_roh"] / info["skala"])
        if info.get("max_roh") is not None:
            obere = min(obere, info["max_roh"] / info["skala"])
    return untere, obere


def kopf(eintrag, heizkreis: str) -> dict[str, Any]:
    """Was die Karte über einen Heizkreis wissen muss, auch wenn er nicht lesbar ist."""
    coordinator = eintrag.runtime_data
    defs = coordinator.zeitprogramm_defs[heizkreis]
    absenk_defs = coordinator.zeitprogramm_absenkung.get(heizkreis)
    abgleich = coordinator.zeitplan_abgleiche.get(heizkreis)
    untere, obere = temperaturgrenzen(defs)
    absenk_untere, absenk_obere = temperaturgrenzen(absenk_defs or {})
    return {
        "eintrag": eintrag.entry_id,
        "anlage": eintrag.title,
        "heizkreis": heizkreis,
        "name": coordinator.funktionsblock(heizkreis),
        "mit_temperatur": all(info["mit_wert"] for info in defs.values()),
        "temperatur_min": untere,
        "temperatur_max": obere,
        "mit_absenkung": absenk_defs is not None,
        "absenkung_min": absenk_untere,
        "absenkung_max": absenk_obere,
        "zeitplan": abgleich.entity_id if abgleich is not None else None,
    }


def programm(
    eintrag,
    heizkreis: str,
    bestand: dict[tuple[str, int], Zeitfenster],
    absenkung: dict[str, float | None] | None,
) -> dict:
    """Das Zeitprogramm für die Karte: je Tag die belegten Fenster, nach Beginn sortiert.

    Beginn und Ende in Viertelstunden ab Mitternacht, die Temperatur in °C
    oder None. Dazu je Tag der Wert außerhalb der Zeitfenster, falls er
    sich einstellen lässt.
    """
    angaben = kopf(eintrag, heizkreis)
    defs = eintrag.runtime_data.zeitprogramm_defs[heizkreis]
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


def _absenk_roh(grad: float, info: dict) -> int:
    """Der Wert außerhalb der Zeitfenster als Rohwert, in den Grenzen der Karte."""
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
    heizkreis: str,
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
    defs = coordinator.zeitprogramm_defs.get(heizkreis)
    if defs is None:
        raise ZeitprogrammFehler(
            "Für diesen Heizkreis gibt es kein beschreibbares Zeitprogramm."
        )
    absenk_defs = coordinator.zeitprogramm_absenkung.get(heizkreis)
    if absenkung is not None and absenk_defs is None:
        raise ZeitprogrammFehler(
            "Den Wert außerhalb der Zeitfenster meldet die Heizung nicht als einstellbar."
        )
    abgleich = coordinator.zeitplan_abgleiche.get(heizkreis)
    if abgleich is not None:
        raise ZeitprogrammFehler(
            f"Das Zeitprogramm folgt dem Zeitplan {abgleich.entity_id}. "
            "Änderungen bitte dort vornehmen."
        )
    bloecke = bloecke_pruefen(fenster)
    nummern = range(1, ZEITFENSTER_JE_TAG + 1)

    async with coordinator.zeitprogramm_sperre:
        bestand = await bestand_lesen(coordinator, heizkreis)
        absenk_bestand = await absenkung_lesen(coordinator, heizkreis)
        ersatz = ersatztemperatur(bestand)
        absenk_neu: dict[str, int] = {}
        if absenkung is not None:
            for tag in WOCHENTAGE:
                if tag not in tage:
                    continue
                roh = _absenk_roh(absenkung, absenk_defs[tag])
                alt = absenk_bestand[tag]
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
                heizkreis,
                WOCHENTAGE[tag],
                nummer,
                als_text(bestand[(tag, nummer)], defs[(tag, nummer)]["skala"]),
                als_text(neues, defs[(tag, nummer)]["skala"]),
            )
        for tag, roh in absenk_neu.items():
            await coordinator.client.async_set_value(absenk_defs[tag]["uri"], str(roh))
            _LOGGER.info(
                "ETA: %s %s Wert außerhalb der Zeitfenster: %s -> %s (Dashboard-Karte)",
                heizkreis,
                WOCHENTAGE[tag],
                absenk_bestand[tag],
                roh / absenk_defs[tag]["skala"],
            )
        if not zu_schreiben and not absenk_neu:
            return programm(eintrag, heizkreis, bestand, absenk_bestand)
        bestand = await bestand_lesen(coordinator, heizkreis)
        absenk_bestand = await absenkung_lesen(coordinator, heizkreis)

    await coordinator.async_request_refresh()
    abweichend = [
        f"{WOCHENTAGE[tag]} {nummer}"
        for (tag, nummer), neues in zu_schreiben.items()
        if not neues.gleich(bestand[(tag, nummer)])
    ] + [
        f"{WOCHENTAGE[tag]} außerhalb"
        for tag, roh in absenk_neu.items()
        if absenk_bestand[tag] is None
        or round(absenk_bestand[tag] * absenk_defs[tag]["skala"]) != roh
    ]
    if abweichend:
        raise ZeitprogrammFehler(
            "Die Heizung meldet nach dem Speichern andere Werte "
            f"({', '.join(abweichend)}). Bitte am Display nachsehen."
        )
    return programm(eintrag, heizkreis, bestand, absenk_bestand)


def _eintrag(hass: HomeAssistant, entry_id: str):
    for eintrag in hass.config_entries.async_loaded_entries(DOMAIN):
        if eintrag.entry_id == entry_id:
            return eintrag
    return None


@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/zeitprogramme"})
@websocket_api.async_response
async def _ws_zeitprogramme(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict
) -> None:
    """Die Zeitprogramme aller geladenen Anlagen, je Heizkreis eines.

    Haben beim Start nicht alle Zeitfenster geantwortet, wird vorher
    nachgeprüft - so erscheint das Programm ohne Neustart.
    """
    heizkreise = []
    for eintrag in hass.config_entries.async_loaded_entries(DOMAIN):
        await eintrag.runtime_data.zeitprogramme_nachpruefen()
        for heizkreis in eintrag.runtime_data.zeitprogramm_defs:
            try:
                bestand = await bestand_lesen(eintrag.runtime_data, heizkreis)
                absenkung = await absenkung_lesen(eintrag.runtime_data, heizkreis)
            except ETAApiError as err:
                heizkreise.append(
                    {**kopf(eintrag, heizkreis), "tage": None, "absenkung": None, "fehler": str(err)}
                )
                continue
            heizkreise.append(programm(eintrag, heizkreis, bestand, absenkung))
    connection.send_result(msg["id"], {"heizkreise": heizkreise})


@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{DOMAIN}/zeitprogramm_setzen",
        vol.Required("eintrag"): str,
        vol.Required("heizkreis"): str,
        vol.Required("tage"): vol.All([vol.In(list(WOCHENTAGE))], vol.Length(min=1)),
        vol.Required("fenster"): vol.All(
            [
                {
                    vol.Required("beginn"): vol.All(int, vol.Range(min=0, max=96)),
                    vol.Required("ende"): vol.All(int, vol.Range(min=0, max=96)),
                    vol.Optional("temperatur"): vol.Any(None, vol.Coerce(float)),
                }
            ],
            vol.Length(max=ZEITFENSTER_JE_TAG),
        ),
        vol.Optional("absenkung"): vol.Any(None, vol.Coerce(float)),
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
    try:
        ergebnis = await zeitprogramm_setzen(
            eintrag, msg["heizkreis"], msg["tage"], msg["fenster"], msg.get("absenkung")
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
