"""Mehrere Puffer und Warmwasser - mit dem Menübaum einer Testanlage.

Die Anlage hat zwei PufferFlex ("PufferFlex", "PufferFlex 2") und zwei
ältere Puffer ("Puffer", "Puffer 2"), alle als Kombispeicher, dazu zwei
Warmwasserspeicher: "WW" mit Zirkulation, "WW 2" ohne. "WW 2" führt die
Zirkulationszeiten trotzdem im Menübaum, ihr Zustand meldet "xxx".
"""

from __future__ import annotations

import xml.etree.ElementTree as ET

import pytest
import voluptuous as vol

from eta_heating_ws.const import (
    CONF_ANZAHL_HEIZKREISE,
    CONF_ANZAHL_PUFFER,
    CONF_ANZAHL_WARMWASSER,
    fub_roles_for_components,
    komponenten_aus_formular,
)
from eta_heating_ws.uri_discovery import fub_namen_im_menue, fub_namen_vorschlagen

from .conftest import FIXTURES
from .test_sensors import setup_integration

MENU = (FIXTURES / "menu_mehrfach.xml").read_text(encoding="utf-8")
NS = "{http://www.eta.co.at/rest/v1}"
KOMPONENTEN = ["kessel", "puffer", "puffer2", "puffer3", "puffer4", "fwm", "fwm2"]
ZIRKULATION_WW2 = "/120/10112/0/0/12273"


def namen_der_anlage() -> list[str]:
    import xmltodict

    return fub_namen_im_menue(xmltodict.parse(MENU))


def fenster_der_anlage() -> dict[str, tuple[int, int, int | None]]:
    """Je Zeitfenster ein Startwert; Temperatur nur bei den Ladezeiten fürs Warmwasser."""
    werte = {}

    def gehen(knoten, weg):
        for kind in knoten.findall(f"{NS}object"):
            name = kind.get("name")
            if name.startswith("Zeitfenster "):
                warm = any("Warmwasser" in teil for teil in weg) and not any(
                    "Zirkulation" in teil for teil in weg
                )
                erstes = name.endswith("1")
                wert = (550 if erstes else 0) if warm else None
                werte[kind.get("uri")] = (0, 96, wert) if erstes else (0, 0, wert)
            gehen(kind, [*weg, name])

    for fub in ET.fromstring(MENU).iter(f"{NS}fub"):
        gehen(fub, [fub.get("name")])
    return werte


async def aufbauen(hass, entry):
    hass.session.menu = MENU
    hass.session.zeitfenster.update(fenster_der_anlage())
    hass.session.texte[ZIRKULATION_WW2] = "xxx"
    entry.data["components"] = KOMPONENTEN
    entry.data["fub_names"] = fub_namen_vorschlagen(
        fub_roles_for_components(KOMPONENTEN), namen_der_anlage()
    )
    coordinator, _ = await setup_integration(hass, entry)
    hass.config_entries.geladen.append(entry)
    return coordinator


def test_namen_kommen_der_reihe_nach_aus_der_anlage():
    vorschlag = fub_namen_vorschlagen(fub_roles_for_components(KOMPONENTEN), namen_der_anlage())

    assert vorschlag == {
        "kessel": "Kessel",
        "sys": "Sys",
        "pufferflex": "PufferFlex",
        "pufferflex2": "PufferFlex 2",
        "pufferflex3": "Puffer",
        "pufferflex4": "Puffer 2",
        "fwm": "WW",
        "fwm2": "WW 2",
    }


def test_gespeicherte_namen_bleiben_neue_bekommen_freie():
    rollen = ["pufferflex", "pufferflex2", "pufferflex3"]
    vorschlag = fub_namen_vorschlagen(
        rollen, namen_der_anlage(), {"pufferflex": "Puffer 2", "pufferflex2": "PufferFlex"}
    )
    assert vorschlag == {"pufferflex": "Puffer 2", "pufferflex2": "PufferFlex", "pufferflex3": "PufferFlex 2"}


async def test_jeder_speicher_bekommt_seine_werte(hass, entry):
    coordinator = await aufbauen(hass, entry)
    uris = coordinator.discovered_uris

    assert uris["fwm_warmwasser"] == "/120/10111/0/11129/0"
    assert uris["fwm2_warmwasser"] == "/120/10112/0/11129/0"
    assert uris["fwm_zirkulationspumpe"] == "/120/10111/0/11137/2001"
    assert "fwm2_zirkulationspumpe" not in uris, "WW 2 hat keine Zirkulation"
    assert "fwm2_zirkulationspumpe" not in coordinator.sensor_defs
    for komponente, block in (
        ("puffer", "/120/10601/"),
        ("puffer2", "/120/10602/"),
        ("puffer3", "/120/10251/"),
        ("puffer4", "/120/10252/"),
    ):
        assert uris[f"{komponente}_fuehler_1"].startswith(block), komponente
    assert coordinator.funktionsblock("puffer4") == "Puffer 2"
    assert coordinator.funktionsblock("fwm2") == "WW 2"


