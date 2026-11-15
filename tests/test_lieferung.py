"""Pelletpreis, Vorrat des Lagers und die Aktion "Pelletlieferung eintragen".

Nach einer Lieferung ändern sich zwei Dinge: der Preis und der Vorrat. Der
Preis stand bisher nur im Formular unter Konfigurieren; jetzt ist er auch
ein Zahlenfeld. Den Vorrat ("Lager > Vorrat") meldet eine echte Anlage als
beschreibbar, in kg mit Skalierung 10, von -100000 bis 100000 kg - so
antwortet hier die Testanlage, wenn vorrat_schreibbar gesetzt ist.

Die Aktion merkt sich die Lieferung, übernimmt den Preis und erhöht den
Vorrat an der Anlage um die gelieferte Menge.
"""

from __future__ import annotations

from datetime import date

import pytest
from homeassistant.exceptions import HomeAssistantError

from eta_heating_ws import entitaet_vorgesehen
from eta_heating_ws import number as number_platform
from eta_heating_ws.const import (
    CONF_LIEFERUNGEN,
    CONF_PELLET_PREIS,
    MAX_LIEFERUNGEN,
)

from .test_config_flow import optionen, options_schritt
from .test_sensors import setup_integration

VORRAT = "/264/10201/0/0/12015"
HEUTE = date(2026, 11, 15)


async def lager_von(hass, entry, vorrat_schreibbar=True, schreibzugriff=True, preis=None):
    """Richtet Kessel und Pelletlager ein und gibt Koordinator und Zahlenfelder nach Schlüssel zurück."""
    hass.session.vorrat_schreibbar = vorrat_schreibbar
    entry.data["components"] = [*entry.data["components"], "lager"]
    entry.data["enable_switches"] = schreibzugriff
    if preis is not None:
        entry.data[CONF_PELLET_PREIS] = preis
    coordinator, _ = await setup_integration(hass, entry)
    gesammelt: list = []
    await number_platform.async_setup_entry(hass, entry, gesammelt.extend)
    for zahl in gesammelt:
        zahl.async_write_ha_state = lambda: None
    hass.session.gesetzte_werte.clear()
    return coordinator, {zahl.translation_key: zahl for zahl in gesammelt}


async def test_vorrat_laesst_sich_einstellen(hass, entry):
    coordinator, zahlen = await lager_von(hass, entry)
    vorrat = zahlen["lager_vorrat_stellen"]

    assert coordinator.zahl_defs["lager_vorrat_stellen"]["uri"] == VORRAT
    assert vorrat.native_value == 3200
    assert vorrat.native_unit_of_measurement == "kg"
    assert (vorrat.native_min_value, vorrat.native_max_value) == (0, 100000), (
        "die Anlage ließe auch negative Werte zu - hier nicht"
    )
    assert vorrat.entity_id == "number.eta_heizung_lager_vorrat"

    await vorrat.async_set_native_value(5000)

    assert hass.session.gesetzte_werte == [(VORRAT, "50000")]


@pytest.mark.parametrize(
    "vorrat_schreibbar, schreibzugriff", [(False, True), (True, False)]
)
async def test_vorrat_nur_wenn_die_anlage_ihn_beschreibbar_meldet_und_mit_schreibzugriff(
    hass, entry, vorrat_schreibbar, schreibzugriff
):
    coordinator, zahlen = await lager_von(hass, entry, vorrat_schreibbar, schreibzugriff)

    assert "lager_vorrat_stellen" not in zahlen
    assert coordinator.vorrat_an_der_anlage is False


async def test_pelletpreis_ist_derselbe_wert_wie_im_formular(hass, entry):
    coordinator, zahlen = await lager_von(hass, entry, preis=310.0)
    preis = zahlen["pellet_preis"]

    assert preis.native_value == 310.0
    assert preis.native_unit_of_measurement == "EUR/t"
    assert preis.entity_id == "number.eta_heizung_pelletpreis"
    assert preis.unique_id == "eta_static_testeintrag_pellet_preis"

    await preis.async_set_native_value(289.5)

    assert coordinator.pellet_preis == 289.5
    assert entry.options[CONF_PELLET_PREIS] == 289.5, "übersteht den Neustart und steht im Formular"
    assert not getattr(hass.config_entries, "neu_laden_bestellt", 0), (
        "die Kostensensoren rechnen sofort mit dem neuen Preis"
    )
    assert hass.session.gesetzte_werte == [], "der Preis steht nur in Home Assistant"


