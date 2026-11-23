"""Das Zahlenfeld "Puffervolumen": ein Feld je Puffer, zwei Orte zum Merken.

Der PufferFlex führt sein Gesamtvolumen an der Anlage (Einstellungen >
Gesamtvolumen). Eine echte Anlage meldet es als beschreibbar, in Litern
ohne Skalierung, von 50 bis 500000 l - so antwortet hier auch die
Testanlage, mit 1200 l. Mit Schreibzugriff stellt das Feld den Wert dort,
und Home Assistant meldet die Änderung eigens. Ohne Schreibzugriff und
beim älteren Funktionsblock "Puffer", der kein Gesamtvolumen führt, merkt
sich das Feld die Liter in Home Assistant.
"""

from __future__ import annotations

import pytest
from homeassistant.exceptions import HomeAssistantError

from eta_heating_ws import entitaet_vorgesehen
from eta_heating_ws import number as number_platform

from .test_config_flow import optionen, options_schritt
from .test_puffer import ALTER_PUFFER, ZWEITER_PUFFER, mit_fub
from .test_sensors import setup_integration

URI = "/120/10601/0/0/13520"
SCHLUESSEL = "puffer_volumen"
"""Unter diesem Schlüssel stehen die Liter des ersten Puffers in der Einrichtung."""


async def mit_puffer(hass, entry, schreibzugriff=True, gemerkt=None, feld="puffer_volumen_stellen"):
    """Richtet Kessel und Puffer ein und gibt Koordinator, Sensoren nach Namen und das Zahlenfeld zurück.

    gemerkt: was das Zahlenfeld vor diesem Start in Home Assistant
    gespeichert hat. async_write_ha_state wird stillgelegt: Ohne laufendes
    Home Assistant gibt es keine Zustandsmaschine.
    """
    if "puffer" not in entry.data["components"] or "puffer2" not in entry.data["components"]:
        entry.data["components"] = ["kessel", "puffer"]
    entry.data["enable_switches"] = schreibzugriff
    if gemerkt is not None:
        entry.options = {SCHLUESSEL: gemerkt}
    coordinator, by_name = await setup_integration(hass, entry)
    gesammelt: list = []
    await number_platform.async_setup_entry(hass, entry, gesammelt.extend)
    [zahl] = [z for z in gesammelt if z.translation_key == feld]
    zahl.async_write_ha_state = lambda: None
    return coordinator, by_name, zahl


async def aelterer_puffer(hass, entry, menu_xml, liter=None, gemerkt=None):
    """Der ältere Funktionsblock "Puffer" als einziger Puffer, mit Schreibzugriff."""
    hass.session.menu = mit_fub(menu_xml, ALTER_PUFFER).replace('name="PufferFlex"', 'name="PufferFlex alt"')
    entry.data["fub_names"] = {"pufferflex": "Puffer"}
    if liter is not None:
        entry.data[SCHLUESSEL] = liter
    return await mit_puffer(hass, entry, gemerkt=gemerkt)


async def test_pufferflex_zeigt_das_gesamtvolumen_der_anlage(hass, entry):
    coordinator, by_name, zahl = await mit_puffer(hass, entry)

    assert isinstance(zahl, number_platform.ETAZahl)
    assert coordinator.zahl_defs["puffer_volumen_stellen"]["uri"] == URI
    assert zahl.native_value == 1200
    assert zahl.native_unit_of_measurement == "L"
    assert zahl.device_class == "volume_storage"
    assert (zahl.native_min_value, zahl.native_max_value) == (50, 100000), "ab 50 l, wie die Anlage"
    assert zahl.entity_id == "number.eta_heizung_puffervolumen"
    assert zahl.unique_id == "eta_static_testeintrag_puffer_volumen_stellen"
    assert zahl.extra_state_attributes == {"gespeichert": "Anlage"}
    assert by_name["Puffer Energieinhalt"].extra_state_attributes["volumen_liter"] == 1200


