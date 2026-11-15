"""Das Bild von Brenner und Fremdwärme wählt der Nutzer selbst.

Was hinter den beiden Funktionsblöcken steht, verrät die Anlage nicht:
Der Brenner kann eine Gastherme oder ein Ölkessel sein, die Fremdwärme
ein Kaminofen oder etwas ganz anderes. Je Komponente gibt es deshalb
eine Auswahl am Gerät - Gas, Öl, Ofen, allgemein -, die beide
Dashboard-Karten abfragen. An der Anlage ändert sie nichts.

Ein Bild für Photovoltaik gibt es nicht: Diese Art der Fremdwärme hat
keinen Temperaturfühler, ihre Werte liest die Integration noch nicht.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from eta_heating_ws import GRAFIKEN, entitaet_vorgesehen
from eta_heating_ws import select as select_platform
from eta_heating_ws.const import BILD_AUSWAHLEN, COMPONENTS
from eta_heating_ws.karte import (
    BRENNER_BILD,
    ERZEUGER_BILDER,
    ERZEUGER_BILDER_VORBEREITET,
    ERZEUGER_VORGABE,
    FREMDWAERME_BILD,
    responsive_karte,
)

from .conftest import UEBERSETZUNGEN
from .test_sensors import setup_integration

ARTEN = ["gas", "oel", "ofen", "allgemein"]


async def auswahlen(hass, entry, komponenten, schreibzugriff=False):
    entry.data["components"] = ["kessel", "puffer", *komponenten]
    entry.data["enable_switches"] = schreibzugriff
    await setup_integration(hass, entry)
    gesammelt: list = []
    await select_platform.async_setup_entry(hass, entry, gesammelt.extend)
    bilder = {e.translation_key: e for e in gesammelt if isinstance(e, select_platform.ETABildAuswahl)}
    for auswahl in bilder.values():
        auswahl.async_write_ha_state = lambda: None
    return bilder


def test_vier_bilder_stehen_zur_wahl():
    assert list(ERZEUGER_BILDER) == ARTEN
    assert ERZEUGER_VORGABE == {"brenner": "gas", "fremdwaerme": "ofen"}


@pytest.mark.parametrize("art", ARTEN)
def test_jedes_bild_hat_kachel_bewegung_und_standbild(art):
    grundbild, bewegt = ERZEUGER_BILDER[art]
    for datei in (f"{grundbild}.png", f"{bewegt}.webp", f"{bewegt}.png"):
        assert (GRAFIKEN / datei).is_file(), datei


def test_bild_der_pv_anlage_ist_fertig_aber_noch_nicht_waehlbar():
    """Es wartet, bis die Integration Fremdwärme aus Photovoltaik liest."""
    assert set(ERZEUGER_BILDER_VORBEREITET) == {"pv"}
    assert not set(ERZEUGER_BILDER_VORBEREITET) & set(ERZEUGER_BILDER)
    grundbild, bewegt = ERZEUGER_BILDER_VORBEREITET["pv"]
    for datei in (f"{grundbild}.png", f"{bewegt}.webp", f"{bewegt}.png"):
        assert (GRAFIKEN / datei).is_file(), datei


def test_vorgabe_ist_das_bisherige_bild_der_komponente():
    """Wer nichts wählt, sieht dasselbe wie vor der Auswahl."""
    for komponente, art in ERZEUGER_VORGABE.items():
        assert ERZEUGER_BILDER[art][0] == COMPONENTS[komponente]["image"]


async def test_auswahl_gibt_es_je_gewaehlter_komponente_auch_ohne_schreibzugriff(hass, entry):
    bilder = await auswahlen(hass, entry, ["brenner", "fremdwaerme"])

    assert set(bilder) == {"brenner_bild", "fremdwaerme_bild"}
    brenner = bilder["brenner_bild"]
    assert brenner.options == ARTEN
    assert brenner.current_option == "gas"
    assert bilder["fremdwaerme_bild"].current_option == "ofen"
    assert brenner.entity_category == "config"
    assert brenner.entity_id == BRENNER_BILD
    assert bilder["fremdwaerme_bild"].entity_id == FREMDWAERME_BILD
    assert brenner.unique_id == f"eta_static_{entry.entry_id}_brenner_bild"


async def test_ohne_brenner_und_fremdwaerme_keine_auswahl(hass, entry):
    assert await auswahlen(hass, entry, []) == {}


async def test_waehlen_schreibt_nichts_an_die_anlage(hass, entry):
    bilder = await auswahlen(hass, entry, ["brenner"], schreibzugriff=True)
    hass.session.gesetzte_werte.clear()

    await bilder["brenner_bild"].async_select_option("oel")

    assert bilder["brenner_bild"].current_option == "oel"
    assert hass.session.gesetzte_werte == []


@pytest.mark.parametrize(
    "gespeichert, erwartet", [("oel", "oel"), (None, "ofen"), ("unknown", "ofen"), ("pv", "ofen")]
)
async def test_nach_dem_neustart_gilt_die_letzte_wahl(hass, entry, gespeichert, erwartet):
    bilder = await auswahlen(hass, entry, ["fremdwaerme"])
    auswahl = bilder["fremdwaerme_bild"]

    async def letzter_zustand():
        return None if gespeichert is None else SimpleNamespace(state=gespeichert)

    auswahl.async_get_last_state = letzter_zustand
    await auswahl.async_added_to_hass()

    assert auswahl.current_option == erwartet


def test_auswahl_bleibt_solange_die_komponente_gewaehlt_ist():
    """Danach räumt die Integration auf, wenn die Komponente abgewählt wird."""
    assert entitaet_vorgesehen("brenner_bild", ["kessel", "brenner"], False, True) is True
    assert entitaet_vorgesehen("brenner_bild", ["kessel"], True, True) is False
    assert entitaet_vorgesehen("fremdwaerme_bild", ["kessel", "fremdwaerme"], False, True) is True
    assert entitaet_vorgesehen("fremdwaerme_bild", ["kessel", "brenner"], False, True) is False


@pytest.mark.parametrize("sprache", ["de", "en"])
def test_jede_wahl_hat_einen_namen_in_beiden_sprachen(sprache):
    texte = json.loads((UEBERSETZUNGEN / f"{sprache}.json").read_text(encoding="utf-8"))
    for key in BILD_AUSWAHLEN:
        eintrag = texte["entity"]["select"][key]
        assert eintrag["name"]
        assert set(eintrag["state"]) == set(ARTEN), key


def kacheln_mit(bildname):
    """Alle Kacheln der Bildkarte, deren Grundbild so heißt - eine je Bildschirmbreite."""
    gefunden = []

    def gehen(knoten):
        if isinstance(knoten, dict):
            if knoten.get("type") == "picture-elements" and f"/{bildname}.png" in knoten.get("image", ""):
                gefunden.append(knoten)
            for wert in knoten.values():
                gehen(wert)
        elif isinstance(knoten, list):
            for wert in knoten:
                gehen(wert)

    gehen(responsive_karte())
    return gefunden


@pytest.mark.parametrize(
    "grundbild, auswahl", [("brenner", BRENNER_BILD), ("fremdwaerme", FREMDWAERME_BILD)]
)
def test_bildkarte_wechselt_das_kachelbild_mit_der_auswahl(grundbild, auswahl):
    kacheln = kacheln_mit(grundbild)

    assert len(kacheln) == 3, "je Bildschirmbreite eine"
    for kachel in kacheln:
        assert kachel["entity"] == auswahl
        assert set(kachel["state_image"]) == set(ARTEN)
        for art, adresse in kachel["state_image"].items():
            assert f"/{ERZEUGER_BILDER[art][0]}.png" in adresse


def bewegte_auflagen(kachel):
    """Je bewegtem Bild die Bedingungen, unter denen es über der Kachel liegt."""
    auflagen = {}
    for element in kachel["elements"]:
        if element.get("type") != "conditional":
            continue
        bild = element["elements"][0]["image"].rsplit("/", 1)[1].split("?")[0]
        if bild.endswith(".webp"):
            auflagen.setdefault(bild, []).append(element["conditions"])
    return auflagen


def test_bildkarte_bewegt_nur_das_gewaehlte_bild_des_brenners():
    auflagen = bewegte_auflagen(kacheln_mit("brenner")[0])

    assert set(auflagen) == {f"{bewegt}.webp" for _, bewegt in ERZEUGER_BILDER.values()}
    [oel] = auflagen["erzeuger_oel_aktiv.webp"]
    assert {"condition": "state", "entity": BRENNER_BILD, "state": "oel"} in oel
    assert {
        "condition": "state",
        "entity": "sensor.eta_heizung_brenner_anforderung",
        "state": "Ein",
    } in oel
    [gas] = auflagen["brenner_aktiv.webp"]
    assert [b["state_not"] for b in gas if b["entity"] == BRENNER_BILD] == [
        "oel", "ofen", "allgemein"
    ], "die Vorgabe gilt auch, solange die Auswahl nichts Bekanntes meldet"


def test_bildkarte_bewegt_die_fremdwaerme_bei_heizen_und_uebertemperatur():
    auflagen = bewegte_auflagen(kacheln_mit("fremdwaerme")[0])

    for bild, bedingungen in auflagen.items():
        zustaende = sorted(
            b["state"]
            for einzeln in bedingungen
            for b in einzeln
            if b["entity"] == "sensor.eta_heizung_fremdwarme_zustand" and "state" in b
        )
        assert zustaende == ["Heizen", "Übertemperatur"], bild
