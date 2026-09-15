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

WURZEL = Path(__file__).resolve().parents[1]
README = WURZEL / "README.md"
KARTE = WURZEL / "dashboard" / "eta-karte.yaml"

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
    return yaml.safe_load(KARTE.read_text(encoding="utf-8"))


def varianten(karte):
    """Die drei Bildschirm-Varianten der Karte."""
    return karte["cards"]


def raster(karte):
    return [variante["card"] for variante in varianten(karte)]


def abgesichert(karte):
    """Entitäten, die in einer eigenen Bedingung stecken und fehlen dürfen."""
    return {
        innen["entity"]
        for element in alle_elemente(karte)
        if element["type"] == "conditional"
        for innen in element["elements"]
    }


def alle_elemente(karte):
    """Alle Elemente der Karte, auch die in Bedingungen verschachtelten.

    Ohne den Abstieg in "conditional" blieben Schalter und Betriebsart
    ungeprüft.
    """

    def absteigen(elemente):
        for element in elemente:
            yield element
            yield from absteigen(element.get("elements", []))

    for gitter in raster(karte):
        for unterkarte in gitter["cards"]:
            yield from absteigen(unterkarte["card"]["elements"])


def test_alle_yaml_bloecke_im_readme_sind_gueltig():
    assert yaml_bloecke()


def test_karte_hat_drei_bildschirm_varianten(karte):
    assert karte["type"] == "vertical-stack"
    abfragen = [v["conditions"][0]["media_query"] for v in varianten(karte)]
    assert len(abfragen) == 3
    for variante in varianten(karte):
        assert variante["conditions"][0]["condition"] == "screen"


def test_varianten_decken_jede_breite_genau_einmal_ab(karte):
    """Ohne Lücke und ohne Überlappung - sonst ist die Karte leer oder doppelt."""
    import re as regex

    grenzen = []
    for variante in varianten(karte):
        abfrage = variante["conditions"][0]["media_query"]
        minimum = regex.search(r"min-width:\s*(\d+)px", abfrage)
        maximum = regex.search(r"max-width:\s*(\d+)px", abfrage)
        grenzen.append(
            (int(minimum.group(1)) if minimum else 0,
             int(maximum.group(1)) if maximum else 10000)
        )
    grenzen.sort()
    assert grenzen[0][0] == 0
    for (_, bis), (ab, _) in zip(grenzen, grenzen[1:]):
        assert ab == bis + 1, f"Lücke oder Überlappung bei {bis}/{ab}"


def test_je_variante_und_komponente_genau_eine_karte(karte):
    for gitter in raster(karte):
        marker = [u["conditions"][0]["state"] for u in gitter["cards"]]
        assert marker == list(COMPONENTS)


def test_karten_verweisen_auf_die_richtige_grafik(karte):
    for gitter in raster(karte):
        for komponente, unterkarte in zip(COMPONENTS, gitter["cards"]):
            erwartet = f"{COMPONENTS[komponente]['image']}.png"
            assert unterkarte["card"]["image"].endswith(erwartet)


def test_nur_gueltige_elementtypen(karte):
    for element in alle_elemente(karte):
        assert element["type"] in GUELTIGE_ELEMENTTYPEN


def test_schmale_varianten_haben_weniger_spalten(karte):
    """Je schmaler die Ansicht, desto weniger Spalten - sonst wird geschnitten."""
    import re as regex

    paare = []
    for gitter, variante in zip(raster(karte), varianten(karte)):
        abfrage = variante["conditions"][0]["media_query"]
        minimum = regex.search(r"min-width:\s*(\d+)px", abfrage)
        paare.append((int(minimum.group(1)) if minimum else 0, gitter["columns"]))
    paare.sort()
    spalten = [s for _, s in paare]
    assert spalten == sorted(spalten), f"Spaltenzahl nicht aufsteigend: {paare}"


def test_readme_verweist_auf_die_kartendatei():
    text = README.read_text(encoding="utf-8")
    assert "dashboard/eta-karte.yaml" in text
    assert "Panel" in text


async def test_jede_referenzierte_entitaet_existiert(hass, entry, karte):
    import json

    from homeassistant.util import slugify

    from .conftest import UEBERSETZUNGEN

    from .test_sensors import setup_integration

    from eta_webservices import select as select_platform
    from eta_webservices import switch as switch_platform

    entry.data["components"] = list(COMPONENTS)
    entry.data["enable_switches"] = True
    _, by_name = await setup_integration(hass, entry)
    vorhanden = {f"sensor.{slugify('ETA Heizung ' + name)}" for name in by_name}

    for bereich, platform in (("switch", switch_platform), ("select", select_platform)):
        gesammelt: list = []
        await platform.async_setup_entry(hass, entry, gesammelt.extend)
        namen = json.loads(
            (UEBERSETZUNGEN / "de.json").read_text(encoding="utf-8")
        )["entity"][bereich]
        vorhanden |= {
            f"{bereich}.{slugify('ETA Heizung ' + namen[e.translation_key]['name'])}"
            for e in gesammelt
        }

    referenziert = {
        unterkarte["conditions"][0]["entity"]
        for gitter in raster(karte)
        for unterkarte in gitter["cards"]
    } | {
        element["entity"]
        for element in alle_elemente(karte)
        if "entity" in element and element["type"] != "conditional"
    }

    fehlend = sorted(referenziert - vorhanden - abgesichert(karte))
    assert not fehlend, f"README verweist auf nicht existierende Entitäten: {fehlend}"


