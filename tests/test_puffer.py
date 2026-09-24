"""Tests für Pufferspeicher: effektives Volumen, Energieinhalt, Ladepumpe, weitere Puffer."""

from __future__ import annotations

import pytest

from .conftest import ohne_objekt
from .test_sensors import setup_integration

VOLUMEN_URI = "/120/10601/0/0/12499"
"""Im Menübaum der Tests steht es wie bei PufferFlex unter Einstellungen > Leistungsregelung."""


def ohne_volumen_im_menue(menu: str) -> str:
    return ohne_objekt(menu, "/120/10601/0/0/13196")


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
    '<object uri="/120/10602/0/0/12528" name="Ladezustand"/>'
    "</object>"
    '<object uri="/120/10602/0/0/12421" name="Einstellungen">'
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
"""Der ältere Funktionsblock "Puffer": zwei Fühler, kein Volumen im Menübaum.

Am Display kennt er es, an die Webservices gibt er es nicht weiter.
"""


def mit_fub(menu: str, fub: str) -> str:
    return menu.replace('<fub uri="/120/10601" name="PufferFlex">', fub + '<fub uri="/120/10601" name="PufferFlex">')


def _wert(zahl):
    from eta_webservices.api import ETAValue

    return ETAValue(zahl, str(zahl), "°C", False, 1)


async def test_pufferflex_nennt_sein_effektives_volumen(hass, entry, menu_xml):
    coordinator, by_name = await setup_integration(hass, entry)
    assert coordinator.discovered_uris["puffer_volumen"] == VOLUMEN_URI
    assert "puffer_volumen" not in coordinator.ueber_kennung
    assert coordinator.puffer_volumen == 825
    volumen = by_name["Puffer effektives Volumen"]
    assert volumen.native_value == 825
    assert volumen.native_unit_of_measurement == "L"
    assert volumen.device_class == "volume_storage"
    assert "Puffer Energieinhalt" in by_name


async def test_volumen_auch_ueber_die_kennung(hass, entry, menu_xml):
    hass.session.menu = menu_xml.replace("Effektives Puffervolumen", "Effective buffer volume")
    coordinator, _ = await setup_integration(hass, entry)
    assert coordinator.puffer_volumen == 825


async def test_ohne_volumen_im_menue_kein_platzhalter(hass, entry, menu_xml):
    """Wie beim älteren Funktionsblock "Puffer": kein "-", kein Energieinhalt, nichts abgefragt."""
    hass.session.menu = ohne_volumen_im_menue(menu_xml)
    coordinator, by_name = await setup_integration(hass, entry)
    assert "puffer_volumen" not in coordinator.discovered_uris
    assert "puffer_volumen" not in coordinator.sensor_defs
    assert coordinator.puffer_volumen is None
    assert "Puffer effektives Volumen" not in by_name
    assert "Puffer Energieinhalt" not in by_name
    assert VOLUMEN_URI not in coordinator.abfragbare_uris.values()


async def test_eingetragenes_volumen_ohne_volumen_der_anlage(hass, entry, menu_xml):
    """Die Liter aus der Einrichtung, wenn der Puffer sie nicht meldet."""
    hass.session.menu = ohne_volumen_im_menue(menu_xml)
    entry.data["puffer_volumen"] = 1000
    coordinator, by_name = await setup_integration(hass, entry)
    assert coordinator.puffer_volumen == 1000
    assert coordinator.volumen_quelle("puffer") == "Einstellung"
    assert "Puffer effektives Volumen" not in by_name
    assert by_name["Puffer Energieinhalt"].extra_state_attributes["volumen_quelle"] == "Einstellung"


async def test_volumen_der_anlage_geht_vor(hass, entry):
    """Ein früher eingetragener Wert stört nicht, wenn die Anlage ihr Volumen meldet."""
    entry.data["puffer_volumen"] = 1000
    coordinator, _ = await setup_integration(hass, entry)
    assert coordinator.puffer_volumen == 825
    assert coordinator.volumen_quelle("puffer") == "Anlage"


async def test_ohne_puffer_kein_volumen(hass, entry, menu_xml):
    entry.data["components"] = ["kessel", "fwm"]
    coordinator, by_name = await setup_integration(hass, entry)
    assert coordinator.puffer_volumen is None
    assert "Puffer effektives Volumen" not in by_name
    assert "Puffer Energieinhalt" not in by_name


