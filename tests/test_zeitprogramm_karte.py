"""Die Dashboard-Karte "ETA Zeitprogramm": lesen und schreiben über Websocket."""

from __future__ import annotations

import json
import sys
from types import SimpleNamespace

import pytest
import voluptuous as vol

from eta_heating_ws import zeitprogramm
from eta_heating_ws.coordinator import KEINE_ANTWORT
from eta_heating_ws.zeitprogramm import (
    ZeitprogrammFehler,
    _ws_zeitprogramm_setzen,
    _ws_zeitprogramme,
    zeitprogramm_setzen,
)

from .test_sensors import setup_integration
from .test_zeitplan import absenk_uri, anlage_mit_fenstern, fenster_uri, mit_zeitprogramm

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
    [heizkreis] = ergebnis["programme"]
    assert heizkreis["eintrag"] == "testeintrag"
    assert heizkreis["anlage"] == "ETA Heizung"
    assert heizkreis["programm"] == "hk1"
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

    assert verbindung.ergebnisse == [(7, {"programme": []})]


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
    [heizkreis] = verbindung.ergebnisse[0][1]["programme"]
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
        "programm": "hk1",
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

    [heizkreis] = verbindung.ergebnisse[0][1]["programme"]
    assert heizkreis["tage"] is None
    assert heizkreis["fehler"]


def test_nachricht_wird_geprueft():
    schema = _ws_zeitprogramm_setzen._ws_schema
    gut = {
        "id": 1,
        "type": "eta_heating_ws/zeitprogramm_setzen",
        "eintrag": "e",
        "programm": "hk1",
        "tage": ["monday"],
        "fenster": [{"beginn": 0, "ende": 96, "temperatur": 21}],
    }
    assert schema(gut)["fenster"][0]["temperatur"] == 21.0
    for falsch in (
        {"tage": []},
        {"tage": ["funday"]},
        {"fenster": [{"beginn": 0, "ende": 97}]},
        {"fenster": [{"beginn": 0, "ende": 4}] * 4},
        {"fenster": [{"beginn": 0, "ende": 96, "temperatur": "nan"}]},
        {"fenster": [{"beginn": 0, "ende": 96, "temperatur": "inf"}]},
        {"absenkung": "nan"},
        {"absenkung": "-inf"},
    ):
        with pytest.raises(vol.Invalid):
            schema({**gut, **falsch})
    assert schema({**gut, "absenkung": None})["absenkung"] is None


def test_karte_passt_zur_schnittstelle():
    """Die Karte ruft genau die Befehle auf, die es gibt, und liest, was sie liefern."""
    quelle = (zeitprogramm.OBERFLAECHE / "eta-zeitprogramm-karte.js").read_text(encoding="utf-8")
    assert zeitprogramm.karte_adresse().split("?")[0].endswith("/eta-zeitprogramm-karte.js")
    for befehl_typ in (_ws_zeitprogramme._ws_command, _ws_zeitprogramm_setzen._ws_command):
        assert f'"{befehl_typ}"' in quelle
    for feld in (
        "eintrag",
        "programm",
        "art",
        "hinweise",
        "name",
        "anlage",
        "mit_temperatur",
        "temperatur_min",
        "temperatur_max",
        "temperatur_vorgabe",
        "zeitplan",
        "tage",
        "fehler",
        "mit_absenkung",
        "absenkung",
        "absenkung_min",
        "absenkung_max",
        "beginn",
        "ende",
        "temperatur",
    ):
        assert f".{feld}" in quelle or f"{feld}:" in quelle, feld
    assert 'customElements.define(KARTE' in quelle
    assert 'return { anzeigen: ["heizzeiten"] };' in quelle, "neue Karten zeigen die Heizzeiten"
    for art in ("heizzeiten", "puffer", "warmwasser"):
        assert f'"{art}"' in quelle, art
    for einstellung in ("farbe_heizzeit", "farbe_absenkzeit"):
        assert f'name: "{einstellung}", selector: {{ ui_color: {{}} }}' in quelle, einstellung
    assert 'const KARTE = "eta-zeitprogramm-karte"' in quelle