@pytest.mark.parametrize("vorher, nachher", [(0.0, 300.0), (300.0, 0.0)])
async def test_preis_von_oder_auf_null_laedt_neu(hass, entry, vorher, nachher):
    """Dann entstehen die Kostensensoren - oder fallen weg."""
    _, zahlen = await lager_von(hass, entry, preis=vorher)

    await zahlen["pellet_preis"].async_set_native_value(nachher)

    assert hass.config_entries.neu_laden_bestellt == 1


async def test_preis_ausserhalb_der_grenzen_wird_nicht_gemerkt(hass, entry):
    coordinator, zahlen = await lager_von(hass, entry, preis=310.0)

    with pytest.raises(HomeAssistantError):
        await zahlen["pellet_preis"].async_set_native_value(5000)

    assert coordinator.pellet_preis == 310.0


def test_pelletpreis_bleibt_mit_kessel_oder_lager():
    assert entitaet_vorgesehen("pellet_preis", ["kessel"], False, True) is True
    assert entitaet_vorgesehen("pellet_preis", ["lager"], False, True) is True
    assert entitaet_vorgesehen("pellet_preis", ["puffer"], False, True) is False


async def test_lieferung_erhoeht_den_vorrat_an_der_anlage(hass, entry):
    coordinator, zahlen = await lager_von(hass, entry, preis=310.0)

    neu = await coordinator.async_lieferung_eintragen(HEUTE, 4000, 289.5)

    assert neu == 7200
    assert hass.session.gesetzte_werte == [(VORRAT, "72000")], "3200 kg + 4000 kg, roh mit Skalierung 10"
    assert coordinator.pellet_preis == 289.5
    assert entry.options[CONF_LIEFERUNGEN] == [
        {"datum": "2026-11-15", "menge": 4000.0, "preis": 289.5}
    ]
    assert zahlen["pellet_preis"].extra_state_attributes == {
        "lieferungen": [{"datum": "2026-11-15", "menge": 4000.0, "preis": 289.5}]
    }


async def test_lieferung_ohne_preis_laesst_den_preis_stehen(hass, entry):
    coordinator, _ = await lager_von(hass, entry, preis=310.0)

    await coordinator.async_lieferung_eintragen(HEUTE, 2000)

    assert coordinator.pellet_preis == 310.0
    assert entry.options[CONF_LIEFERUNGEN] == [{"datum": "2026-11-15", "menge": 2000.0}]


@pytest.mark.parametrize(
    "vorrat_schreibbar, schreibzugriff", [(False, True), (True, False)]
)
async def test_ohne_beschreibbaren_vorrat_wird_nur_gemerkt(
    hass, entry, vorrat_schreibbar, schreibzugriff
):
    """Dann stellt man den Vorrat wie bisher am Display ein."""
    coordinator, _ = await lager_von(hass, entry, vorrat_schreibbar, schreibzugriff)

    neu = await coordinator.async_lieferung_eintragen(HEUTE, 4000, 300)

    assert neu is None
    assert hass.session.gesetzte_werte == []
    assert entry.options[CONF_LIEFERUNGEN] == [
        {"datum": "2026-11-15", "menge": 4000.0, "preis": 300.0}
    ]
    assert coordinator.pellet_preis == 300.0


async def test_lehnt_die_anlage_ab_ist_nichts_gemerkt(hass, entry):
    coordinator, _ = await lager_von(hass, entry, preis=310.0)
    hass.session.fail_uris.add("0/0/12015")

    with pytest.raises(HomeAssistantError):
        await coordinator.async_lieferung_eintragen(HEUTE, 4000, 289.5)

    assert CONF_LIEFERUNGEN not in entry.options
    assert coordinator.pellet_preis == 310.0


async def test_mehr_als_die_anlage_annimmt_wird_nicht_geschrieben(hass, entry):
    coordinator, _ = await lager_von(hass, entry)

    with pytest.raises(HomeAssistantError, match="höchstens 100000 kg"):
        await coordinator.async_lieferung_eintragen(HEUTE, 99000)

    assert hass.session.gesetzte_werte == []
    assert CONF_LIEFERUNGEN not in entry.options


async def test_ohne_gemeldeten_vorrat_wird_nichts_eingetragen(hass, entry):
    coordinator, _ = await lager_von(hass, entry)
    coordinator.data.pop("lager_vorrat")

    with pytest.raises(HomeAssistantError):
        await coordinator.async_lieferung_eintragen(HEUTE, 4000)

    assert hass.session.gesetzte_werte == []
    assert CONF_LIEFERUNGEN not in entry.options


