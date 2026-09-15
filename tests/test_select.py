"""Tests für die Betriebsart der Heizkreise."""

from __future__ import annotations

import pytest
from homeassistant.exceptions import HomeAssistantError

from eta_webservices import select as select_platform

from .test_sensors import setup_integration


async def aufbauen(hass, entry):
    """Richtet die Integration ein und gibt die Auswahlen zurück.

    async_write_ha_state wird stillgelegt: Es schreibt in die
    Zustandsmaschine von Home Assistant, die es hier ohne laufende
    Instanz nicht gibt.
    """
    coordinator, _ = await setup_integration(hass, entry)
    entities: list = []
    await select_platform.async_setup_entry(hass, entry, entities.extend)
    for eintrag in entities:
        eintrag.async_write_ha_state = lambda: None
    return coordinator, {e.translation_key: e for e in entities}


async def test_betriebsart_entsteht_je_heizkreis(hass, entry):
    """Nur wo Anlage und Tasten es hergeben - HK2 hat keine."""
    entry.data["components"] = ["kessel", "hk1", "hk2"]
    _, auswahl = await aufbauen(hass, entry)

    assert "heizkreis_betriebsart" in auswahl
    assert "heizkreis2_betriebsart" not in auswahl


async def test_optionen_und_gelesener_zustand(hass, entry):
    _, auswahl = await aufbauen(hass, entry)
    betriebsart = auswahl["heizkreis_betriebsart"]

    assert betriebsart.options == ["aus", "automatik", "heizen", "absenken"]
    assert betriebsart.current_option == "automatik"


async def test_umschalten_schreibt_die_richtige_taste(hass, entry):
    coordinator, auswahl = await aufbauen(hass, entry)
    betriebsart = auswahl["heizkreis_betriebsart"]
    heizen = coordinator.select_defs["heizkreis_betriebsart"]["tasten"]["heizen"]

    hass.session.gesetzte_werte.clear()
    await betriebsart.async_select_option("heizen")

    assert hass.session.gesetzte_werte == [(heizen["uri"], heizen["ein_roh"])]
    assert betriebsart.current_option == "heizen"


async def test_aus_geht_ueber_die_ein_aus_taste(hass, entry):
    """"Aus" hat keine eigene Taste, es ist der Heizkreis selbst."""
    coordinator, auswahl = await aufbauen(hass, entry)
    betriebsart = auswahl["heizkreis_betriebsart"]
    schalter = coordinator.switch_defs["heizkreis_schalter"]

    hass.session.gesetzte_werte.clear()
    await betriebsart.async_select_option("aus")

    assert hass.session.gesetzte_werte == [(schalter["uri"], schalter["aus_roh"])]
    assert betriebsart.current_option == "aus"


async def test_aus_heraus_wird_erst_eingeschaltet(hass, entry):
    """Sonst bliebe die Auswahl wirkungslos, weil der Heizkreis aus ist."""
    coordinator, auswahl = await aufbauen(hass, entry)
    betriebsart = auswahl["heizkreis_betriebsart"]
    schalter = coordinator.switch_defs["heizkreis_schalter"]
    absenken = coordinator.select_defs["heizkreis_betriebsart"]["tasten"]["absenken"]

    await betriebsart.async_select_option("aus")
    hass.session.gesetzte_werte.clear()
    await betriebsart.async_select_option("absenken")

    assert hass.session.gesetzte_werte == [
        (schalter["uri"], schalter["ein_roh"]),
        (absenken["uri"], absenken["ein_roh"]),
    ]


async def test_abgelehntes_schreiben_meldet_einen_fehler(hass, entry):
    _, auswahl = await aufbauen(hass, entry)
    betriebsart = auswahl["heizkreis_betriebsart"]

    hass.session.schreiben_erlaubt = False
    with pytest.raises(HomeAssistantError):
        await betriebsart.async_select_option("heizen")


async def test_unbekannte_betriebsart_wird_abgelehnt(hass, entry):
    _, auswahl = await aufbauen(hass, entry)
    with pytest.raises(HomeAssistantError):
        await auswahl["heizkreis_betriebsart"].async_select_option("party")


async def test_ohne_schreibzugriff_keine_betriebsart(hass, entry):
    entry.data["enable_switches"] = False
    coordinator, auswahl = await aufbauen(hass, entry)

    assert coordinator.select_defs == {}
    assert auswahl == {}


async def test_gewaehlte_betriebsart_wird_auch_zurueckgelesen(hass, entry):
    """Nicht nur schreiben - die Anlage muss danach dasselbe melden.

    Auto, Heizen und Absenken sind an der Anlage Radioknöpfe. Prüft man
    nur, was geschrieben wurde, sieht eine Auswahl richtig aus, die
    anschließend den falschen Zustand meldet.
    """
    coordinator, auswahl = await aufbauen(hass, entry)
    betriebsart = auswahl["heizkreis_betriebsart"]

    for wunsch in ("heizen", "absenken", "automatik"):
        await betriebsart.async_select_option(wunsch)
        await coordinator.async_refresh()
        assert betriebsart.current_option == wunsch, wunsch


async def test_aus_und_zurueck(hass, entry):
    coordinator, auswahl = await aufbauen(hass, entry)
    betriebsart = auswahl["heizkreis_betriebsart"]

    await betriebsart.async_select_option("heizen")
    await coordinator.async_refresh()
    assert betriebsart.current_option == "heizen"


async def test_traege_anlage_laesst_die_betriebsart_nicht_zurueckspringen(hass, entry):
    """Wie beim Schalter: Die Anlage übernimmt einen Tastendruck verzögert.

    Wurde die Vorwegnahme schon bei der ersten Abfrage verworfen, sprang die
    Auswahl auf die alte Betriebsart zurück, obwohl die Taste gedrückt war.
    """
    _, auswahl = await aufbauen(hass, entry)
    betriebsart = auswahl["heizkreis_betriebsart"]

    hass.session.traege = True
    await betriebsart.async_select_option("absenken")
    assert betriebsart.current_option == "absenken"

    betriebsart._handle_coordinator_update()
    assert betriebsart.current_option == "absenken", "Auswahl springt zurück"


async def test_dauerhafter_widerspruch_entscheidet_zugunsten_der_anlage(hass, entry):
    """Eine Betriebsart, die die Anlage nie übernimmt, darf nicht haften."""
    from eta_webservices.switch import VERWERFEN_NACH

    _, auswahl = await aufbauen(hass, entry)
    betriebsart = auswahl["heizkreis_betriebsart"]
    vorher = betriebsart.current_option

    hass.session.traege = True
    await betriebsart.async_select_option("absenken")

    for _ in range(VERWERFEN_NACH):
        betriebsart._handle_coordinator_update()

    assert betriebsart.current_option == vorher, "Anlage setzt sich nicht durch"