async def test_schreibt_das_gesamtvolumen_an_die_anlage_und_meldet_es(hass, entry, puffer_meldungen):
    coordinator, by_name, zahl = await mit_puffer(hass, entry)
    hass.session.gesetzte_werte.clear()

    await zahl.async_set_native_value(2000)

    assert hass.session.gesetzte_werte == [(URI, "2000")]
    assert zahl.native_value == 2000
    assert coordinator.puffer_volumen == 2000, "nach dem Schreiben neu gelesen"
    assert by_name["Puffer Energieinhalt"].extra_state_attributes["volumen_quelle"] == "Anlage"
    [(text, angaben)] = puffer_meldungen
    assert "jetzt auf 2000 l" in text
    assert "Vorher standen dort 1200 l" in text
    assert "„PufferFlex“" in text
    assert text.endswith("Die Heizung rechnet nun mit diesem Wert.")
    assert angaben["title"] == "Puffervolumen an der Heizung geändert"
    assert angaben["notification_id"] == "eta_heating_ws_testeintrag_puffer_volumen_stellen"
    assert SCHLUESSEL not in entry.options, "in Home Assistant wird dabei nichts gemerkt"


async def test_derselbe_wert_gibt_keine_meldung(hass, entry, puffer_meldungen):
    _, _, zahl = await mit_puffer(hass, entry)

    await zahl.async_set_native_value(1200)

    assert puffer_meldungen == []


@pytest.mark.parametrize("liter", [0, 49, 100001])
async def test_wert_ausserhalb_der_grenzen_geht_nicht_an_die_anlage(hass, entry, puffer_meldungen, liter):
    _, _, zahl = await mit_puffer(hass, entry)
    hass.session.gesetzte_werte.clear()

    with pytest.raises(HomeAssistantError, match="Nur zwischen 50 und 100000 L"):
        await zahl.async_set_native_value(liter)

    assert hass.session.gesetzte_werte == []
    assert puffer_meldungen == []
    assert zahl.native_value == 1200


async def test_lehnt_die_anlage_ab_bleibt_es_beim_alten(hass, entry, puffer_meldungen):
    coordinator, _, zahl = await mit_puffer(hass, entry)
    hass.session.schreiben_erlaubt = False

    with pytest.raises(HomeAssistantError, match="nicht angenommen"):
        await zahl.async_set_native_value(2000)

    assert puffer_meldungen == []
    assert zahl.native_value == 1200
    assert coordinator.puffer_volumen == 1200


async def test_schreiben_an_die_anlage_verwirft_den_wert_aus_home_assistant(hass, entry):
    """Sonst gälte er wieder, sobald der Schreibzugriff einmal fehlt."""
    coordinator, _, zahl = await mit_puffer(hass, entry, gemerkt=900)
    assert zahl.native_value == 1200, "mit Schreibzugriff zählt nur die Anlage"

    await zahl.async_set_native_value(2000)

    assert entry.options == {SCHLUESSEL: 0}
    assert coordinator.puffer_volumen_eingetragen["puffer"] == 0
    assert getattr(hass.config_entries, "neu_laden_bestellt", 0) == 0


async def test_ohne_schreibzugriff_zeigt_das_feld_den_wert_der_anlage(hass, entry):
    coordinator, _, zahl = await mit_puffer(hass, entry, schreibzugriff=False)

    assert isinstance(zahl, number_platform.ETAPuffervolumenEigen)
    assert coordinator.zahl_defs == {}
    assert zahl.entity_id == "number.eta_heizung_puffervolumen"
    assert zahl.unique_id == "eta_static_testeintrag_puffer_volumen_stellen"
    assert zahl.native_value == 1200
    assert zahl.native_unit_of_measurement == "L"
    assert (zahl.native_min_value, zahl.native_max_value) == (0, 100000)
    assert zahl.extra_state_attributes == {"gespeichert": "Home Assistant", "wert_der_anlage": 1200}
    assert coordinator.volumen_quelle("puffer") == "Anlage"