def test_kein_hash_kommentar_im_modul():
    """Projektregel: Erklärungen stehen in Docstrings."""
    with open(sys.modules[zeitprogramm.__name__].__file__, encoding="utf-8") as datei:
        assert not any(zeile.lstrip().startswith("#") for zeile in datei)


async def test_karte_prueft_nach_wenn_beim_start_antworten_fehlten(hass, entry, menu_xml, monkeypatch):
    """Beim Start beschäftigt, beim Öffnen der Karte wieder da - ohne Neustart."""
    from eta_heating_ws.api import ETAApiClient
    from eta_heating_ws.coordinator import KEINE_ANTWORT

    original = ETAApiClient.async_get_varinfo
    stumm = {fenster_uri("wednesday", 2)}

    async def beschaeftigt(self, uri):
        if uri in stumm:
            return None
        return await original(self, uri)

    monkeypatch.setattr(ETAApiClient, "async_get_varinfo", beschaeftigt)
    coordinator = await aufbauen(hass, entry, menu_xml)
    assert coordinator.zeitprogramm_defs == {}
    assert coordinator.zeitprogramm_pruefung["hk1"]["fenster"] == {"Mittwoch 2": KEINE_ANTWORT}

    verbindung = await befehl(hass, _ws_zeitprogramme, type="eta_heating_ws/zeitprogramme")
    assert verbindung.ergebnisse[0][1]["programme"] == [], "noch immer keine Antwort"

    stumm.clear()
    verbindung = await befehl(hass, _ws_zeitprogramme, type="eta_heating_ws/zeitprogramme")
    assert verbindung.ergebnisse[0][1]["programme"] == [], "höchstens einmal je Minute"

    coordinator._zuletzt_nachgeprueft -= 61
    verbindung = await befehl(hass, _ws_zeitprogramme, type="eta_heating_ws/zeitprogramme")
    [heizkreis] = verbindung.ergebnisse[0][1]["programme"]
    assert heizkreis["tage"]["wednesday"] == [{"beginn": 22, "ende": 90, "temperatur": 20.0}]
    assert coordinator.zeitprogramm_pruefung == {}


async def test_echtes_nein_wird_nicht_nachgeprueft(hass, entry, menu_xml, monkeypatch):
    """Meldet die Anlage ein Fenster als nicht beschreibbar, bleibt es dabei."""
    hass.session.zeitfenster_schreibbar = False
    coordinator = await aufbauen(hass, entry, menu_xml)
    zaehler = hass.session.count

    await befehl(hass, _ws_zeitprogramme, type="eta_heating_ws/zeitprogramme")

    assert hass.session.count == zaehler
    assert coordinator.zeitprogramm_defs == {}


async def test_karte_liest_die_absenktemperatur(hass, entry, menu_xml):
    await aufbauen(hass, entry, menu_xml)
    hass.session.absenkwerte[absenk_uri("sunday")] = 175

    verbindung = await befehl(hass, _ws_zeitprogramme, type="eta_heating_ws/zeitprogramme")

    [heizkreis] = verbindung.ergebnisse[0][1]["programme"]
    assert heizkreis["mit_absenkung"] is True
    assert (heizkreis["absenkung_min"], heizkreis["absenkung_max"]) == (10.0, 30.0)
    assert heizkreis["absenkung"]["monday"] == 16.0
    assert heizkreis["absenkung"]["sunday"] == 17.5


