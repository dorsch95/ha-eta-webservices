"""Zeitplan aus Home Assistant ins Zeitprogramm eines Heizkreises."""

from __future__ import annotations

import json
import sys
from datetime import time

import pytest

from eta_heating_ws.api import Zeitfenster, zeitfenster_aus_text
from eta_heating_ws.const import WOCHENTAGE
from eta_heating_ws.zeitplan import (
    ZeitplanAbgleich,
    aenderungen,
    als_text,
    bloecke,
    viertelstunde,
)

from .test_sensors import setup_integration

HK = "/120/10101/12113/0"
TAGE = list(WOCHENTAGE)


def fenster_uri(tag: str, nummer: int) -> str:
    """Wie an der Zweitanlage: Montag 1081 mit 1082 bis 1084, jeder Tag vier weiter."""
    return f"{HK}/{1081 + 4 * TAGE.index(tag) + nummer}"


def mit_zeitprogramm(menu: str) -> str:
    """Heizkreis 1 mit seinen Heizzeiten: je Wochentag drei Zeitfenster."""
    tage = ""
    for tag, name in WOCHENTAGE.items():
        tag_uri = f"{HK}/{1081 + 4 * TAGE.index(tag)}"
        tage += f'<object uri="{tag_uri}" name="{name}">'
        tage += f'<object uri="{HK}/{1111 + TAGE.index(tag)}" name="Wert außerhalb der Zeitfenster"/>'
        for nummer in (1, 2, 3):
            tage += f'<object uri="{fenster_uri(tag, nummer)}" name="Zeitfenster {nummer}"/>'
        tage += "</object>"
    schaltzustand = f'<object uri="{HK}/1109" name="Schaltzustand"/>'
    assert schaltzustand in menu
    return menu.replace(schaltzustand, schaltzustand + tage)


def anlage_mit_fenstern(session, mit_wert=True) -> None:
    """Täglich 5:30 bis 22:30 bei 20 °C, die anderen beiden Fenster leer."""
    for tag in TAGE:
        session.zeitfenster[fenster_uri(tag, 1)] = (22, 90, 200 if mit_wert else None)
        session.zeitfenster[fenster_uri(tag, 2)] = (0, 0, 0 if mit_wert else None)
        session.zeitfenster[fenster_uri(tag, 3)] = (0, 0, 0 if mit_wert else None)


def plan(**tage) -> dict:
    """Ein Wochenplan in Viertelstunden; nicht genannte Tage wie Montag."""
    standard = tage.get("monday", [(22, 90, None)])
    return {tag: tage.get(tag, standard) for tag in TAGE}


async def aufbauen(hass, entry, menu_xml, mit_wert=True):
    hass.session.menu = mit_zeitprogramm(menu_xml)
    anlage_mit_fenstern(hass.session, mit_wert)
    coordinator, _ = await setup_integration(hass, entry)
    abgleich = ZeitplanAbgleich(hass, coordinator, "hk1", "schedule.heizen")
    return coordinator, abgleich


def mit_plan(abgleich, wochenplan) -> None:
    async def lesen():
        return wochenplan

    abgleich.plan_lesen = lesen


@pytest.mark.parametrize(
    ("text", "erwartet"),
    [
        ("05:30 - 22:30 20,0", Zeitfenster(22, 90, 200)),
        ("00:00 - 24:00 21,0", Zeitfenster(0, 96, 210)),
        ("00:00 - 24:00", Zeitfenster(0, 96, None)),
        ("00:00 - 00:00 0,0", Zeitfenster(0, 0, 0)),
        ("Aus", None),
    ],
)
def test_zeitfenster_aus_dem_text_der_anlage(text, erwartet):
    assert zeitfenster_aus_text(text, 10) == erwartet


def test_uhrzeiten_in_viertelstunden():
    assert viertelstunde(time(5, 30)) == 22
    assert viertelstunde(time(5, 37)) == 22
    assert viertelstunde(time(5, 38)) == 23
    assert viertelstunde(time.max) == 96, "24:00 im Zeitplan-Helfer"
    assert viertelstunde("22:30:00") == 90
    assert viertelstunde("24:00:00") == 96


