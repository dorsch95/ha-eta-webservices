"""Das Fassungsvermögen des Pelletlagers: ein Zahlenfeld, zwei Orte zum Merken.

Kann das Feld an die Anlage schreiben, stellt es dort "Maximaler Vorrat" -
das prüft test_zahlen.py. Hier geht es um den anderen Fall: ohne
Schreibzugriff, oder an einer Anlage, die den Wert nicht führt oder
nicht beschreibbar meldet. Dann merkt sich das Feld seinen Wert in Home
Assistant, und Füllstand und Sensor rechnen damit. Ältere Regelungen
führen "Maximaler Vorrat" gar nicht im Menübaum - dort blieb der
Füllstand sonst leer.
"""

from __future__ import annotations

import pytest
from homeassistant.exceptions import HomeAssistantError

from eta_heating_ws import binary_sensor as binary_sensor_platform
from eta_heating_ws import entitaet_vorgesehen
from eta_heating_ws import number as number_platform
from eta_heating_ws.api import ETAValue
from eta_heating_ws.const import CONF_LAGER_MAXIMUM

from .conftest import FIXTURES
from .test_config_flow import _options_schema, optionen, options_schritt
from .test_sensors import setup_integration

ALTE_ANLAGE = (FIXTURES / "menu_alt.xml").read_text(encoding="utf-8")
URI = "/264/10201/0/0/12790"


def kg(zahl: float) -> ETAValue:
    return ETAValue(zahl, str(zahl), "kg", False, 0)


async def mit_lager(hass, entry, schreibzugriff=False, gemerkt=None):
    """Richtet Kessel und Pelletlager ein, mit 3200 kg Vorrat.

    Gibt Koordinator, Sensoren nach Namen und das Zahlenfeld zurück.
    gemerkt: was das Zahlenfeld vor diesem Start in Home Assistant
    gespeichert hat.
    """
    entry.data["components"] = ["kessel", "lager"]
    entry.data["enable_switches"] = schreibzugriff
    if gemerkt is not None:
        entry.options = {CONF_LAGER_MAXIMUM: gemerkt}
    coordinator, by_name = await setup_integration(hass, entry)
    coordinator.data["lager_vorrat"] = kg(3200)
    gesammelt: list = []
    await number_platform.async_setup_entry(hass, entry, gesammelt.extend)
    [zahl] = [z for z in gesammelt if z.translation_key == "lager_maximum_stellen"]
    zahl.async_write_ha_state = lambda: None
    return coordinator, by_name, zahl


async def aeltere_anlage(hass, entry, gemerkt=None):
    hass.session.menu = ALTE_ANLAGE
    hass.session.varinfo_unterstuetzt = False
    return await mit_lager(hass, entry, gemerkt=gemerkt)


async def test_ohne_schreibzugriff_zeigt_das_feld_den_wert_der_anlage(hass, entry):
    coordinator, by_name, zahl = await mit_lager(hass, entry)

    assert isinstance(zahl, number_platform.ETALagerMaximumEigen)
    assert zahl.entity_id == "number.eta_heizung_lager_fassungsvermogen"
    assert zahl.unique_id == "eta_static_testeintrag_lager_maximum_stellen"
    assert zahl.native_value == 6400
    assert (zahl.native_min_value, zahl.native_max_value) == (0, 100000)
    assert zahl.extra_state_attributes == {"gespeichert": "Home Assistant", "wert_der_anlage": 6400}
    assert coordinator.lager_fassungsvermoegen_quelle() == "Anlage"
    assert by_name["Lager Füllstand"].native_value == 50