async def test_absenktemperatur_fuer_mehrere_tage(hass, entry, menu_xml):
    await aufbauen(hass, entry, menu_xml)
    wie_bisher = [{"beginn": 22, "ende": 90, "temperatur": 20.0}]

    ergebnis = await zeitprogramm_setzen(
        entry, "hk1", ["saturday", "sunday"], wie_bisher, absenkung=17.5
    )

    assert hass.session.gesetzte_zeitfenster == [], "die Fenster bleiben, wie sie sind"
    assert sorted(hass.session.gesetzte_werte) == [
        (absenk_uri("saturday"), "175"),
        (absenk_uri("sunday"), "175"),
    ]
    assert ergebnis["absenkung"]["saturday"] == 17.5
    assert ergebnis["absenkung"]["friday"] == 16.0

    hass.session.gesetzte_werte.clear()
    await zeitprogramm_setzen(entry, "hk1", ["saturday"], wie_bisher, absenkung=17.5)
    assert hass.session.gesetzte_werte == [], "schon so"

    await zeitprogramm_setzen(entry, "hk1", ["monday"], wie_bisher, absenkung=4.0)
    assert hass.session.absenkwerte[absenk_uri("monday")] == 100, "nicht unter 10 °C"


async def test_ohne_angabe_bleibt_die_absenktemperatur(hass, entry, menu_xml):
    await aufbauen(hass, entry, menu_xml)

    await zeitprogramm_setzen(
        entry, "hk1", ["monday"], [{"beginn": 24, "ende": 88, "temperatur": 20.0}]
    )

    assert hass.session.gesetzte_werte == []
    assert hass.session.absenkwerte[absenk_uri("monday")] == 160


async def test_absenktemperatur_nicht_beschreibbar(hass, entry, menu_xml):
    """Dann bleibt es beim Zeitprogramm ohne sie."""
    hass.session.absenkwerte_schreibbar = False
    coordinator = await aufbauen(hass, entry, menu_xml)
    assert "hk1" in coordinator.zeitprogramm_defs
    assert coordinator.zeitprogramm_absenkung == {}

    verbindung = await befehl(hass, _ws_zeitprogramme, type="eta_heating_ws/zeitprogramme")
    [heizkreis] = verbindung.ergebnisse[0][1]["programme"]
    assert heizkreis["mit_absenkung"] is False
    assert heizkreis["absenkung"] is None

    with pytest.raises(ZeitprogrammFehler):
        await zeitprogramm_setzen(
            entry, "hk1", ["monday"], [{"beginn": 22, "ende": 90, "temperatur": 20.0}], 18.0
        )


async def test_websocket_mit_absenktemperatur(hass, entry, menu_xml):
    await aufbauen(hass, entry, menu_xml)

    verbindung = await befehl(
        hass,
        _ws_zeitprogramm_setzen,
        type="eta_heating_ws/zeitprogramm_setzen",
        eintrag="testeintrag",
        programm="hk1",
        tage=["wednesday"],
        fenster=[{"beginn": 22, "ende": 90, "temperatur": 20.0}],
        absenkung=18.5,
    )

    assert verbindung.ergebnisse[0][1]["absenkung"]["wednesday"] == 18.5
    assert _ws_zeitprogramm_setzen._ws_schema(
        {
            "id": 1,
            "type": "eta_heating_ws/zeitprogramm_setzen",
            "eintrag": "e",
            "programm": "hk1",
            "tage": ["monday"],
            "fenster": [],
            "absenkung": "17",
        }
    )["absenkung"] == 17.0


async def test_einzelner_unlesbarer_absenkwert(hass, entry, menu_xml):
    """Antwortet ein Tag nicht, bleibt das Programm lesbar und Speichern möglich."""
    await aufbauen(hass, entry, menu_xml)
    hass.session.fail_uris = {absenk_uri("sunday")}

    verbindung = await befehl(hass, _ws_zeitprogramme, type="eta_heating_ws/zeitprogramme")
    [heizkreis] = verbindung.ergebnisse[0][1]["programme"]
    assert heizkreis["fehler"] is None
    assert heizkreis["absenkung"]["sunday"] is None
    assert heizkreis["absenkung"]["monday"] == 16.0

    ergebnis = await zeitprogramm_setzen(
        entry, "hk1", ["monday"], [{"beginn": 24, "ende": 88, "temperatur": 20.0}]
    )
    assert ergebnis["tage"]["monday"] == [{"beginn": 24, "ende": 88, "temperatur": 20.0}]


