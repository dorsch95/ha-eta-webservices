"""Prüft, dass alle Übersetzungsdateien dieselben Schlüssel haben."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

COMPONENT = Path(__file__).resolve().parents[1] / "custom_components" / "eta_webservices"
STRINGS = COMPONENT / "strings.json"
TRANSLATIONS = sorted((COMPONENT / "translations").glob("*.json"))


def flatten(data, prefix=""):
    keys = set()
    for key, value in data.items():
        path = f"{prefix}.{key}" if prefix else key
        if isinstance(value, dict):
            keys |= flatten(value, path)
        else:
            keys.add(path)
    return keys


def test_es_gibt_uebersetzungen():
    assert TRANSLATIONS, "keine Übersetzungsdateien gefunden"
    assert {p.name for p in TRANSLATIONS} >= {"de.json", "en.json"}


@pytest.mark.parametrize("path", TRANSLATIONS, ids=lambda p: p.name)
def test_uebersetzung_deckt_alle_schluessel_ab(path):
    erwartet = flatten(json.loads(STRINGS.read_text(encoding="utf-8")))
    vorhanden = flatten(json.loads(path.read_text(encoding="utf-8")))
    assert erwartet == vorhanden


@pytest.mark.parametrize("path", TRANSLATIONS, ids=lambda p: p.name)
def test_keine_leeren_texte(path):
    data = json.loads(path.read_text(encoding="utf-8"))

    def walk(node):
        for value in node.values():
            if isinstance(value, dict):
                walk(value)
            else:
                assert isinstance(value, str) and value.strip()

    walk(data)


def test_fub_felder_sind_uebersetzt():
    from eta_webservices.const import FUB_ROLE_DEFAULT_NAMES

    erwartet = flatten(json.loads(STRINGS.read_text(encoding="utf-8")))
    for role in FUB_ROLE_DEFAULT_NAMES:
        assert f"config.step.fub_names.data.{role}" in erwartet
        assert f"options.step.fub_names.data.{role}" in erwartet


def test_jede_entitaet_ist_in_allen_sprachen_benannt():
    from eta_webservices.const import SENSORS

    schluessel = {info["translation_key"] for info in SENSORS.values()}
    for pfad in TRANSLATIONS:
        namen = json.loads(pfad.read_text(encoding="utf-8"))["entity"]["sensor"]
        assert schluessel <= set(namen), pfad.name


@pytest.mark.parametrize("path", [STRINGS, *TRANSLATIONS], ids=lambda p: p.name)
def test_uebersetzungsschluessel_sind_gueltig(path):
    """Home Assistant lässt nur [a-z0-9-_] als Schlüssel zu.

    hassfest weist Umlaute und Großbuchstaben zurück. Der interne
    Sensorschlüssel darf davon abweichen (er steckt in der unique_id und
    lässt sich nicht mehr ändern), der Übersetzungsschlüssel nicht.
    """
    import re

    daten = json.loads(path.read_text(encoding="utf-8"))
    for bereich, eintraege in daten.get("entity", {}).items():
        for schluessel in eintraege:
            assert re.fullmatch(r"[a-z0-9][a-z0-9\-_]*[a-z0-9]", schluessel), (
                f"{bereich}.{schluessel}"
            )


def test_sensoren_verweisen_auf_gueltige_uebersetzungsschluessel():
    import re

    from eta_webservices.const import SENSORS, puffer_fuehler_info

    schluessel = [info["translation_key"] for info in SENSORS.values()]
    schluessel += [puffer_fuehler_info(i, False)["translation_key"] for i in range(1, 10)]
    for eintrag in schluessel:
        assert re.fullmatch(r"[a-z0-9][a-z0-9\-_]*[a-z0-9]", eintrag), eintrag


def test_jeder_tabellenschluessel_hat_seinen_suchpfad():
    """Die Schlüssel der Tabellen und der Suche müssen deckungsgleich sein.

    Ein Sensor ohne Suchpfad bekäme nie eine URI, ein Suchpfad ohne Sensor
    liefe ins Leere. Der Test fängt außerdem eine Tücke von Python ab: Zwei
    direkt aufeinanderfolgende Zeichenketten werden stillschweigend
    verkettet. Ein Beschreibungstext, der versehentlich vor einem Schlüssel
    landet, verschmilzt deshalb mit ihm - der Eintrag verschwindet lautlos,
    ohne Syntaxfehler und ohne dass sich die Anzahl der Einträge ändert.
    """
    from eta_webservices.const import PUFFER_SPEICHER, SELECTS, SENSORS, SWITCHES
    from eta_webservices.uri_discovery import (
        BETRIEBSART_ROLES,
        DISCOVERY_PATHS,
        PUMPEN,
        SWITCH_ROLES,
    )

    volumen = {f"{k}_volumen" for k in PUFFER_SPEICHER}
    assert set(SENSORS) == set(DISCOVERY_PATHS) | set(PUMPEN) | volumen
    assert set(SWITCHES) == set(SWITCH_ROLES)
    assert set(SELECTS) == set(BETRIEBSART_ROLES)
