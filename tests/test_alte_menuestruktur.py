"""Ältere Regelung ohne Ein- und Ausgangsebene - mit dem Menübaum einer echten Anlage.

Pelletskessel mit Software 3.42.0 von 2017 und Webservices 1.1, dazu
Puffer, zwei Warmwasserspeicher, drei Heizkreise, Solar und Lager. Kein
Funktionsblock führt einen Zweig "Eingänge" oder "Ausgänge" mit Fühlern:
Die Messwerte stehen nur als Anzeigewerte auf der Funktionsebene, etwa
Kessel > Kessel > Kessel. Die Blöcke "Sys " und "Puffer " tragen ein
Leerzeichen am Ende. Warmwasserspeicher und Heizkreise heißen an der
Anlage nach ihren Bewohnern; hier stehen dafür neutrale Namen.
"""

from __future__ import annotations

import pytest

from eta_heating_ws.api import ETAApiClient
from eta_heating_ws.const import FUB_ROLE_DEFAULT_NAMES
from eta_heating_ws.uri_discovery import (
    ANZEIGEWERTE,
    DISCOVERY_PATHS,
    KENNUNGEN,
    SWITCH_ROLES,
    async_discover_uris,
    fub_namen_im_menue,
    fub_namen_vorschlagen,
)

from .conftest import FIXTURES, ohne_objekt
from .test_sensors import setup_integration

MENU = (FIXTURES / "menu_alt.xml").read_text(encoding="utf-8")

NAMEN = {
    "fwm": "Boiler 1",
    "fwm2": "Boiler 2",
    "hk": "HK Wohnung 1",
    "hk2": "HK Wohnung 2",
}
"""Was der Betreiber von Hand einträgt - der Rest heißt wie ab Werk."""

KESSEL = "/40/10021"
LAGER = "/40/10201"
PUFFER = "/121/10251"
BOILER_1 = "/121/10112"
BOILER_2 = "/121/10111"
HK_1 = "/121/10102"
HK_2 = "/121/10101"

ERWARTET = {
    "kessel_temperatur": f"{KESSEL}/0/0/12161",
    "ruecklauf_temperatur": f"{KESSEL}/0/0/12999",
    "restsauerstoff": f"{KESSEL}/0/0/12164",
    "kessel_druck": f"{KESSEL}/0/0/12180",
    "kessel_zustand": f"{KESSEL}/0/0/12000",
    "aussentemperatur": "/121/10241/0/0/12197",
    "heizkreis_vorlauf": f"{HK_1}/0/0/12241",
    "heizkreis_raum": f"{HK_1}/0/0/12634",
    "heizkreis2_vorlauf": f"{HK_2}/0/0/12241",
    "heizkreis2_raum": f"{HK_2}/0/0/12634",
    "puffer_fuehler_1": f"{PUFFER}/0/0/12242",
    "puffer_fuehler_2": f"{PUFFER}/0/0/12244",
    "puffer_zustand": f"{PUFFER}/0/0/12207",
    "fwm_warmwasser": f"{BOILER_1}/0/0/12271",
    "fwm_zustand": f"{BOILER_1}/0/0/12129",
    "fwm2_warmwasser": f"{BOILER_2}/0/0/12271",
    "fwm2_zustand": f"{BOILER_2}/0/0/12129",
    "lager_vorrat": f"{LAGER}/0/0/12015",
    "lager_warngrenze": f"{LAGER}/0/0/12042",
    "lager_zustand": f"{LAGER}/0/0/12058",
    "solar_kollektor": "/121/10221/0/0/12275",
}
"""Wo die Messwerte an dieser Anlage stehen - so hat ihr Betreiber sie abgefragt."""


async def suchen(hass, namen=None, ueber_kennung=None, fub_namen=None):
    hass.session.menu = MENU
    client = ETAApiClient(hass, hass.session, "192.0.2.10", 8080)
    uris, fuehler = await async_discover_uris(
        client, NAMEN if namen is None else namen, ueber_kennung, fub_namen
    )
    return uris, fuehler


@pytest.mark.parametrize("key, uri", sorted(ERWARTET.items()))
async def test_messwerte_der_funktionsebene_werden_gefunden(hass, key, uri):
    uris, _ = await suchen(hass)
    assert uris[key] == uri


async def test_was_die_anlage_nicht_fuehrt_bleibt_weg(hass):
    """Ladezustand, Fassungsvermögen und Solarertrag stehen nicht in diesem Menübaum."""
    uris, _ = await suchen(hass)
    for key in ("puffer_ladezustand", "lager_maximum", "solar_leistung", "solar_ertrag_heute"):
        assert key not in uris


async def test_treffer_ueber_anzeigewerte_stehen_in_der_diagnose(hass):
    ueber_kennung: set = set()
    await suchen(hass, ueber_kennung=ueber_kennung)
    assert {"kessel_temperatur", "aussentemperatur", "fwm_warmwasser", "puffer_zustand"} <= (
        ueber_kennung
    )


@pytest.mark.parametrize(
    "eingetragen",
    [{}, {"sys": "Sys", "pufferflex": "Puffer"}, {"sys": "Sys ", "pufferflex": "Puffer "}],
    ids=["vorbelegt", "ohne Leerzeichen", "mit Leerzeichen"],
)
async def test_block_mit_leerzeichen_am_ende_wird_gefunden(hass, eingetragen):
    """Am Display ist das Leerzeichen nicht zu sehen - es darf keine Rolle spielen."""
    fub_namen: dict = {}
    uris, fuehler = await suchen(hass, {**NAMEN, **eingetragen}, fub_namen=fub_namen)

    assert uris["aussentemperatur"] == "/121/10241/0/0/12197"
    assert fuehler == [1, 2]
    assert fub_namen["sys"] == "Sys " and fub_namen["pufferflex"] == "Puffer "


