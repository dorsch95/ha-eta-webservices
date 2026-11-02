"""Lade- und Bereitschaftszeiten von Puffer und Frischwassermodul in der Zeitprogramm-Karte."""

from __future__ import annotations

import pytest

from eta_heating_ws.const import WOCHENTAGE
from eta_heating_ws.zeitprogramm import _ws_zeitprogramme, zeitprogramm_setzen

from .test_sensors import setup_integration
from .test_zeitplan import anlage_mit_fenstern, mit_zeitprogramm
from .test_zeitprogramm_karte import befehl

TAGE = list(WOCHENTAGE)
PUFFER = "/120/10601/12130/0"
WARMWASSER = "/79/10531/12318/0"


def programm_xml(stamm: str, name: str) -> str:
    """Ein Zeitprogramm mit je Wochentag drei Zeitfenstern und dem Wert außerhalb."""
    teile = [f'<object uri="{stamm}/0" name="{name}">']
    for i, tag in enumerate(WOCHENTAGE.values()):
        teile.append(f'<object uri="{stamm}/{1081 + 4 * i}" name="{tag}">')
        teile.append(f'<object uri="{stamm}/{1111 + i}" name="Wert außerhalb der Zeitfenster"/>')
        for nummer in (1, 2, 3):
            teile.append(f'<object uri="{stamm}/{1081 + 4 * i + nummer}" name="Zeitfenster {nummer}"/>')
        teile.append("</object>")
    teile.append("</object>")
    return "".join(teile)


def mit_ladezeiten(menu: str) -> str:
    """Wie an der Anlage des Nutzers: Puffer-Ladezeiten und Bereitschaftszeiten des FWM."""
    puffer = '<fub uri="/120/10601" name="PufferFlex">'
    fwm = '<fub uri="/79/10531" name="FWM">'
    assert puffer in menu and fwm in menu
    menu = menu.replace(
        puffer,
        puffer
        + '<object uri="/120/10601/0/0/12528" name="Erzeuger Kessel/Puffer">'
        + programm_xml(PUFFER, "Ladezeiten")
        + "</object>",
    )
    return menu.replace(
        fwm,
        fwm
        + '<object uri="/79/10531/0/0/12271" name="Warmwasser">'
        + programm_xml(WARMWASSER, "Bereitschaftszeiten")
        + "</object>",
    )


def fenster(stamm: str, tag: str, nummer: int) -> str:
    return f"{stamm}/{1081 + 4 * TAGE.index(tag) + nummer}"


async def aufbauen(hass, entry, menu_xml):
    """Heizzeiten wie gehabt, Puffer täglich 6 bis 22 Uhr bei 60 °C, Warmwasser rund um die Uhr bei 50 °C."""
    hass.session.menu = mit_ladezeiten(mit_zeitprogramm(menu_xml))
    anlage_mit_fenstern(hass.session)
    for tag in TAGE:
        hass.session.zeitfenster[fenster(PUFFER, tag, 1)] = (24, 88, 600)
        hass.session.zeitfenster[fenster(WARMWASSER, tag, 1)] = (0, 96, 500)
        for nummer in (2, 3):
            hass.session.zeitfenster[fenster(PUFFER, tag, nummer)] = (0, 0, 0)
            hass.session.zeitfenster[fenster(WARMWASSER, tag, nummer)] = (0, 0, 0)
    coordinator, _ = await setup_integration(hass, entry)
    hass.config_entries.geladen.append(entry)
    hass.session.gesetzte_zeitfenster.clear()
    return coordinator


async def test_findet_lade_und_bereitschaftszeiten(hass, entry, menu_xml):
    coordinator = await aufbauen(hass, entry, menu_xml)

    assert set(coordinator.zeitprogramm_defs) == {"hk1", "puffer_12130", "fwm_12318"}
    assert coordinator.zeitprogramm_art("hk1") == "heizzeiten"
    assert coordinator.zeitprogramm_art("puffer_12130") == "puffer"
    assert coordinator.zeitprogramm_art("fwm_12318") == "warmwasser"
    assert coordinator.zeitprogramm_name("puffer_12130") == "Erzeuger Kessel/Puffer › Ladezeiten"
    assert coordinator.zeitprogramm_name("fwm_12318") == "Warmwasser › Bereitschaftszeiten"
    assert set(coordinator.zeitprogramm_absenkung) == {"hk1"}, "Wert außerhalb nur bei Heizzeiten"
    assert coordinator.zeitplan_abgleiche == {}


