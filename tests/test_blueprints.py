"""Prüft die mitgelieferten Blueprints mit dem Schema von Home Assistant.

Ein Blueprint fällt sonst erst beim Nutzer auf: Home Assistant lehnt ihn
beim Importieren ab, und zwar ohne dass jemand von uns es merkt.
"""

from __future__ import annotations

import pathlib

import pytest
from homeassistant.components.automation.config import AUTOMATION_BLUEPRINT_SCHEMA
from homeassistant.components.blueprint.models import Blueprint, BlueprintInputs
from homeassistant.util.yaml import loader as ha_yaml

ORDNER = pathlib.Path(__file__).parent.parent / "blueprints" / "automation" / "eta_webservices"
"""Der Ordner behält den alten Namen der Integration.

Importierte Blueprints merken sich ihre Adresse (source_url). Bliebe der
Ordner nicht, liefe „Erneut importieren“ nach dem Umbenennen ins Leere.
"""
DATEIEN = sorted(ORDNER.glob("*.yaml"))


def laden(pfad: pathlib.Path) -> Blueprint:
    return Blueprint(
        ha_yaml.load_yaml(str(pfad)),
        expected_domain="automation",
        path=str(pfad),
        schema=AUTOMATION_BLUEPRINT_SCHEMA,
    )


def test_es_gibt_blueprints():
    assert DATEIEN


@pytest.mark.parametrize("pfad", DATEIEN, ids=lambda p: p.name)
def test_blueprint_ist_gueltig(pfad):
    bp = laden(pfad)
    assert bp.name
    assert bp.metadata["description"]
    assert bp.inputs


@pytest.mark.parametrize("pfad", DATEIEN, ids=lambda p: p.name)
def test_quellverweis_zeigt_auf_diese_datei(pfad):
    bp = laden(pfad)
    assert bp.metadata["source_url"].endswith(pfad.name)


@pytest.mark.parametrize("pfad", DATEIEN, ids=lambda p: p.name)
def test_eingaben_lassen_sich_einsetzen(pfad):
    """Erst beim Einsetzen zeigt sich, ob jedes !input auch deklariert ist."""
    bp = laden(pfad)
    beispiele = {
        "stoerungsmelder": "binary_sensor.eta_heizung_storung",
        "erinnerung": "binary_sensor.eta_heizung_aschebox_leeren",
        "vorratsmelder": "binary_sensor.eta_heizung_pelletvorrat_niedrig",
        "betriebsart": "select.eta_heizung_heizkreis_1_betriebsart",
        "fenster": ["binary_sensor.fenster_kueche"],
        "aktion": [{"action": "persistent_notification.create", "data": {"message": "x"}}],
        "wartezeit": {"minutes": 5},
        "offen_seit": {"minutes": 1},
        "zurueck_auf": "automatik",
        "sperre": "switch.eta_heizung_kessel_sperren",
        "waermequelle": "input_boolean.kaminofen",
        "sperren_nach": {"minutes": 1},
        "freigeben_nach": {"minutes": 5},
    }
    eingaben = {name: beispiele[name] for name in bp.inputs}
    ergebnis = BlueprintInputs(
        bp, {"use_blueprint": {"path": pfad.name, "input": eingaben}}
    ).async_substitute()

    assert "blueprint" not in ergebnis
    assert ergebnis.get("triggers") or ergebnis.get("trigger")
    assert ergebnis.get("actions") or ergebnis.get("action")


@pytest.mark.parametrize("pfad", DATEIEN, ids=lambda p: p.name)
def test_readme_bietet_den_import_mit_einem_klick(pfad):
    """Jeder Blueprint hat im README einen Import-Knopf auf genau diese Datei."""
    from urllib.parse import quote

    readme = (ORDNER.parents[2] / "README.md").read_text(encoding="utf-8")
    ziel = laden(pfad).metadata["source_url"]
    assert "blueprint_import/?blueprint_url=" + quote(ziel, safe="") in readme


def test_kesselsperre_schreibt_nur_bei_bedarf_und_holt_nach():
    """Der Blueprint zum Sperren des Kessels schont die Anlage und vergisst nichts.

    Der Eingang der Verriegelung ist eine dauerhaft gespeicherte Einstellung:
    Geschrieben wird nur, wenn der Schalter anders steht als verlangt. War
    die Heizung nicht erreichbar, als die Wärmequelle ausging, bliebe der
    Kessel sonst gesperrt - deshalb löst auch die Rückkehr des Schalters aus.
    """
    roh = ha_yaml.load_yaml(str(ORDNER / "kessel_sperren.yaml"))

    rueckkehr = [
        t for t in roh["triggers"] if t.get("not_from") == ["on", "off"] and t.get("to") == ["on", "off"]
    ]
    assert len(rueckkehr) == 1
    assert any(t.get("trigger") == "homeassistant" and t.get("event") == "start" for t in roh["triggers"])

    faelle = roh["actions"][0]["choose"]
    bedingung = {
        fall["sequence"][0]["action"]: fall["conditions"][0]["value_template"] for fall in faelle
    }
    assert "is_state(waermequelle, 'on') and is_state(sperre, 'off')" in bedingung["switch.turn_on"]
    assert "is_state(waermequelle, 'off') and is_state(sperre, 'on')" in bedingung["switch.turn_off"]