def test_bloecke_werden_sortiert_gerundet_und_zusammengefasst():
    tag = [
        {"from": time(12, 0), "to": time(22, 30)},
        {"from": time(5, 30), "to": time(12, 0)},
        {"from": time(23, 0), "to": time(23, 5)},
    ]
    assert bloecke(tag) == [(22, 90, None)], "aneinander, gleiche Temperatur; 5 Minuten fallen weg"
    mit_temperatur = [
        {"from": time(5, 30), "to": time(12, 0), "data": {"temperatur": 21}},
        {"from": time(12, 0), "to": time(22, 30), "data": {"temperature": "19.5"}},
    ]
    assert bloecke(mit_temperatur) == [(22, 48, 21.0), (48, 90, 19.5)]


def test_gleicher_plan_schreibt_nichts():
    bestand, defs = _woche(Zeitfenster(22, 90, 200))
    zu_schreiben, zu_voll = aenderungen(plan(), bestand, defs)
    assert zu_schreiben == {}
    assert zu_voll == []


def test_ohne_temperatur_bleibt_die_der_anlage():
    """Für Heizkreise, an denen nur Tag und Absenkung zählen."""
    bestand, defs = _woche(Zeitfenster(22, 90, 200))
    zu_schreiben, _ = aenderungen(plan(saturday=[(28, 92, None)]), bestand, defs)
    assert zu_schreiben == {("saturday", 1): Zeitfenster(28, 92, 200)}


def test_temperatur_aus_dem_block_wird_geschrieben_und_begrenzt():
    bestand, defs = _woche(Zeitfenster(22, 90, 200))
    zu_schreiben, _ = aenderungen(
        plan(monday=[(22, 90, 21.0)], sunday=[(22, 90, 35.0)]), bestand, defs
    )
    assert zu_schreiben[("monday", 1)] == Zeitfenster(22, 90, 210)
    assert zu_schreiben[("sunday", 1)] == Zeitfenster(22, 90, 300), "höchstens 30 °C"


def test_neues_fenster_uebernimmt_die_temperatur_der_woche():
    bestand, defs = _woche(Zeitfenster(22, 90, 200))
    zu_schreiben, _ = aenderungen(plan(friday=[(22, 48, None), (60, 90, None)]), bestand, defs)
    assert zu_schreiben == {
        ("friday", 1): Zeitfenster(22, 48, 200),
        ("friday", 2): Zeitfenster(60, 90, 200),
    }


def test_weggefallener_block_leert_sein_fenster():
    bestand, defs = _woche(Zeitfenster(22, 90, 200), Zeitfenster(92, 96, 180))
    zu_schreiben, _ = aenderungen(plan(), bestand, defs)
    assert set(zu_schreiben) == {(tag, 2) for tag in TAGE}
    assert zu_schreiben[("monday", 2)] == Zeitfenster(0, 0, 180), "der Wert bleibt"


def test_tag_mit_vier_bloecken_wird_ausgelassen():
    bestand, defs = _woche(Zeitfenster(22, 90, 200))
    vier = [(20, 24, None), (28, 32, None), (36, 40, None), (44, 48, None)]
    zu_schreiben, zu_voll = aenderungen(plan(tuesday=vier), bestand, defs)
    assert zu_voll == ["tuesday"]
    assert zu_schreiben == {}


def test_fenster_ohne_temperatur():
    bestand, defs = _woche(Zeitfenster(22, 90, None), mit_wert=False)
    zu_schreiben, _ = aenderungen(plan(monday=[(24, 88, 21.0)]), bestand, defs)
    assert set(zu_schreiben.values()) == {Zeitfenster(24, 88, None)}


def test_fenster_als_text():
    assert als_text(Zeitfenster(22, 90, 200), 10) == "05:30 - 22:30 20,0"
    assert als_text(Zeitfenster(0, 96, None), 10) == "00:00 - 24:00"
    assert als_text(Zeitfenster(0, 0, 0), 10) == "-"


def _woche(erstes, zweites=None, mit_wert=True):
    leer = Zeitfenster(0, 0, 0 if mit_wert else None)
    bestand = {}
    for tag in TAGE:
        bestand[(tag, 1)] = erstes
        bestand[(tag, 2)] = zweites or leer
        bestand[(tag, 3)] = leer
    info = {"skala": 10.0, "mit_wert": mit_wert, "min_roh": 0.0, "max_roh": 800.0, "vorgabe_roh": 210.0}
    return bestand, {fenster: info for fenster in bestand}