async def test_ohne_schreibzugriff_merkt_sich_home_assistant_den_wert(hass, entry):
    coordinator, by_name, zahl = await mit_lager(hass, entry)
    hass.session.gesetzte_werte.clear()

    await zahl.async_set_native_value(8000)

    assert hass.session.gesetzte_werte == [], "an die Anlage geht nichts"
    assert entry.options == {CONF_LAGER_MAXIMUM: 8000}, "übersteht den Neustart"
    assert zahl.native_value == 8000
    assert coordinator.lager_fassungsvermoegen() == 8000
    assert coordinator.lager_fassungsvermoegen_quelle() == "Home Assistant"
    assert by_name["Lager Füllstand"].native_value == 40
    assert by_name["Lager Füllstand"].extra_state_attributes == {
        "fassungsvermoegen": 8000,
        "fassungsvermoegen_quelle": "Home Assistant",
    }


async def test_sensor_folgt_dem_zahlenfeld_ohne_neu_laden(hass, entry):
    _, by_name, zahl = await mit_lager(hass, entry)
    sensor = by_name["Lager Fassungsvermögen"]
    assert sensor.native_value == 6400
    assert sensor.extra_state_attributes["quelle"] == "Anlage"

    await zahl.async_set_native_value(8000)

    assert sensor.native_value == 8000
    assert sensor.native_unit_of_measurement == "kg"
    assert sensor.extra_state_attributes["quelle"] == "Home Assistant"
    assert sensor.extra_state_attributes["wert_der_anlage"] == 6400


async def test_null_verwirft_den_eigenen_wert(hass, entry):
    coordinator, by_name, zahl = await mit_lager(hass, entry, gemerkt=8000)
    assert zahl.native_value == 8000, "nach dem Neustart wieder da"

    await zahl.async_set_native_value(0)

    assert entry.options == {}
    assert zahl.native_value == 6400, "wieder der Wert der Anlage"
    assert by_name["Lager Füllstand"].native_value == 50
    assert coordinator.lager_fassungsvermoegen_quelle() == "Anlage"


async def test_wert_ausserhalb_der_grenzen_wird_nicht_gemerkt(hass, entry):
    _, _, zahl = await mit_lager(hass, entry)

    with pytest.raises(HomeAssistantError):
        await zahl.async_set_native_value(100001)
    with pytest.raises(HomeAssistantError):
        await zahl.async_set_native_value(-1)

    assert entry.options == {}


async def test_mit_schreibzugriff_zaehlt_allein_die_anlage(hass, entry):
    """Ein früher gemerkter Wert gilt nicht mehr, sobald das Feld an die Anlage schreibt."""
    coordinator, by_name, zahl = await mit_lager(hass, entry, schreibzugriff=True, gemerkt=8000)

    assert isinstance(zahl, number_platform.ETAZahl)
    assert zahl.extra_state_attributes == {"gespeichert": "Anlage"}
    assert zahl.native_value == 6400
    assert coordinator.lager_maximum_eigen is None
    assert by_name["Lager Füllstand"].native_value == 50
    assert by_name["Lager Fassungsvermögen"].native_value == 6400


async def test_schreiben_an_die_anlage_verwirft_den_gemerkten_wert(hass, entry):
    """Sonst gälte er wieder, wenn der Schreibzugriff später wegfällt."""
    coordinator, _, zahl = await mit_lager(hass, entry, schreibzugriff=True, gemerkt=8000)
    hass.session.gesetzte_werte.clear()

    await zahl.async_set_native_value(7000)

    assert hass.session.gesetzte_werte == [(URI, "70000")]
    assert entry.options == {}
    assert coordinator.lager_maximum_eingetragen == 0


async def test_meldet_die_anlage_den_wert_nicht_beschreibbar_bleibt_er_in_home_assistant(
    hass, entry
):
    hass.session.lager_schreibbar = False
    coordinator, by_name, zahl = await mit_lager(hass, entry, schreibzugriff=True)
    hass.session.gesetzte_werte.clear()

    await zahl.async_set_native_value(8000)

    assert isinstance(zahl, number_platform.ETALagerMaximumEigen)
    assert hass.session.gesetzte_werte == []
    assert by_name["Lager Füllstand"].native_value == 40