@pytest.mark.parametrize("volumen", ["0", "12", "5000000"])
async def test_unplausibles_volumen_gilt_nicht(hass, entry, menu_xml, volumen):
    coordinator, by_name = await setup_integration(hass, entry)
    coordinator.data["puffer_volumen"] = _wert(float(volumen))
    assert coordinator.puffer_volumen is None
    assert by_name["Puffer Energieinhalt"].native_value is None


async def test_energieinhalt_aus_volumen_und_fuehlern(hass, entry, menu_xml):
    coordinator, by_name = await setup_integration(hass, entry)
    energie = by_name["Puffer Energieinhalt"]
    fuehler = sorted(k for k in coordinator.sensor_defs if k.startswith("puffer_fuehler_"))
    for key, temperatur in zip(fuehler, (70, 60, 50, 40, 30, 20, 20, 20, 20)):
        coordinator.data[key] = _wert(temperatur)
    anzahl = len(fuehler)
    ueber = sum(max(0, t - 30) for t in (70, 60, 50, 40, 30, 20, 20, 20, 20)[:anzahl])
    assert energie.native_value == pytest.approx(round(ueber / anzahl * 825 * 0.001163, 2))
    assert energie.native_unit_of_measurement == "kWh"
    assert energie.device_class == "energy_storage"
    assert energie.extra_state_attributes == {
        "volumen_liter": 825,
        "volumen_quelle": "Anlage",
        "ab_temperatur": 30.0,
    }
    coordinator.data.pop(fuehler[-1])
    assert energie.native_value is None, "mit fehlendem Fühler wäre das Mittel schief"


def test_energieinhalt_wird_mit_dem_volumen_aufgeraeumt():
    from eta_webservices import entitaet_vorgesehen

    mit = {"puffer"}
    assert entitaet_vorgesehen("puffer_energieinhalt", ["kessel", "puffer"], False, False, False, mit)
    assert entitaet_vorgesehen("puffer_energieinhalt", ["kessel", "puffer"], False, False) is False
    assert entitaet_vorgesehen("puffer_energieinhalt", ["kessel"], False, False, False, mit) is False


async def test_diagnose_nennt_das_volumen(hass, entry, menu_xml):
    from eta_webservices.diagnostics import async_get_config_entry_diagnostics

    await setup_integration(hass, entry)
    diagnose = await async_get_config_entry_diagnostics(hass, entry)
    assert diagnose["konfiguration"]["puffer_volumen"] == {"puffer": 825}
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
    """Fühler, Ladezustand, effektives Volumen und Ladepumpe - kein Energieinhalt."""
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
        "Puffer 2 effektives Volumen",
    ]
    assert coordinator.discovered_uris["puffer2_fuehler_1"] == "/120/10602/0/11327/0"
    assert coordinator.volumen("puffer2") == 825
    assert coordinator.puffer_mit_volumen == {"puffer", "puffer2"}
    assert by_name["Puffer 2 Fühler 1"].extra_state_attributes["position"] == "oben"
    assert by_name["Puffer 2 Fühler 3"].extra_state_attributes["position"] == "unten"
    assert "Puffer 2 Energieinhalt" not in by_name


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


async def test_alter_puffer_als_zweiter_hat_keinen_ladezustand(hass, entry, menu_xml):
    """Der ältere Funktionsblock führt keinen - dann entsteht auch kein "-"."""
    hass.session.menu = mit_fub(menu_xml, ALTER_PUFFER)
    entry.data["components"] = ["kessel", "puffer", "puffer2"]
    entry.data["fub_names"] = {"pufferflex": "PufferFlex", "pufferflex2": "Puffer"}
    coordinator, by_name = await setup_integration(hass, entry)
    assert sorted(n for n in by_name if n.startswith("Puffer 2")) == [
        "Puffer 2 Fühler 1",
        "Puffer 2 Fühler 2",
    ]
    assert coordinator.volumen("puffer2") is None


def test_puffer_fuehler_bekommen_ihren_puffer_im_namen():
    from eta_webservices.const import puffer_fuehler_info

    info = puffer_fuehler_info(1, False, "puffer3")
    assert info["name"] == "Puffer 3 Fühler 1"
    assert info["translation_key"] == "puffer3_fuehler_1"
    assert info["component"] == "puffer3"
