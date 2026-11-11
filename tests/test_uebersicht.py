"""Die Karte "ETA Übersicht": wer woran hängt und was die Karte von der Anlage erfährt.

Der Menübaum nennt zu "Erzeuger" und "Verbraucher" eines Puffers nur
Temperaturen und Einstellungen, nicht den angeschlossenen Funktionsblock.
Deshalb gilt eine Vorgabe, und bei mehreren Puffern oder einer Fernleitung
fragt der Dialog nach.
"""

from __future__ import annotations

import json

import eta_heating_ws
from eta_heating_ws.uebersicht import _ws_uebersicht, karte_adresse
from eta_heating_ws.verbindungen import (
    braucht_auswahl,
    feld,
    felder,
    im_kreis,
    moegliche_quellen,
    verbindungen,
    vorgabe,
)

from .conftest import FakeConfigEntry, ohne_version
from .test_config_flow import optionen, options_schritt
from .test_zeitprogramm_karte import Verbindung

EINFACH = ["kessel", "puffer", "fwm", "hk1", "hk2", "lager", "solar"]
MIT_FERNLEITUNG = ["kessel", "puffer", "puffer2", "fwm", "hk1", "hk2", "solar", "brenner", "fernleitung"]


def test_vorgabe_einer_einfachen_anlage():
    assert vorgabe(EINFACH) == {
        "puffer": "kessel",
        "fwm": "puffer",
        "hk1": "puffer",
        "hk2": "puffer",
        "solar": "puffer",
    }
    assert not braucht_auswahl(EINFACH), "mit einem Puffer gibt es nichts zu fragen"


def test_vorgabe_mit_mehreren_puffern_und_fernleitung():
    wege = vorgabe(MIT_FERNLEITUNG)

    assert wege["puffer"] == "kessel"
    assert wege["puffer2"] == "puffer", "weitere Puffer hängen hintereinander"
    assert wege["fernleitung"] == "puffer"
    assert wege["hk1"] == wege["fwm"] == "puffer2", "Verbraucher am letzten Puffer"
    assert wege["solar"] == wege["brenner"] == "puffer", "Erzeuger laden in den ersten"
    assert braucht_auswahl(MIT_FERNLEITUNG)


def test_ohne_puffer_haengt_alles_am_kessel():
    wege = vorgabe(["kessel", "hk1", "fwm", "solar"])

    assert wege == {"hk1": "kessel", "fwm": "kessel", "solar": None}


def test_puffer_und_fernleitung_bekommen_und_geben_waerme():
    """Zur Wahl stehen Kessel, jeder Puffer und die Fernleitung - nur nicht das Teil selbst."""
    assert moegliche_quellen(MIT_FERNLEITUNG, "puffer2") == ["kessel", "puffer", "fernleitung"]
    assert moegliche_quellen(MIT_FERNLEITUNG, "fernleitung") == ["kessel", "puffer", "puffer2"]
    assert moegliche_quellen(MIT_FERNLEITUNG, "hk1") == ["kessel", "puffer", "puffer2", "fernleitung"]
    assert moegliche_quellen(MIT_FERNLEITUNG, "solar") == ["puffer", "puffer2"], "lädt in einen Puffer"


def test_gespeicherte_auswahl_gilt():
    """Kessel -> Puffer 1 -> Fernleitung -> Puffer 2, Heizkreis 1 am ersten Puffer."""
    wege = verbindungen(MIT_FERNLEITUNG, {"puffer2": "fernleitung", "hk1": "puffer"})

    assert wege["puffer2"] == "fernleitung"
    assert wege["fernleitung"] == "puffer"
    assert wege["hk1"] == "puffer"
    assert wege["hk2"] == "puffer2", "der Rest bleibt bei der Vorgabe"


def test_auswahl_fuer_entfernte_teile_wird_uebergangen():
    wege = verbindungen(EINFACH, {"hk1": "puffer2", "hk3": "puffer", "puffer": "fernleitung"})

    assert wege == vorgabe(EINFACH)


def test_kreis_wird_erkannt_und_haengt_am_kessel():
    assert im_kreis(MIT_FERNLEITUNG, {"puffer": "puffer2"}), "Puffer 2 hängt laut Vorgabe an Puffer 1"
    assert not im_kreis(MIT_FERNLEITUNG, {"puffer2": "fernleitung"})

    wege = verbindungen(MIT_FERNLEITUNG, {"puffer": "puffer2"})

    assert "kessel" in (wege["puffer"], wege["puffer2"])
    assert not im_kreis(MIT_FERNLEITUNG, {k: v for k, v in wege.items() if v})


def test_felder_nur_wo_es_etwas_zu_waehlen_gibt():
    assert felder(MIT_FERNLEITUNG) == [
        "puffer", "puffer2", "fwm", "hk1", "hk2", "solar", "brenner", "fernleitung"
    ]
    assert "solar" not in felder(["kessel", "puffer", "fernleitung", "solar"]), "nur ein Puffer als Ziel"


FUB_NAMEN = {"kessel": "Kessel", "sys": "Sys", "pufferflex": "PufferFlex", "pufferflex2": "PufferFlex 2"}


async def test_dialog_fragt_bei_zwei_puffern(monkeypatch):
    flow, _ = await options_schritt(
        monkeypatch, {}, optionen(components=["puffer", "puffer2", "hk1", "fernleitung"])
    )
    schritt = await flow.async_step_fub_names({**FUB_NAMEN, "hk": "HK", "fernleitung": "Fernl"})

    assert schritt["step_id"] == "verbindungen"
    vorbelegt = {str(k): k.default() for k in schritt["data_schema"].schema}
    assert vorbelegt == {
        feld("puffer"): "kessel",
        feld("puffer2"): "puffer",
        feld("hk1"): "puffer2",
        feld("fernleitung"): "puffer",
    }

    fertig = await flow.async_step_verbindungen({**vorbelegt, feld("puffer2"): "fernleitung"})

    assert fertig["type"] == "create_entry"
    assert fertig["data"]["verbindungen"]["puffer2"] == "fernleitung"