async def test_zeitprogramm_nur_mit_schreibzugriff(hass, entry, menu_xml):
    coordinator, _ = await aufbauen(hass, entry, menu_xml)
    assert set(coordinator.zeitprogramm_defs) == {"hk1"}
    assert len(coordinator.zeitprogramm_defs["hk1"]) == 21
    assert coordinator.zeitprogramm_defs["hk1"][("monday", 1)]["mit_wert"] is True

    entry.data["enable_switches"] = False
    ohne, _ = await setup_integration(hass, entry)
    assert ohne.zeitprogramm_defs == {}


async def test_nicht_beschreibbar_bleibt_unangetastet(hass, entry, menu_xml):
    hass.session.zeitfenster_schreibbar = False
    hass.session.menu = mit_zeitprogramm(menu_xml)
    anlage_mit_fenstern(hass.session)
    coordinator, _ = await setup_integration(hass, entry)
    assert coordinator.zeitprogramm_defs == {}


async def test_abgleich_schreibt_nur_die_abweichung(hass, entry, menu_xml):
    _, abgleich = await aufbauen(hass, entry, menu_xml)
    mit_plan(abgleich, plan(saturday=[(28, 92, None)]))

    assert await abgleich.abgleichen() is True
    assert hass.session.gesetzte_zeitfenster == [
        (fenster_uri("saturday", 1), {"begin": "28", "end": "92", "value": "200"})
    ]
    assert hass.session.zeitfenster_text(fenster_uri("saturday", 1)) == "07:00 - 23:00 20,0"

    hass.session.gesetzte_zeitfenster.clear()
    assert await abgleich.abgleichen() is True
    assert hass.session.gesetzte_zeitfenster == [], "unveränderter Plan: nichts lesen, nichts schreiben"


async def test_ohne_temperatur_an_der_anlage(hass, entry, menu_xml):
    _, abgleich = await aufbauen(hass, entry, menu_xml, mit_wert=False)
    mit_plan(abgleich, plan(monday=[(24, 88, 21.0)]))

    assert await abgleich.abgleichen() is True
    assert {daten["begin"] for _, daten in hass.session.gesetzte_zeitfenster} == {"24"}
    assert all("value" not in daten for _, daten in hass.session.gesetzte_zeitfenster)
    assert len(hass.session.gesetzte_zeitfenster) == 7


async def test_leere_woche_wird_nicht_geschrieben(hass, entry, menu_xml):
    _, abgleich = await aufbauen(hass, entry, menu_xml)
    mit_plan(abgleich, {tag: [] for tag in TAGE})

    assert await abgleich.abgleichen() is False
    assert hass.session.gesetzte_zeitfenster == []


async def test_zu_voller_tag_meldet_sich(hass, entry, menu_xml, reparaturen):
    _, abgleich = await aufbauen(hass, entry, menu_xml)
    vier = [(20, 24, None), (28, 32, None), (36, 40, None), (44, 48, None)]
    mit_plan(abgleich, plan(tuesday=vier, sunday=[(32, 88, None)]))

    assert await abgleich.abgleichen() is False
    (hinweis,) = reparaturen["angelegt"]
    assert hinweis[0].endswith("hk1_zeitplan_zu_voll")
    assert hinweis[1]["tage"] == "Dienstag"
    assert [uri for uri, _ in hass.session.gesetzte_zeitfenster] == [fenster_uri("sunday", 1)]

    mit_plan(abgleich, plan(sunday=[(32, 88, None)]))
    assert await abgleich.abgleichen() is True
    assert reparaturen["entfernt"][-1].endswith("hk1_zeitplan_zu_voll")


async def test_abgelehnt_wird_spaeter_wiederholt(hass, entry, menu_xml):
    _, abgleich = await aufbauen(hass, entry, menu_xml)
    mit_plan(abgleich, plan(saturday=[(28, 92, None)]))
    hass.session.schreiben_erlaubt = False

    assert await abgleich.abgleichen() is False

    hass.session.schreiben_erlaubt = True
    assert await abgleich.abgleichen() is True
    assert hass.session.zeitfenster_text(fenster_uri("saturday", 1)) == "07:00 - 23:00 20,0"


