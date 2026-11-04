"""Warmwasserspeicher, Kombi-Puffer und Zirkulation - mit dem Menübaum einer echten Testanlage.

Die Anlage hat drei Blöcke: "WW" (Warmwasserspeicher), "Puffer" (älterer
Puffer als Kombispeicher) und "PufferFlex" (als Kombispeicher), alle mit
aktivierter Zirkulation.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET

from eta_heating_ws.const import KOMBI_GRENZEN, WARMWASSER_GRENZEN
from eta_heating_ws.zeitprogramm import _ws_zeitprogramme, zeitprogramm_setzen

from .conftest import FIXTURES
from .test_sensors import setup_integration
from .test_zeitprogramm_karte import befehl

MENU = (FIXTURES / "menu_warmwasser.xml").read_text(encoding="utf-8")
NS = "{http://www.eta.co.at/rest/v1}"
MAXIMUM = "/120/10111/0/0/12169"


def fenster_der_anlage() -> dict[str, tuple[int, int, int | None]]:
    """Je Zeitfenster im Menübaum ein Startwert: Fenster 1 ganztags, 2 und 3 leer.

    Warmwasser-Ladezeiten tragen eine Temperatur (55 °C), Puffer-Ladezeiten
    und Zirkulationszeiten nicht - wie an der Testanlage.
    """
    werte = {}

    def gehen(knoten, weg):
        for kind in knoten.findall(f"{NS}object"):
            name = kind.get("name")
            if name.startswith("Zeitfenster "):
                ohne = any("Zirkulation" in teil or teil in ("Puffer oben", "Erzeuger Kessel/Puffer") for teil in weg)
                wert = None if ohne else (550 if name.endswith("1") else 0)
                werte[kind.get("uri")] = (0, 96, wert) if name.endswith("1") else (0, 0, wert)
            gehen(kind, [*weg, name])

    for fub in ET.fromstring(MENU).iter(f"{NS}fub"):
        gehen(fub, [fub.get("name")])
    return werte


async def aufbauen(hass, entry):
    hass.session.menu = MENU
    hass.session.zeitfenster.update(fenster_der_anlage())
    entry.data["components"] = ["kessel", "puffer", "puffer2", "fwm"]
    entry.data["fub_names"] = {"pufferflex2": "Puffer"}
    coordinator, _ = await setup_integration(hass, entry)
    hass.config_entries.geladen.append(entry)
    hass.session.gesetzte_zeitfenster.clear()
    return coordinator


async def test_alle_programme_der_testanlage(hass, entry):
    coordinator = await aufbauen(hass, entry)

    erwartet = {
        "fwm_12130": ("warmwasser", "WW › Warmwasserspeicher › Ladezeiten"),
        "fwm_12175": ("zirkulation", "WW › Zirkulation › Zirkulationszeiten"),
        "puffer_12130": ("puffer", "PufferFlex › Erzeuger Kessel/Puffer › Ladezeiten"),
        "puffer_12235": ("warmwasser", "PufferFlex › Warmwasserbereich › Ladezeiten"),
        "puffer_12175": ("zirkulation", "PufferFlex › Zirkulation › Zirkulationszeiten"),
        "puffer2_12130": ("puffer", "Puffer › Puffer oben › Ladezeiten"),
        "puffer2_12235": ("warmwasser", "Puffer › Warmwasser › Ladezeiten"),
        "puffer2_12175": ("zirkulation", "Puffer › Zirkulation › Zirkulationszeiten"),
    }
    assert set(coordinator.zeitprogramm_defs) == set(erwartet)
    for programm, (art, name) in erwartet.items():
        assert coordinator.zeitprogramm_art(programm) == art, programm
        assert coordinator.zeitprogramm_name(programm) == name, programm


def test_nur_der_speicher_hat_ein_maximum():
    from eta_heating_ws.uri_discovery import _weitere_zeitprogramme
    import xmltodict

    fubs = xmltodict.parse(MENU)["eta"]["menu"]["fub"]
    namen: dict = {}
    for fub in fubs:
        _weitere_zeitprogramme(fub, fub["@name"].casefold(), namen)
    assert namen["ww_12130"]["maximum_uri"] == MAXIMUM
    assert namen["puffer_12235"]["maximum_uri"] is None
    assert namen["pufferflex_12235"]["maximum_uri"] is None


async def test_grenzen_je_warmwasser(hass, entry):
    coordinator = await aufbauen(hass, entry)

    assert coordinator.zeitprogramm_defs["fwm_12130"][("monday", 1)]["grenzen"] == WARMWASSER_GRENZEN
    assert coordinator.zeitprogramm_defs["puffer2_12235"][("monday", 1)]["grenzen"] == KOMBI_GRENZEN
    assert coordinator.zeitprogramm_defs["puffer_12235"][("monday", 1)]["grenzen"] == KOMBI_GRENZEN
    assert "grenzen" not in coordinator.zeitprogramm_defs["fwm_12175"][("monday", 1)]

    verbindung = await befehl(hass, _ws_zeitprogramme, type="eta_heating_ws/zeitprogramme")
    programme = {p["programm"]: p for p in verbindung.ergebnisse[0][1]["programme"]}

    speicher = programme["fwm_12130"]
    assert speicher["temperatur_max"] == 55.5, "Warmwasserspeicher max. der Attrappe"
    assert speicher["temperatur_max_grund"] == "Warmwasserspeicher max."
    assert speicher["hinweise"] == {"verbruehschutz": 60.0, "regelung": None}, "WW ist kein FWM"
    assert programme["puffer2_12235"]["temperatur_max_grund"] is None
    for zirkulation in ("fwm_12175", "puffer_12175", "puffer2_12175"):
        assert programme[zirkulation]["mit_temperatur"] is False
        assert programme[zirkulation]["hinweise"] is None


async def test_speicher_nicht_ueber_sein_maximum(hass, entry):
    await aufbauen(hass, entry)
    fenster = "/120/10111/12130/0/1082"

    await zeitprogramm_setzen(
        entry, "fwm_12130", ["monday"], [{"beginn": 20, "ende": 88, "temperatur": 70.0}]
    )
    assert hass.session.zeitfenster_text(fenster) == "05:00 - 22:00 55,5"

    await zeitprogramm_setzen(
        entry, "fwm_12130", ["monday"], [{"beginn": 20, "ende": 88, "temperatur": 50.0}]
    )
    assert hass.session.zeitfenster_text(fenster) == "05:00 - 22:00 50,0"


async def test_zirkulation_nur_zeiten(hass, entry):
    await aufbauen(hass, entry)

    await zeitprogramm_setzen(
        entry, "fwm_12175", ["monday"], [{"beginn": 24, "ende": 40, "temperatur": 70.0}]
    )

    [(uri, daten)] = hass.session.gesetzte_zeitfenster
    assert uri == "/120/10111/12175/0/1082"
    assert daten == {"begin": "24", "end": "40"}

