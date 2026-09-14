"""Prüft die Dashboard-Vorlage im README gegen die echte Integration.

Die Karte im README ist Teil des Produkts: Wenn sie Entitäten oder
Elementtypen nennt, die es nicht gibt, bekommt der Nutzer im Dashboard
einen Konfigurationsfehler. Deshalb wird sie hier gegen die tatsächlich
erzeugten Entitäten und gegen die gültigen picture-elements-Typen geprüft.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

from eta_webservices.const import COMPONENTS

README = Path(__file__).resolve().parents[1] / "README.md"

GUELTIGE_ELEMENTTYPEN = {
    "conditional",
    "icon",
    "image",
    "service-button",
    "action-button",
    "state-badge",
    "state-icon",
    "state-label",
}


def yaml_bloecke():
    text = README.read_text(encoding="utf-8")
    return [yaml.safe_load(b) for b in re.findall(r"```yaml\n(.*?)```", text, re.DOTALL)]


@pytest.fixture(scope="module")
def karte():
    for block in yaml_bloecke():
        if isinstance(block, dict) and block.get("type") == "grid":
            return block
    pytest.fail("keine grid-Karte im README gefunden")


def alle_elemente(karte):
    for unterkarte in karte["cards"]:
        for element in unterkarte["card"]["elements"]:
            yield element


def test_alle_yaml_bloecke_sind_gueltig():
    assert yaml_bloecke()


def test_je_komponente_genau_eine_karte(karte):
    marker = [
        unterkarte["conditions"][0]["state"] for unterkarte in karte["cards"]
    ]
    assert marker == list(COMPONENTS)


def test_karten_verweisen_auf_die_richtige_grafik(karte):
    for komponente, unterkarte in zip(COMPONENTS, karte["cards"]):
        erwartet = f"{COMPONENTS[komponente]['image']}.png"
        assert unterkarte["card"]["image"].endswith(erwartet)


def test_nur_gueltige_elementtypen(karte):
    for element in alle_elemente(karte):
        assert element["type"] in GUELTIGE_ELEMENTTYPEN


def test_spaltenzahl_reicht_fuer_alle_komponenten(karte):
    assert karte["columns"] >= 4


async def test_jede_referenzierte_entitaet_existiert(hass, entry, karte):
    from homeassistant.util import slugify

    from .test_sensors import setup_integration

    entry.data["components"] = list(COMPONENTS)
    _, by_name = await setup_integration(hass, entry)
    vorhanden = {f"sensor.{slugify('ETA Heizung ' + name)}" for name in by_name}

    referenziert = {
        unterkarte["conditions"][0]["entity"] for unterkarte in karte["cards"]
    } | {element["entity"] for element in alle_elemente(karte) if "entity" in element}

    fehlend = sorted(referenziert - vorhanden)
    assert not fehlend, f"README verweist auf nicht existierende Entitäten: {fehlend}"