async def test_ohne_schreibzugriff_merkt_sich_home_assistant_den_wert(hass, entry, puffer_meldungen):
    coordinator, by_name, zahl = await mit_puffer(hass, entry, schreibzugriff=False)
    hass.session.gesetzte_werte.clear()

    await zahl.async_set_native_value(900)

    assert hass.session.gesetzte_werte == [], "an die Anlage geht nichts"
    assert puffer_meldungen == []
    assert entry.options == {SCHLUESSEL: 900}, "übersteht den Neustart"
    assert zahl.native_value == 900
    assert zahl.extra_state_attributes["wert_der_anlage"] == 1200
    assert coordinator.puffer_volumen == 900
    assert by_name["Puffer Energieinhalt"].extra_state_attributes == {
        "volumen_liter": 900,
        "volumen_quelle": "Home Assistant",
        "ab_temperatur": 30.0,
    }
    assert getattr(hass.config_entries, "neu_laden_bestellt", 0) == 0, "der Energieinhalt bleibt"


async def test_null_verwirft_den_eigenen_wert(hass, entry):
    coordinator, _, zahl = await mit_puffer(hass, entry, schreibzugriff=False, gemerkt=900)
    assert zahl.native_value == 900, "nach dem Neustart wieder da"

    await zahl.async_set_native_value(0)

    assert entry.options == {SCHLUESSEL: 0}
    assert zahl.native_value == 1200, "wieder der Wert der Anlage"
    assert coordinator.volumen_quelle("puffer") == "Anlage"


async def test_meldet_die_anlage_es_nicht_als_beschreibbar_bleibt_der_wert_in_home_assistant(hass, entry):
    hass.session.volumen_schreibbar = False

    coordinator, _, zahl = await mit_puffer(hass, entry)
    hass.session.gesetzte_werte.clear()
    await zahl.async_set_native_value(900)

    assert isinstance(zahl, number_platform.ETAPuffervolumenEigen)
    assert "puffer_volumen_stellen" not in coordinator.zahl_defs
    assert hass.session.gesetzte_werte == []
    assert coordinator.puffer_volumen == 900


@pytest.mark.parametrize("liter", [-1, 100001])
async def test_eigener_wert_ausserhalb_der_grenzen_wird_nicht_gemerkt(hass, entry, liter):
    _, _, zahl = await mit_puffer(hass, entry, schreibzugriff=False)

    with pytest.raises(HomeAssistantError, match="Nur zwischen 0 und 100000 L"):
        await zahl.async_set_native_value(liter)

    assert entry.options == {}


async def test_aelterer_puffer_ohne_liter_zeigt_nichts(hass, entry, menu_xml):
    """Er führt kein Gesamtvolumen - auch mit Schreibzugriff merkt sich das Feld den Wert in Home Assistant."""
    coordinator, by_name, zahl = await aelterer_puffer(hass, entry, menu_xml)

    assert isinstance(zahl, number_platform.ETAPuffervolumenEigen)
    assert zahl.native_value is None
    assert zahl.extra_state_attributes == {"gespeichert": "Home Assistant", "wert_der_anlage": None}
    assert coordinator.puffer_volumen is None
    assert "Puffer Energieinhalt" not in by_name


async def test_aelterer_puffer_bekommt_seine_liter_im_feld(hass, entry, menu_xml):
    """Mit den ersten Litern entsteht der Energieinhalt - dafür wird neu geladen."""
    coordinator, _, zahl = await aelterer_puffer(hass, entry, menu_xml)
    hass.session.gesetzte_werte.clear()

    await zahl.async_set_native_value(1500)

    assert hass.session.gesetzte_werte == []
    assert entry.options == {SCHLUESSEL: 1500}
    assert zahl.native_value == 1500
    assert coordinator.puffer_volumen == 1500
    assert coordinator.volumen_quelle("puffer") == "Home Assistant"
    assert hass.config_entries.neu_laden_bestellt == 1


async def test_aelterer_puffer_zeigt_die_liter_aus_der_einrichtung(hass, entry, menu_xml):
    coordinator, by_name, zahl = await aelterer_puffer(hass, entry, menu_xml, liter=1500)
    assert zahl.native_value == 1500

    await zahl.async_set_native_value(1800)

    assert entry.options == {SCHLUESSEL: 1800}
    assert by_name["Puffer Energieinhalt"].extra_state_attributes["volumen_liter"] == 1800
    assert getattr(hass.config_entries, "neu_laden_bestellt", 0) == 0


