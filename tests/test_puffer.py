"""Tests für Pufferspeicher: Puffervolumen, Ladepumpe, weitere Puffer."""

from __future__ import annotations

import pytest

from .conftest import ohne_objekt
from .test_sensors import setup_integration

VOLUMEN_URI = "/120/10601/0/0/13520"
"""Das Gesamtvolumen des PufferFlex steht unter Einstellungen, gesucht wird nach dem Namen.

Die Attrappe meldet dafür 1200 l und für das "Effektive Puffervolumen"
daneben 825 l - das liest die Integration nicht.
"""


def ohne_volumen_im_menue(menu: str) -> str:
    return ohne_objekt(menu, VOLUMEN_URI)


def mit_ladepumpe(menu: str) -> str:
    """PufferFlex, im ETA-Assistenten als dezentral geladen eingerichtet."""
    return menu.replace(
        '<object uri="/120/10601/0/0/19403" name="Puffer">',
        '<object uri="/120/10601/0/0/10991" name="Ausgänge">'
        '<object uri="/120/10601/0/11157/0" name="Pufferladeventil/-pumpe">'
        '<object uri="/120/10601/0/11157/2001" name="Anforderung"/>'
        '<object uri="/120/10601/0/11157/2002" name="Zustand"/>'
        "</object></object>"
        '<object uri="/120/10601/0/0/19403" name="Puffer">',
    )


ZWEITER_PUFFER = (
    '<fub uri="/120/10602" name="PufferFlex 2">'
    '<object uri="/120/10602/0/0/10990" name="Eingänge">'
    '<object uri="/120/10602/0/11327/0" name="Fühler 1 (oben)"/>'
    '<object uri="/120/10602/0/11328/0" name="Fühler 2"/>'
    '<object uri="/120/10602/0/11329/0" name="Fühler 3"/>'
    "</object>"
    '<object uri="/120/10602/0/0/10991" name="Ausgänge">'
    '<object uri="/120/10602/0/11157/0" name="Pufferladeventil/-pumpe">'
    '<object uri="/120/10602/0/11157/2001" name="Anforderung"/>'
    "</object></object>"
    '<object uri="/120/10602/0/0/19403" name="Puffer">'
    '<object uri="/120/10602/0/0/12208" name="Puffer-Zustand detailliert"/>'
    '<object uri="/120/10602/0/0/12528" name="Ladezustand"/>'
    "</object>"
    '<object uri="/120/10602/0/0/12421" name="Einstellungen">'
    '<object uri="/120/10602/0/0/13520" name="Gesamtvolumen"/>'
    '<object uri="/120/10602/0/0/13196" name="Leistungsregelung">'
    '<object uri="/120/10602/0/0/12499" name="Effektives Puffervolumen"/>'
    "</object></object>"
    "</fub>"
)
"""Ein zweiter, dezentral geladener PufferFlex mit drei Fühlern."""

ALTER_PUFFER = (
    '<fub uri="/120/10251" name="Puffer">'
    '<object uri="/120/10251/0/0/10990" name="Eingänge">'
    '<object uri="/120/10251/0/11153/0" name="Puffer oben"/>'
    '<object uri="/120/10251/0/11155/0" name="Puffer unten"/>'
    "</object>"
    '<object uri="/120/10251/0/0/19403" name="Puffer">'
    '<object uri="/120/10251/0/0/12208" name="Puffer-Zustand detailliert"/>'
    '<object uri="/120/10251/0/0/12242" name="Puffer oben">'
    '<object uri="/120/10251/0/0/12211" name="Puffer oben Min"/>'
    "</object></object>"
    "</fub>"
)
"""Der ältere Funktionsblock "Puffer": zwei Fühler, kein Gesamtvolumen im Menübaum."""


def mit_fub(menu: str, fub: str) -> str:
    return menu.replace('<fub uri="/120/10601" name="PufferFlex">', fub + '<fub uri="/120/10601" name="PufferFlex">')


def _wert(zahl):
    from eta_heating_ws.api import ETAValue

    return ETAValue(zahl, str(zahl), "°C", False, 1)


