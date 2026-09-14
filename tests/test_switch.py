"""Tests für die Schalter von Kessel und Heizkreisen.

Ein Schalter schreibt in eine Heizungssteuerung. Deshalb liegt der
Schwerpunkt hier nicht darauf, dass er entsteht, sondern darauf, dass er
in allen unklaren Fällen **nicht** entsteht - und dass nie ein geratener
Rohwert geschrieben wird.
"""

from __future__ import annotations

import pytest

import eta_webservices
from eta_webservices import switch as switch_platform

from .conftest import entity_name
from .test_sensors import setup_integration


async def setup_mit_schaltern(hass, entry):
    coordinator = (await setup_integration(hass, entry))[0]
    schalter: list = []
    await switch_platform.async_setup_entry(hass, entry, schalter.extend)
    return coordinator, {entity_name(s, "de"): s for s in schalter}


def entity_name_switch(entity) -> str:
    import json

    from .conftest import UEBERSETZUNGEN

    daten = json.loads((UEBERSETZUNGEN / "de.json").read_text(encoding="utf-8"))
    return daten["entity"]["switch"][entity.translation_key]["name"]


async def schalter_von(hass, entry):
    """Richtet die Integration ein und gibt die Schalter nach Namen zurück.

    async_write_ha_state wird stillgelegt: Es schreibt in die
    Zustandsmaschine von Home Assistant, die es hier ohne laufende
    Instanz nicht gibt. Für die Tests zählt, welchen Zustand die Entität
    meldet, nicht wie sie ihn veröffentlicht.
    """
    coordinator, _ = await setup_integration(hass, entry)
    gesammelt: list = []
    await switch_platform.async_setup_entry(hass, entry, gesammelt.extend)
    for eintrag in gesammelt:
        eintrag.async_write_ha_state = lambda: None
    return coordinator, {entity_name_switch(s): s for s in gesammelt}


async def test_schalter_uebernimmt_die_rohwerte_der_anlage(hass, entry):
    """Die Rohwerte stammen aus varinfo, nicht aus einer Annahme."""
    coordinator, _ = await schalter_von(hass, entry)
    if not coordinator.switch_defs:
        pytest.skip("im Fixture ist kein Schalter enthalten")

    for definition in coordinator.switch_defs.values():
        assert definition["ein_roh"] == "950"
        assert definition["aus_roh"] == "949"
        assert definition["ein_text"] == "Heizbetrieb"


async def test_kein_schalter_wenn_die_anlage_nicht_schreiben_laesst(hass, entry):
    hass.session.schreibbar = False
    coordinator, schalter = await schalter_von(hass, entry)
    assert coordinator.switch_defs == {}
    assert schalter == {}


async def test_kein_schalter_ohne_varinfo(hass, entry):
    """Ältere Anlagen kennen varinfo nicht - dann lieber gar kein Schalter."""
    hass.session.varinfo_unterstuetzt = False
    coordinator, schalter = await schalter_von(hass, entry)
    assert coordinator.switch_defs == {}
    assert schalter == {}


async def test_kein_schalter_bei_mehr_als_zwei_zustaenden(hass, entry, monkeypatch):
    async def drei_zustaende(uri):
        return {
            "writable": True,
            "raw_values": {"Aus": "1", "Heizen": "2", "Absenken": "3"},
            "valid_values": ["Aus", "Heizen", "Absenken"],
            "type": "TEXT",
        }

    from eta_webservices.api import ETAApiClient

    monkeypatch.setattr(ETAApiClient, "async_get_varinfo", lambda self, uri: drei_zustaende(uri))
    coordinator, _ = await schalter_von(hass, entry)
    assert coordinator.switch_defs == {}


async def test_kein_schalter_wenn_unklar_ist_was_aus_bedeutet(hass, entry, monkeypatch):
    async def unklar(uri):
        return {
            "writable": True,
            "raw_values": {"Modus A": "1", "Modus B": "2"},
            "valid_values": ["Modus A", "Modus B"],
            "type": "TEXT",
        }

    from eta_webservices.api import ETAApiClient

    monkeypatch.setattr(ETAApiClient, "async_get_varinfo", lambda self, uri: unklar(uri))
    coordinator, _ = await schalter_von(hass, entry)
    assert coordinator.switch_defs == {}


async def test_schalter_erzeugt_keinen_doppelten_sensor(hass, entry):
    coordinator, _ = await setup_integration(hass, entry)
    from eta_webservices import sensor as sensor_platform

    sensoren: list = []
    await sensor_platform.async_setup_entry(hass, entry, sensoren.extend)
    schluessel = {s._key for s in sensoren}
    assert not (schluessel & set(coordinator.switch_defs))


