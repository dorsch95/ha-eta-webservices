"""Prüft die Formulare für neue Issues auf GitHub.

GitHub zeigt ein fehlerhaftes Formular nicht an und fällt still auf das
leere Textfeld zurück - dann fehlt genau die Diagnose-Datei, um die es geht.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

ORDNER = Path(__file__).resolve().parents[1] / ".github" / "ISSUE_TEMPLATE"
FORMULARE = sorted(p for p in ORDNER.glob("*.yml") if p.name != "config.yml")
TYPEN = {"markdown", "textarea", "input", "dropdown", "checkboxes"}


def test_es_gibt_formulare():
    assert {p.name for p in FORMULARE} >= {"fehler.yml", "anlage.yml"}


@pytest.mark.parametrize("pfad", FORMULARE, ids=lambda p: p.name)
def test_formular_ist_gueltig(pfad):
    formular = yaml.safe_load(pfad.read_text(encoding="utf-8"))
    assert formular["name"] and formular["description"]

    ids = []
    for feld in formular["body"]:
        assert feld["type"] in TYPEN, feld
        if feld["type"] == "markdown":
            assert feld["attributes"]["value"].strip()
            continue
        assert feld["attributes"]["label"]
        ids.append(feld["id"])
        if feld["type"] == "dropdown":
            assert feld["attributes"]["options"]
    assert len(ids) == len(set(ids)), "doppelte id"


@pytest.mark.parametrize("pfad", FORMULARE, ids=lambda p: p.name)
def test_formular_fragt_nach_der_diagnose(pfad):
    formular = yaml.safe_load(pfad.read_text(encoding="utf-8"))
    diagnose = [f for f in formular["body"] if f.get("id") == "diagnose"]
    assert diagnose and diagnose[0]["validations"]["required"] is True


def test_verweis_zeigt_auf_einen_vorhandenen_abschnitt():
    konfiguration = yaml.safe_load((ORDNER / "config.yml").read_text(encoding="utf-8"))
    readme = (ORDNER.parents[1] / "README.md").read_text(encoding="utf-8")
    for link in konfiguration["contact_links"]:
        anker = link["url"].split("#", 1)[1]
        assert anker == "-fehlersuche"
        assert "## 🩺 Fehlersuche" in readme
