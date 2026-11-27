"""Konfigurieren ist nach Menüpunkten getrennt.

Früher stand alles in einem Formular, dem bis zu sieben Schritte folgten -
auch für den, der nur den Pelletpreis ändern wollte. Jetzt wählt der
Nutzer, was er ändern will. Gespeichert wird weiter die ganze
Einrichtung: Was ein Menüpunkt nicht fragt, bleibt, wie es war.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import voluptuous as vol

from eta_heating_ws import config_flow as modul
from eta_heating_ws.config_flow import ABSCHNITTE, FOLGESCHRITTE, _abschnitt_schema, _connection_schema
from eta_heating_ws.const import (
    CONF_FEHLENDE_AUSBLENDEN,
    CONF_FREMDERZEUGER_ENTITAET,
    CONF_FREMDERZEUGER_FREIGEBEN_NACH,
    CONF_FREMDERZEUGER_FUEHLER,
    CONF_FREMDERZEUGER_NAME,
    CONF_FREMDERZEUGER_SCHWELLE,
    CONF_FREMDERZEUGER_SPERREN_NACH,
    CONF_FREMDERZEUGER_SPERRT,
    CONF_KESSEL_GESPERRT,
    CONF_LAGER_MAXIMUM,
    CONF_LIEFERUNGEN,
    CONF_WEITERE_INTERVALL,
    CONF_WEITERE_JE_ABFRAGE,
    CONF_WEITERE_WERTE,
    CONF_ZUORDNUNGEN,
    KESSEL_GESPERRT_AUSGESCHALTET,
    WOCHENTAGE,
    fub_roles_for_components,
    normalize_components,
)
from eta_heating_ws.verbindungen import felder as verbindung_teile
from eta_heating_ws.verbindungen import feld as verbindung_feld
from eta_heating_ws.verbindungen import verbindungen

from .test_config_flow import optionen, options_schritt

TEXTE = Path(__file__).parent.parent / "custom_components" / "eta_heating_ws"
OFEN = "input_boolean.kaminofen"
FUEHLER = "sensor.ofen_temperatur"
FENSTER = {(tag, nummer): f"/{tag}/{nummer}" for tag in WOCHENTAGE for nummer in (1, 2, 3)}
KOMPONENTEN = normalize_components(
    ["puffer", "puffer2", "fwm", "hk1", "hk2", "solar", "fremderzeuger"]
)

ALLES = {
    "host": "192.0.2.10",
    "port": 8080,
    "components": KOMPONENTEN,
    "scan_interval": 45,
    "schnell_intervall": 5,
    "enable_errors": False,
    CONF_FEHLENDE_AUSBLENDEN: True,
    "enable_switches": True,
    "kessel_sperre": True,
    "verbrauch_zeitraeume": False,
    "prognose": False,
    "pellet_kwh_per_kg": 4.7,
    "pellet_preis": 289.0,
    "wetter": "weather.zuhause",
    "fub_names": {rolle: f"Block {rolle}" for rolle in fub_roles_for_components(KOMPONENTEN)},
    CONF_FREMDERZEUGER_NAME: "Kachelofen",
    CONF_FREMDERZEUGER_ENTITAET: None,
    CONF_FREMDERZEUGER_FUEHLER: FUEHLER,
    CONF_FREMDERZEUGER_SPERRT: ["kessel"],
    CONF_FREMDERZEUGER_SPERREN_NACH: 2.0,
    CONF_FREMDERZEUGER_FREIGEBEN_NACH: 10.0,
    CONF_FREMDERZEUGER_SCHWELLE: 85.0,
    "puffer_volumen": 1000,
    "puffer2_volumen": 650,
    "hk1_raumfuehler": "sensor.wohnzimmer",
    "hk1_zeitplan": "schedule.heizen",
    "hk2_zeitplan": None,
    "verbindungen": {
        teil: verbindungen(KOMPONENTEN, {"puffer2": "kessel"})[teil]
        for teil in verbindung_teile(KOMPONENTEN)
    },
    CONF_LAGER_MAXIMUM: 8000.0,
    CONF_LIEFERUNGEN: [{"datum": "2026-11-15", "menge": 4000.0, "preis": 289.5}],
    CONF_WEITERE_WERTE: [{"uri": "/120/10601/0/0/12499", "name": "Volumen"}],
    CONF_WEITERE_JE_ABFRAGE: 50,
    CONF_WEITERE_INTERVALL: 120,
    CONF_ZUORDNUNGEN: {"kessel_druck": "/40/10021/0/0/12006"},
    CONF_KESSEL_GESPERRT: KESSEL_GESPERRT_AUSGESCHALTET,
}
"""Eine Einrichtung, in der jeder Schritt von Konfigurieren etwas gespeichert hat.

