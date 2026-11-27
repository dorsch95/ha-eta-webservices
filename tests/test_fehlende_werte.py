"""Ältere Anlagen: der Menübaum eines Stückholzkessels, Vorschläge, Zuordnung von Hand, ausgeblendete Werte.

Der Menübaum in fixtures/menu_stueckholz.xml stammt aus der Diagnose
einer echten Anlage: ETA SH30 von 2015 mit dem älteren Funktionsblock
"Puffer" und Webservices 1.1 (Issue 11). Unter "Kessel" gibt es dort
kein "Eingänge" - die Fühler stehen auf der Funktionsebene.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass
from homeassistant.components.sensor.const import DEVICE_CLASS_STATE_CLASSES, DEVICE_CLASS_UNITS

from eta_heating_ws import abhaengige, entitaeten_abmelden, platzhalter
from eta_heating_ws import weitere_werte as weitere
from eta_heating_ws import zuordnung
from eta_heating_ws.api import ETAApiClient, ETAValue
from eta_heating_ws.const import CONF_FEHLENDE_AUSBLENDEN, CONF_ZUORDNUNGEN, SENSORS, ZAHLEN
from eta_heating_ws.sensor import ETAWeitererWert
from eta_heating_ws.uri_discovery import (
    DISCOVERY_PATHS,
    FLEXIBLE_PFAD_MUSTER,
    PUMPEN,
    async_discover_uris,
    fub_namen_abgleich,
    kandidaten_fuer_zuordnung,
    vorschlaege_fuer_zuordnung,
)

from .conftest import FIXTURES, FakeConfigEntry, load_menu
from .test_partikelabscheider import menu_mit_abscheider
from .test_sensors import setup_integration

STUECKHOLZ = (FIXTURES / "menu_stueckholz.xml").read_text(encoding="utf-8")
KESSEL = "/48/10391"
PUFFER = "/120/10251"

FEHLT_AM_STUECKHOLZKESSEL = {
    "kessel_druck": "Kesseldruck",
    "pellet_tagesbehälter": "Pellet Inhalt Tagesbehälter",
    "pellet_gesamtverbrauch": "Pellet Gesamtverbrauch",
    "aschebox_verbrauch": "Aschebox Verbrauch seit Leerung",
    "entaschung_verbrauch": "Verbrauch seit Entaschung",
    "aschebox_schwelle": "Aschebox Leeren nach",
}
"""Was der Menübaum des Stückholzkessels nicht führt, je mit dem Namen des Sensors."""


async def suchen(hass, menu: str = STUECKHOLZ, **angaben):
    hass.session.menu = menu
    client = ETAApiClient(hass, hass.session, "192.0.2.10", 8080)
    return (await async_discover_uris(client, angaben.pop("fub_namen", {}), **angaben))[0]


async def menuebaum(hass, menu: str = STUECKHOLZ):
    hass.session.menu = menu
    return await ETAApiClient(hass, hass.session, "192.0.2.10", 8080).async_get_menu()


def einrichtung(komponenten=("kessel", "puffer"), **angaben) -> FakeConfigEntry:
    return FakeConfigEntry(
        {
            "host": "192.0.2.10",
            "port": 8080,
            "components": list(komponenten),
            "enable_switches": False,
            "enable_errors": True,
            "scan_interval": 30,
            **angaben,
        }
    )


async def test_stueckholzkessel_wird_erkannt(hass):
    ueber_kennung: set[str] = set()
    hass.session.menu = STUECKHOLZ
    client = ETAApiClient(hass, hass.session, "192.0.2.10", 8080)
    uris, fuehler = await async_discover_uris(client, {}, ueber_kennung)

    erwartet = {
        "kessel_temperatur": f"{KESSEL}/0/0/12161",
        "ruecklauf_temperatur": f"{KESSEL}/0/0/12220",
        "abgas_temperatur": f"{KESSEL}/0/0/12162",
        "restsauerstoff": f"{KESSEL}/0/0/12164",
        "kessel_soll": f"{KESSEL}/0/0/12001",
        "kessel_zustand": f"{KESSEL}/0/0/12000",
        "kessel_volllaststunden": f"{KESSEL}/0/0/12153",
        "aussentemperatur": "/48/10241/0/0/12197",
        "puffer_fuehler_1": f"{PUFFER}/0/0/12242",
        "puffer_fuehler_2": f"{PUFFER}/0/0/12522",
        "puffer_fuehler_3": f"{PUFFER}/0/0/12244",
        "puffer_ladezustand": f"{PUFFER}/0/0/12528",
        "puffer_zustand": f"{PUFFER}/0/0/12207",
        "kessel_entaschen": f"{KESSEL}/0/0/12112",
        "kessel_schalter": f"{KESSEL}/0/0/12080",
    }
    assert {key: uris.get(key) for key in erwartet} == erwartet
    assert fuehler == [1, 2, 3]
    assert not set(FEHLT_AM_STUECKHOLZKESSEL) & set(uris)
    assert "ruecklauf_temperatur" not in ueber_kennung, "über den Namen Kessel > Rücklauf"
    assert {"kessel_temperatur", "abgas_temperatur", "restsauerstoff", "aussentemperatur"} <= (
        ueber_kennung
    ), "die Anzeigewerte der Funktionsebene"


async def test_ruecklauf_ueber_die_kennung_wenn_der_name_anders_lautet(hass):
    """Mit einer anderen Sprache am Display passt der Name nicht, die Kennung 12220 schon."""
    ueber_kennung: set[str] = set()
    hass.session.menu = STUECKHOLZ.replace('name="Rücklauf"', 'name="Return"')
    client = ETAApiClient(hass, hass.session, "192.0.2.10", 8080)
    uris, _ = await async_discover_uris(client, {}, ueber_kennung)

    assert uris["ruecklauf_temperatur"] == f"{KESSEL}/0/0/12220"
    assert "ruecklauf_temperatur" in ueber_kennung


async def test_ruecklauf_eines_anderen_blocks_zaehlt_nicht(hass):
    """Die Kennung 12220 trägt auch der Rücklauf eines Heizkreises - gesucht wird nur im Kessel."""
    menu = """<eta xmlns="http://www.eta.co.at/rest/v1" version="1.0"><menu uri="/user/menu">
    <fub uri="/48/10391" name="Kessel">
      <object uri="/48/10391/0/0/12000" name="Kessel">
        <object uri="/48/10391/0/0/12161" name="Kessel"/>
      </object>
    </fub>
    <fub uri="/120/10101" name="HK">
      <object uri="/120/10101/0/0/12092" name="Heizkreis">
        <object uri="/120/10101/0/0/12220" name="Rücklauf"/>
      </object>
    </fub>
    </menu></eta>"""
    uris = await suchen(hass, menu)

    assert uris["kessel_temperatur"] == "/48/10391/0/0/12161"
    assert "ruecklauf_temperatur" not in uris


VERMUTUNGEN = """<?xml version="1.0" encoding="utf-8"?>
<eta version="1.0" xmlns="http://www.eta.co.at/rest/v1">
  <menu>
    <fub uri="/99/90001" name="Kessel">
      <object uri="/99/90001/0/0/50000" name="Messwerte">
        <object uri="/99/90001/0/0/50001" name="Kessel Temperatur Soll"/>
        <object uri="/99/90001/0/0/50002" name="Kessel Min"/>
        <object uri="/99/90001/0/0/50003" name="Boiler temperature"/>
        <object uri="/99/90001/0/0/50004" name="Rücklauf">
          <object uri="/99/90001/0/0/50005" name="Rücklauf Soll"/>
          <object uri="/99/90001/0/0/50006" name="Rücklauf Min"/>
          <object uri="/99/90001/0/0/50007" name="Rücklauf Solar"/>
          <object uri="/99/90001/0/0/50008" name="Rücklauf Position"/>
        </object>
        <object uri="/99/90001/0/0/50009" name="Abgas Gebläse"/>
        <object uri="/99/90001/0/0/50010" name="Flue gas temperature"/>
        <object uri="/99/90001/0/0/50011" name="Residual oxygen"/>
        <object uri="/99/90001/0/0/50012" name="Boiler pressure"/>
        <object uri="/99/90001/0/0/50015" name="Boiler setpoint requested"/>
        <object uri="/99/90001/0/0/50013" name="Boiler setpoint"/>
        <object uri="/99/90001/0/0/50014" name="Boiler state detailed"/>
      </object>
    </fub>
    <fub uri="/99/90002" name="Sys">
      <object uri="/99/90002/0/0/51000" name="Umwelt">
        <object uri="/99/90002/0/0/51001" name="Outside temperature Solar"/>
        <object uri="/99/90002/0/0/51002" name="Outside temperature"/>
      </object>
    </fub>
  </menu>