async def test_aelterer_puffer_null_gilt_auch_gegen_die_liter_aus_der_einrichtung(hass, entry, menu_xml):
    """Die 0 wird gespeichert - sonst gälte nach dem Neustart wieder der Wert aus der Ersteinrichtung."""
    coordinator, _, zahl = await aelterer_puffer(hass, entry, menu_xml, liter=1500)

    await zahl.async_set_native_value(0)

    assert entry.options == {SCHLUESSEL: 0}
    assert entry.data[SCHLUESSEL] == 1500
    assert coordinator.puffer_volumen is None
    assert hass.config_entries.neu_laden_bestellt == 1, "der Energieinhalt entfällt"

    neu, by_name, feld = await aelterer_puffer(hass, entry, menu_xml)
    assert neu.puffer_volumen is None
    assert feld.native_value is None
    assert "Puffer Energieinhalt" not in by_name


async def test_zweiter_puffer_hat_sein_eigenes_feld(hass, entry, menu_xml):
    hass.session.menu = mit_fub(menu_xml, ZWEITER_PUFFER)
    entry.data["components"] = ["kessel", "puffer", "puffer2"]
    coordinator, _, zahl = await mit_puffer(hass, entry, feld="puffer2_volumen_stellen")
    hass.session.gesetzte_werte.clear()

    assert zahl.entity_id == "number.eta_heizung_puffer_2_volumen"
    assert zahl.native_value == 1200

    await zahl.async_set_native_value(800)

    assert hass.session.gesetzte_werte == [("/120/10602/0/0/13520", "800")]
    assert coordinator.volumen("puffer2") == 800
    assert coordinator.volumen("puffer") == 1200


async def test_konfigurieren_behaelt_das_volumen_eines_puffers_ohne_eigenen_schritt(monkeypatch):
    """Die Optionen werden beim Speichern ersetzt - beim PufferFlex steht der Wert in keinem Formular."""
    bisher = {**optionen(components=["puffer", "puffer2"]), SCHLUESSEL: 900.0, "puffer2_volumen": 700.0}
    flow, ergebnis = await options_schritt(monkeypatch, bisher, optionen(components=["puffer"]))
    for _ in range(4):
        if ergebnis["type"] == "create_entry":
            break
        ergebnis = await getattr(flow, f"async_step_{ergebnis['step_id']}")(
            {str(feld): feld.default() for feld in ergebnis["data_schema"].schema}
        )

    assert ergebnis["type"] == "create_entry"
    assert ergebnis["data"][SCHLUESSEL] == 900.0
    assert "puffer2_volumen" not in ergebnis["data"], "der zweite Puffer ist nicht mehr gewählt"


def test_zahlenfeld_gibt_es_mit_puffer_auch_ohne_schreibzugriff():
    """Danach räumt die Integration auf, wenn eine Komponente wegfällt."""
    assert entitaet_vorgesehen("puffer_volumen_stellen", ["kessel", "puffer"], True, True) is True
    assert entitaet_vorgesehen("puffer_volumen_stellen", ["kessel", "puffer"], False, True) is True
    assert entitaet_vorgesehen("puffer_volumen_stellen", ["kessel"], True, True) is False
    assert entitaet_vorgesehen("puffer3_volumen_stellen", ["kessel", "puffer"], False, True) is False
    assert entitaet_vorgesehen("puffer3_volumen_stellen", ["kessel", "puffer3"], False, True) is True


@pytest.mark.parametrize("schluessel", ["puffer_volumen", "puffer2_volumen", "puffer8_volumen"])
def test_fruehere_sensoren_zum_volumen_werden_aufgeraeumt(schluessel):
    """Die Sensoren "Puffer effektives Volumen" gibt es nicht mehr, auch nicht mit gewähltem Puffer."""
    komponenten = ["kessel", "puffer", "puffer2", "puffer8"]
    assert entitaet_vorgesehen(schluessel, komponenten, True, True) is False
