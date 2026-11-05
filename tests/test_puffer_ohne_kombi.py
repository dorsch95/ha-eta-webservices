"""Puffer ohne Kombispeicher und ohne Zirkulation - mit dem Menübaum der Anlage des Nutzers.

Der PufferFlex führt "Puffer > Warmwasserbereich" samt Ladezeiten auch ohne
Kombispeicher im Menübaum; seine Soll Temperatur meldet dann keine Einheit.
Eine Zirkulation ist nicht aktiviert - Zirkulationszeiten stehen nicht im
Menübaum, beim FWM nur der Zähler "Laufzeit Zirkulation".
"""

from __future__ import annotations

import xml.etree.ElementTree as ET

from eta_heating_ws.diagnostics import async_get_config_entry_diagnostics
from eta_heating_ws.zeitprogramm import _ws_zeitprogramme

from .conftest import FIXTURES
from .test_sensors import setup_integration
from .test_zeitprogramm_karte import befehl

MENU = (FIXTURES / "menu_ohne_kombi.xml").read_text(encoding="utf-8")
NS = "{http://www.eta.co.at/rest/v1}"
SOLL = "/120/10601/0/0/12293"
"""Puffer > Warmwasserbereich > Soll Temperatur - an der Anlage ohne Einheit."""


def fenster_der_anlage() -> dict[str, tuple[int, int, int | None]]:
    """Je Zeitfenster ein Startwert, mit Temperatur nur bei den Bereitschaftszeiten des FWM."""
    werte = {}
    for knoten in ET.fromstring(MENU).iter(f"{NS}object"):
        name = knoten.get("name")
        if not name.startswith("Zeitfenster "):
            continue
        uri = knoten.get("uri")
        erstes = name.endswith("1")
        wert = (500 if erstes else 0) if "/12318/" in uri else None
        werte[uri] = (0, 96, wert) if erstes else (0, 0, wert)
    return werte


async def aufbauen(hass, entry, kombi=False):
    """kombi: Die Soll Temperatur meldet "°C" wie an einer Anlage mit Kombispeicher."""
    hass.session.menu = MENU
    hass.session.zeitfenster.update(fenster_der_anlage())
    if not kombi:
        hass.session.ohne_einheit.add(SOLL)
    entry.data["components"] = ["puffer", "fwm"]
    coordinator, _ = await setup_integration(hass, entry)
    hass.config_entries.geladen.append(entry)
    return coordinator


async def test_ohne_kombispeicher_kein_warmwasserbereich(hass, entry):
    coordinator = await aufbauen(hass, entry)

    assert coordinator.zeitprogramm_namen["puffer_12235"]["soll_uri"] == SOLL
    assert set(coordinator.zeitprogramm_defs) == {"puffer_12130", "fwm_12318"}
    assert "nicht eingerichtet" in coordinator.zeitprogramm_pruefung["puffer_12235"]["grund"]
    assert coordinator.zeitprogramm_name("fwm_12318") == "Warmwasser › Bereitschaftszeiten", (
        "der ausgeblendete Warmwasserbereich zählt nicht als zweites Warmwasser"
    )


async def test_mit_kombispeicher_bleibt_er(hass, entry):
    coordinator = await aufbauen(hass, entry, kombi=True)

    assert set(coordinator.zeitprogramm_defs) == {"puffer_12130", "puffer_12235", "fwm_12318"}
    assert coordinator.zeitprogramm_name("fwm_12318") == "FWM › Warmwasser › Bereitschaftszeiten"
    assert coordinator.zeitprogramm_name("puffer_12235") == "PufferFlex › Warmwasserbereich › Ladezeiten"


async def test_ohne_antwort_wie_bisher(hass, entry):
    hass.session.fail_uris = {SOLL}

    coordinator = await aufbauen(hass, entry)

    assert "puffer_12235" in coordinator.zeitprogramm_defs


async def test_nur_programme_mit_eigenem_warmwasserbereich(hass, entry):
    coordinator = await aufbauen(hass, entry)

    assert coordinator.zeitprogramm_namen["puffer_12130"]["soll_uri"] is None
    assert coordinator.zeitprogramm_namen["fwm_12318"]["soll_uri"] is None, (
        "das FWM hat seine Soll Temperatur auch, wird aber nicht geprüft"
    )


async def test_ohne_zirkulation_keine_zirkulationszeiten(hass, entry):
    coordinator = await aufbauen(hass, entry)

    assert [
        programm
        for programm in coordinator.zeitprogramm_namen
        if coordinator.zeitprogramm_art(programm) == "zirkulation"
    ] == []


async def test_einstellungen_der_karte_fragen_keine_zeiten_ab(hass, entry):
    await aufbauen(hass, entry)
    vorher = hass.session.count

    verbindung = await befehl(
        hass, _ws_zeitprogramme, type="eta_heating_ws/zeitprogramme", ohne_zeiten=True
    )

    assert hass.session.count == vorher
    programme = verbindung.ergebnisse[0][1]["programme"]
    assert {p["programm"]: p["art"] for p in programme} == {
        "puffer_12130": "puffer",
        "fwm_12318": "warmwasser",
    }
    assert all("tage" not in p for p in programme)


async def test_diagnose_nennt_den_grund(hass, entry):
    await aufbauen(hass, entry)

    diagnose = await async_get_config_entry_diagnostics(hass, entry)

    befund = diagnose["schreibzugriff"]["zeitprogramm_nicht_beschreibbar"]["puffer_12235"]
    assert "nicht eingerichtet" in befund["grund"]
    assert 'unit=""' in befund["varinfo_beispiel"]
