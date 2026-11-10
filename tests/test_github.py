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


WURZEL = ORDNER.parents[1]
RELEASE = WURZEL / ".github" / "workflows" / "release.yml"


def hacs_json() -> dict:
    import json

    return json.loads((WURZEL / "hacs.json").read_text(encoding="utf-8"))


def paket_job() -> dict:
    return yaml.safe_load(RELEASE.read_text(encoding="utf-8"))["jobs"]["paket"]


def test_hacs_laedt_die_zip_datei_vom_release():
    """Nur an einer angehängten Datei zählt GitHub die Downloads.

    HACS lädt sie statt des Quellcodes, wenn hacs.json das sagt. Den
    Hauptzweig kann es dann nicht mehr installieren - dort hängt keine
    Datei -, deshalb ist er in der Versionsauswahl ausgeblendet.
    """
    from eta_heating_ws.const import DOMAIN

    einstellung = hacs_json()
    assert einstellung["zip_release"] is True
    assert einstellung["filename"] == f"{DOMAIN}.zip"
    assert einstellung["hide_default_branch"] is True


def test_release_haengt_die_zip_datei_an():
    job = paket_job()
    schritte = "\n".join(schritt.get("run", "") for schritt in job["steps"])
    assert job["permissions"] == {"contents": "write"}, "sonst darf der Job nichts hochladen"
    assert f'gh release upload "$TAG" "$RUNNER_TEMP/{hacs_json()["filename"]}"' in schritte
    ausloeser = yaml.safe_load(RELEASE.read_text(encoding="utf-8"))[True]
    assert ausloeser["release"]["types"] == ["published"]


def test_zip_datei_entpackt_sich_zur_integration(tmp_path):
    """HACS entpackt die Datei direkt nach custom_components/eta_heating_ws.

    Der Schritt aus dem Workflow läuft hier wirklich: manifest.json muss
    oben in der Zip-Datei liegen, und es fehlt keine Datei der Integration.
    """
    import os
    import shutil
    import subprocess
    import zipfile

    if not shutil.which("zip") or not shutil.which("unzip"):
        pytest.skip("zip oder unzip fehlt auf diesem Rechner")
    packen = next(s["run"] for s in paket_job()["steps"] if "zip -r" in s.get("run", ""))
    subprocess.run(
        ["bash", "-e", "-c", packen],
        cwd=WURZEL,
        env={**os.environ, "RUNNER_TEMP": str(tmp_path)},
        check=True,
        capture_output=True,
    )

    integration = WURZEL / "custom_components" / "eta_heating_ws"
    erwartet = {
        str(pfad.relative_to(integration))
        for pfad in integration.rglob("*")
        if pfad.is_file() and "__pycache__" not in pfad.parts
    }
    with zipfile.ZipFile(tmp_path / hacs_json()["filename"]) as paket:
        enthalten = {name for name in paket.namelist() if not name.endswith("/")}
    assert "manifest.json" in enthalten
    assert enthalten == erwartet