async def test_pufferflex_meldet_sein_gesamtvolumen(hass, entry, menu_xml):
    """Gelesen wird es mit, einen Sensor bekommt es nicht - es steht im Zahlenfeld."""
    coordinator, by_name = await setup_integration(hass, entry)
    assert coordinator.discovered_uris["puffer_volumen"] == VOLUMEN_URI
    assert "puffer_volumen" not in coordinator.ueber_kennung
    assert coordinator.sensor_defs["puffer_volumen"]["platform"] == "number"
    assert VOLUMEN_URI in coordinator.abfragbare_uris.values()
    assert coordinator.puffer_volumen == 1200
    assert not [name for name in by_name if "olumen" in name]
    assert "Puffer Energieinhalt" not in by_name


async def test_volumen_auch_ueber_die_kennung(hass, entry, menu_xml):
    hass.session.menu = menu_xml.replace('name="Gesamtvolumen"', 'name="Total volume"')
    coordinator, _ = await setup_integration(hass, entry)
    assert coordinator.discovered_uris["puffer_volumen"] == VOLUMEN_URI
    assert coordinator.puffer_volumen == 1200


async def test_ohne_gesamtvolumen_im_menue_kein_volumen(hass, entry, menu_xml):
    """Das "Effektive Puffervolumen" allein zählt nicht: kein Volumen, nichts abgefragt."""
    hass.session.menu = ohne_volumen_im_menue(menu_xml)
    assert "Effektives Puffervolumen" in hass.session.menu
    coordinator, by_name = await setup_integration(hass, entry)
    assert "puffer_volumen" not in coordinator.discovered_uris
    assert "puffer_volumen" not in coordinator.sensor_defs
    assert coordinator.puffer_volumen is None
    abgefragt = set(coordinator.abfragbare_uris.values())
    assert VOLUMEN_URI not in abgefragt
    assert "/120/10601/0/0/12499" not in abgefragt


async def test_eingetragenes_volumen_ohne_volumen_der_anlage(hass, entry, menu_xml):
    """Die Liter aus der Einrichtung, wenn der Puffer kein Gesamtvolumen führt."""
    hass.session.menu = ohne_volumen_im_menue(menu_xml)
    entry.data["puffer_volumen"] = 1000
    coordinator, by_name = await setup_integration(hass, entry)
    assert coordinator.puffer_volumen == 1000
    assert coordinator.volumen_quelle("puffer") == "Home Assistant"


async def test_schreibt_das_feld_an_die_anlage_zaehlt_nur_ihr_wert(hass, entry):
    """Ein früher eingetragener Wert stört dann nicht."""
    entry.data["puffer_volumen"] = 1000
    coordinator, _ = await setup_integration(hass, entry)
    assert coordinator.puffer_volumen_an_der_anlage("puffer")
    assert coordinator.puffer_volumen == 1200
    assert coordinator.volumen_quelle("puffer") == "Anlage"


async def test_ohne_schreibzugriff_gehen_eingetragene_liter_vor(hass, entry):
    entry.data["puffer_volumen"] = 1000
    entry.data["enable_switches"] = False
    coordinator, _ = await setup_integration(hass, entry)
    assert not coordinator.puffer_volumen_an_der_anlage("puffer")
    assert coordinator.puffer_volumen == 1000
    assert coordinator.volumen_quelle("puffer") == "Home Assistant"


async def test_ohne_puffer_kein_volumen(hass, entry, menu_xml):
    entry.data["components"] = ["kessel", "fwm"]
    coordinator, by_name = await setup_integration(hass, entry)
    assert coordinator.puffer_volumen is None
    assert coordinator.puffer_mit_volumen == set()


@pytest.mark.parametrize("volumen", ["0", "12", "5000000"])
async def test_unplausibles_volumen_gilt_nicht(hass, entry, menu_xml, volumen):
    coordinator, by_name = await setup_integration(hass, entry)
    coordinator.data["puffer_volumen"] = _wert(float(volumen))
    assert coordinator.puffer_volumen is None


def test_der_energieinhalt_wird_aufgeraeumt():
    """Den Sensor "Puffer Energieinhalt" gibt es nicht mehr, auch nicht mit bekanntem Volumen."""
    from eta_heating_ws import entitaet_vorgesehen

    assert entitaet_vorgesehen("puffer_energieinhalt", ["kessel", "puffer"], True, True) is False


async def test_kein_sensor_rechnet_mit_dem_volumen(hass, entry):
    _, by_name = await setup_integration(hass, entry)
    for sensor in by_name.values():
        assert "volumen_liter" not in (sensor.extra_state_attributes or {})


