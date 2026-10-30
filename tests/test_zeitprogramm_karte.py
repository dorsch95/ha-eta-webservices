"""Die Dashboard-Karte "ETA Zeitprogramm": lesen und schreiben über Websocket."""

from __future__ import annotations

import json
import sys
from types import SimpleNamespace

import pytest
import voluptuous as vol

from eta_heating_ws import zeitprogramm
from eta_heating_ws.zeitprogramm import (
    ZeitprogrammFehler,
    _ws_zeitprogramm_setzen,
    _ws_zeitprogramme,
    zeitprogramm_setzen,
)

from .test_sensors import setup_integration
from .test_zeitplan import anlage_mit_fenstern, fenster_uri, mit_zeitprogramm

WERKTAGE = ["monday", "tuesday", "wednesday", "thursday", "friday"]


class Verbindung:
    """Was die Websocket-Befehle von der Verbindung zum Browser brauchen."""

    def __init__(self) -> None:
        self.ergebnisse: list = []
        self.fehler: list = []

    def send_result(self, msg_id, result=None) -> None:
        self.ergebnisse.append((msg_id, result))

    def send_error(self, msg_id, code, message, *args, **kwargs) -> None:
        self.fehler.append((msg_id, code, message))


async def aufbauen(hass, entry, menu_xml, mit_wert=True):
    """Heizkreis 1 mit Zeitprogramm, täglich 5:30 bis 22:30, ohne Zeitplan-Helfer."""
    hass.session.menu = mit_zeitprogramm(menu_xml)
    anlage_mit_fenstern(hass.session, mit_wert)
    coordinator, _ = await setup_integration(hass, entry)
    hass.config_entries.geladen.append(entry)
    hass.session.gesetzte_zeitfenster.clear()
    return coordinator


async def befehl(hass, handler, **nachricht):
    verbindung = Verbindung()
    await handler.__wrapped__(hass, verbindung, {"id": 7, **nachricht})
    return verbindung


async def test_karte_liest_das_zeitprogramm(hass, entry, menu_xml):
    await aufbauen(hass, entry, menu_xml)

    verbindung = await befehl(hass, _ws_zeitprogramme, type="eta_heating_ws/zeitprogramme")

    [(msg_id, ergebnis)] = verbindung.ergebnisse
    assert msg_id == 7
    json.dumps(ergebnis)
    [heizkreis] = ergebnis["heizkreise"]
    assert heizkreis["eintrag"] == "testeintrag"
    assert heizkreis["anlage"] == "ETA Heizung"
    assert heizkreis["heizkreis"] == "hk1"
    assert heizkreis["name"]
    assert heizkreis["mit_temperatur"] is True
    assert (heizkreis["temperatur_min"], heizkreis["temperatur_max"]) == (10.0, 30.0), (
        "die Anlage nimmt 0 bis 80 °C, die Karte wie der Thermostat 10 bis 30"
    )
    assert heizkreis["zeitplan"] is None
    assert heizkreis["fehler"] is None
    assert heizkreis["tage"]["monday"] == [{"beginn": 22, "ende": 90, "temperatur": 20.0}]
    assert set(heizkreis["tage"]) == set(WERKTAGE) | {"saturday", "sunday"}


async def test_ohne_schreibzugriff_nichts_zu_bearbeiten(hass, entry, menu_xml):
    entry.data["enable_switches"] = False
    await aufbauen(hass, entry, menu_xml)

    verbindung = await befehl(hass, _ws_zeitprogramme, type="eta_heating_ws/zeitprogramme")

    assert verbindung.ergebnisse == [(7, {"heizkreise": []})]


async def test_mehrere_tage_auf_einmal_und_nur_was_sich_aendert(hass, entry, menu_xml):
    await aufbauen(hass, entry, menu_xml)
    morgens_abends = [
        {"beginn": 64, "ende": 88, "temperatur": 21.0},
        {"beginn": 24, "ende": 32, "temperatur": 21.0},
    ]

    ergebnis = await zeitprogramm_setzen(entry, "hk1", WERKTAGE, morgens_abends)

    for tag in WERKTAGE:
        assert hass.session.zeitfenster_text(fenster_uri(tag, 1)) == "06:00 - 08:00 21,0"
        assert hass.session.zeitfenster_text(fenster_uri(tag, 2)) == "16:00 - 22:00 21,0"
        assert ergebnis["tage"][tag] == [
            {"beginn": 24, "ende": 32, "temperatur": 21.0},
            {"beginn": 64, "ende": 88, "temperatur": 21.0},
        ]
    assert len(hass.session.gesetzte_zeitfenster) == 10, "Fenster 3 bleibt leer und unberührt"
    assert hass.session.zeitfenster_text(fenster_uri("saturday", 1)) == "05:30 - 22:30 20,0"
    assert ergebnis["tage"]["saturday"] == [{"beginn": 22, "ende": 90, "temperatur": 20.0}]

    hass.session.gesetzte_zeitfenster.clear()
    await zeitprogramm_setzen(entry, "hk1", WERKTAGE, morgens_abends)
    assert hass.session.gesetzte_zeitfenster == [], "schon so, nichts zu schreiben"


