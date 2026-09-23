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