async def test_formular_schlaegt_die_bloecke_der_anlage_vor(hass):
    hass.session.menu = MENU
    client = ETAApiClient(hass, hass.session, "192.0.2.10", 8080)
    namen = fub_namen_im_menue(await client.async_get_menu())
    vorschlag = fub_namen_vorschlagen(["kessel", "sys", "pufferflex", "lager"], namen)

    assert vorschlag == {"kessel": "Kessel", "sys": "Sys ", "pufferflex": "Puffer ", "lager": "Lager"}


async def test_nur_die_beiden_pufferfuehler_zaehlen(hass):
    """ "Puffer oben Solar" und "Puffer unten Solar" gehören zur Solarregelung."""
    uris, fuehler = await suchen(hass)

    assert fuehler == [1, 2]
    assert f"{PUFFER}/0/0/12322" not in uris.values()
    assert f"{PUFFER}/0/0/12245" not in uris.values()


async def test_anzeigewert_bleibt_im_eigenen_funktionsblock(hass):
    """Der dritte Heizkreis hat keinen Raumfühler und bekommt keinen fremden.

    Auch der Block "F.Wärme" führt ein Objekt "Kessel" mit der Kennung der
    Kesseltemperatur - sie kommt trotzdem aus dem Kessel.
    """
    uris, _ = await suchen(hass, {**NAMEN, "hk3": "Fbh"})

    assert uris["heizkreis3_vorlauf"] == "/121/10103/0/0/12241"
    assert "heizkreis3_raum" not in uris
    assert uris["kessel_temperatur"].startswith(KESSEL)


def test_anzeigewerte_gehoeren_zu_gesuchten_messwerten():
    assert set(ANZEIGEWERTE) <= set(DISCOVERY_PATHS)
    assert not set(ANZEIGEWERTE) & set(SWITCH_ROLES)
    for key, kennung in ANZEIGEWERTE.items():
        assert kennung.count("/") == 2 and all(t.isdigit() for t in kennung.split("/"))
        assert KENNUNGEN.get(key) != kennung, key


@pytest.mark.parametrize(
    "datei", ["menu.xml", "menu_mehrfach.xml", "menu_ohne_kombi.xml", "menu_warmwasser.xml"]
)
async def test_neuere_anlagen_brauchen_keine_anzeigewerte(hass, datei):
    """Mit Ein- und Ausgangsebene findet der Namenspfad alles - wie bisher."""
    text = (FIXTURES / datei).read_text(encoding="utf-8")
    hass.session.menu = text
    client = ETAApiClient(hass, hass.session, "192.0.2.10", 8080)
    namen = fub_namen_vorschlagen(
        list(FUB_ROLE_DEFAULT_NAMES), fub_namen_im_menue(await client.async_get_menu())
    )
    ueber_kennung: set = set()
    await async_discover_uris(client, namen, ueber_kennung)

    assert ueber_kennung == set()


async def test_fehlt_der_fuehler_einer_neueren_anlage_greift_der_anzeigewert(hass, menu_xml):
    """Die Kesseltemperatur steht auch dort zusätzlich unter Kessel > Kessel > Kessel."""
    hass.session.menu = ohne_objekt(menu_xml, "/264/10891/0/11109/0")
    client = ETAApiClient(hass, hass.session, "192.0.2.10", 8080)
    ueber_kennung: set = set()
    uris, _ = await async_discover_uris(client, {}, ueber_kennung)

    assert uris["kessel_temperatur"] == "/264/10891/0/0/12161"
    assert "kessel_temperatur" in ueber_kennung


async def aufbauen(hass, entry):
    hass.session.menu = MENU
    hass.session.varinfo_unterstuetzt = False
    entry.data["components"] = [
        "kessel", "puffer", "fwm", "fwm2", "hk1", "hk2", "lager", "solar"
    ]
    entry.data["fub_names"] = dict(NAMEN)
    entry.data["enable_switches"] = False
    return await setup_integration(hass, entry)


async def test_sensoren_der_aelteren_anlage_bekommen_werte(hass, entry):
    """Webservices 1.1 kennen kein /user/varinfo - gelesen wird trotzdem."""
    coordinator, by_name = await aufbauen(hass, entry)

    for key in ERWARTET:
        assert key in coordinator.sensor_defs, key
    for name in (
        "Kesseltemperatur",
        "Rücklauftemperatur",
        "Außentemperatur",
        "Heizkreis Vorlauftemperatur",
        "Heizkreis 2 Vorlauftemperatur",
    ):
        assert by_name[name].native_value == pytest.approx(55.5), name
    assert "Heizkreis Raumtemperatur" in by_name and "Heizkreis 2 Raumtemperatur" in by_name


async def test_keine_meldung_ueber_fehlende_warmwasserspeicher(hass, entry, reparaturen):
    """Vorher blieben beide Warmwasserspeicher ohne Treffer und standen unter Reparaturen."""
    await aufbauen(hass, entry)

    gemeldet = [issue_id for issue_id, _ in reparaturen["angelegt"]]
    assert not [issue_id for issue_id in gemeldet if issue_id.endswith("_nicht_gefunden")]
