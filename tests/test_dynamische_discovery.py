"""Tests für dynamische Discovery, URI-Overrides, Ausblendung fehlender Sensoren und Zusatzwert-Klassen."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass

from eta_heating_ws import entitaet_vorgesehen
from eta_heating_ws import weitere_werte as weitere
from eta_heating_ws.api import ETAApiClient
from eta_heating_ws.const import CONF_HIDE_MISSING_SENSORS
from eta_heating_ws.sensor import ETAWeitererWert
from eta_heating_ws.uri_discovery import async_discover_uris, fub_namen_abgleich

from .conftest import FakeConfigEntry
from .test_sensors import setup_integration

FIXTURES = Path(__file__).parent / "fixtures"


def _load_stueckholz_menu() -> str:
    return (FIXTURES / "menu_stueckholz.xml").read_text(encoding="utf-8")


async def _discover(
    hass,
    fub_overrides=None,
    *,
    uri_overrides=None,
    dynamisch_gefunden=None,
):
    client = ETAApiClient(hass, hass.session, "192.0.2.10", 8080)
    return await async_discover_uris(
        client,
        fub_overrides or {},
        uri_overrides=uri_overrides,
        dynamisch_gefunden=dynamisch_gefunden,
    )


async def test_stueckholz_fixture_entdeckt_alle_erwarteten_uris(hass):
    hass.session.menu = _load_stueckholz_menu()

    uris, indices = await _discover(hass)

    erwartet = {
        "kessel_temperatur": "/48/10391/0/0/12161",
        "ruecklauf_temperatur": "/48/10391/0/0/12220",
        "abgas_temperatur": "/48/10391/0/0/12162",
        "restsauerstoff": "/48/10391/0/0/12164",
        "kessel_soll": "/48/10391/0/0/12001",
        "kessel_zustand": "/48/10391/0/0/12000",
        "kessel_volllaststunden": "/48/10391/0/0/12153",
        "aussentemperatur": "/48/10241/0/0/12197",
        "puffer_fuehler_1": "/120/10251/0/0/12242",
        "puffer_fuehler_2": "/120/10251/0/0/12522",
        "puffer_fuehler_3": "/120/10251/0/0/12244",
        "puffer_ladezustand": "/120/10251/0/0/12528",
        "puffer_zustand": "/120/10251/0/0/12207",
        "kessel_entaschen": "/48/10391/0/0/12112",
        "kessel_schalter": "/48/10391/0/0/12080",
    }
    for key, uri in erwartet.items():
        assert uris.get(key) == uri, key
    assert indices == [1, 2, 3]


BRANCH_UND_STAGE4_XML = """<?xml version="1.0" encoding="utf-8"?>
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


async def test_stage4_loest_verzweigungen_und_fremde_ids_mit_ausschlussregeln(hass):
    """Stage 4 findet Branch-Knoten und tiefe Sprach-Aliase, ohne Ausschlussbegriffe zu wählen."""
    hass.session.menu = BRANCH_UND_STAGE4_XML
    dynamisch: set[str] = set()

    uris, _ = await _discover(hass, dynamisch_gefunden=dynamisch)

    assert uris["kessel_temperatur"] == "/99/90001/0/0/50003"
    assert uris["ruecklauf_temperatur"] == "/99/90001/0/0/50004"
    assert uris["abgas_temperatur"] == "/99/90001/0/0/50010"
    assert uris["restsauerstoff"] == "/99/90001/0/0/50011"
    assert uris["kessel_druck"] == "/99/90001/0/0/50012"
    assert uris["kessel_soll"] == "/99/90001/0/0/50013"
    assert uris["kessel_zustand"] == "/99/90001/0/0/50014"
    assert uris["aussentemperatur"] == "/99/90002/0/0/51002"

    # Keiner der ausgeschlossenen Knoten (Soll, Min, Solar, Position, Gebläse) darf gewählt werden
    assert uris["ruecklauf_temperatur"] not in {
        "/99/90001/0/0/50005",
        "/99/90001/0/0/50006",
        "/99/90001/0/0/50007",
        "/99/90001/0/0/50008",
    }
    assert uris["aussentemperatur"] != "/99/90002/0/0/51001"
    assert {
        "kessel_temperatur",
        "ruecklauf_temperatur",
        "abgas_temperatur",
        "restsauerstoff",
        "kessel_druck",
        "kessel_soll",
        "kessel_zustand",
        "aussentemperatur",
    } <= dynamisch