Die Entität des Fremderzeugers und der Zeitplan von Heizkreis 2 sind
ausdrücklich geleert, siehe config_flow._geleert.
"""
GESPEICHERT = {key: wert for key, wert in ALLES.items() if key not in ("host", "port")}


async def anlage_mit_allem(hass, host, port, namen, komponenten, schreiben):
    """Die Anlage bietet für Heizkreis 1 einen Raumfühler und für beide ein Zeitprogramm."""
    if not schreiben:
        return [], {}, {}
    return [], {"hk1": {"uri": None, "sekunden": None}}, {"hk1": FENSTER, "hk2": FENSTER}


async def nicht_lesbar(*_):
    return None


def unveraendert(schritt) -> dict:
    """Was ein Formular liefert, wenn der Nutzer nichts anfasst: Vorgaben und Vorschläge."""
    eingabe = {}
    for feld in schritt["data_schema"].schema:
        if feld.default is not vol.UNDEFINED:
            eingabe[str(feld)] = feld.default()
        elif (feld.description or {}).get("suggested_value") is not None:
            eingabe[str(feld)] = feld.description["suggested_value"]
    return eingabe


async def bis_zum_speichern(flow, schritt, eingaben=None, gezeigt=None) -> dict:
    """Schickt jeden weiteren Schritt unverändert ab - oder mit dem, was eingaben für ihn nennt."""
    for _ in range(8):
        if schritt["type"] == "create_entry":
            return schritt["data"]
        name = schritt["step_id"]
        if gezeigt is not None:
            gezeigt.append(name)
        eingabe = unveraendert(schritt) if schritt.get("data_schema") else {}
        schritt = await getattr(flow, f"async_step_{name}")({**eingabe, **(eingaben or {}).get(name, {})})
    raise AssertionError("kein Ende")


@pytest.fixture
def zeitprogramm_lesbar(monkeypatch):
    """Der Schritt der Zeitpläne liest, was im Zeitprogramm der Anlage steht."""
    from eta_heating_ws.api import ETAApiClient, ETAValue

    async def lesen(self, uri):
        return ETAValue(0.0, "00:00 - 00:00 0,0", "°C", False, 1)

    monkeypatch.setattr(modul, "async_get_clientsession", lambda hass: None)
    monkeypatch.setattr(ETAApiClient, "async_get_value", lesen)


def test_jedes_feld_steht_in_genau_einem_menuepunkt():
    """Zusammen sind es die Felder der Ersteinrichtung ohne die Adresse.

    Was in keinem Formular steht - Pelletpreis, Fassungsvermögen des
    Lagers, Lieferungen -, bleibt beim Speichern trotzdem erhalten, siehe
    test_unveraendert_abgeschickt_aendert_kein_menuepunkt_etwas.
    """
    verteilt = [feld for felder in ABSCHNITTE.values() for feld in felder]
    einrichtung = {str(feld) for feld in _connection_schema({}).schema} - {"host", "port"}

    assert len(verteilt) == len(set(verteilt))
    assert set(verteilt) == einrichtung
    for abschnitt, felder in ABSCHNITTE.items():
        assert [str(feld) for feld in _abschnitt_schema(abschnitt, {}).schema] == list(felder)


def test_jeder_menuepunkt_kennt_seine_folgeschritte():
    assert set(ABSCHNITTE) < set(FOLGESCHRITTE)
    assert FOLGESCHRITTE["abfrage"] == FOLGESCHRITTE["pellets"] == ()
    for abschnitt in ("fremderzeuger", "verbindungen"):
        assert FOLGESCHRITTE[abschnitt] == (abschnitt,), "diese Menüpunkte bestehen aus ihrem Schritt"
    for schritte in FOLGESCHRITTE.values():
        for schritt in schritte:
            assert hasattr(modul.ETAOptionsFlow, f"async_step_{schritt}")


@pytest.mark.parametrize("datei", ["strings.json", "translations/de.json", "translations/en.json"])
def test_menue_und_formulare_sind_beschriftet(datei):
    schritte = json.loads((TEXTE / datei).read_text(encoding="utf-8"))["options"]["step"]

    assert list(schritte["init"]["menu_options"]) == [
        *ABSCHNITTE,
        "fremderzeuger",
        "verbindungen",
        "weitere_werte",
        "fehlende_werte",
    ]
    assert "einstellungen" not in schritte
    for abschnitt, felder in ABSCHNITTE.items():
        assert schritte[abschnitt]["title"]
        assert list(schritte[abschnitt]["data"]) == list(felder)
        assert set(schritte[abschnitt]["data_description"]) <= set(felder)


@pytest.mark.parametrize(
    ("komponenten", "zusaetzlich"),
    [
        (["kessel", "puffer", "hk1"], []),
        (["kessel", "puffer", "fremderzeuger"], ["fremderzeuger"]),
        (["kessel", "puffer", "puffer2", "hk1"], ["verbindungen"]),
        (["kessel", "fernleitung", "hk1"], ["verbindungen"]),
        (KOMPONENTEN, ["fremderzeuger", "verbindungen"]),
    ],
)
async def test_das_menue_zeigt_fremderzeuger_und_anlagenbild_nur_wo_es_sie_gibt(
    monkeypatch, komponenten, zusaetzlich
):
    flow = modul.ETAOptionsFlow()
    monkeypatch.setattr(
        modul.ETAOptionsFlow, "_current", property(lambda self: {"components": komponenten})
    )
    monkeypatch.setattr(
        modul.ETAOptionsFlow, "async_show_menu", lambda self, **angaben: {"type": "menu", **angaben}
    )

    menue = await flow.async_step_init()

    assert menue == {
        "type": "menu",
        "step_id": "init",
        "menu_options": [
            "anlage",
            "abfrage",
            "pellets",
            "schalten",
            *zusaetzlich,
            "weitere_werte",
            "fehlende_werte",
        ],
    }


@pytest.mark.parametrize(
    ("abschnitt", "schritte"),
    [
        ("anlage", ["fub_names"]),
        ("abfrage", []),
        ("pellets", []),
        ("schalten", ["raumfuehler", "zeitplaene"]),
        ("fremderzeuger", ["fremderzeuger"]),
        ("verbindungen", ["verbindungen"]),
    ],
)
async def test_unveraendert_abgeschickt_aendert_kein_menuepunkt_etwas(
    monkeypatch, zeitprogramm_lesbar, abschnitt, schritte
):
    """Gespeichert wird die ganze Einrichtung - auch alles, was der Menüpunkt gar nicht zeigt."""
    eingabe = unveraendert({"data_schema": _abschnitt_schema(abschnitt, ALLES, ALLES["wetter"])}) if abschnitt in ABSCHNITTE else None
    gezeigt = []

    flow, schritt = await options_schritt(monkeypatch, ALLES, eingabe, abschnitt, anlage_mit_allem)
    gespeichert = await bis_zum_speichern(flow, schritt, gezeigt=gezeigt)

    assert gezeigt == schritte
    assert gespeichert == GESPEICHERT


@pytest.mark.parametrize("abschnitt", ["anlage", "schalten"])
async def test_antwortet_die_anlage_nicht_bleibt_auch_alles(monkeypatch, abschnitt):
    eingabe = unveraendert({"data_schema": _abschnitt_schema(abschnitt, ALLES)})
    bisher = {**ALLES, "puffer2_volumen": None}

    flow, schritt = await options_schritt(monkeypatch, bisher, eingabe, abschnitt, nicht_lesbar)
    gespeichert = await bis_zum_speichern(flow, schritt)

    assert gespeichert == {**GESPEICHERT, "puffer2_volumen": None}


async def test_abfrage_speichert_nur_ihre_drei_felder(monkeypatch):
    _, ergebnis = await options_schritt(
        monkeypatch,
        ALLES,
        {"scan_interval": 30.0, "schnell_intervall": 0.0, "enable_errors": True},
        "abfrage",
    )

    assert ergebnis["type"] == "create_entry"
    assert ergebnis["data"] == {
        **GESPEICHERT,
        "scan_interval": 30,
        "schnell_intervall": 0,
        "enable_errors": True,
    }
    assert type(ergebnis["data"]["scan_interval"]) is int


async def test_pellets_speichert_nur_ihre_vier_felder(monkeypatch):
    """Der Pelletpreis gehört nicht dazu: Er steht im Zahlenfeld am Gerät und bleibt, wie er ist."""
    _, ergebnis = await options_schritt(
        monkeypatch,
        ALLES,
        {"pellet_kwh_per_kg": 4.9, "verbrauch_zeitraeume": True, "prognose": True},
        "pellets",
    )

    assert ergebnis["data"] == {
        **GESPEICHERT,
        "pellet_kwh_per_kg": 4.9,
        "verbrauch_zeitraeume": True,
        "prognose": True,
        "wetter": "",
    }, "das geleerte Wetterfeld heißt: keine Vorhersage"
    assert ergebnis["data"]["pellet_preis"] == 289.0


async def test_formulare_der_menuepunkte_sind_mit_dem_bisherigen_vorbelegt(monkeypatch):
    monkeypatch.setattr(modul.ETAOptionsFlow, "_current", property(lambda self: ALLES))
    monkeypatch.setattr(
        modul.ETAOptionsFlow, "async_show_form", lambda self, **angaben: {"type": "form", **angaben}
    )
    monkeypatch.setattr(modul, "wetter_vorschlag", lambda hass, current: current["wetter"])
    flow = modul.ETAOptionsFlow()
    flow.hass = None

    pellets = await flow.async_step_pellets()
    anlage = await flow.async_step_anlage()
    abfrage = await flow.async_step_abfrage()
    schalten = await flow.async_step_schalten()

    assert unveraendert(pellets) == {
        "pellet_kwh_per_kg": 4.7,
        "verbrauch_zeitraeume": False,
        "prognose": False,
        "wetter": "weather.zuhause",
    }
    assert unveraendert(anlage) == {
        "anzahl_puffer": "2",
        "anzahl_warmwasser": "1",
        "anzahl_heizkreise": "2",
        "components": ["solar", "fremderzeuger"],
        CONF_FEHLENDE_AUSBLENDEN: True,
    }
    assert unveraendert(abfrage) == {"scan_interval": 45, "schnell_intervall": 5, "enable_errors": False}
    assert unveraendert(schalten) == {"enable_switches": True, "kessel_sperre": True}
    assert (anlage["last_step"], abfrage["last_step"], pellets["last_step"]) == (False, True, True)


async def test_anlage_fragt_nach_einem_neu_gewaehlten_fremderzeuger(monkeypatch):
    """Er weiß noch nicht, woran er erkennt, dass geheizt wird."""
    bisher = {"components": ["kessel", "puffer"], "enable_switches": True}
    gezeigt = []

    flow, schritt = await options_schritt(
        monkeypatch, bisher, optionen(components=["puffer", "fremderzeuger"])
    )
    gespeichert = await bis_zum_speichern(
        flow,
        schritt,
        {"fremderzeuger": {CONF_FREMDERZEUGER_ENTITAET: OFEN, CONF_FREMDERZEUGER_SPERRT: ["kessel"]}},
        gezeigt,
    )

    assert gezeigt == ["fub_names", "fremderzeuger"]
    assert gespeichert[CONF_FREMDERZEUGER_ENTITAET] == OFEN
    assert gespeichert[CONF_FREMDERZEUGER_SPERRT] == ["kessel"]
    assert gespeichert["enable_switches"] is True, "der Schreibzugriff bleibt, wie er war"


async def test_anlage_fragt_nach_den_verbindungen_wenn_sich_die_komponenten_aendern(monkeypatch):
    bisher = {"components": ["kessel", "puffer", "hk1"]}
    gezeigt = []

    flow, schritt = await options_schritt(
        monkeypatch, bisher, optionen(components=["puffer", "puffer2", "hk1"])
    )
    gespeichert = await bis_zum_speichern(
        flow, schritt, {"verbindungen": {verbindung_feld("hk1"): "puffer"}}, gezeigt
    )

    assert gezeigt == ["fub_names", "verbindungen"]
    assert gespeichert["verbindungen"]["hk1"] == "puffer"


async def test_anlage_nimmt_abgewaehltes_aus_der_einrichtung(monkeypatch):
    """Zweiter Puffer, Heizkreis 2 und Fremderzeuger gibt es nicht mehr - ihre Angaben auch nicht."""
    flow, schritt = await options_schritt(
        monkeypatch, ALLES, optionen(components=["puffer", "fwm", "hk1", "solar"])
    )
    gespeichert = await bis_zum_speichern(flow, schritt)

    for weg in (
        "puffer2_volumen",
        CONF_FREMDERZEUGER_NAME,
        CONF_FREMDERZEUGER_FUEHLER,
        CONF_FREMDERZEUGER_SPERRT,
        CONF_FREMDERZEUGER_SCHWELLE,
    ):
        assert weg not in gespeichert, weg
    assert gespeichert["components"] == normalize_components(["puffer", "fwm", "hk1", "solar"])
    assert set(gespeichert["fub_names"]) == set(
        fub_roles_for_components(gespeichert["components"])
    )
    assert gespeichert["puffer_volumen"] == 1000
    assert gespeichert["hk1_raumfuehler"] == "sensor.wohnzimmer"
    assert gespeichert["hk2_zeitplan"] is None, "ausdrücklich Geleertes bleibt geleert"
    assert gespeichert[CONF_FREMDERZEUGER_ENTITAET] is None


async def test_schalten_neu_eingeschaltet_warnt_und_fragt_den_fremderzeuger(
    monkeypatch, zeitprogramm_lesbar
):
    """Erst mit Schreibzugriff lässt sich wählen, welche Kessel der Fremderzeuger sperrt."""
    bisher = {**ALLES, "enable_switches": False, "kessel_sperre": False}
    gezeigt = []

    flow, schritt = await options_schritt(
        monkeypatch, bisher, {"enable_switches": True, "kessel_sperre": False}, "schalten", anlage_mit_allem
    )
    gespeichert = await bis_zum_speichern(flow, schritt, gezeigt=gezeigt)

    assert gezeigt == ["switch_warning", "fremderzeuger", "raumfuehler", "zeitplaene"]
    assert gespeichert == {**GESPEICHERT, "kessel_sperre": False}


async def test_schalten_ausgeschaltet_fragt_nichts_und_liest_die_anlage_nicht(monkeypatch):
    """Raumfühler und Zeitplan fallen weg wie bisher - ausdrücklich Geleertes bleibt geleert."""
    gelesen = []

    async def pruefung(*angaben):
        gelesen.append(angaben)
        return [], {}, {}

    flow, ergebnis = await options_schritt(
        monkeypatch, ALLES, {"enable_switches": False, "kessel_sperre": True}, "schalten", pruefung
    )

    assert ergebnis["type"] == "create_entry"
    assert gelesen == []
    erwartet = {**GESPEICHERT, "enable_switches": False}
    del erwartet["hk1_raumfuehler"], erwartet["hk1_zeitplan"]
    assert ergebnis["data"] == erwartet


async def test_schalten_laesst_fallen_was_die_anlage_nicht_mehr_anbietet(monkeypatch):
    """Meldet die Anlage keinen Raumfühler und kein Zeitprogramm mehr, schreibt auch niemand mehr dorthin."""

    async def ohne_alles(*_):
        return [], {}, {}

    _, ergebnis = await options_schritt(
        monkeypatch, ALLES, {"enable_switches": True, "kessel_sperre": True}, "schalten", ohne_alles
    )

    erwartet = dict(GESPEICHERT)
    del erwartet["hk1_raumfuehler"], erwartet["hk1_zeitplan"]
    assert ergebnis["data"] == erwartet


async def test_fremderzeuger_als_menuepunkt(monkeypatch):
    """Ohne Schreibzugriff zeigt er nur Name, Entität und Fühler - was er sperrt, bleibt gespeichert."""
    bisher = {**ALLES, "enable_switches": False}

    flow, schritt = await options_schritt(monkeypatch, bisher, abschnitt="fremderzeuger")

    assert schritt["step_id"] == "fremderzeuger"
    assert [str(feld) for feld in schritt["data_schema"].schema] == [
        CONF_FREMDERZEUGER_NAME,
        CONF_FREMDERZEUGER_ENTITAET,
        CONF_FREMDERZEUGER_FUEHLER,
    ]

    ohne = await flow.async_step_fremderzeuger({CONF_FREMDERZEUGER_NAME: "Ofen"})
    assert ohne["errors"] == {"base": "fremderzeuger_ohne_quelle"}

    fertig = await flow.async_step_fremderzeuger(
        {CONF_FREMDERZEUGER_NAME: "Ofen", CONF_FREMDERZEUGER_ENTITAET: OFEN}
    )
    erwartet = {
        **GESPEICHERT,
        "enable_switches": False,
        CONF_FREMDERZEUGER_NAME: "Ofen",
        CONF_FREMDERZEUGER_ENTITAET: OFEN,
        CONF_FREMDERZEUGER_FUEHLER: None,
    }
    del erwartet["hk1_raumfuehler"], erwartet["hk1_zeitplan"], erwartet[CONF_FREMDERZEUGER_SCHWELLE]
    assert fertig["type"] == "create_entry"
    assert fertig["data"] == erwartet, "ohne Fühler gibt es auch keine Sperrtemperatur mehr"


async def test_verbindungen_als_menuepunkt(monkeypatch):
    flow, schritt = await options_schritt(monkeypatch, ALLES, abschnitt="verbindungen")

    assert schritt["step_id"] == "verbindungen"
    vorbelegt = unveraendert(schritt)
    assert vorbelegt[verbindung_feld("puffer2")] == "kessel"

    kreis = await flow.async_step_verbindungen(
        {**vorbelegt, verbindung_feld("puffer"): "puffer2", verbindung_feld("puffer2"): "puffer"}
    )
    assert kreis["errors"] == {"base": "verbindung_im_kreis"}

    fertig = await flow.async_step_verbindungen({**vorbelegt, verbindung_feld("puffer2"): "puffer"})
    assert fertig["type"] == "create_entry"
    assert fertig["data"] == {
        **GESPEICHERT,
        "verbindungen": {**GESPEICHERT["verbindungen"], "puffer2": "puffer"},
    }