async def test_ohne_temperatur_an_der_anlage(hass, entry, menu_xml):
    await aufbauen(hass, entry, menu_xml, mit_wert=False)

    ergebnis = await zeitprogramm_setzen(
        entry, "hk1", ["sunday"], [{"beginn": 32, "ende": 88, "temperatur": None}]
    )

    assert ergebnis["mit_temperatur"] is False
    assert ergebnis["tage"]["sunday"] == [{"beginn": 32, "ende": 88, "temperatur": None}]
    [(uri, daten)] = hass.session.gesetzte_zeitfenster
    assert uri == fenster_uri("sunday", 1)
    assert daten == {"begin": "32", "end": "88"}, "keine Temperatur, wo die Anlage keine hat"


async def test_ohne_angabe_bleibt_die_temperatur(hass, entry, menu_xml):
    await aufbauen(hass, entry, menu_xml)

    await zeitprogramm_setzen(
        entry, "hk1", ["monday"], [{"beginn": 20, "ende": 40}, {"beginn": 60, "ende": 90}]
    )

    assert hass.session.zeitfenster_text(fenster_uri("monday", 1)) == "05:00 - 10:00 20,0"
    assert hass.session.zeitfenster_text(fenster_uri("monday", 2)) == "15:00 - 22:30 20,0", (
        "das neue Fenster übernimmt die Temperatur der Woche"
    )


async def test_tag_ohne_zeitfenster(hass, entry, menu_xml):
    await aufbauen(hass, entry, menu_xml)

    ergebnis = await zeitprogramm_setzen(entry, "hk1", ["sunday"], [])

    assert ergebnis["tage"]["sunday"] == []
    assert hass.session.zeitfenster[fenster_uri("sunday", 1)][:2] == (0, 0)


async def test_temperatur_wird_begrenzt(hass, entry, menu_xml):
    await aufbauen(hass, entry, menu_xml)

    await zeitprogramm_setzen(
        entry, "hk1", ["monday"], [{"beginn": 22, "ende": 90, "temperatur": 45.0}]
    )

    assert hass.session.zeitfenster_text(fenster_uri("monday", 1)) == "05:30 - 22:30 30,0"


@pytest.mark.parametrize(
    "fenster",
    [
        [{"beginn": 40, "ende": 40, "temperatur": 20.0}],
        [{"beginn": 50, "ende": 30, "temperatur": 20.0}],
        [{"beginn": 20, "ende": 50, "temperatur": 20.0}, {"beginn": 40, "ende": 60, "temperatur": 20.0}],
    ],
    ids=["ohne_dauer", "verkehrt", "ueberschnitten"],
)
async def test_unmoegliche_fenster_werden_abgelehnt(hass, entry, menu_xml, fenster):
    await aufbauen(hass, entry, menu_xml)

    with pytest.raises(ZeitprogrammFehler):
        await zeitprogramm_setzen(entry, "hk1", ["monday"], fenster)
    assert hass.session.gesetzte_zeitfenster == []


async def test_mit_zeitplan_helfer_nur_anzeigen(hass, entry, menu_xml):
    """Sonst überschriebe der nächste Abgleich die Änderung wieder."""
    coordinator = await aufbauen(hass, entry, menu_xml)
    coordinator.zeitplan_abgleiche["hk1"] = SimpleNamespace(entity_id="schedule.heizen")

    with pytest.raises(ZeitprogrammFehler, match="schedule.heizen"):
        await zeitprogramm_setzen(
            entry, "hk1", ["monday"], [{"beginn": 24, "ende": 88, "temperatur": 21.0}]
        )
    assert hass.session.gesetzte_zeitfenster == []

    verbindung = await befehl(hass, _ws_zeitprogramme, type="eta_heating_ws/zeitprogramme")
    [heizkreis] = verbindung.ergebnisse[0][1]["heizkreise"]
    assert heizkreis["zeitplan"] == "schedule.heizen"
    assert heizkreis["tage"]["monday"], "angezeigt wird es trotzdem"


