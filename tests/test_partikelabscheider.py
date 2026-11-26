"""Partikelabscheider - mit dem Funktionsblock "Part.-Absch." einer echten Anlage.

Der Block steht in fixtures/fub_partikelabscheider.xml so, wie die Anlage
ihn unter /user/menu meldet. Er führt sieben Netzteile, gleich wie viele
eingebaut sind: "Abscheider Netzteil", "Abscheider Netzteil 2" bis "6"
und "Abscheider Netzteil rechts". Die Integration liest je Netzteil
Hochspannung, Strom und Leistung - sonst nichts, und sie schreibt dort
nie: Der Abscheider arbeitet mit Hochspannung.
"""

from __future__ import annotations

from eta_heating_ws import weitere_werte as weitere
from eta_heating_ws.api import ETAApiClient
from eta_heating_ws.const import (
    COMPONENTS,
    PARTIKEL_BEIWERTE,
    PARTIKEL_NETZTEILE,
    SELECTS,
    SENSORS,
    SWITCHES,
    ZAHLEN,
)
from eta_heating_ws.uebersicht import anlage
from eta_heating_ws.uri_discovery import (
    async_discover_uris,
    fub_namen_im_menue,
    fub_namen_vorschlagen,
)
from eta_heating_ws.verbindungen import vorgabe

from .conftest import FIXTURES, FakeConfigEntry, load_menu
from .test_sensors import setup_integration

ABSCHEIDER = (FIXTURES / "fub_partikelabscheider.xml").read_text(encoding="utf-8")
BLOCK = "/264/10571"

ERWARTET = {
    "partikelabscheider_spannung": f"{BLOCK}/14912/0/13125",
    "partikelabscheider_strom": f"{BLOCK}/14912/0/13127",
    "partikelabscheider_leistung": f"{BLOCK}/14912/0/14530",
    "partikelabscheider_2_spannung": f"{BLOCK}/14909/0/13125",
    "partikelabscheider_2_strom": f"{BLOCK}/14909/0/13127",
    "partikelabscheider_2_leistung": f"{BLOCK}/14909/0/14530",
    "partikelabscheider_6_leistung": f"{BLOCK}/14921/0/14530",
    "partikelabscheider_rechts_spannung": f"{BLOCK}/14913/0/13125",
    "partikelabscheider_leistung_soll": f"{BLOCK}/0/11318/2328",
    "partikelabscheider_leistung_max": f"{BLOCK}/14912/0/15424",
}
"""Wo die Werte im Menübaum der Anlage stehen."""


def menu_mit_abscheider(block: str = ABSCHEIDER) -> str:
    return load_menu().replace("</menu>", f"{block}</menu>")


async def suchen(hass, menu: str, ueber_kennung=None):
    hass.session.menu = menu
    client = ETAApiClient(hass, hass.session, "192.0.2.10", 8080)
    uris, _ = await async_discover_uris(client, {}, ueber_kennung)
    return uris


def melden(hass, werte: dict[str, tuple]) -> None:
    """Lässt die Attrappe zu diesen Adressen Rohwert, Text, Einheit und Teiler melden.

    Die Zahlen sind ausgedacht: Was eine echte Anlage hier meldet, ist an
    keinem Bericht belegt.
    """
    sonst = hass.session._wert_fuer

    def wert_fuer(uri: str) -> dict:
        pfad = uri.split("/user/var", 1)[-1]
        if pfad in werte:
            roh, text, einheit, teiler = werte[pfad]
            return {"value": str(roh), "str_value": text, "unit": einheit, "scale": str(teiler)}
        return sonst(uri)

    hass.session._wert_fuer = wert_fuer


def eintrag(**optionen) -> FakeConfigEntry:
    return FakeConfigEntry(
        data={"host": "192.0.2.10", "port": 8080, "components": ["kessel", "puffer", "partikelabscheider"]},
        options=optionen,
    )


async def test_werte_werden_ueber_ihre_namen_gefunden(hass):
    ueber_kennung: set = set()
    uris = await suchen(hass, menu_mit_abscheider(), ueber_kennung)

    assert {key: uris.get(key) for key in ERWARTET} == ERWARTET
    assert not ueber_kennung & set(ERWARTET)
    assert len([key for key in uris if key.startswith("partikelabscheider")]) == 7 * 3 + 2