async def test_stage0_uri_overrides_vorrang_und_ungueltige_ignoriert(hass):
    hass.session.menu = _load_stueckholz_menu()

    # Gültige URI aus dem Menübaum überschreibt die automatische Erkennung
    uris, _ = await _discover(
        hass,
        uri_overrides={
            "kessel_temperatur": "/48/10391/0/0/12006",
            "ruecklauf_temperatur": "/48/10391/0/11163/2121",
        },
    )
    assert uris["kessel_temperatur"] == "/48/10391/0/0/12006"
    assert uris["ruecklauf_temperatur"] == "/48/10391/0/11163/2121"

    # Nicht existierende Override-URI wird sicher ignoriert, normale Discovery läuft weiter
    uris_fallback, _ = await _discover(
        hass,
        uri_overrides={"kessel_temperatur": "/99/99999/0/0/99999"},
    )
    assert uris_fallback["kessel_temperatur"] == "/48/10391/0/0/12161"


def test_fub_namen_abgleich():
    vorschlag, fehlende = fub_namen_abgleich(
        ["kessel", "pufferflex", "sys"],
        ["Puffer", "Kessel", "Sys"],
    )
    assert fehlende == []
    assert vorschlag == {"kessel": "Kessel", "pufferflex": "Puffer", "sys": "Sys"}

    # Umbenannter Kessel -> Delta auf kessel
    _, fehlende_umbenannt = fub_namen_abgleich(
        ["kessel", "pufferflex", "sys"],
        ["Puffer", "Holzkessel", "Sys"],
    )
    assert fehlende_umbenannt == ["kessel"]

    # Fehlender FUB -> Delta auf sys
    _, fehlende_lücke = fub_namen_abgleich(
        ["kessel", "pufferflex", "sys"],
        ["Puffer", "Kessel"],
    )
    assert fehlende_lücke == ["sys"]

    # Anlage offline ([]) -> alle Rollen als fehlend gemeldet
    _, fehlende_offline = fub_namen_abgleich(
        ["kessel", "pufferflex", "sys"],
        [],
    )
    assert fehlende_offline == ["kessel", "pufferflex", "sys"]


async def test_hide_missing_sensors_false_zeigt_platzhalter(hass):
    hass.session.menu = _load_stueckholz_menu()
    entry = FakeConfigEntry(
        {
            "host": "192.0.2.10",
            "port": 8080,
            "components": ["kessel", "puffer"],
            "enable_switches": False,
            "enable_errors": True,
            "scan_interval": 30,
            CONF_HIDE_MISSING_SENSORS: False,
        }
    )

    _, by_name = await setup_integration(hass, entry)

    assert isinstance(by_name["Rücklauftemperatur"].native_value, float)
    assert by_name["Rücklauftemperatur"].native_value != "-"
    assert by_name["Kesseltemperatur"].native_value != "-"
    for fehlend in (
        "Pellet Gesamtverbrauch",
        "Pellet Inhalt Tagesbehälter",
        "Aschebox Verbrauch seit Leerung",
        "Aschebox Leeren nach",
        "Verbrauch seit Entaschung",
        "Kesseldruck",
        "Pellet Energieverbrauch gesamt",
        "Aschebox Status",
    ):
        assert by_name[fehlend].native_value == "-", fehlend