async def test_anlage_meldet_anderes_zurueck(hass, entry, menu_xml, monkeypatch):
    await aufbauen(hass, entry, menu_xml)
    session = hass.session
    monkeypatch.setattr(
        session,
        "_zeitfenster_setzen",
        lambda uri, daten: session._tracked(f'<eta version="1.0"><success uri="{uri}"/></eta>'),
    )

    with pytest.raises(ZeitprogrammFehler, match="Montag 1"):
        await zeitprogramm_setzen(
            entry, "hk1", ["monday"], [{"beginn": 24, "ende": 88, "temperatur": 20.0}]
        )


async def test_websocket_schreiben(hass, entry, menu_xml):
    await aufbauen(hass, entry, menu_xml)
    nachricht = {
        "type": "eta_heating_ws/zeitprogramm_setzen",
        "eintrag": "testeintrag",
        "heizkreis": "hk1",
        "tage": ["saturday", "sunday"],
        "fenster": [{"beginn": 28, "ende": 92, "temperatur": 21.5}],
    }

    verbindung = await befehl(hass, _ws_zeitprogramm_setzen, **nachricht)

    [(_, ergebnis)] = verbindung.ergebnisse
    assert ergebnis["tage"]["saturday"] == [{"beginn": 28, "ende": 92, "temperatur": 21.5}]
    assert hass.session.zeitfenster_text(fenster_uri("sunday", 1)) == "07:00 - 23:00 21,5"

    verbindung = await befehl(hass, _ws_zeitprogramm_setzen, **{**nachricht, "eintrag": "weg"})
    assert verbindung.fehler[0][1] == "nicht_geladen"

    ueberschnitten = [{"beginn": 20, "ende": 50}, {"beginn": 40, "ende": 60}]
    verbindung = await befehl(
        hass, _ws_zeitprogramm_setzen, **{**nachricht, "fenster": ueberschnitten}
    )
    assert verbindung.fehler[0][1:] == ("abgelehnt", "Zeitfenster dürfen sich nicht überschneiden.")

    hass.session.fail_uris = {"/user/var"}
    verbindung = await befehl(hass, _ws_zeitprogramm_setzen, **nachricht)
    assert verbindung.fehler[0][1] == "anlage"


async def test_nicht_lesbares_programm(hass, entry, menu_xml):
    await aufbauen(hass, entry, menu_xml)
    hass.session.fail_uris = {fenster_uri("friday", 2)}

    verbindung = await befehl(hass, _ws_zeitprogramme, type="eta_heating_ws/zeitprogramme")

    [heizkreis] = verbindung.ergebnisse[0][1]["heizkreise"]
    assert heizkreis["tage"] is None
    assert heizkreis["fehler"]


def test_nachricht_wird_geprueft():
    schema = _ws_zeitprogramm_setzen._ws_schema
    gut = {
        "id": 1,
        "type": "eta_heating_ws/zeitprogramm_setzen",
        "eintrag": "e",
        "heizkreis": "hk1",
        "tage": ["monday"],
        "fenster": [{"beginn": 0, "ende": 96, "temperatur": 21}],
    }
    assert schema(gut)["fenster"][0]["temperatur"] == 21.0
    for falsch in (
        {"tage": []},
        {"tage": ["funday"]},
        {"fenster": [{"beginn": 0, "ende": 97}]},
        {"fenster": [{"beginn": 0, "ende": 4}] * 4},
    ):
        with pytest.raises(vol.Invalid):
            schema({**gut, **falsch})


def test_karte_passt_zur_schnittstelle():
    """Die Karte ruft genau die Befehle auf, die es gibt, und liest, was sie liefern."""
    quelle = (zeitprogramm.OBERFLAECHE / "eta-zeitprogramm-karte.js").read_text(encoding="utf-8")
    assert zeitprogramm.karte_adresse().split("?")[0].endswith("/eta-zeitprogramm-karte.js")
    for befehl_typ in (_ws_zeitprogramme._ws_command, _ws_zeitprogramm_setzen._ws_command):
        assert f'"{befehl_typ}"' in quelle
    for feld in (
        "eintrag",
        "heizkreis",
        "name",
        "anlage",
        "mit_temperatur",
        "temperatur_min",
        "temperatur_max",
        "zeitplan",
        "tage",
        "fehler",
        "beginn",
        "ende",
        "temperatur",
    ):
        assert f".{feld}" in quelle or f"{feld}:" in quelle, feld
    assert 'customElements.define(KARTE' in quelle
    assert 'const KARTE = "eta-zeitprogramm-karte"' in quelle


def test_kein_hash_kommentar_im_modul():
    """Projektregel: Erklärungen stehen in Docstrings."""
    with open(sys.modules[zeitprogramm.__name__].__file__, encoding="utf-8") as datei:
        assert not any(zeile.lstrip().startswith("#") for zeile in datei)