async def test_ohne_passende_namen_greift_die_kennung(hass):
    """Etwa bei einem Display in anderer Sprache: Die Kennungen bleiben dieselben."""
    fremd = (
        ABSCHEIDER.replace('name="Partikelabscheider"', 'name="Separator"')
        .replace('name="Ausgänge"', 'name="Outputs"')
        .replace("Hochspannung Ist", "Voltage")
        .replace("Strom Ist", "Current")
        .replace("Aktuelle Leistung", "Power")
    )
    ueber_kennung: set = set()
    uris = await suchen(hass, menu_mit_abscheider(fremd), ueber_kennung)

    assert {key: uris.get(key) for key in ERWARTET} == ERWARTET
    assert set(ERWARTET) <= ueber_kennung


async def test_ohne_abscheider_bleiben_die_werte_weg(hass):
    uris = await suchen(hass, load_menu())
    assert not [key for key in uris if key.startswith("partikelabscheider")]


async def test_formular_schlaegt_den_block_vor(hass):
    hass.session.menu = menu_mit_abscheider()
    client = ETAApiClient(hass, hass.session, "192.0.2.10", 8080)
    namen = fub_namen_im_menue(await client.async_get_menu())
    assert fub_namen_vorschlagen(["partikelabscheider"], namen) == {"partikelabscheider": "Part.-Absch."}


def test_es_gibt_nur_spannung_strom_und_leistung():
    """Je Netzteil drei Sensoren - Soll und Maximum der Leistung sind Attribute, keine Sensoren."""
    eigene = {key: info for key, info in SENSORS.items() if info["component"] == "partikelabscheider"}
    assert len(eigene) == len(PARTIKEL_NETZTEILE) * 3 == 21
    assert {key.rsplit("_", 1)[1] for key in eigene} == {"spannung", "strom", "leistung"}
    assert all(info.get("einheit_der_anlage") for info in eigene.values())
    assert not {f"partikelabscheider_{art}" for art in PARTIKEL_BEIWERTE} & set(SENSORS)


def test_nur_das_erste_netzteil_ist_ab_werk_an():
    """Der Menübaum führt alle sieben, gleich wie viele eingebaut sind."""
    aus = {key for key, info in SENSORS.items() if info.get("ab_werk_aus")}
    assert aus == {
        f"partikelabscheider{anhang}_{art}"
        for anhang in list(PARTIKEL_NETZTEILE)[1:]
        for art in ("spannung", "strom", "leistung")
    }
    assert all(SENSORS[key].get("nur_wenn_vorhanden") for key in aus)


def test_am_abscheider_wird_nie_geschrieben():
    """Kein Schalter, keine Auswahl, kein Zahlenfeld - er arbeitet mit Hochspannung."""
    for tabelle in (SWITCHES, SELECTS, ZAHLEN):
        assert not [
            key
            for key, info in tabelle.items()
            if "partikel" in key or info.get("component") == "partikelabscheider"
        ]


async def test_sensoren_und_attribute(hass):
    hass.session.menu = menu_mit_abscheider()
    melden(
        hass,
        {
            ERWARTET["partikelabscheider_spannung"]: (284, "28,4", "kV", 10),
            ERWARTET["partikelabscheider_strom"]: (35, "0,35", "mA", 100),
            ERWARTET["partikelabscheider_leistung"]: (99, "9,9", "W", 10),
            ERWARTET["partikelabscheider_leistung_soll"]: (120, "12,0", "W", 10),
            ERWARTET["partikelabscheider_leistung_max"]: (300, "30,0", "W", 10),
        },
    )
    coordinator, by_name = await setup_integration(hass, eintrag(enable_switches=True))

    spannung = by_name["Partikelabscheider Hochspannung"]
    assert spannung.native_value == 28.4
    assert spannung.native_unit_of_measurement == "kV"
    assert spannung.entity_registry_enabled_default is True
    assert by_name["Partikelabscheider Strom"].native_unit_of_measurement == "mA"

    leistung = by_name["Partikelabscheider Leistung"]
    assert leistung.native_value == 9.9
    assert leistung.extra_state_attributes["soll"] == 12.0
    assert leistung.extra_state_attributes["maximum"] == 30.0

    zweites = by_name["Partikelabscheider Netzteil 2 Hochspannung"]
    assert zweites.entity_registry_enabled_default is False
    assert by_name["Partikelabscheider Netzteil rechts Leistung"].entity_registry_enabled_default is False

    assert not [name for name in by_name if "Leistung Soll" in name or "Leistung Max" in name]
    assert not [name for name in by_name if "Partikelabscheider" in name and "Zustand" in name]
    schreibbar = {
        key
        for key, info in coordinator.sensor_defs.items()
        if info.get("platform") in ("switch", "select", "number", "button", "climate")
    }
    assert not [key for key in schreibbar if "partikel" in key]