async def test_gespeichert_aber_nicht_nachgelesen(hass, entry, menu_xml, monkeypatch):
    """Antwortet die Heizung nach dem Schreiben nicht, sagt die Karte, dass gespeichert ist."""
    from eta_heating_ws import zeitprogramm as modul
    from eta_heating_ws.api import ETAApiError

    await aufbauen(hass, entry, menu_xml)
    original = modul.bestand_lesen
    aufrufe = []

    async def zweites_mal_stumm(coordinator, programm):
        aufrufe.append(programm)
        if len(aufrufe) > 1:
            raise ETAApiError("Zeitüberschreitung")
        return await original(coordinator, programm)

    monkeypatch.setattr(modul, "bestand_lesen", zweites_mal_stumm)
    with pytest.raises(ZeitprogrammFehler, match="Gespeichert"):
        await zeitprogramm_setzen(
            entry, "hk1", ["monday"], [{"beginn": 24, "ende": 88, "temperatur": 20.0}]
        )
    assert hass.session.zeitfenster_text(fenster_uri("monday", 1)) == "06:00 - 22:00 20,0"


async def test_absenkung_vom_display_bleibt(hass, entry, menu_xml):
    """8 °C außerhalb der Zeitfenster: unverändert bleibt sie, an andere Tage nur in den Grenzen."""
    await aufbauen(hass, entry, menu_xml)
    hass.session.absenkwerte[absenk_uri("monday")] = 80
    wie_bisher = [{"beginn": 22, "ende": 90, "temperatur": 20.0}]

    await zeitprogramm_setzen(entry, "hk1", ["monday"], wie_bisher, absenkung=8.0)
    assert hass.session.gesetzte_werte == []

    await zeitprogramm_setzen(entry, "hk1", ["monday", "tuesday"], wie_bisher, absenkung=8.0)
    assert hass.session.absenkwerte[absenk_uri("monday")] == 80
    assert hass.session.absenkwerte[absenk_uri("tuesday")] == 100


async def test_programm_kommt_waehrend_des_lesens_dazu(hass, entry, menu_xml, monkeypatch):
    """Trägt eine Nachprüfung gerade ein Programm nach, bricht das Lesen nicht ab."""
    from eta_heating_ws import zeitprogramm as modul

    coordinator = await aufbauen(hass, entry, menu_xml)
    original = modul.bestand_lesen

    async def mit_nachtrag(coord, programm):
        coordinator.zeitprogramm_defs.setdefault("dazu", coordinator.zeitprogramm_defs["hk1"])
        return await original(coord, programm)

    monkeypatch.setattr(modul, "bestand_lesen", mit_nachtrag)
    verbindung = await befehl(hass, _ws_zeitprogramme, type="eta_heating_ws/zeitprogramme")
    assert verbindung.ergebnisse, verbindung.fehler


async def test_diagnose_zeigt_das_fenster_das_nicht_passte(hass, entry, menu_xml, monkeypatch):
    from eta_heating_ws.api import ETAApiClient
    from eta_heating_ws.diagnostics import async_get_config_entry_diagnostics

    original = ETAApiClient.async_get_varinfo

    async def mittwoch_gesperrt(self, uri):
        info = await original(self, uri)
        if uri == fenster_uri("wednesday", 2):
            info = {**info, "writable": False}
        return info

    monkeypatch.setattr(ETAApiClient, "async_get_varinfo", mittwoch_gesperrt)
    await aufbauen(hass, entry, menu_xml)

    bericht = await async_get_config_entry_diagnostics(hass, entry)
    befund = bericht["schreibzugriff"]["zeitprogramm_nicht_beschreibbar"]["hk1"]
    assert befund["fenster"] == {"Mittwoch 2": "Typ TIMESLOT, beschreibbar nein, Grenzen erkannt"}
    assert befund["beispiel_fenster"] == "Mittwoch 2"
    assert "<type>TIMESLOT</type>" in befund["varinfo_beispiel"]