async def test_warmwasser_im_bereich_des_puffers(hass, entry, menu_xml):
    """Ladezeiten unter "Warmwasserbereich" zählen zu Warmwasser, nicht zum Puffer."""
    hass.session.menu = mit_ladezeiten(menu_xml).replace(
        "Erzeuger Kessel/Puffer", "Warmwasserbereich"
    )
    coordinator, _ = await setup_integration(hass, entry)
    assert coordinator.zeitprogramm_art("puffer_12130") == "warmwasser"


async def test_nur_mit_der_komponente(hass, entry, menu_xml):
    entry.data["components"] = ["kessel", "puffer", "hk1"]
    coordinator = await aufbauen(hass, entry, menu_xml)
    assert "fwm_12318" not in coordinator.zeitprogramm_defs
    assert "puffer_12130" in coordinator.zeitprogramm_defs


async def test_karte_kennt_die_art(hass, entry, menu_xml):
    await aufbauen(hass, entry, menu_xml)

    verbindung = await befehl(hass, _ws_zeitprogramme, type="eta_heating_ws/zeitprogramme")

    programme = {p["programm"]: p for p in verbindung.ergebnisse[0][1]["programme"]}
    assert programme["hk1"]["art"] == "heizzeiten"
    assert programme["hk1"]["temperatur_aenderbar"] is True
    warmwasser = programme["fwm_12318"]
    assert warmwasser["art"] == "warmwasser"
    assert warmwasser["temperatur_aenderbar"] is False
    assert warmwasser["mit_absenkung"] is False
    assert warmwasser["tage"]["monday"] == [{"beginn": 0, "ende": 96, "temperatur": 50.0}]
    assert programme["puffer_12130"]["tage"]["sunday"] == [
        {"beginn": 24, "ende": 88, "temperatur": 60.0}
    ]


async def test_nur_die_zeiten_werden_geschrieben(hass, entry, menu_xml):
    """Eine Warmwassertemperatur aus der Karte kommt nie bei der Anlage an."""
    await aufbauen(hass, entry, menu_xml)

    ergebnis = await zeitprogramm_setzen(
        entry, "fwm_12318", ["monday"], [{"beginn": 22, "ende": 88, "temperatur": 75.0}]
    )

    assert hass.session.zeitfenster_text(fenster(WARMWASSER, "monday", 1)) == "05:30 - 22:00 50,0"
    assert ergebnis["tage"]["monday"] == [{"beginn": 22, "ende": 88, "temperatur": 50.0}]


async def test_neues_fenster_nimmt_die_temperatur_des_programms(hass, entry, menu_xml):
    await aufbauen(hass, entry, menu_xml)

    await zeitprogramm_setzen(
        entry,
        "puffer_12130",
        ["saturday", "sunday"],
        [{"beginn": 24, "ende": 40}, {"beginn": 64, "ende": 88}],
    )

    for tag in ("saturday", "sunday"):
        assert hass.session.zeitfenster_text(fenster(PUFFER, tag, 1)) == "06:00 - 10:00 60,0"
        assert hass.session.zeitfenster_text(fenster(PUFFER, tag, 2)) == "16:00 - 22:00 60,0"
    assert hass.session.zeitfenster_text(fenster(PUFFER, "friday", 1)) == "06:00 - 22:00 60,0"


async def test_absenkung_gibt_es_nur_bei_heizzeiten(hass, entry, menu_xml):
    from eta_heating_ws.zeitprogramm import ZeitprogrammFehler

    await aufbauen(hass, entry, menu_xml)
    with pytest.raises(ZeitprogrammFehler):
        await zeitprogramm_setzen(
            entry, "fwm_12318", ["monday"], [{"beginn": 0, "ende": 96}], absenkung=40.0
        )
