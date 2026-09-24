"""Tests für das Zeitprogramm eines Heizkreises: Heizzeit oder Absenkzeit."""

from __future__ import annotations

from homeassistant.components.sensor import SensorDeviceClass

from eta_webservices import karte
from eta_webservices.api import ETAApiClient
from eta_webservices.uri_discovery import async_discover_uris

from .test_sensors import setup_integration
from .test_thermostat import aufbauen

SCHALTZUSTAND = "/120/10101/12113/0/1109"


async def test_zeitprogramm_zeigt_heizzeit_und_absenkzeit(hass, entry):
    coordinator, by_name = await setup_integration(hass, entry)
    sensor = by_name["Heizkreis Zeitprogramm"]
    assert sensor.device_class == SensorDeviceClass.ENUM
    assert sensor.options == ["heizzeit", "absenkzeit"]
    assert sensor.native_unit_of_measurement is None
    assert sensor.native_value == "heizzeit"

    hass.session.geschrieben[SCHALTZUSTAND] = "1802"
    await coordinator.async_refresh()
    assert sensor.native_value == "absenkzeit"


async def test_zeitprogramm_nur_wo_der_menuebaum_es_hat(hass, entry):
    """HK2 der Testanlage führt keine Heizzeiten - dann kein Sensor mit "-"."""
    coordinator, by_name = await setup_integration(hass, entry)
    assert "Heizkreis 2 Zeitprogramm" not in by_name
    assert "heizkreis2_zeitprogramm" not in coordinator.sensor_defs


async def test_unbekannter_schaltzustand_ist_kein_zustand(hass, entry):
    coordinator, by_name = await setup_integration(hass, entry)
    coordinator.data["heizkreis_zeitprogramm"].text = "Störung"
    assert by_name["Heizkreis Zeitprogramm"].native_value is None
    assert coordinator.zustand("heizkreis_zeitprogramm") is None
    assert coordinator.zustand("kessel_zustand") is None, "ohne feste Zustände"


async def test_zeitprogramm_wird_auch_ueber_die_kennung_gefunden(hass, menu_xml):
    """Etwa bei einem Display in anderer Sprache."""
    hass.session.menu = menu_xml.replace('name="Heizzeiten"', 'name="Heating times"')
    client = ETAApiClient(hass, hass.session, "192.0.2.10", 8080)
    ueber_kennung: set = set()
    uris, _ = await async_discover_uris(client, {}, ueber_kennung)
    assert uris["heizkreis_zeitprogramm"] == SCHALTZUSTAND
    assert "heizkreis_zeitprogramm" in ueber_kennung


async def test_thermostat_nennt_das_zeitprogramm(hass, entry, menu_xml):
    coordinator, _, thermostate = await aufbauen(hass, entry, menu_xml)
    thermostat = thermostate["heizkreis_thermostat"]
    assert thermostat.extra_state_attributes["zeitprogramm"] == "heizzeit"
    hass.session.geschrieben[SCHALTZUSTAND] = "1802"
    await coordinator.async_refresh()
    assert thermostat.extra_state_attributes["zeitprogramm"] == "absenkzeit"


def test_kachel_zeigt_das_zeitprogramm_nur_im_auto_modus():
    element = karte.zeitprogramm(
        "heizkreis_2_zeitprogramm", "heizkreis_2_betriebsart", 31, 95, kurz=False
    )
    assert element["conditions"] == [
        {
            "condition": "state",
            "entity": "sensor.eta_heizung_heizkreis_2_zeitprogramm",
            "state_not": "unknown",
        },
        {
            "condition": "state",
            "entity": "select.eta_heizung_heizkreis_2_betriebsart",
            "state_not": ["heizen", "absenken", "aus"],
        },
    ]
    (label,) = element["elements"]
    assert label["prefix"] == "Zeitprogramm: "
    kurz = karte.zeitprogramm("heizkreis_zeitprogramm", "heizkreis_1_betriebsart", 31, 95, True)
    assert "prefix" not in kurz["elements"][0]


def test_jede_heizkreis_kachel_hat_ihr_zeitprogramm():
    gitter = karte.grid(spalten=4, schrift=100, kurz=False)
    for nummer, praefix in (("1", "heizkreis"), ("2", "heizkreis_2"), ("3", "heizkreis_3"), ("4", "heizkreis_4")):
        (kachel,) = [
            k for k in gitter["cards"]
            if k["conditions"][0]["entity"] == f"sensor.eta_heizung_komponente_heizkreis_{nummer}"
        ]
        entitaeten = [
            innen["entity"]
            for element in kachel["card"]["elements"]
            for innen in element.get("elements", [element])
            if "entity" in innen
        ]
        assert f"sensor.eta_heizung_{praefix}_zeitprogramm" in entitaeten