async def test_einschalten_schreibt_den_rohwert_der_anlage(hass, entry):
    coordinator, schalter = await schalter_von(hass, entry)
    if not schalter:
        pytest.skip("im Fixture ist kein Schalter enthalten")

    einer = next(iter(schalter.values()))
    await einer.async_turn_on()

    assert hass.session.gesetzte_werte
    uri, wert = hass.session.gesetzte_werte[-1]
    assert wert == "950"
    assert uri == einer._uri


async def test_ausschalten_schreibt_den_aus_rohwert(hass, entry):
    _, schalter = await schalter_von(hass, entry)
    if not schalter:
        pytest.skip("im Fixture ist kein Schalter enthalten")

    einer = next(iter(schalter.values()))
    await einer.async_turn_off()
    assert hass.session.gesetzte_werte[-1][1] == "949"


async def test_abgelehnter_schaltbefehl_meldet_sich(hass, entry):
    from homeassistant.exceptions import HomeAssistantError

    _, schalter = await schalter_von(hass, entry)
    if not schalter:
        pytest.skip("im Fixture ist kein Schalter enthalten")

    hass.session.schreiben_erlaubt = False
    einer = next(iter(schalter.values()))
    with pytest.raises(HomeAssistantError):
        await einer.async_turn_on()


async def test_schalter_liest_seinen_zustand_von_der_anlage(hass, entry):
    coordinator, schalter = await schalter_von(hass, entry)
    if not schalter:
        pytest.skip("im Fixture ist kein Schalter enthalten")

    einer = next(iter(schalter.values()))
    assert einer.is_on is True


async def test_switch_plattform_ist_eingetragen():
    from eta_webservices.const import PLATFORMS

    assert "switch" in [str(p) for p in PLATFORMS]


async def test_schalter_meldet_sofort_zurueck(hass, entry):
    """Ohne Vorwegnahme springt der Schalter im Dashboard zurück.

    Home Assistant fragt die Anlage nach einem Schaltbefehl erst
    verzögert erneut ab. Solange muss der Schalter den erwarteten Zustand
    zeigen, sonst wirkt die Bedienung kaputt.
    """
    _, schalter = await schalter_von(hass, entry)
    if not schalter:
        pytest.skip("im Fixture ist kein Schalter enthalten")

    einer = next(iter(schalter.values()))
    assert einer.is_on is True

    await einer.async_turn_off()
    assert einer.is_on is False, "Schalter zeigt nicht sofort den neuen Zustand"


async def test_nach_der_abfrage_gilt_wieder_die_anlage(hass, entry):
    """Die Vorwegnahme darf einen abweichenden Anlagenzustand nicht überdecken."""
    coordinator, schalter = await schalter_von(hass, entry)
    if not schalter:
        pytest.skip("im Fixture ist kein Schalter enthalten")

    einer = next(iter(schalter.values()))
    await einer.async_turn_off()
    assert einer.is_on is False

    einer._handle_coordinator_update()
    assert einer.is_on is True, "Anlagenzustand setzt sich nicht wieder durch"


async def test_beide_komponenten_bekommen_ihren_schalter(hass, entry):
    coordinator, schalter = await schalter_von(hass, entry)
    assert "kessel_schalter" in coordinator.switch_defs
    assert "heizkreis_schalter" in coordinator.switch_defs
    assert set(schalter) == {"Kessel", "Heizkreis 1"}


async def test_ohne_freigabe_entsteht_kein_schalter(hass, entry):
    """Schalter sind standardmäßig aus - Schreibzugriff will gewollt sein."""
    entry.data["enable_switches"] = False
    coordinator, schalter = await schalter_von(hass, entry)
    assert coordinator.switch_defs == {}
    assert schalter == {}


async def test_standard_ist_ohne_schalter(hass, entry):
    """Ein Eintrag ohne die Option bekommt keine Schalter untergeschoben."""
    entry.data.pop("enable_switches")
    coordinator, schalter = await schalter_von(hass, entry)
    assert coordinator.switch_defs == {}
    assert schalter == {}


async def test_ohne_freigabe_wird_gar_nicht_erst_nachgefragt(hass, entry):
    """Ist der Schreibzugriff aus, spart das auch die varinfo-Abfragen."""
    entry.data["enable_switches"] = False
    coordinator, _ = await schalter_von(hass, entry)
    assert not any(k.endswith("_schalter") for k in coordinator.sensor_defs)