async def test_dialog_nimmt_keinen_kreis_an(monkeypatch):
    flow, _ = await options_schritt(monkeypatch, {}, optionen(components=["puffer", "puffer2"]))
    schritt = await flow.async_step_fub_names(FUB_NAMEN)

    nochmal = await flow.async_step_verbindungen(
        {feld("puffer"): "puffer2", feld("puffer2"): "puffer"}
    )

    assert nochmal["type"] == "form"
    assert nochmal["errors"] == {"base": "verbindung_im_kreis"}
    assert {str(k): k.default() for k in nochmal["data_schema"].schema} != {
        str(k): k.default() for k in schritt["data_schema"].schema
    }, "die Auswahl des Nutzers bleibt stehen"


async def test_dialog_zeigt_die_bisherige_auswahl(monkeypatch):
    bisher = {"verbindungen": {"puffer2": "kessel"}}
    flow, _ = await options_schritt(monkeypatch, bisher, optionen(components=["puffer", "puffer2"]))

    schritt = await flow.async_step_fub_names(FUB_NAMEN)

    assert {str(k): k.default() for k in schritt["data_schema"].schema}[feld("puffer2")] == "kessel"


async def test_ohne_menuebaum_bleibt_die_auswahl(monkeypatch):
    from eta_heating_ws import config_flow as modul

    bisher = {"verbindungen": {"puffer2": "kessel"}}
    flow, _ = await options_schritt(monkeypatch, bisher, optionen(components=["puffer", "puffer2"]))

    async def nicht_lesbar(*_):
        return None

    monkeypatch.setattr(modul, "_anlage_pruefen", nicht_lesbar)
    fertig = await flow.async_step_fub_names(FUB_NAMEN)

    assert fertig["type"] == "create_entry"
    assert fertig["data"]["verbindungen"] == {"puffer2": "kessel"}


async def uebersicht(hass):
    verbindung = Verbindung()
    _ws_uebersicht(hass, verbindung, {"id": 3, "type": "eta_heating_ws/uebersicht"})
    [(msg_id, ergebnis)] = verbindung.ergebnisse
    assert msg_id == 3
    json.dumps(ergebnis)
    return ergebnis["anlagen"]


async def test_karte_erfaehrt_teile_und_verbindungen(hass, entry):
    assert await eta_heating_ws.async_setup_entry(hass, entry)
    hass.config_entries.geladen.append(entry)

    [anlage] = await uebersicht(hass)

    assert anlage["eintrag"] == "testeintrag"
    assert anlage["schreiben"] is True
    teile = {teil["id"]: teil for teil in anlage["teile"]}
    assert list(teile) == ["kessel", "puffer", "fwm", "hk1", "hk2"]
    assert teile["kessel"]["art"] == "kessel" and teile["kessel"]["von"] is None
    assert teile["puffer"] == {"id": "puffer", "art": "puffer", "nummer": 1, "block": "PufferFlex", "von": "kessel"}
    assert teile["hk2"]["art"] == "heizkreis" and teile["hk2"]["nummer"] == 2
    assert teile["hk2"]["von"] == "puffer"
    assert teile["fwm"]["bauart"] == "fwm", "das Frischwassermodul bekommt ein eigenes Bild"


async def test_karte_folgt_der_auswahl_im_dialog(hass):
    eintrag = FakeConfigEntry(
        {
            "host": "192.0.2.10",
            "port": 8080,
            "components": ["kessel", "puffer", "puffer2", "hk1", "fernleitung"],
        },
        {"verbindungen": {"puffer2": "fernleitung", "hk1": "puffer"}},
    )
    assert await eta_heating_ws.async_setup_entry(hass, eintrag)
    hass.config_entries.geladen.append(eintrag)

    [anlage] = await uebersicht(hass)

    von = {teil["id"]: teil["von"] for teil in anlage["teile"]}
    assert von == {
        "kessel": None,
        "puffer": "kessel",
        "puffer2": "fernleitung",
        "hk1": "puffer",
        "fernleitung": "puffer",
    }
    assert anlage["schreiben"] is False


async def test_karte_findet_entitaeten_ueber_ihren_schluessel(hass, entry):
    """Auch umbenannte: Die Karte fragt nach dem Schlüssel, nicht nach der ID."""
    assert await eta_heating_ws.async_setup_entry(hass, entry)
    hass.config_entries.geladen.append(entry)
    register = hass.entity_registry
    register.anlegen("sensor.keller_kessel", "eta_static_testeintrag_kessel_temperatur", "testeintrag")
    register.anlegen("switch.eta_heizung_kessel", "eta_switch_testeintrag_kessel_schalter", "testeintrag")
    register.anlegen("sensor.fremd", "eta_static_andere_kessel_temperatur", "andere")
    register.anlegen("sensor.aus", "eta_static_testeintrag_kessel_druck", "testeintrag")
    register.eintraege["sensor.aus"].disabled_by = "user"

    [anlage] = await uebersicht(hass)

    assert anlage["entitaeten"] == {
        "kessel_temperatur": "sensor.keller_kessel",
        "kessel_schalter": "switch.eta_heizung_kessel",
    }


def test_karte_liegt_bei_der_integration():
    from eta_heating_ws.zeitprogramm import OBERFLAECHE

    assert ohne_version(karte_adresse()) == "/eta_heating_ws/oberflaeche/eta-uebersicht-karte.js"
    assert (OBERFLAECHE / "eta-uebersicht-karte.js").is_file()
