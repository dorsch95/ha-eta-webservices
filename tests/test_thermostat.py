"""Tests für Thermostat und Raumfühler über die externe Schnittstelle."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from homeassistant.components.climate import PRESET_ECO, HVACAction, HVACMode
from homeassistant.exceptions import HomeAssistantError

from eta_webservices import climate as climate_platform
from eta_webservices import select as select_platform
from eta_webservices.raumfuehler import RaumfuehlerSender, raumwert_roh, takt

from .test_sensors import setup_integration

HK = "/120/10101"
RAUM_EXTERN = f"{HK}/0/0/13046"
RAUM_SOLL = f"{HK}/0/0/12127"
ZEIT = f"{HK}/0/0/13168"


def mit_schnittstelle(menu: str) -> str:
    """Heizkreis 1, im ETA-Assistenten mit "Raumfühler ext. Schnittstelle" eingerichtet."""
    return menu.replace(
        f'<object uri="{HK}/0/11060/0" name="Vorlauf"/>',
        f'<object uri="{HK}/0/11060/0" name="Vorlauf"/>'
        f'<object uri="{RAUM_EXTERN}" name="Raumtemperatur über externe Schnittstellen">'
        f'<object uri="{HK}/0/0/12634" name="Raum"/>'
        f'<object uri="{ZEIT}" name="Zeitüberwachung"/>'
        "</object>",
    ).replace(
        f'<object uri="{HK}/0/0/12182" name="Sonstiges">',
        f'<object uri="{HK}/0/0/12634" name="Raum"><object uri="{RAUM_SOLL}" name="Raum Soll"/></object>'
        f'<object uri="{HK}/0/0/12182" name="Sonstiges">',
    )


async def aufbauen(hass, entry, menu_xml):
    hass.session.menu = mit_schnittstelle(menu_xml)
    coordinator, by_name = await setup_integration(hass, entry)
    auswahlen: list = []
    await select_platform.async_setup_entry(hass, entry, auswahlen.extend)
    thermostate: list = []
    await climate_platform.async_setup_entry(hass, entry, thermostate.extend)
    for entitaet in (*auswahlen, *thermostate):
        entitaet.async_write_ha_state = lambda: None
    return coordinator, by_name, {t.translation_key: t for t in thermostate}


async def test_thermostat_nur_mit_externer_schnittstelle(hass, entry, menu_xml):
    coordinator, by_name, thermostate = await aufbauen(hass, entry, menu_xml)
    assert set(thermostate) == {"heizkreis_thermostat"}, "HK2 hat keine Schnittstelle"
    assert set(coordinator.thermostat_defs) == {"hk1"}
    assert "Heizkreis Raumtemperatur" in by_name
    assert "Heizkreis 2 Raumtemperatur" not in by_name


async def test_ohne_schreibzugriff_kein_thermostat(hass, entry, menu_xml):
    """Die Raumtemperatur lesen geht trotzdem."""
    entry.data["enable_switches"] = False
    coordinator, by_name, thermostate = await aufbauen(hass, entry, menu_xml)
    assert thermostate == {}
    assert by_name["Heizkreis Raumtemperatur"].native_value is None, "--- heißt kein Wert"


async def test_ohne_schnittstelle_kein_thermostat(hass, entry):
    coordinator, _ = await setup_integration(hass, entry)
    assert coordinator.thermostat_defs == {}


async def test_thermostat_zeigt_raum_soll_und_betriebsart(hass, entry, menu_xml):
    coordinator, _, thermostate = await aufbauen(hass, entry, menu_xml)
    thermostat = thermostate["heizkreis_thermostat"]
    assert thermostat.current_temperature is None
    assert thermostat.target_temperature == 21.0
    assert (thermostat.min_temp, thermostat.max_temp) == (10.0, 30.0)
    assert thermostat.hvac_modes == [HVACMode.AUTO, HVACMode.HEAT, HVACMode.OFF]
    assert thermostat.hvac_mode == HVACMode.AUTO
    assert thermostat.preset_modes == ["none", PRESET_ECO]
    assert thermostat.hvac_action == HVACAction.HEATING
    assert thermostat.entity_id == "climate.eta_heizung_heizkreis_1_thermostat"


async def test_solltemperatur_wird_gerundet_und_begrenzt(hass, entry, menu_xml):
    _, _, thermostate = await aufbauen(hass, entry, menu_xml)
    thermostat = thermostate["heizkreis_thermostat"]
    hass.session.gesetzte_werte.clear()
    await thermostat.async_set_temperature(temperature=22.3)
    assert hass.session.gesetzte_werte == [(RAUM_SOLL, "225")]
    assert thermostat.target_temperature == 22.5
    with pytest.raises(HomeAssistantError):
        await thermostat.async_set_temperature(temperature=35)
    assert hass.session.gesetzte_werte == [(RAUM_SOLL, "225")]


async def test_eco_ist_absenken(hass, entry, menu_xml):
    coordinator, _, thermostate = await aufbauen(hass, entry, menu_xml)
    thermostat = thermostate["heizkreis_thermostat"]
    absenken = coordinator.select_defs["heizkreis_betriebsart"]["tasten"]["absenken"]
    hass.session.gesetzte_werte.clear()
    await thermostat.async_set_preset_mode(PRESET_ECO)
    assert (absenken["uri"], absenken["ein_roh"]) in hass.session.gesetzte_werte
    assert thermostat.preset_mode == PRESET_ECO
    assert thermostat.hvac_mode == HVACMode.HEAT


def test_raumwert_wird_umgerechnet_und_begrenzt():
    objekt = {"scale": 10.0, "min_roh": -200.0, "max_roh": 500.0}

    def zustand(wert, einheit="°C"):
        return SimpleNamespace(state=wert, attributes={"unit_of_measurement": einheit})

    assert raumwert_roh(zustand("21.53"), objekt) == "215"
    assert raumwert_roh(zustand("71.6", "°F"), objekt) == "220"
    assert raumwert_roh(zustand("60"), objekt) == "500"
    for ungueltig in ("unknown", "unavailable", "warm"):
        assert raumwert_roh(zustand(ungueltig), objekt) is None
    assert raumwert_roh(None, objekt) is None


def test_takt_bleibt_unter_der_halben_zeitueberwachung():
    assert takt(None) == 30
    assert takt(600) == 30
    assert takt(60) == 30
    assert takt(40) == 20
    assert takt(12) == 10


async def test_sender_schreibt_nur_gueltige_werte(hass, entry, menu_xml):
    coordinator, _, _ = await aufbauen(hass, entry, menu_xml)
    zustaende = {"sensor.wohnzimmer": SimpleNamespace(state="21.5", attributes={})}
    ha = SimpleNamespace(states=SimpleNamespace(get=zustaende.get))
    sender = RaumfuehlerSender(ha, coordinator, "hk1", "sensor.wohnzimmer")

    hass.session.gesetzte_werte.clear()
    assert await sender.schreiben() is True
    assert hass.session.gesetzte_werte == [(RAUM_EXTERN, "215")]

    zustaende["sensor.wohnzimmer"] = SimpleNamespace(state="unavailable", attributes={})
    assert await sender.schreiben() is False, "kein Ersatzwert"
    assert len(hass.session.gesetzte_werte) == 1


async def test_sender_schreibt_nicht_ohne_zeitueberwachung(hass, entry, menu_xml):
    """Steht sie auf 0, behielte die Anlage einen alten Wert womöglich für immer."""
    hass.session.geschrieben[ZEIT] = "0"
    coordinator, _, _ = await aufbauen(hass, entry, menu_xml)
    zustaende = {"sensor.wohnzimmer": SimpleNamespace(state="21.5", attributes={})}
    sender = RaumfuehlerSender(
        SimpleNamespace(states=SimpleNamespace(get=zustaende.get)), coordinator, "hk1", "sensor.wohnzimmer"
    )
    hass.session.gesetzte_werte.clear()
    assert await sender.schreiben() is False
    assert hass.session.gesetzte_werte == []


async def test_geschriebener_raumwert_erscheint_als_istwert(hass, entry, menu_xml):
    coordinator, by_name, thermostate = await aufbauen(hass, entry, menu_xml)
    hass.session.geschrieben[RAUM_EXTERN] = "215"
    await coordinator.async_refresh()
    assert thermostate["heizkreis_thermostat"].current_temperature == 21.5
    assert by_name["Heizkreis Raumtemperatur"].native_value == pytest.approx(21.5)


def test_thermostat_wird_mit_dem_schreibzugriff_aufgeraeumt():
    from eta_webservices import entitaet_vorgesehen

    assert entitaet_vorgesehen("heizkreis_thermostat", ["kessel", "hk1"], True, False)
    assert entitaet_vorgesehen("heizkreis_thermostat", ["kessel", "hk1"], False, False) is False
    assert entitaet_vorgesehen("heizkreis2_thermostat", ["kessel", "hk1"], True, False) is False


def test_kachel_zeigt_raum_nur_mit_raumwert():
    """Sonst stünde dort ein leeres "Raum: °C". Soll fehlt nur bei "Aus"."""
    from eta_webservices import karte

    raum, soll = karte.thermostat_zeile("heizkreis_1_thermostat", 39, 95)
    entitaet = "climate.eta_heizung_heizkreis_1_thermostat"
    assert raum["conditions"] == [
        {"condition": "state", "entity": entitaet, "state_not": "unknown"},
        {"condition": "state", "entity": entitaet, "state_not": "unknown", "attribute": "current_temperature"},
    ]
    assert raum["elements"][0]["attribute"] == "current_temperature"
    assert soll["conditions"] == [
        {"condition": "state", "entity": entitaet, "state_not": "unknown"},
        {"condition": "state", "entity": entitaet, "state_not": "off"},
    ], "Soll in jedem Modus außer Aus"
    assert soll["elements"][0]["attribute"] == "temperature"