def _stumm_fuer(monkeypatch, stumm: set[str]) -> dict[str, int]:
    """Lässt /user/varinfo für diese URIs nicht antworten und zählt die Anfragen je URI."""
    from eta_heating_ws.api import ETAApiClient

    original = ETAApiClient.async_get_varinfo
    zaehler: dict[str, int] = {}

    async def stumm_oder_nicht(self, uri):
        zaehler[uri] = zaehler.get(uri, 0) + 1
        if uri in stumm:
            return None
        return await original(self, uri)

    monkeypatch.setattr(ETAApiClient, "async_get_varinfo", stumm_oder_nicht)
    return zaehler


async def test_spaet_erkannter_heizkreis_startet_seinen_zeitplan(hass, entry, menu_xml, monkeypatch):
    """Ist ein Zeitplan gewählt, läuft sein Abgleich an, sobald der Heizkreis erkannt ist."""
    import eta_heating_ws

    gestartet = []
    monkeypatch.setattr(
        eta_heating_ws.ZeitplanAbgleich, "starten", lambda self: gestartet.append(self.heizkreis)
    )
    stumm = {fenster_uri("wednesday", 2)}
    _stumm_fuer(monkeypatch, stumm)
    entry.data["hk1_zeitplan"] = "schedule.heizen"
    coordinator = await aufbauen(hass, entry, menu_xml)
    assert coordinator.zeitplan_abgleiche == {}

    stumm.clear()
    verbindung = await befehl(hass, _ws_zeitprogramme, type="eta_heating_ws/zeitprogramme")

    assert gestartet == ["hk1"]
    [heizkreis] = verbindung.ergebnisse[0][1]["programme"]
    assert heizkreis["zeitplan"] == "schedule.heizen", "die Karte zeigt ihn gleich als gesperrt"


async def test_absenkung_wird_nachgeprueft(hass, entry, menu_xml, monkeypatch):
    stumm = {absenk_uri("sunday")}
    _stumm_fuer(monkeypatch, stumm)
    coordinator = await aufbauen(hass, entry, menu_xml)
    assert coordinator.zeitprogramm_absenkung == {}
    assert coordinator.absenkung_pruefung["hk1"]["tage"] == {"Sonntag": KEINE_ANTWORT}

    stumm.clear()
    verbindung = await befehl(hass, _ws_zeitprogramme, type="eta_heating_ws/zeitprogramme")

    [heizkreis] = verbindung.ergebnisse[0][1]["programme"]
    assert heizkreis["mit_absenkung"] is True
    assert coordinator.absenkung_pruefung == {}


async def test_nachpruefen_hoert_irgendwann_auf(hass, entry, menu_xml, monkeypatch):
    """Kennt die Anlage /user/varinfo nicht, fragt die Karte nicht endlos weiter."""
    from eta_heating_ws.coordinator import NACHPRUEFEN_HOECHSTENS

    zaehler = _stumm_fuer(monkeypatch, {fenster_uri("wednesday", 2)})
    coordinator = await aufbauen(hass, entry, menu_xml)
    uri = fenster_uri("wednesday", 2)
    nach_dem_start = zaehler[uri]

    for _ in range(NACHPRUEFEN_HOECHSTENS + 3):
        coordinator._zuletzt_nachgeprueft = float("-inf")
        await coordinator.zeitprogramme_nachpruefen()

    assert zaehler[uri] - nach_dem_start == 2 * NACHPRUEFEN_HOECHSTENS, "je Nachprüfung zwei Versuche"


async def test_karte_fragt_nur_ihren_heizkreis(hass, entry, menu_xml):
    await aufbauen(hass, entry, menu_xml)

    for heizkreis, erwartet in (("hk1", ["hk1"]), ("hk2", []), (None, ["hk1"])):
        verbindung = await befehl(
            hass,
            _ws_zeitprogramme,
            type="eta_heating_ws/zeitprogramme",
            arten=["heizzeiten"],
            heizkreis=heizkreis,
        )
        assert [p["programm"] for p in verbindung.ergebnisse[0][1]["programme"]] == erwartet