async def test_diagnose_zeigt_die_zeitfenster(hass, entry, menu_xml):
    """Frisch gelesen, auch bevor ein Zeitplan gewählt ist."""
    from eta_heating_ws.diagnostics import _zeitprogramm

    coordinator, abgleich = await aufbauen(hass, entry, menu_xml)
    vorher = await _zeitprogramm(coordinator, "hk1")
    assert vorher["zeitplan"] is None
    assert vorher["zeitfenster"]["monday 1"] == "05:30 - 22:30 20,0"
    assert vorher["zeitfenster"]["monday 2"] == "-"

    coordinator.zeitplan_abgleiche["hk1"] = abgleich
    mit_plan(abgleich, plan(saturday=[(28, 92, None)]))
    await abgleich.abgleichen()
    diagnose = await _zeitprogramm(coordinator, "hk1")
    assert diagnose["zeitplan"] == "schedule.heizen"
    assert diagnose["zeitfenster"]["saturday 1"] == "07:00 - 23:00 20,0"

    hass.session.fail_uris.add("/12113/0/1082")
    assert (await _zeitprogramm(coordinator, "hk1"))["zeitfenster"]["monday 1"].startswith(
        "nicht lesbar"
    )


@pytest.fixture
async def echtes_hass(tmp_path):
    """Ein echtes Home Assistant mit einem Zeitplan-Helfer aus YAML."""
    from homeassistant import bootstrap, config_entries, loader
    from homeassistant.core import HomeAssistant
    from homeassistant.setup import async_setup_component

    hass = HomeAssistant(str(tmp_path))
    hass.config.skip_pip = True
    loader.async_setup(hass)
    hass.config_entries = config_entries.ConfigEntries(hass, {})
    await bootstrap.async_load_base_functionality(hass)
    assert await async_setup_component(
        hass,
        "schedule",
        {
            "schedule": {
                "heizen": {
                    "name": "Heizen",
                    "monday": [
                        {"from": "05:30:00", "to": "12:00:00", "data": {"temperatur": 21}},
                        {"from": "12:00:00", "to": "24:00:00"},
                    ],
                    "saturday": [{"from": "07:00:00", "to": "23:00:00"}],
                }
            }
        },
    )
    await hass.async_block_till_done()
    try:
        yield hass
    finally:
        await hass.async_stop(force=True)


async def test_plan_aus_dem_echten_zeitplan_helfer(echtes_hass):
    """So liefert der Zeitplan-Helfer von Home Assistant seine Blöcke."""
    coordinator = type("Koordinator", (), {"zeitprogramm_defs": {"hk1": {}}})()
    abgleich = ZeitplanAbgleich(echtes_hass, coordinator, "hk1", "schedule.heizen")

    wochenplan = await abgleich.plan_lesen()

    assert wochenplan["monday"] == [(22, 48, 21.0), (48, 96, None)]
    assert wochenplan["saturday"] == [(28, 92, None)]
    assert wochenplan["sunday"] == []
    json.dumps(wochenplan)


async def test_geaenderter_zeitplan_wird_sofort_bemerkt(echtes_hass):
    """Auch wenn der Zustand des Helfers gleich bleibt - Home Assistant meldet es als "reported"."""
    coordinator = type("Koordinator", (), {"zeitprogramm_defs": {"hk1": {}}})()
    abgleich = ZeitplanAbgleich(echtes_hass, coordinator, "hk1", "schedule.heizen")
    aufrufe = []

    async def zaehlen():
        aufrufe.append(1)

    abgleich.abgleichen = zaehlen
    abgleich.starten()
    await echtes_hass.async_block_till_done()
    assert len(aufrufe) == 1, "beim Start"

    zustand = echtes_hass.states.get("schedule.heizen")
    echtes_hass.states.async_set(zustand.entity_id, zustand.state, zustand.attributes)
    await echtes_hass.async_block_till_done()
    assert len(aufrufe) == 2
    abgleich.stoppen()


async def test_ohne_helfer_kein_plan(echtes_hass):
    coordinator = type("Koordinator", (), {"zeitprogramm_defs": {"hk1": {}}})()
    abgleich = ZeitplanAbgleich(echtes_hass, coordinator, "hk1", "schedule.gibt_es_nicht")
    assert await abgleich.plan_lesen() is None


def test_kein_hash_kommentar_im_modul():
    """Projektregel: Erklärungen stehen in Docstrings."""
    quelle = sys.modules[ZeitplanAbgleich.__module__].__file__
    with open(quelle, encoding="utf-8") as datei:
        assert not any(zeile.lstrip().startswith("#") for zeile in datei)
