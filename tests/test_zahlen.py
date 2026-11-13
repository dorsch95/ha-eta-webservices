"""Das Fassungsvermögen des Pelletlagers aus Home Assistant einstellen.

"Lager > Vorrat > Maximaler Vorrat" steht an der Anlage. Eine echte Anlage
meldet den Wert als beschreibbar, in kg mit Skalierung 10, von 0 bis
100000 kg - so antwortet hier auch die Testanlage. Das Zahlenfeld gibt es
nur mit freigegebenem Schreibzugriff und nur, wenn die Anlage das
Schreiben zulässt.
"""

from __future__ import annotations

import pytest
from homeassistant.exceptions import HomeAssistantError

from eta_heating_ws import entitaet_vorgesehen
from eta_heating_ws import number as number_platform

from .test_sensors import setup_integration

URI = "/264/10201/0/0/12790"


async def zahlen_von(hass, entry, **freigaben):
    """Richtet die Anlage mit Pelletlager ein und gibt die Zahlenfelder nach Schlüssel zurück.

    async_write_ha_state wird stillgelegt, wie bei den Schaltern: Ohne
    laufendes Home Assistant gibt es keine Zustandsmaschine.
    """
    entry.data["components"] = [*entry.data["components"], "lager"]
    entry.data.update(freigaben)
    coordinator, _ = await setup_integration(hass, entry)
    gesammelt: list = []
    await number_platform.async_setup_entry(hass, entry, gesammelt.extend)
    for zahl in gesammelt:
        zahl.async_write_ha_state = lambda: None
    return coordinator, {zahl.translation_key: zahl for zahl in gesammelt}


async def test_fassungsvermoegen_laesst_sich_einstellen(hass, entry):
    coordinator, zahlen = await zahlen_von(hass, entry)

    zahl = zahlen["lager_maximum_stellen"]

    assert coordinator.zahl_defs["lager_maximum_stellen"]["uri"] == URI
    assert zahl.native_value == 6400, "derselbe Wert wie der Sensor Lager Fassungsvermögen"
    assert zahl.native_unit_of_measurement == "kg"
    assert (zahl.native_min_value, zahl.native_max_value) == (0, 100000), "die Grenzen der Anlage"
    assert zahl.entity_id == "number.eta_heizung_lager_fassungsvermogen"
    assert zahl.unique_id == "eta_static_testeintrag_lager_maximum_stellen"


async def test_schreibt_den_rohwert_mit_der_skalierung_der_anlage(hass, entry):
    coordinator, zahlen = await zahlen_von(hass, entry)
    zahl = zahlen["lager_maximum_stellen"]
    hass.session.gesetzte_werte.clear()

    await zahl.async_set_native_value(8000)

    assert hass.session.gesetzte_werte == [(URI, "80000")], "8000 kg sind roh 80000"
    assert zahl.native_value == 8000
    assert coordinator.zahl("lager_maximum") == 8000, "der Sensor zeigt den neuen Wert nach dem Neulesen"


async def test_neuer_wert_steht_sofort_da_auch_wenn_die_anlage_ihn_noch_nicht_meldet(hass, entry):
    """Echte Anlagen übernehmen einen geschriebenen Wert nicht sofort in ihre Antworten."""
    coordinator, zahlen = await zahlen_von(hass, entry)
    zahl = zahlen["lager_maximum_stellen"]

    hass.session.traege = True
    await zahl.async_set_native_value(8000)
    zahl._handle_coordinator_update()

    assert coordinator.zahl("lager_maximum") == 6400, "die Anlage meldet noch den alten Wert"
    assert zahl.native_value == 8000

    hass.session.traege = False
    await coordinator.async_refresh()
    zahl._handle_coordinator_update()

    assert zahl._erwartet is None, "bestätigt - ab jetzt zählt wieder, was die Anlage meldet"
    assert zahl.native_value == 8000


async def test_wert_ausserhalb_der_grenzen_wird_nicht_geschrieben(hass, entry):
    _, zahlen = await zahlen_von(hass, entry)
    zahl = zahlen["lager_maximum_stellen"]
    hass.session.gesetzte_werte.clear()

    with pytest.raises(HomeAssistantError):
        await zahl.async_set_native_value(100001)
    with pytest.raises(HomeAssistantError):
        await zahl.async_set_native_value(-1)

    assert hass.session.gesetzte_werte == []


async def test_ablehnung_der_anlage_wird_gemeldet(hass, entry):
    _, zahlen = await zahlen_von(hass, entry)
    zahl = zahlen["lager_maximum_stellen"]

    hass.session.fail_uris.add("12790")
    with pytest.raises(HomeAssistantError):
        await zahl.async_set_native_value(7000)

    assert zahl.native_value == 6400 or zahl.native_value is None, "kein vorweggenommener Wert"
    assert zahl._erwartet is None


async def test_ohne_schreibzugriff_kein_zahlenfeld(hass, entry):
    coordinator, zahlen = await zahlen_von(hass, entry, enable_switches=False)

    assert zahlen == {}
    assert coordinator.zahl_defs == {}
    assert "lager_maximum" in coordinator.sensor_defs, "der Sensor bleibt"


async def test_kein_zahlenfeld_wenn_die_anlage_das_schreiben_nicht_zulaesst(hass, entry):
    hass.session.lager_schreibbar = False

    _, zahlen = await zahlen_von(hass, entry)

    assert zahlen == {}


async def test_ohne_pelletlager_kein_zahlenfeld(hass, entry):
    coordinator, _ = await setup_integration(hass, entry)

    assert coordinator.zahl_defs == {}


def test_zahlenfeld_gehoert_zu_schreibzugriff_und_pelletlager():
    """Danach räumt die Integration auf, wenn eine Freigabe oder Komponente wegfällt."""
    assert entitaet_vorgesehen("lager_maximum_stellen", ["kessel", "lager"], True, True) is True
    assert entitaet_vorgesehen("lager_maximum_stellen", ["kessel", "lager"], False, True) is False
    assert entitaet_vorgesehen("lager_maximum_stellen", ["kessel"], True, True) is False