async def test_aeltere_regelung_ohne_eintrag_hat_keinen_fuellstand(hass, entry):
    coordinator, by_name, zahl = await aeltere_anlage(hass, entry)

    assert "lager_maximum" not in coordinator.discovered_uris
    assert zahl.native_value is None
    assert coordinator.lager_fassungsvermoegen() is None
    assert by_name["Lager Füllstand"].native_value is None
    sensor = by_name["Lager Fassungsvermögen"]
    assert sensor.native_value is None
    assert sensor.extra_state_attributes["anzeige"] == "-"


async def test_aeltere_regelung_rechnet_mit_dem_zahlenfeld(hass, entry):
    coordinator, by_name, zahl = await aeltere_anlage(hass, entry)

    await zahl.async_set_native_value(6400)

    assert by_name["Lager Füllstand"].native_value == 50
    sensor = by_name["Lager Fassungsvermögen"]
    assert sensor.native_value == 6400
    assert sensor.native_unit_of_measurement == "kg"
    assert sensor.extra_state_attributes["wert_der_anlage"] is None
    assert "anzeige" not in sensor.extra_state_attributes


async def test_warnung_nennt_den_fuellstand_nach_dem_zahlenfeld(hass, entry):
    _, _, zahl = await mit_lager(hass, entry)
    gesammelt: list = []
    await binary_sensor_platform.async_setup_entry(hass, entry, gesammelt.extend)
    warnung = next(e for e in gesammelt if e.translation_key == "lager_niedrig")

    await zahl.async_set_native_value(8000)

    assert warnung.extra_state_attributes["fuellstand_prozent"] == 40.0


async def test_meldet_die_anlage_null_bleibt_der_fuellstand_leer(hass, entry):
    """Eine Division durch 0 kg gibt es nicht - ab Werk steht dort teils 0."""
    coordinator, by_name, _ = await mit_lager(hass, entry)
    coordinator.data["lager_maximum"] = kg(0)

    assert coordinator.lager_fassungsvermoegen() is None
    assert by_name["Lager Füllstand"].native_value is None


def test_formular_fragt_nicht_nach_dem_fassungsvermoegen():
    """Dafür gibt es das Zahlenfeld am Gerät - eine Stelle, nicht zwei."""
    assert CONF_LAGER_MAXIMUM not in _options_schema({}).schema


async def test_konfigurieren_behaelt_den_gemerkten_wert(monkeypatch):
    """Die Optionen werden beim Speichern ersetzt - der Wert steht in keinem Formular."""
    bisher = {**optionen(), CONF_LAGER_MAXIMUM: 8000.0}
    flow, ergebnis = await options_schritt(monkeypatch, bisher, optionen())
    for _ in range(4):
        if ergebnis["type"] == "create_entry":
            break
        ergebnis = await getattr(flow, f"async_step_{ergebnis['step_id']}")(
            {str(feld): feld.default() for feld in ergebnis["data_schema"].schema}
        )

    assert ergebnis["type"] == "create_entry"
    assert ergebnis["data"][CONF_LAGER_MAXIMUM] == 8000.0


def test_zahlenfeld_gibt_es_mit_pelletlager_auch_ohne_schreibzugriff():
    """Danach räumt die Integration auf, wenn eine Komponente wegfällt."""
    assert entitaet_vorgesehen("lager_maximum_stellen", ["kessel", "lager"], True, True) is True
    assert entitaet_vorgesehen("lager_maximum_stellen", ["kessel", "lager"], False, True) is True
    assert entitaet_vorgesehen("lager_maximum_stellen", ["kessel"], True, True) is False
    assert entitaet_vorgesehen("lager_maximum_stellen", ["kessel"], False, True) is False


async def test_diagnose_nennt_fassungsvermoegen_und_quelle(hass, entry):
    from eta_heating_ws.diagnostics import async_get_config_entry_diagnostics

    _, _, zahl = await mit_lager(hass, entry)
    await zahl.async_set_native_value(8000)
    bericht = await async_get_config_entry_diagnostics(hass, entry)

    assert bericht["konfiguration"]["lager_fassungsvermoegen"] == 8000
    assert bericht["konfiguration"]["lager_fassungsvermoegen_quelle"] == "Home Assistant"