async def test_zeitprogramme_aller_speicher(hass, entry):
    coordinator = await aufbauen(hass, entry)

    assert "fwm2_12175" not in coordinator.zeitprogramm_defs, "WW 2 ohne Zirkulation"
    assert "nicht aktiviert" in coordinator.zeitprogramm_pruefung["fwm2_12175"]["grund"]
    for programm in (
        "fwm_12130",
        "fwm_12175",
        "fwm2_12130",
        "puffer_12235",
        "puffer2_12235",
        "puffer3_12235",
        "puffer4_12235",
        "puffer4_12130",
    ):
        assert programm in coordinator.zeitprogramm_defs, programm
    assert coordinator.zeitprogramm_art("fwm2_12130") == "warmwasser"
    assert coordinator.zeitprogramm_name("fwm2_12130") == "WW 2 › Warmwasserspeicher › Ladezeiten"
    assert coordinator.zeitprogramm_name("puffer4_12235") == "Puffer 2 › Warmwasser › Ladezeiten"


def test_anzahl_wird_zu_komponenten():
    eingabe = {
        CONF_ANZAHL_PUFFER: 4,
        CONF_ANZAHL_WARMWASSER: 2,
        CONF_ANZAHL_HEIZKREISE: 1,
        "components": ["lager"],
    }
    assert komponenten_aus_formular(eingabe) == [
        "kessel", "puffer", "puffer2", "puffer3", "puffer4", "fwm", "fwm2", "hk1", "lager",
    ]


def test_gleiche_anzahl_behaelt_die_bisherigen_plaetze():
    bisher = ["kessel", "puffer", "hk1", "hk3"]
    eingabe = {CONF_ANZAHL_PUFFER: 1, CONF_ANZAHL_WARMWASSER: 0, CONF_ANZAHL_HEIZKREISE: 2}
    assert komponenten_aus_formular(eingabe, bisher) == ["kessel", "puffer", "hk1", "hk3"]

    eingabe[CONF_ANZAHL_HEIZKREISE] = 3
    assert komponenten_aus_formular(eingabe, bisher) == ["kessel", "puffer", "hk1", "hk2", "hk3"]


def test_ohne_anzahl_zaehlt_die_auswahl():
    """So kamen die Komponenten vor den Anzahl-Feldern - etwa aus älteren Aufrufen."""
    assert komponenten_aus_formular({"components": ["puffer", "puffer2", "fwm", "hk2"]}) == [
        "kessel", "puffer", "puffer2", "fwm", "hk2",
    ]


def test_formular_begrenzt_die_anzahl():
    from eta_heating_ws.config_flow import _connection_schema

    gueltig = {"host": "192.0.2.10", "port": 8080, "components": []}
    schema = _connection_schema({})
    ergebnis = schema({**gueltig, CONF_ANZAHL_PUFFER: 8, CONF_ANZAHL_WARMWASSER: 8})
    assert (ergebnis[CONF_ANZAHL_PUFFER], ergebnis[CONF_ANZAHL_HEIZKREISE]) == (8, 0)
    for falsch in (
        {CONF_ANZAHL_PUFFER: 9},
        {CONF_ANZAHL_WARMWASSER: 9},
        {CONF_ANZAHL_HEIZKREISE: 5},
        {CONF_ANZAHL_PUFFER: -1},
        {"components": ["puffer"]},
    ):
        with pytest.raises(vol.Invalid):
            schema({**gueltig, **falsch})


def test_formular_zeigt_die_bisherige_anzahl():
    from eta_heating_ws.config_flow import _options_schema

    schema = _options_schema({"components": ["kessel", "puffer", "puffer2", "fwm", "hk1", "hk3", "solar"]})
    vorgaben = {str(k): k.default() for k in schema.schema if callable(k.default)}
    assert vorgaben[CONF_ANZAHL_PUFFER] == 2
    assert vorgaben[CONF_ANZAHL_WARMWASSER] == 1
    assert vorgaben[CONF_ANZAHL_HEIZKREISE] == 2
    assert vorgaben["components"] == ["solar"]


async def test_namensformular_ist_aus_der_anlage_vorbelegt(monkeypatch):
    from eta_heating_ws import config_flow as modul

    async def namen(*_):
        return namen_der_anlage()

    monkeypatch.setattr(modul, "_fub_namen_der_anlage", namen)
    monkeypatch.setattr(
        modul.ETAConfigFlow, "async_show_form", lambda self, **kwargs: {"type": "form", **kwargs}
    )
    flow = modul.ETAConfigFlow()
    flow._data = {"host": "192.0.2.10", "port": 8080, "components": KOMPONENTEN}
    formular = await flow.async_step_fub_names()

    vorgaben = {str(k): k.default() for k in formular["data_schema"].schema}
    assert vorgaben["pufferflex3"] == "Puffer"
    assert vorgaben["fwm2"] == "WW 2"
