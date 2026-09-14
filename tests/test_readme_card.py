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


ABSICHTLICHE_BEISPIELE = {
    "sensor.eta_heizung_boiler_temperature",
}
"""Erwähnungen, die absichtlich keiner echten Entität entsprechen.

Hier steht nur das englische Beispiel aus dem Sprachhinweis. Namen, die
auf einen Unterstrich enden, sind im Fließtext als Präfix gemeint
(z.B. "sensor.eta_heizung_puffer_fuhler_") und werden ohnehin übergangen.
"""


def readme_text() -> str:
    return README.read_text(encoding="utf-8")


def test_jede_genannte_entitaet_kann_entstehen():
    """Jede sensor.*-Erwähnung im README muss einer echten Entität entsprechen.

    Betrifft auch den Fließtext, nicht nur die Karte - ein Tippfehler in
    einer Anleitung kostet den Nutzer genauso viel Zeit wie einer im YAML.
    """
    import json
    import re

    from homeassistant.util import slugify

    from .conftest import UEBERSETZUNGEN

    namen = json.loads(
        (UEBERSETZUNGEN / "de.json").read_text(encoding="utf-8")
    )["entity"]["sensor"]
    moeglich = {
        f"sensor.{slugify('ETA Heizung ' + eintrag['name'])}"
        for eintrag in namen.values()
    }
    genannt = set(re.findall(r"sensor\.eta_heizung_[a-z0-9_]+", readme_text()))

    genannt = {name for name in genannt if not name.endswith("_")}
    unbekannt = sorted(genannt - moeglich - ABSICHTLICHE_BEISPIELE)
    assert not unbekannt, f"README nennt Entitäten, die nicht entstehen: {unbekannt}"


def test_jede_komponente_ist_beschrieben():
    text = readme_text()
    for key, info in COMPONENTS.items():
        assert info["name"] in text or key in text, key


def test_genannte_grenzwerte_stimmen_mit_dem_code_ueberein():
    """Zahlen im Fließtext veralten still - hier fallen sie auf."""
    import json
    from pathlib import Path

    from eta_webservices.const import (
        DEFAULT_PELLET_KWH_PER_KG,
        DEFAULT_SCAN_INTERVAL,
        MAX_SCAN_INTERVAL,
        MIN_SCAN_INTERVAL,
        PUFFER_FUEHLER_MAX,
    )

    text = readme_text()
    hacs = json.loads(
        (Path(__file__).resolve().parents[1] / "hacs.json").read_text(encoding="utf-8")
    )

    erwartet = {
        f"{DEFAULT_SCAN_INTERVAL} Sekunden": "Standard-Abfrageintervall",
        f"{MIN_SCAN_INTERVAL} bis {MAX_SCAN_INTERVAL}": "Intervallgrenzen",
        str(DEFAULT_PELLET_KWH_PER_KG).replace(".", ","): "Standard-Heizwert",
        f"3 bis {PUFFER_FUEHLER_MAX}": "Pufferfühler-Spanne",
        hacs["homeassistant"].rsplit(".", 1)[0]: "Mindestversion von Home Assistant",
    }
    for wert, label in erwartet.items():
        assert wert in text, f"{label}: '{wert}' fehlt im README"


def test_genannte_bilder_werden_ausgeliefert():
    import re

    from eta_webservices.images import IMAGES_DATA

    for bild in re.findall(r"ha-eta-webservices/([a-z0-9_]+)\.png", readme_text()):
        assert bild in IMAGES_DATA, bild


def test_fub_standardnamen_stehen_in_der_tabelle():
    from eta_webservices.const import FUB_ROLE_DEFAULT_NAMES

    text = readme_text()
    for rolle, namen in FUB_ROLE_DEFAULT_NAMES.items():
        assert any(f"`{name}`" in text for name in namen), rolle