async def test_ohne_den_block_gibt_es_nur_platzhalter_fuer_das_erste_netzteil(hass):
    """Gewählt, aber nicht im Menübaum: Die weiteren Netzteile bleiben dann ganz weg."""
    coordinator, by_name = await setup_integration(hass, eintrag())
    namen = sorted(name for name in by_name if name.startswith("Partikelabscheider"))
    assert namen == ["Partikelabscheider Hochspannung", "Partikelabscheider Leistung", "Partikelabscheider Strom"]


def test_der_block_steht_unter_weitere_werte_nicht_zur_wahl():
    """Von ihm gibt es nur die festen Sensoren - belegt unter /264/10571."""
    baum = {
        "eta": {
            "menu": {
                "fub": [
                    {"@name": "Kessel", "@uri": "/264/10891", "object": {"@name": "Abgas", "@uri": "/264/10891/0/0/1"}},
                    {"@name": "Part.-Absch.", "@uri": "/264/10571", "object": {"@name": "Zählerstände", "@uri": "/264/10571/0/0/12010"}},
                ]
            }
        }
    }
    assert list(weitere.menue_werte(baum)) == ["/264/10891/0/0/1"]
    alt = {"uri": "/264/10571/14912/0/13148", "fub": "Part.-Absch.", "pfad": ["Überschläge pro Stunde"], "zahl": True}
    assert weitere.gewaehlte([alt]) == []


async def test_die_bauform_der_elektrode_ist_am_geraet_waehlbar(hass):
    """Kurz bei ePE, eSH und eTWIN, lang bei eHACK und ePE-K - an der Anlage ändert die Auswahl nichts."""
    from eta_heating_ws import select
    from eta_heating_ws.const import BILD_AUSWAHLEN, PARTIKEL_BILDER

    assert PARTIKEL_BILDER == ["kurz", "lang"]
    assert BILD_AUSWAHLEN["partikelabscheider_bild"]["vorgabe"] == "kurz"

    hass.session.menu = menu_mit_abscheider()
    entry = eintrag()
    coordinator, _ = await setup_integration(hass, entry)
    entry.runtime_data = coordinator
    angelegt: list = []
    await select.async_setup_entry(hass, entry, angelegt.extend)
    [auswahl] = [e for e in angelegt if e.unique_id.endswith("partikelabscheider_bild")]
    assert auswahl.options == ["kurz", "lang"]
    assert auswahl.current_option == "kurz"
    assert not hass.session.gesetzte_werte


def test_der_abscheider_haengt_an_keiner_leitung():
    """Er gehört zum Kessel und ist weder Erzeuger noch Verbraucher."""
    komponenten = ["kessel", "puffer", "hk1", "partikelabscheider"]
    assert "partikelabscheider" not in vorgabe(komponenten)
    assert COMPONENTS["partikelabscheider"]["image"] is None


async def test_die_karte_zeigt_ihn_gleich_hinter_dem_kessel(hass):
    hass.session.menu = menu_mit_abscheider()
    entry = FakeConfigEntry(
        data={"host": "192.0.2.10", "port": 8080, "components": ["kessel", "puffer", "hk1", "lager", "partikelabscheider"]},
    )
    coordinator, _ = await setup_integration(hass, entry)
    entry.runtime_data = coordinator
    teile = anlage(hass, entry)["teile"]
    assert [teil["id"] for teil in teile][:2] == ["kessel", "partikelabscheider"]
    abscheider = teile[1]
    assert abscheider["art"] == "partikelabscheider"
    assert abscheider["von"] is None
    assert abscheider["block"] == "Part.-Absch."
