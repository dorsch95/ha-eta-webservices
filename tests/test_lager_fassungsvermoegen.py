"""Das Fassungsvermögen des Pelletlagers von Hand eintragen.

Ohne Eintrag gilt "Maximaler Vorrat" der Anlage. Ältere Regelungen führen
ihn nicht im Menübaum - dort bleibt der Füllstand leer, bis in den
Einstellungen ein Fassungsvermögen steht. Ein eingetragener Wert hat auch
an einer Anlage Vorrang, die selbst einen meldet.
"""

from __future__ import annotations

import pytest
import voluptuous as vol

from eta_heating_ws import binary_sensor as binary_sensor_platform
from eta_heating_ws.api import ETAValue
from eta_heating_ws.config_flow import _options_schema
from eta_heating_ws.const import CONF_LAGER_MAXIMUM, MAX_LAGER_MAXIMUM

from .conftest import FIXTURES
from .test_sensors import setup_integration

ALTE_ANLAGE = (FIXTURES / "menu_alt.xml").read_text(encoding="utf-8")


def kg(zahl: float) -> ETAValue:
    return ETAValue(zahl, str(zahl), "kg", False, 0)


async def mit_lager(hass, entry, eingetragen=None):
    entry.data["components"] = ["kessel", "lager"]
    if eingetragen is not None:
        entry.data[CONF_LAGER_MAXIMUM] = eingetragen
    coordinator, by_name = await setup_integration(hass, entry)
    coordinator.data["lager_vorrat"] = kg(3200)
    return coordinator, by_name


async def test_ohne_eintrag_gilt_der_wert_der_anlage(hass, entry):
    coordinator, by_name = await mit_lager(hass, entry)

    assert coordinator.lager_fassungsvermoegen() == 6400
    assert coordinator.lager_fassungsvermoegen_quelle() == "Anlage"
    assert by_name["Lager Füllstand"].native_value == 50
    assert by_name["Lager Fassungsvermögen"].native_value == 6400


async def test_eintrag_hat_vorrang_vor_der_anlage(hass, entry):
    coordinator, by_name = await mit_lager(hass, entry, eingetragen=8000)

    assert coordinator.lager_fassungsvermoegen() == 8000
    assert coordinator.lager_fassungsvermoegen_quelle() == "Einstellung"
    assert by_name["Lager Füllstand"].native_value == 40
    assert by_name["Lager Füllstand"].extra_state_attributes == {
        "fassungsvermoegen": 8000,
        "fassungsvermoegen_quelle": "Einstellung",
    }


async def test_sensor_zeigt_den_eintrag_und_nennt_den_wert_der_anlage(hass, entry):
    _, by_name = await mit_lager(hass, entry, eingetragen=8000)
    sensor = by_name["Lager Fassungsvermögen"]

    assert sensor.native_value == 8000
    assert sensor.native_unit_of_measurement == "kg"
    assert sensor.unique_id.endswith("_lager_maximum"), "dieselbe Entität wie ohne Eintrag"
    assert sensor.extra_state_attributes == {"quelle": "Einstellung", "wert_der_anlage": 6400}


async def aeltere_anlage(hass, entry, eingetragen=None):
    hass.session.menu = ALTE_ANLAGE
    hass.session.varinfo_unterstuetzt = False
    entry.data["enable_switches"] = False
    return await mit_lager(hass, entry, eingetragen)


async def test_aeltere_regelung_ohne_eintrag_hat_keinen_fuellstand(hass, entry):
    coordinator, by_name = await aeltere_anlage(hass, entry)

    assert "lager_maximum" not in coordinator.discovered_uris
    assert coordinator.lager_fassungsvermoegen() is None
    assert by_name["Lager Füllstand"].native_value is None
    assert by_name["Lager Fassungsvermögen"].native_value == "-"


async def test_aeltere_regelung_rechnet_mit_dem_eintrag(hass, entry):
    coordinator, by_name = await aeltere_anlage(hass, entry, eingetragen=6400)

    assert by_name["Lager Füllstand"].native_value == 50
    assert by_name["Lager Fassungsvermögen"].native_value == 6400
    assert by_name["Lager Fassungsvermögen"].extra_state_attributes["wert_der_anlage"] is None


async def test_warnung_nennt_den_fuellstand_nach_dem_eintrag(hass, entry):
    await mit_lager(hass, entry, eingetragen=8000)
    gesammelt: list = []
    await binary_sensor_platform.async_setup_entry(hass, entry, gesammelt.extend)
    warnung = next(e for e in gesammelt if e.translation_key == "lager_niedrig")

    assert warnung.extra_state_attributes["fuellstand_prozent"] == 40.0


async def test_meldet_die_anlage_null_bleibt_der_fuellstand_leer(hass, entry):
    """Eine Division durch 0 kg gibt es nicht - ab Werk steht dort teils 0."""
    coordinator, by_name = await mit_lager(hass, entry)
    coordinator.data["lager_maximum"] = kg(0)

    assert coordinator.lager_fassungsvermoegen() is None
    assert by_name["Lager Füllstand"].native_value is None


def test_formular_fragt_nach_dem_fassungsvermoegen():
    schema = _options_schema({})
    feld = next(k for k in schema.schema if k == CONF_LAGER_MAXIMUM)

    assert feld.default() == 0, "ohne Eintrag gilt der Wert der Anlage"
    assert _options_schema({CONF_LAGER_MAXIMUM: 8000}).schema
    pruefen = schema.schema[feld]
    assert pruefen("7500") == 7500
    with pytest.raises(vol.Invalid):
        pruefen(MAX_LAGER_MAXIMUM + 1)
    with pytest.raises(vol.Invalid):
        pruefen(-1)


async def test_diagnose_nennt_fassungsvermoegen_und_quelle(hass, entry):
    from eta_heating_ws.diagnostics import async_get_config_entry_diagnostics

    await mit_lager(hass, entry, eingetragen=8000)
    bericht = await async_get_config_entry_diagnostics(hass, entry)

    assert bericht["konfiguration"]["lager_fassungsvermoegen"] == 8000
    assert bericht["konfiguration"]["lager_fassungsvermoegen_quelle"] == "Einstellung"