def test_nicht_immer_vorhandene_elemente_sind_abgesichert(karte):
    """Wer eine Entität nennt, die fehlen kann, muss sie absichern.

    Schalter und Betriebsart entstehen nur bei freigegebenem
    Schreibzugriff. Sie müssen deshalb in einer Bedingung auf genau ihre
    eigene Entität stecken.
    """
    for element in alle_elemente(karte):
        if element["type"] != "conditional":
            continue
        bedingung = element["conditions"][0]
        assert bedingung["state_not"] == "unknown"
        for innen in element["elements"]:
            assert innen["entity"] == bedingung["entity"], innen


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
    """Jede Entitäts-Erwähnung im README muss einer echten Entität entsprechen.

    Betrifft auch den Fließtext, nicht nur die Karte - ein Tippfehler in
    einer Anleitung kostet den Nutzer genauso viel Zeit wie einer im YAML.
    """
    import json
    import re

    from homeassistant.util import slugify

    from .conftest import UEBERSETZUNGEN

    entitaeten = json.loads(
        (UEBERSETZUNGEN / "de.json").read_text(encoding="utf-8")
    )["entity"]
    moeglich = {
        f"{bereich}.{slugify('ETA Heizung ' + eintrag['name'])}"
        for bereich, namen in entitaeten.items()
        for eintrag in namen.values()
    }
    genannt = set(
        re.findall(
            r"\b(?:binary_sensor|sensor)\.eta_heizung_[a-z0-9_]+",
            readme_text() + KARTE.read_text(encoding="utf-8"),
        )
    )

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

    text = readme_text() + KARTE.read_text(encoding="utf-8")
    bilder = set(re.findall(r"ha-eta-webservices/([a-z0-9_]+)\.png", text))
    assert bilder, "keine Bildverweise gefunden"
    for bild in bilder:
        assert bild in IMAGES_DATA, bild


def test_kartendatei_ist_aktuell():
    """Die Karte muss zu ihrem Erzeugungsskript passen.

    Sonst laufen eine von Hand geänderte Karte und das Skript auseinander,
    und der nächste Lauf des Skripts wirft die Änderung weg.
    """
    import subprocess
    import sys

    vorher = KARTE.read_text(encoding="utf-8")
    subprocess.run(
        [sys.executable, str(WURZEL / "dashboard" / "karte_bauen.py")],
        check=True,
        capture_output=True,
    )
    nachher = KARTE.read_text(encoding="utf-8")
    assert vorher == nachher, (
        "eta-karte.yaml weicht von karte_bauen.py ab - "
        "Skript ausführen oder Änderung dort nachziehen"
    )


def test_fub_standardnamen_stehen_in_der_tabelle():
    from eta_webservices.const import FUB_ROLE_DEFAULT_NAMES

    text = readme_text()
    for rolle, namen in FUB_ROLE_DEFAULT_NAMES.items():
        assert any(f"`{name}`" in text for name in namen), rolle


def entitaetstabelle() -> list[str]:
    """Die Zeilen, die die Entitätsübersicht im README enthalten muss."""
    import json

    from homeassistant.util import slugify

    from eta_webservices.const import SELECTS, SENSORS, SWITCHES

    from .conftest import UEBERSETZUNGEN

    namen = json.loads(
        (UEBERSETZUNGEN / "de.json").read_text(encoding="utf-8")
    )["entity"]

    def zeile(bereich, key, einheit):
        name = namen[bereich][key]["name"]
        eid = f"{bereich}.{slugify('ETA Heizung ' + name)}"
        return f"| `{eid}` | {name} | {einheit} |"

    zeilen = [
        zeile(
            "sensor",
            info["translation_key"],
            info.get("default_unit") or ("Text" if info.get("is_string") else "–"),
        )
        for info in SENSORS.values()
    ]
    zeilen += [zeile("switch", i["translation_key"], "Schalter") for i in SWITCHES.values()]
    zeilen += [zeile("select", i["translation_key"], "Auswahl") for i in SELECTS.values()]
    return zeilen


def test_entitaetsuebersicht_ist_vollstaendig():
    """Jede Entität muss in der Übersicht des README stehen.

    Sonst beschreibt die Anleitung eine Integration, die es so nicht
    mehr gibt.
    """
    text = readme_text()
    fehlend = [zeile for zeile in entitaetstabelle() if zeile not in text]
    assert not fehlend, f"Nicht in der README-Übersicht: {fehlend}"