</eta>
"""
"""Ein erdachter Menübaum mit fremden Kennungen, an dem nur FLEXIBLE_PFAD_MUSTER etwas erkennt."""

VERMUTET = {
    "kessel_temperatur": "/99/90001/0/0/50003",
    "ruecklauf_temperatur": "/99/90001/0/0/50004",
    "abgas_temperatur": "/99/90001/0/0/50010",
    "restsauerstoff": "/99/90001/0/0/50011",
    "kessel_druck": "/99/90001/0/0/50012",
    "kessel_soll": "/99/90001/0/0/50013",
    "kessel_zustand": "/99/90001/0/0/50014",
    "aussentemperatur": "/99/90002/0/0/51002",
}


async def test_eine_vermutung_uebernimmt_die_erkennung_nie_von_selbst(hass):
    """Was nur FLEXIBLE_PFAD_MUSTER erkennt, bleibt ungefunden und kommt als Vorschlag."""
    uris = await suchen(hass, VERMUTUNGEN)
    assert not set(VERMUTET) & set(uris)

    vorschlaege = vorschlaege_fuer_zuordnung(await menuebaum(hass, VERMUTUNGEN), list(SENSORS))
    assert vorschlaege == VERMUTET, "ohne Soll, Min, Solar, Position, Gebläse und requested"


async def test_am_stueckholzkessel_gibt_es_keinen_vorschlag(hass):
    """An der echten Anlage findet die Vermutung nichts, was nicht schon gefunden ist."""
    gefunden = await suchen(hass)
    fehlend = zuordnung.fehlende(["kessel", "puffer"], gefunden)
    assert vorschlaege_fuer_zuordnung(await menuebaum(hass), fehlend) == {}


def test_vermutet_wird_nur_was_sich_zuordnen_laesst():
    assert all(zuordnung.zuordenbar(key) or key.startswith("lager_") for key in FLEXIBLE_PFAD_MUSTER)
    assert not zuordnung.zuordenbar("lager_vorrat")


async def test_eine_zuordnung_von_hand_geht_der_suche_vor(hass):
    von_hand: set[str] = set()
    uris = await suchen(
        hass,
        zuordnungen={
            "kessel_druck": f"{KESSEL}/0/0/12204",
            "ruecklauf_temperatur": f"{KESSEL}/0/11163/2121",
        },
        von_hand=von_hand,
    )

    assert uris["kessel_druck"] == f"{KESSEL}/0/0/12204"
    assert uris["ruecklauf_temperatur"] == f"{KESSEL}/0/11163/2121"
    assert von_hand == {"kessel_druck", "ruecklauf_temperatur"}
    assert uris["kessel_temperatur"] == f"{KESSEL}/0/0/12161"


@pytest.mark.parametrize(
    "adresse",
    [
        "/99/99999/0/0/99999",
        f"{PUFFER}/0/0/12242",
        "",
        None,
        12204,
    ],
)
async def test_eine_zuordnung_gilt_nur_im_eigenen_funktionsblock(hass, adresse):
    """Eine Adresse, die es nicht gibt oder die in einem anderen Block steht, zählt nicht."""
    von_hand: set[str] = set()
    uris = await suchen(
        hass,
        zuordnungen={"kessel_druck": adresse, "kessel_temperatur": adresse},
        von_hand=von_hand,
    )

    assert "kessel_druck" not in uris
    assert uris["kessel_temperatur"] == f"{KESSEL}/0/0/12161"
    assert von_hand == set()


async def test_schalter_und_tasten_lassen_sich_nicht_zuordnen(hass):
    """Wer dort einen falschen Eintrag wählte, schriebe an die falsche Stelle."""
    fremd = f"{KESSEL}/0/0/12161"
    uris = await suchen(
        hass,
        zuordnungen={
            "kessel_schalter": fremd,
            "kessel_entaschen": fremd,
            "puffer_volumen": fremd,
            "puffer_fuehler_1": fremd,
        },
    )

    assert uris["kessel_schalter"] == f"{KESSEL}/0/0/12080"
    assert uris["kessel_entaschen"] == f"{KESSEL}/0/0/12112"
    assert "puffer_volumen" not in uris
    assert uris["puffer_fuehler_1"] == f"{PUFFER}/0/0/12242"


async def test_was_die_integration_beschreibt_laesst_sich_nicht_zuordnen(hass):
    """Vorrat und Fassungsvermögen des Lagers schreibt das Zahlenfeld an ihre Adresse."""
    assert zuordnung.BESCHRIEBEN == {definition["quelle"] for definition in ZAHLEN.values()}
    assert {"lager_vorrat", "lager_maximum"} <= zuordnung.BESCHRIEBEN
    for key in ("lager_vorrat", "lager_maximum", "kessel_schalter", "partikelabscheider_spannung"):
        assert not zuordnung.zuordenbar(key), key
    for key in ("kessel_temperatur", "kessel_druck", "puffer_zustand", "lager_warngrenze"):
        assert zuordnung.zuordenbar(key), key

    uris = await suchen(hass, load_menu(), zuordnungen={"lager_vorrat": "/40/10201/0/0/12016"})
    assert uris.get("lager_vorrat") != "/40/10201/0/0/12016"
    assert zuordnung.gueltige(
        {"lager_vorrat": "/1/2", "kessel_druck": "/3/4", "kessel_soll": "", "abgas_temperatur": 5}
    ) == {"kessel_druck": "/3/4"}
    assert zuordnung.gueltige(None) == {}


def test_jeden_sensor_sucht_die_erkennung_im_menuebaum():
    """Darauf baut zuordnung.zuordenbar: Zu jedem Sensor gibt es einen Funktionsblock."""
    assert set(SENSORS) <= set(DISCOVERY_PATHS) | set(PUMPEN)


async def test_zur_wahl_steht_nur_der_eigene_funktionsblock(hass):
    kandidaten = kandidaten_fuer_zuordnung(
        await menuebaum(hass),
        ["kessel_druck", "puffer_warmwasser", "lager_vorrat", "kessel_schalter", "solar_kollektor"],
    )

    assert set(kandidaten) == {"kessel_druck", "puffer_warmwasser"}
    kessel = kandidaten["kessel_druck"]
    assert len(kessel) == 34
    assert all(uri.startswith(KESSEL) for uri in kessel)
    assert kessel[f"{KESSEL}/0/0/12220"] == "Kessel › Rücklauf"
    assert kessel[f"{KESSEL}/0/11163/2121"] == "Kessel › Rücklauf › Rücklaufmischer › Ist Temperatur"

    puffer = kandidaten["puffer_warmwasser"]
    assert all(uri.startswith(PUFFER) for uri in puffer)
    assert puffer[f"{PUFFER}/12130/0/1110"] == "Puffer › Puffer oben › Ladezeiten › Temperatur"
    for im_zeitprogramm in ("1081", "1082", "1111"):
        assert f"{PUFFER}/12130/0/{im_zeitprogramm}" not in puffer, "Wochentag, Zeitfenster, Absenktemperatur"


async def test_aus_dem_partikelabscheider_steht_nichts_zur_wahl(hass):
    """Aus seinem Funktionsblock gibt es nur Hochspannung, Strom und Leistung."""
    schluessel = [key for key, info in SENSORS.items() if info["component"] == "partikelabscheider"]
    menu = await menuebaum(hass, menu_mit_abscheider())

    assert schluessel
    assert kandidaten_fuer_zuordnung(menu, schluessel) == {}
    assert vorschlaege_fuer_zuordnung(menu, schluessel) == {}
    uris = await suchen(
        hass,
        menu_mit_abscheider(),
        zuordnungen={"partikelabscheider_2_spannung": "/264/10571/14912/0/13125"},
    )
    assert uris["partikelabscheider_2_spannung"] == "/264/10571/14909/0/13125"


async def test_zum_zuordnen_steht_an_was_fehlt_oder_schon_zugeordnet_ist(hass):
    gefunden = await suchen(hass)

    assert zuordnung.fehlende(["kessel", "puffer"], gefunden) == [
        *FEHLT_AM_STUECKHOLZKESSEL,
        "puffer_ladepumpe",
        "puffer_warmwasser",
        "puffer_warmwasser_zustand",
    ]
    assert zuordnung.fehlende(["kessel"], gefunden) == list(FEHLT_AM_STUECKHOLZKESSEL)
    mit_zuordnung = zuordnung.fehlende(
        ["kessel"], gefunden, {"ruecklauf_temperatur": f"{KESSEL}/0/11163/2121"}
    )
    assert mit_zuordnung == ["ruecklauf_temperatur", *FEHLT_AM_STUECKHOLZKESSEL]
    assert "lager_vorrat" not in zuordnung.fehlende(["kessel", "lager"], gefunden)


def wert(zahl=None, text="", einheit="", ist_text=False) -> ETAValue:
    return ETAValue(zahl, text, einheit, ist_text, 1)


@pytest.mark.parametrize(
    "key, gelesen, erwartet",
    [
        ("ruecklauf_temperatur", wert(69.1, "69,1", "°C"), True),
        ("ruecklauf_temperatur", wert(None, "---", "°C"), True),
        ("ruecklauf_temperatur", wert(1.6, "1,6", "bar"), False),
        ("ruecklauf_temperatur", wert(None, "Ein", "", True), False),
        ("ruecklauf_temperatur", None, False),
        ("kessel_druck", wert(1.6, "1,6", "bar"), True),
        ("kessel_druck", wert(69.1, "69,1", "°C"), False),
        ("pellet_gesamtverbrauch", wert(9281.0, "9281", "h"), False),
        ("pellet_gesamtverbrauch", wert(5210.0, "5210", "kg"), True),
        ("kessel_zustand", wert(None, "Heizen", "", True), True),
        ("kessel_zustand", wert(81.9, "81,9", "°C"), False),
        ("kessel_zustand", wert(None, " ", "", True), False),
        ("fwm_durchfluss", wert(12.0, "12,0", "l/min"), True),
        ("fwm_durchfluss", wert(None, "Aus", "", True), False),
    ],
)
def test_ein_eintrag_passt_nur_mit_art_und_einheit_des_messwerts(key, gelesen, erwartet):
    assert zuordnung.passt(key, gelesen) is erwartet


def test_liter_schreibt_die_anlage_klein():
    assert zuordnung.gleiche_einheit("l", "L")
    assert zuordnung.gleiche_einheit(" °C", "°C")
    assert not zuordnung.gleiche_einheit("kg", "t")
    assert not zuordnung.gleiche_einheit(None, "kg")


def test_anzeige_zeigt_was_die_anlage_anzeigt():
    assert zuordnung.anzeige(wert(69.1, "69,1", "°C")) == "69,1 °C"
    assert zuordnung.anzeige(wert(None, "Heizen", "", True)) == "Heizen"
    assert zuordnung.anzeige(wert(3.0, "3", "")) == "3"
    assert zuordnung.anzeige(None) == ""


def test_funktionsblock_namen_gelten_als_bestaetigt_wenn_die_anlage_alle_meldet():
    rollen = ["kessel", "pufferflex", "sys"]

    vorschlag, fehlende = fub_namen_abgleich(rollen, ["Puffer", "Kessel", "Sys"])
    assert fehlende == []
    assert vorschlag == {"kessel": "Kessel", "pufferflex": "Puffer", "sys": "Sys"}

    assert fub_namen_abgleich(rollen, ["Puffer", "Holzkessel", "Sys"])[1] == ["kessel"]
    assert fub_namen_abgleich(rollen, ["Puffer", "Kessel"])[1] == ["sys"]
    assert fub_namen_abgleich(rollen, [])[1] == rollen
    assert fub_namen_abgleich(["kessel", "pufferflex", "pufferflex2"], ["Kessel", "Puffer"])[1] == [
        "pufferflex2"
    ], "ein Block für zwei Puffer"


async def test_ohne_ausblenden_steht_ein_platzhalter(hass):
    hass.session.menu = STUECKHOLZ
    _, by_name = await setup_integration(hass, einrichtung())

    assert isinstance(by_name["Rücklauftemperatur"].native_value, float)
    assert isinstance(by_name["Kesseltemperatur"].native_value, float)
    for name in (*FEHLT_AM_STUECKHOLZKESSEL.values(), "Pellet Energieverbrauch gesamt", "Aschebox Status"):
        assert by_name[name].native_value == "-", name


async def test_mit_ausblenden_gibt_es_den_sensor_nicht(hass):
    hass.session.menu = STUECKHOLZ
    coordinator, by_name = await setup_integration(hass, einrichtung(**{CONF_FEHLENDE_AUSBLENDEN: True}))

    assert coordinator.fehlende_ausblenden is True
    assert isinstance(by_name["Rücklauftemperatur"].native_value, float)
    assert isinstance(by_name["Kesseltemperatur"].native_value, float)
    for name in (*FEHLT_AM_STUECKHOLZKESSEL.values(), "Pellet Energieverbrauch gesamt", "Aschebox Status"):
        assert name not in by_name, name
    assert not set(FEHLT_AM_STUECKHOLZKESSEL) & set(coordinator.sensor_defs)


async def test_das_fassungsvermoegen_bleibt_auch_ausgeblendet(hass):
    """Es kann aus Home Assistant stammen - der Sensor folgt dem Zahlenfeld."""
    hass.session.menu = STUECKHOLZ
    _, by_name = await setup_integration(
        hass, einrichtung(("kessel", "lager"), **{CONF_FEHLENDE_AUSBLENDEN: True})
    )

    assert "Lager Fassungsvermögen" in by_name
    assert "Lager Vorrat" not in by_name
    assert "Lager Füllstand" not in by_name


async def test_eine_zuordnung_von_hand_ergibt_einen_sensor(hass):
    hass.session.menu = STUECKHOLZ
    hass.session.werte[f"{KESSEL}/0/0/12204"] = {
        "value": "16",
        "str_value": "1,6",
        "unit": "bar",
        "scale": "10",
    }
    coordinator, by_name = await setup_integration(
        hass,
        einrichtung(
            **{
                CONF_FEHLENDE_AUSBLENDEN: True,
                CONF_ZUORDNUNGEN: {"kessel_druck": f"{KESSEL}/0/0/12204", "lager_vorrat": "/1/2"},
            }
        ),
    )

    assert coordinator.zuordnungen == {"kessel_druck": f"{KESSEL}/0/0/12204"}
    assert coordinator.von_hand == {"kessel_druck"}
    assert by_name["Kesseldruck"].native_value == pytest.approx(1.6)
    assert by_name["Kesseldruck"].native_unit_of_measurement == "bar"


def _eintraege(hass, entry, *schluessel):
    for key in schluessel:
        hass.entity_registry.anlegen(
            f"sensor.eta_{key}", f"eta_static_{entry.entry_id}_{key}", entry.entry_id
        )


async def test_platzhalter_sind_was_keine_adresse_hat_und_was_daran_haengt(hass):
    hass.session.menu = STUECKHOLZ
    entry = einrichtung()
    coordinator, _ = await setup_integration(hass, entry)

    erwartet = {*FEHLT_AM_STUECKHOLZKESSEL, "aschebox_status", "aschebox_faellig", "pellet_energie_gesamt"}
    assert platzhalter(coordinator) == erwartet
    assert abhaengige({"lager_vorrat"}) == {
        "lager_vorrat",
        "lager_niedrig",
        "lager_fuellstand",
        "lager_reicht_bis",
        "lager_bestellen_bis",
        "lager_reichweite",
    }
    assert abhaengige({"kessel_druck"}) == {"kessel_druck"}

    _eintraege(hass, entry, "kessel_druck", "aschebox_status", "kessel_temperatur", "ruecklauf_temperatur")
    entitaeten_abmelden(hass, entry, platzhalter(coordinator))
    assert set(hass.entity_registry.eintraege) == {
        "sensor.eta_kessel_temperatur",
        "sensor.eta_ruecklauf_temperatur",
    }


async def test_der_gerechnete_ladezustand_ist_kein_platzhalter(hass):
    """Der ältere Puffer ohne Ladezustand: Der Sensor hat keine Adresse, aber einen Wert."""
    hass.session.menu = STUECKHOLZ.replace(f"{PUFFER}/0/0/12528", f"{PUFFER}/0/0/99998")
    coordinator, by_name = await setup_integration(hass, einrichtung())

    assert coordinator.puffer_mit_berechnetem_ladezustand == ["puffer"]
    assert "puffer_ladezustand" not in platzhalter(coordinator)

    hass.session.menu = STUECKHOLZ.replace(f"{PUFFER}/0/0/12528", f"{PUFFER}/0/0/99998")
    _, ausgeblendet = await setup_integration(hass, einrichtung(**{CONF_FEHLENDE_AUSBLENDEN: True}))
    assert "Puffer Ladezustand" in ausgeblendet


async def test_der_start_entfernt_keinen_fehlenden_sensor(hass):
    """Ein Aussetzer der Anlage darf keine Entität samt ihren Anpassungen löschen."""
    hass.session.menu = STUECKHOLZ
    entry = einrichtung(**{CONF_FEHLENDE_AUSBLENDEN: True})
    _eintraege(hass, entry, "kessel_druck", "kessel_temperatur")
    await setup_integration(hass, entry)

    assert set(hass.entity_registry.eintraege) >= {"sensor.eta_kessel_druck", "sensor.eta_kessel_temperatur"}


async def test_weitere_werte_stehen_je_funktionsblock(hass):
    """Auch die Einträge der Zeitprogramme bleiben in ihrem Funktionsblock."""
    werte = weitere.menue_werte(await menuebaum(hass))
    gruppen = weitere.gruppen_fuer_menue(werte, {f"{KESSEL}/0/0/12161"})

    assert list(gruppen) == ["Puffer", "Kessel", "Sys"]
    assert gruppen["Puffer"][f"{PUFFER}/12130/0/1082"] == (
        "Puffer › Puffer oben › Ladezeiten › Montag › Zeitfenster 1"
    )
    assert gruppen["Kessel"][f"{KESSEL}/0/0/12165"] == "Kessel › Abgasgebläse"
    assert f"{KESSEL}/0/0/12161" not in gruppen["Kessel"], "ein fester Sensor"

    bisher = {
        f"{KESSEL}/0/0/12161": werte[f"{KESSEL}/0/0/12161"],
        "/48/10391/0/0/1": {"fub": "Kessel", "pfad": ["Früher"]},
    }
    gewaehlt = weitere.gruppen_fuer_menue(werte, {f"{KESSEL}/0/0/12161"}, bisher)["Kessel"]
    assert gewaehlt[f"{KESSEL}/0/0/12161"] == "Kessel › Kessel"
    assert gewaehlt["/48/10391/0/0/1"] == "Früher"


MESSWERT = SensorStateClass.MEASUREMENT
ZAEHLER = SensorStateClass.TOTAL_INCREASING


@pytest.mark.parametrize(
    "pfad, einheit, klasse, zustandsklasse",
    [
        (["Kessel", "Kessel"], "°C", SensorDeviceClass.TEMPERATURE, MESSWERT),
        (["Kessel", "Kesseldruck"], "bar", SensorDeviceClass.PRESSURE, MESSWERT),
        (["Solar", "Leistung"], "kW", SensorDeviceClass.POWER, MESSWERT),
        (["Solar", "Wärmemenge"], "kWh", SensorDeviceClass.ENERGY, ZAEHLER),
        (["Solar", "Ertrag heute"], "kWh", SensorDeviceClass.ENERGY, ZAEHLER),
        (["Solar", "Ertrag gestern"], "kWh", SensorDeviceClass.ENERGY, None),
        (["Kessel", "Zählerstände", "Gesamtverbrauch"], "kg", SensorDeviceClass.WEIGHT, ZAEHLER),
        (["Kessel", "Verbrauch seit Entaschung"], "kg", SensorDeviceClass.WEIGHT, ZAEHLER),
        (["Lager", "Vorrat"], "kg", SensorDeviceClass.WEIGHT, MESSWERT),
        (["Kessel", "Zählerstände", "Volllaststunden"], "s", SensorDeviceClass.DURATION, ZAEHLER),
        (["Kessel", "Nachlaufzeit"], "s", SensorDeviceClass.DURATION, MESSWERT),
        (["Part.-Absch.", "Hochspannung"], "kV", SensorDeviceClass.VOLTAGE, MESSWERT),
        (["Puffer", "Gesamtvolumen"], "l", None, MESSWERT),
        (["FWM", "Durchfluss"], "l/min", None, MESSWERT),
        (["Puffer", "Ladezustand"], "%", None, MESSWERT),
        (["Lager", "Vorrat"], "t", None, MESSWERT),
        (["Kessel", "Zählerstände", "Übertemperatur"], "", None, MESSWERT),
    ],
)
def test_ein_weiterer_wert_bekommt_seine_klasse_nach_der_einheit(pfad, einheit, klasse, zustandsklasse):
    koordinator = SimpleNamespace(
        config_entry=SimpleNamespace(entry_id="test"), device_info=None, data={}
    )
    eintrag = {"uri": "/1/2/0/0/9", "fub": pfad[0], "pfad": pfad[1:], "zahl": True, "einheit": einheit}
    sensor = ETAWeitererWert(koordinator, "wert_1_2_0_0_9", eintrag)

    assert sensor.device_class == klasse
    assert sensor.state_class == zustandsklasse
    assert sensor.native_unit_of_measurement == (einheit or None)


def test_ein_text_bekommt_keine_klasse():
    koordinator = SimpleNamespace(
        config_entry=SimpleNamespace(entry_id="test"), device_info=None, data={}
    )
    eintrag = {"uri": "/1/2/0/0/9", "fub": "Kessel", "pfad": ["Zustand"], "zahl": False}
    sensor = ETAWeitererWert(koordinator, "wert_1_2_0_0_9", eintrag)

    assert sensor.device_class is None
    assert sensor.state_class is None


def test_ein_unterschied_in_kelvin_ist_keine_temperatur():
    """Home Assistant rechnete 5 K sonst in -268 °C um."""
    klasse, zustandsklasse = weitere.sensor_klassen("K", "Puffer › Einschaltdifferenz")

    assert klasse != SensorDeviceClass.TEMPERATURE
    assert klasse == getattr(SensorDeviceClass, "TEMPERATURE_DELTA", None)
    assert zustandsklasse == MESSWERT


@pytest.mark.parametrize("einheit", list(weitere.KLASSEN))
def test_jede_klasse_nimmt_home_assistant_mit_dieser_einheit_an(einheit):
    """Sonst warnt Home Assistant bei jedem Start im Protokoll."""
    for name in ("Kessel › Kessel", "Kessel › Zählerstände › Wert", "Solar › Ertrag gestern"):
        klasse, zustandsklasse = weitere.sensor_klassen(einheit, name)
        if klasse is None:
            continue
        assert einheit in {str(getattr(e, "value", e)) for e in DEVICE_CLASS_UNITS[klasse]}
        assert zustandsklasse is None or zustandsklasse in DEVICE_CLASS_STATE_CLASSES[klasse]
