"""Brennwert-Wärmetauscher - mit dem Funktionsblock "Brennwert-WT" einer echten Anlage.

Der Block steht in fixtures/fub_brennwert.xml so, wie die Anlage ihn
unter /user/menu meldet. Die Integration führt seinen Zustand in den
Worten der Anlage. Dieselbe Anlage nennt als mögliche Zustände: Aus,
Bereit, Heizen, Spülen, Spülpause, Füllen, Störung, Verriegelt,
Kondensatwanne voll und Spülen (Test).
"""

from __future__ import annotations

from eta_heating_ws import weitere_werte as weitere
from eta_heating_ws.api import ETAApiClient
from eta_heating_ws.const import SELECTS, SENSORS, SWITCHES, ZAHLEN
from eta_heating_ws.uebersicht import anlage
from eta_heating_ws.uri_discovery import (
    async_discover_uris,
    fub_namen_im_menue,
    fub_namen_vorschlagen,
)
from eta_heating_ws.verbindungen import vorgabe

from .conftest import FIXTURES, FakeConfigEntry, load_menu
from .test_sensors import setup_integration

TAUSCHER = (FIXTURES / "fub_brennwert.xml").read_text(encoding="utf-8")
ZUSTAND = "/264/10851/0/0/12731"


def menu_mit_tauscher(block: str = TAUSCHER) -> str:
    return load_menu().replace("</menu>", f"{block}</menu>")


async def suchen(hass, menu: str, ueber_kennung=None):
    hass.session.menu = menu
    client = ETAApiClient(hass, hass.session, "192.0.2.10", 8080)
    uris, _ = await async_discover_uris(client, {}, ueber_kennung)
    return uris


def eintrag(*weitere_komponenten: str) -> FakeConfigEntry:
    return FakeConfigEntry(
        data={"host": "192.0.2.10", "port": 8080, "components": ["kessel", "puffer", "brennwert", *weitere_komponenten]},
    )


async def test_zustand_wird_ueber_seinen_namen_gefunden(hass):
    ueber_kennung: set = set()
    uris = await suchen(hass, menu_mit_tauscher(), ueber_kennung)
    assert uris.get("brennwert_zustand") == ZUSTAND
    assert "brennwert_zustand" not in ueber_kennung


async def test_ohne_passende_namen_greift_die_kennung(hass):
    fremd = TAUSCHER.replace("Brennwertwärmetauscher-Zustand detailliert", "State").replace(
        'name="Brennwertwärmetauscher"', 'name="Heat exchanger"'
    )
    ueber_kennung: set = set()
    uris = await suchen(hass, menu_mit_tauscher(fremd), ueber_kennung)
    assert uris.get("brennwert_zustand") == ZUSTAND
    assert "brennwert_zustand" in ueber_kennung


async def test_ohne_tauscher_bleibt_der_zustand_weg(hass):
    uris = await suchen(hass, load_menu())
    assert "brennwert_zustand" not in uris


async def test_formular_schlaegt_den_block_vor(hass):
    hass.session.menu = menu_mit_tauscher()
    client = ETAApiClient(hass, hass.session, "192.0.2.10", 8080)
    namen = fub_namen_im_menue(await client.async_get_menu())
    assert fub_namen_vorschlagen(["brennwert"], namen) == {"brennwert": "Brennwert-WT"}


def test_es_gibt_nur_den_zustand_und_nichts_zu_schreiben():
    eigene = [key for key, info in SENSORS.items() if info["component"] == "brennwert"]
    assert eigene == ["brennwert_zustand"]
    assert SENSORS["brennwert_zustand"]["is_string"] is True
    for tabelle in (SWITCHES, SELECTS, ZAHLEN):
        assert not [key for key, info in tabelle.items() if info.get("component") == "brennwert"]


async def test_der_sensor_zeigt_die_worte_der_anlage(hass):
    hass.session.menu = menu_mit_tauscher()
    hass.session.texte[ZUSTAND] = "Spülen"
    coordinator, by_name = await setup_integration(hass, eintrag())
    zustand = by_name["Brennwert-Wärmetauscher Zustand"]
    assert zustand.native_value == "Spülen"
    assert zustand.native_unit_of_measurement is None


async def test_die_uebrigen_werte_des_blocks_bleiben_waehlbar(hass):
    """Anders als beim Partikelabscheider: Spülwassermenge und Co. gibt es über Weitere Werte."""
    hass.session.menu = menu_mit_tauscher()
    client = ETAApiClient(hass, hass.session, "192.0.2.10", 8080)
    werte = weitere.menue_werte(await client.async_get_menu())
    block = {uri: eintrag for uri, eintrag in werte.items() if eintrag["fub"] == "Brennwert-WT"}
    assert "/264/10851/0/0/14063" in block
    assert block["/264/10851/0/0/14063"]["pfad"] == ["Zählerstände", "Spülwassermenge gesamt"]


async def test_er_ist_kein_eigenes_teil_der_karte(hass):
    """Die Karte zeigt ihn klein am Kessel: Sie bekommt seinen Zustand, aber kein Teil dafür."""
    hass.session.menu = menu_mit_tauscher()
    entry = eintrag("hk1", "lager")
    coordinator, _ = await setup_integration(hass, entry)
    entry.runtime_data = coordinator
    teile = anlage(hass, entry)["teile"]
    assert "brennwert" not in [teil["id"] for teil in teile]
    assert "brennwert" in coordinator.components
    assert "brennwert_zustand" in coordinator.sensor_defs
    assert "brennwert" not in vorgabe(["kessel", "puffer", "hk1", "brennwert"])