async def test_diagnose_nennt_das_volumen(hass, entry, menu_xml):
    from eta_heating_ws.diagnostics import async_get_config_entry_diagnostics

    await setup_integration(hass, entry)
    diagnose = await async_get_config_entry_diagnostics(hass, entry)
    assert diagnose["konfiguration"]["puffer_volumen"] == {"puffer": 1200}
    assert "aeltere_puffer" not in diagnose["konfiguration"]
    assert diagnose["konfiguration"]["puffer_volumen_quelle"] == {"puffer": "Anlage"}
    assert diagnose["erkennung"]["pufferfuehler"] == {"puffer": [1, 2, 3, 4, 5]}


async def test_ladepumpe_nur_bei_dezentraler_ladung(hass, entry, menu_xml):
    """Zentral geladen sind die Ausgänge leer - dann gibt es keine Entität, auch kein "-"."""
    coordinator, by_name = await setup_integration(hass, entry)
    assert "puffer_ladepumpe" not in coordinator.sensor_defs
    assert "Puffer Ladepumpe" not in by_name


async def test_ladepumpe_bei_dezentraler_ladung(hass, entry, menu_xml):
    hass.session.menu = mit_ladepumpe(menu_xml)
    coordinator, by_name = await setup_integration(hass, entry)
    assert coordinator.discovered_uris["puffer_ladepumpe"] == "/120/10601/0/11157/2001"
    assert by_name["Puffer Ladepumpe"].native_value == "Ein"


async def test_zweiter_puffer_mit_fuehlern_volumen_und_pumpe(hass, entry, menu_xml):
    """Fühler, Zustand, Ladezustand und Ladepumpe als Sensoren."""
    hass.session.menu = mit_fub(menu_xml, ZWEITER_PUFFER)
    entry.data["components"] = ["kessel", "puffer", "puffer2"]
    coordinator, by_name = await setup_integration(hass, entry)
    zweiter = sorted(n for n in by_name if n.startswith("Puffer 2"))
    assert zweiter == [
        "Puffer 2 Fühler 1",
        "Puffer 2 Fühler 2",
        "Puffer 2 Fühler 3",
        "Puffer 2 Ladepumpe",
        "Puffer 2 Ladezustand",
        "Puffer 2 Zustand",
    ]
    assert coordinator.discovered_uris["puffer2_fuehler_1"] == "/120/10602/0/11327/0"
    assert coordinator.volumen("puffer2") == 1200
    assert coordinator.puffer_mit_volumen == {"puffer", "puffer2"}
    assert by_name["Puffer 2 Fühler 1"].extra_state_attributes["position"] == "oben"
    assert by_name["Puffer 2 Fühler 3"].extra_state_attributes["position"] == "unten"


async def test_alter_puffer_nennt_seine_fuehler_oben_und_unten(hass, entry, menu_xml):
    """Ohne "Fühler 1 … 9": Puffer oben und Puffer unten, von oben nach unten nummeriert.

    "Puffer oben" unter "Puffer" ist die Einstellung der Ladung, kein Fühler.
    """
    menu = mit_fub(menu_xml, ALTER_PUFFER)
    hass.session.menu = menu.replace('name="PufferFlex"', 'name="PufferFlex alt"')
    coordinator, by_name = await setup_integration(hass, entry)
    fuehler = {k: v for k, v in coordinator.discovered_uris.items() if k.startswith("puffer_fuehler_")}
    assert fuehler == {
        "puffer_fuehler_1": "/120/10251/0/11153/0",
        "puffer_fuehler_2": "/120/10251/0/11155/0",
    }
    assert "puffer_volumen" not in coordinator.discovered_uris
    assert "Puffer Fühler 2" in by_name
    assert "Puffer Fühler 3" not in by_name