async def test_hide_missing_sensors_true_laesst_fehlende_sensoren_weg(hass):
    hass.session.menu = _load_stueckholz_menu()
    entry = FakeConfigEntry(
        {
            "host": "192.0.2.10",
            "port": 8080,
            "components": ["kessel", "puffer"],
            "enable_switches": False,
            "enable_errors": True,
            "scan_interval": 30,
            CONF_HIDE_MISSING_SENSORS: True,
        }
    )

    coordinator, by_name = await setup_integration(hass, entry)

    assert isinstance(by_name["Rücklauftemperatur"].native_value, float)
    assert isinstance(by_name["Kesseltemperatur"].native_value, float)

    for fehlend in (
        "Pellet Gesamtverbrauch",
        "Pellet Inhalt Tagesbehälter",
        "Aschebox Verbrauch seit Leerung",
        "Aschebox Leeren nach",
        "Verbrauch seit Entaschung",
        "Kesseldruck",
        "Pellet Energieverbrauch gesamt",
        "Aschebox Status",
    ):
        assert fehlend not in by_name, fehlend

    mit_uri = {key for key, info in coordinator.sensor_defs.items() if info.get("uri")}
    assert entitaet_vorgesehen(
        "ruecklauf_temperatur",
        ["kessel", "puffer"],
        False,
        True,
        hide_missing_sensors=True,
        mit_uri=mit_uri,
    ) is True
    assert entitaet_vorgesehen(
        "kessel_temperatur",
        ["kessel", "puffer"],
        False,
        True,
        hide_missing_sensors=True,
        mit_uri=mit_uri,
    ) is True
    for missing_key in (
        "pellet_gesamtverbrauch",
        "pellet_tagesbehälter",
        "aschebox_verbrauch",
        "aschebox_schwelle",
        "entaschung_verbrauch",
        "kessel_druck",
        "pellet_energie_gesamt",
        "aschebox_status",
    ):
        assert entitaet_vorgesehen(
            missing_key,
            ["kessel", "puffer"],
            False,
            True,
            hide_missing_sensors=True,
            mit_uri=mit_uri,
        ) is False, missing_key


async def test_gruppen_fuer_menue_trennt_zeiten_und_kessel(hass):
    hass.session.menu = _load_stueckholz_menu()
    client = ETAApiClient(hass, hass.session, "192.0.2.10", 8080)
    parsed = await client.async_get_menu()
    werte = weitere.menue_werte(parsed)
    gruppen = weitere.gruppen_fuer_menue(werte, set())

    assert "Zeiten" in gruppen
    assert list(gruppen)[-1] == "Zeiten"
    assert "/120/10251/12130/0/1081" in gruppen["Zeiten"]  # Montag
    assert "/120/10251/12130/0/1082" in gruppen["Zeiten"]  # Zeitfenster 1
    assert "/120/10251/12130/0/1111" in gruppen["Zeiten"]  # Absenktemperatur
    assert "/48/10391/0/0/12165" in gruppen["Kessel"]  # Abgasgebläse
    assert "/48/10391/0/11123/0" in gruppen["Kessel"]  # Kesselpumpe
    assert "/120/10251/12130/0/1081" not in gruppen.get("Puffer", {})


@pytest.mark.parametrize(
    "pfad, zahl, einheit, erwartete_device_class, erwartete_state_class",
    [
        (["Kessel", "Kesseltemperatur"], True, "°C", SensorDeviceClass.TEMPERATURE, SensorStateClass.MEASUREMENT),
        (["Solar", "Wärmemenge"], True, "kWh", SensorDeviceClass.ENERGY, SensorStateClass.TOTAL_INCREASING),
        (["Kessel", "Gesamtverbrauch"], True, "kg", SensorDeviceClass.WEIGHT, SensorStateClass.TOTAL_INCREASING),
        (["Lager", "Vorrat"], True, "kg", SensorDeviceClass.WEIGHT, SensorStateClass.MEASUREMENT),
        (["Solar", "Ertrag gestern"], True, "kWh", SensorDeviceClass.ENERGY, None),
        (["Kessel", "Kesseldruck"], True, "bar", SensorDeviceClass.PRESSURE, SensorStateClass.MEASUREMENT),
        (["FWM", "Durchfluss"], True, "l/min", SensorDeviceClass.VOLUME_FLOW_RATE, SensorStateClass.MEASUREMENT),
        (["Solar", "Leistung"], True, "kW", SensorDeviceClass.POWER, SensorStateClass.MEASUREMENT),
        (["Kessel", "Zustand"], False, None, None, None),
    ],
)
def test_eta_weiterer_wert_device_class_und_state_class(
    pfad, zahl, einheit, erwartete_device_class, erwartete_state_class
):
    dummy_coordinator = SimpleNamespace(
        config_entry=SimpleNamespace(entry_id="test"),
        device_info=None,
        data={},
    )
    eintrag = {
        "uri": "/1/2/0/0/999",
        "fub": pfad[0],
        "pfad": pfad[1:],
        "zahl": zahl,
        **({"einheit": einheit, "stellen": 1} if zahl else {}),
    }
    sensor = ETAWeitererWert(dummy_coordinator, "wert_1_2_0_0_999", eintrag)
    assert sensor.device_class == erwartete_device_class
    assert sensor.state_class == erwartete_state_class
