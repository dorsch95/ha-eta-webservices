"""Fremdwärme - mit dem Funktionsblock "Ofen" einer echten Anlage.

Ein Kaminofen mit Wassertasche speist dort über eine Ladepumpe in den
Puffer. Die ETA-Regelung steuert ihn nicht, sie misst nur seine
Temperatur und gibt die Ladepumpe frei. Der Block steht in
fixtures/fub_ofen.xml so, wie die Anlage ihn unter /user/menu meldet.

"Ofen" hat der Betreiber jener Anlage vergeben. Ab Werk heißt der Block
"F.Wärme": So legt ihn der Konfigurations-Assistent an einer zweiten
Anlage an, mit demselben Menübaum Objekt für Objekt, und so heißt er an
einer älteren Regelung (fixtures/menu_alt.xml), die seine Werte nur auf
der Funktionsebene führt.
"""

from __future__ import annotations

import pytest

from eta_heating_ws.api import ETAApiClient
from eta_heating_ws.uri_discovery import (
    async_discover_uris,
    fub_namen_im_menue,
    fub_namen_vorschlagen,
)
from eta_heating_ws.verbindungen import ERZEUGER, moegliche_quellen, vorgabe

from .conftest import FIXTURES, FakeConfigEntry, load_menu
from .test_sensors import setup_integration

OFEN = (FIXTURES / "fub_ofen.xml").read_text(encoding="utf-8")
BLOCK = "/272/10291"

ERWARTET = {
    "fremdwaerme_temperatur": f"{BLOCK}/0/11112/0",
    "fremdwaerme_speicher": f"{BLOCK}/0/11089/0",
    "fremdwaerme_zustand": f"{BLOCK}/0/0/12386",
    "fremdwaerme_ladepumpe": f"{BLOCK}/0/11088/2001",
}
"""Wo die Werte an der Anlage stehen - so hat sie ihr Betreiber abgefragt."""


def menu_mit_ofen(block: str = OFEN) -> str:
    return load_menu().replace("</menu>", f"{block}</menu>")


async def suchen(hass, menu: str, ueber_kennung=None):
    hass.session.menu = menu
    client = ETAApiClient(hass, hass.session, "192.0.2.10", 8080)
    uris, _ = await async_discover_uris(client, {}, ueber_kennung)
    return uris


async def test_werte_werden_ueber_ihre_namen_gefunden(hass):
    ueber_kennung: set = set()
    uris = await suchen(hass, menu_mit_ofen(), ueber_kennung)

    assert {key: uris.get(key) for key in ERWARTET} == ERWARTET
    assert not ueber_kennung & set(ERWARTET)


async def test_ohne_passende_namen_greift_die_kennung(hass):
    """Etwa bei einem Display in anderer Sprache: Die Kennungen bleiben dieselben."""
    fremd = (
        OFEN.replace('name="Eingänge"', 'name="Inputs"')
        .replace('name="Ausgänge"', 'name="Outputs"')
        .replace("Fremdwärme-Zustand detailliert", "External heat state")
    )
    ueber_kennung: set = set()
    uris = await suchen(hass, menu_mit_ofen(fremd), ueber_kennung)

    assert {key: uris.get(key) for key in ERWARTET} == ERWARTET
    assert set(ERWARTET) <= ueber_kennung


async def test_ohne_ofen_bleiben_die_werte_weg(hass):
    uris = await suchen(hass, load_menu())
    assert not set(ERWARTET) & set(uris)


async def test_formular_schlaegt_den_ofen_vor(hass):
    hass.session.menu = menu_mit_ofen()
    client = ETAApiClient(hass, hass.session, "192.0.2.10", 8080)
    namen = fub_namen_im_menue(await client.async_get_menu())

    assert fub_namen_vorschlagen(["fremdwaerme"], namen) == {"fremdwaerme": "Ofen"}


async def test_block_heisst_ab_werk_f_waerme(hass):
    """Der Werksname wird ohne Eintrag gefunden und im Formular vorgeschlagen."""
    ab_werk = OFEN.replace('name="Ofen"', 'name="F.Wärme"')
    uris = await suchen(hass, menu_mit_ofen(ab_werk))
    client = ETAApiClient(hass, hass.session, "192.0.2.10", 8080)
    namen = fub_namen_im_menue(await client.async_get_menu())

    assert {key: uris.get(key) for key in ERWARTET} == ERWARTET
    assert fub_namen_vorschlagen(["fremdwaerme"], namen) == {"fremdwaerme": "F.Wärme"}


async def test_aeltere_regelung_fuehrt_die_werte_auf_der_funktionsebene(hass):
    """Dort gibt es weder "Eingänge" noch "Ausgänge" - die Kennungen sind dieselben."""
    block = "/121/10291"
    ueber_kennung: set = set()
    uris = await suchen(
        hass, (FIXTURES / "menu_alt.xml").read_text(encoding="utf-8"), ueber_kennung
    )

    assert {key: uris.get(key) for key in ERWARTET} == {
        "fremdwaerme_temperatur": f"{block}/0/0/12383",
        "fremdwaerme_speicher": f"{block}/0/0/12491",
        "fremdwaerme_zustand": f"{block}/0/0/12386",
        "fremdwaerme_ladepumpe": f"{block}/0/11088/2001",
    }
    assert set(ERWARTET) <= ueber_kennung


def test_kachel_hat_ein_eigenes_bild_mit_feuer():
    """Ofen statt Brenner: Grundbild, bewegtes Feuer und sein Standbild."""
    from eta_heating_ws import GRAFIKEN
    from eta_heating_ws.const import COMPONENTS

    assert COMPONENTS["fremdwaerme"]["image"] == "fremdwaerme"
    for datei in ("fremdwaerme.png", "fremdwaerme_aktiv.webp", "fremdwaerme_aktiv.png"):
        assert (GRAFIKEN / datei).is_file(), datei


def test_fremdwaerme_laedt_in_den_ersten_puffer():
    komponenten = ["kessel", "puffer", "puffer2", "hk1", "fremdwaerme"]

    assert "fremdwaerme" in ERZEUGER
    assert vorgabe(komponenten)["fremdwaerme"] == "puffer"
    assert moegliche_quellen(komponenten, "fremdwaerme") == ["puffer", "puffer2"]


@pytest.fixture
def menu_xml() -> str:
    return menu_mit_ofen()


async def test_sensoren_entstehen_und_lesen_den_zustand(hass):
    hass.session.texte["/272/10291/0/0/12386"] = "Heizen"
    entry = FakeConfigEntry(
        {
            "host": "192.0.2.10",
            "port": 8080,
            "components": ["kessel", "puffer", "fremdwaerme"],
            "enable_switches": False,
            "enable_errors": False,
            "scan_interval": 30,
        }
    )
    _, by_name = await setup_integration(hass, entry)

    for name in (
        "Fremdwärme Temperatur",
        "Fremdwärme Speichertemperatur",
        "Fremdwärme Ladepumpe",
        "Komponente Fremdwärme",
    ):
        assert name in by_name, name
    assert by_name["Fremdwärme Zustand"].native_value == "Heizen"
    assert by_name["Fremdwärme Temperatur"].native_unit_of_measurement == "°C"
    assert by_name["Komponente Fremdwärme"].native_value == "fremdwaerme"