async def test_alter_puffer_als_zweiter_bekommt_berechneten_ladezustand(hass, entry, menu_xml):
    """Der ältere Funktionsblock führt keinen - er wird aus den Fühlern gerechnet."""
    hass.session.menu = mit_fub(menu_xml, ALTER_PUFFER)
    entry.data["components"] = ["kessel", "puffer", "puffer2"]
    entry.data["fub_names"] = {"pufferflex": "PufferFlex", "pufferflex2": "Puffer"}
    coordinator, by_name = await setup_integration(hass, entry)
    assert sorted(n for n in by_name if n.startswith("Puffer 2")) == [
        "Puffer 2 Fühler 1",
        "Puffer 2 Fühler 2",
        "Puffer 2 Ladezustand",
        "Puffer 2 Zustand",
    ]
    assert coordinator.volumen("puffer2") is None
    assert coordinator.puffer_mit_berechnetem_ladezustand == ["puffer2"]

    ladezustand = by_name["Puffer 2 Ladezustand"]
    assert ladezustand.native_value == pytest.approx(51.0), "beide Fühler 55,5 °C"
    assert ladezustand.native_unit_of_measurement == "%"
    assert ladezustand.unique_id.endswith("_puffer2_ladezustand")
    assert ladezustand.extra_state_attributes == {
        "berechnet": True,
        "leer_bei": 30.0,
        "voll_bei": 80.0,
        "fuehler": 2,
    }


@pytest.mark.parametrize(
    "temperaturen, erwartet",
    [
        ([30.0, 30.0], 0.0),
        ([80.0, 80.0], 100.0),
        ([55.0, 55.0], 50.0),
        ([80.0, 30.0], 50.0),
        ([95.0, 20.0], 50.0),
        ([70.0, 60.0, 50.0, 40.0], 50.0),
        ([], None),
    ],
)
def test_ladezustand_aus_den_fuehlern(temperaturen, erwartet):
    """0 % bis 30 °C, 100 % ab 80 °C, jeder Fühler für einen gleich großen Teil."""
    from eta_heating_ws.prognose import puffer_ladezustand

    assert puffer_ladezustand(temperaturen) == (
        pytest.approx(erwartet) if erwartet is not None else None
    )


async def test_gemeldeter_ladezustand_bleibt_der_der_anlage(hass, entry):
    """PufferFlex meldet ihn selbst - gerechnet wird dann nicht."""
    coordinator, by_name = await setup_integration(hass, entry)

    assert coordinator.puffer_mit_berechnetem_ladezustand == []
    assert "berechnet" not in by_name["Puffer Ladezustand"].extra_state_attributes


async def test_berechneter_ladezustand_bleibt_leer_wenn_ein_fuehler_fehlt(hass, entry, menu_xml):
    hass.session.menu = mit_fub(menu_xml, ALTER_PUFFER)
    entry.data["components"] = ["kessel", "puffer", "puffer2"]
    entry.data["fub_names"] = {"pufferflex": "PufferFlex", "pufferflex2": "Puffer"}
    coordinator, by_name = await setup_integration(hass, entry)
    del coordinator.data["puffer2_fuehler_2"]

    assert by_name["Puffer 2 Ladezustand"].native_value is None


async def test_puffer_ohne_fuehler_behaelt_den_strich(hass, entry, menu_xml):
    """Ohne Fühler gibt es nichts zu rechnen - der erste Puffer zeigt weiter "-"."""
    hass.session.menu = ohne_objekt(menu_xml, "/120/10601/0/0/12528", "/120/10601/0/0/10990")
    coordinator, by_name = await setup_integration(hass, entry)

    assert coordinator.puffer_mit_berechnetem_ladezustand == []
    assert by_name["Puffer Ladezustand"].native_value == "-"


def test_puffer_fuehler_bekommen_ihren_puffer_im_namen():
    from eta_heating_ws.const import puffer_fuehler_info

    info = puffer_fuehler_info(1, False, "puffer3")
    assert info["name"] == "Puffer 3 Fühler 1"
    assert info["translation_key"] == "puffer3_fuehler_1"
    assert info["component"] == "puffer3"


async def test_marker_nennt_den_funktionsblock_wie_im_menuebaum(hass, entry, menu_xml):
    """Auch wenn die Erkennung vom vorbelegten "PufferFlex" auf "Puffer" ausweicht."""
    menu = mit_fub(menu_xml, ALTER_PUFFER)
    hass.session.menu = menu.replace('name="PufferFlex"', 'name="PufferFlex alt"')
    entry.data["components"] = ["kessel", "puffer", "puffer2"]
    entry.data["fub_names"] = {"pufferflex": "PufferFlex"}
    coordinator, by_name = await setup_integration(hass, entry)
    assert by_name["Komponente Pufferspeicher"].extra_state_attributes == {"funktionsblock": "Puffer"}
    assert coordinator.funktionsblock("puffer2") == "Pufferspeicher 2", "nicht gefunden"