async def test_nur_die_letzten_lieferungen_bleiben(hass, entry):
    coordinator, zahlen = await lager_von(hass, entry, vorrat_schreibbar=False)

    for tag in range(MAX_LIEFERUNGEN + 3):
        await coordinator.async_lieferung_eintragen(date(2026, 1, 1 + tag), 100 + tag)

    gemerkt = entry.options[CONF_LIEFERUNGEN]
    assert len(gemerkt) == MAX_LIEFERUNGEN
    assert gemerkt[-1] == {"datum": "2026-01-23", "menge": 122.0}
    assert zahlen["pellet_preis"].extra_state_attributes["lieferungen"][0]["datum"] == "2026-01-23", (
        "die neueste zuerst"
    )


async def test_konfigurieren_behaelt_die_lieferungen(monkeypatch):
    """Die Optionen werden beim Speichern ersetzt - die Lieferungen stehen in keinem Formular."""
    lieferungen = [{"datum": "2026-11-15", "menge": 4000.0, "preis": 289.5}]
    bisher = {**optionen(), CONF_LIEFERUNGEN: lieferungen}
    flow, ergebnis = await options_schritt(monkeypatch, bisher, optionen())
    for _ in range(6):
        if ergebnis["type"] == "create_entry":
            break
        schema = ergebnis.get("data_schema")
        vorgaben = {str(feld): feld.default() for feld in schema.schema} if schema else {}
        ergebnis = await getattr(flow, f"async_step_{ergebnis['step_id']}")(vorgaben)

    assert ergebnis["type"] == "create_entry"
    assert ergebnis["data"][CONF_LIEFERUNGEN] == lieferungen


async def test_aktion_nimmt_datum_menge_und_preis(hass, entry):
    """Die Aktion ist bei Home Assistant angemeldet und reicht an den Koordinator weiter."""
    from types import SimpleNamespace

    from eta_heating_ws import aktionen

    coordinator, _ = await lager_von(hass, entry, preis=310.0)
    entry.runtime_data = coordinator
    angemeldet: dict = {}

    class Dienste:
        def async_register(self, domain, name, funktion, schema=None, **kwargs):
            angemeldet[name] = (funktion, schema)

    geladen = SimpleNamespace(async_loaded_entries=lambda domain: [entry])
    aktionen.async_aktionen_registrieren(SimpleNamespace(services=Dienste(), config_entries=geladen))
    funktion, schema = angemeldet["lieferung_eintragen"]

    daten = schema({"datum": "2026-11-15", "menge": "4000", "preis": 289.5})
    antwort = await funktion(SimpleNamespace(data=daten))

    assert antwort == {"vorrat_geschrieben": True, "vorrat": 7200}
    assert entry.options[CONF_LIEFERUNGEN][-1] == {"datum": "2026-11-15", "menge": 4000.0, "preis": 289.5}

    import voluptuous as vol

    for falsch in ({"menge": 0}, {"menge": 4000, "preis": -1}, {"preis": 300}):
        with pytest.raises(vol.Invalid):
            schema(falsch)


async def test_im_lager_steht_nichts_nach_dem_komma(hass, entry):
    """Die Anlage führt den Vorrat auf 100 Gramm genau - gezeigt werden ganze Kilogramm."""
    from eta_heating_ws.sensor import ETALagerMaximumSensor, ETAMeasurementSensor

    coordinator, zahlen = await lager_von(hass, entry)
    for key in ("lager_vorrat", "lager_warngrenze", "lager_maximum"):
        coordinator.data[key].dec_places = 1

    for key in ("lager_vorrat", "lager_warngrenze"):
        sensor = ETAMeasurementSensor(coordinator, key, coordinator.sensor_defs[key])
        assert sensor.suggested_display_precision == 0, key
    maximum = ETALagerMaximumSensor(coordinator, coordinator.sensor_defs["lager_maximum"])
    assert maximum.suggested_display_precision == 0

    hass.session.geschrieben[VORRAT] = "19167"
    await coordinator.async_refresh()
    assert coordinator.zahl("lager_vorrat") == pytest.approx(1916.7)
    assert zahlen["lager_vorrat_stellen"].native_value == 1917, "das Zahlenfeld zeigt ganze Kilogramm"

    neu = await coordinator.async_lieferung_eintragen(HEUTE, 4000)
    assert neu == pytest.approx(5916.7), "gerechnet wird mit dem genauen Wert"
    assert hass.session.gesetzte_werte[-1] == (VORRAT, "59167")
