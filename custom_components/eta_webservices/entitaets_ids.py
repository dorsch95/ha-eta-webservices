"""Entitäts-IDs, die in jeder Spracheinstellung gleich lauten.

Home Assistant bildet die ID einer neuen Entität aus ihrem übersetzten
Namen. Bei englischer Spracheinstellung hieße die Kesseltemperatur
sensor.eta_heizung_boiler_temperature statt
sensor.eta_heizung_kesseltemperatur - und die Dashboard-Karte, das README
und jede geteilte Automatisierung zeigten ins Leere. Deshalb schlägt die
Integration immer die ID vor, die eine deutschsprachige Installation
bekäme. Der angezeigte Name bleibt übersetzt.

Bereits eingerichtete Entitäten behalten ihre ID; der Vorschlag gilt nur
beim ersten Anlegen.
"""

from __future__ import annotations

import json
from pathlib import Path

from homeassistant.util import slugify

GERAETENAME = "ETA Heizung"
"""Der Name des Geräts - Home Assistant stellt ihn jeder ID voran."""

DEUTSCH = Path(__file__).parent / "translations" / "de.json"

type Namen = dict[str, dict[str, str]]
"""Deutscher Name je Plattform und Übersetzungsschlüssel."""


def deutsche_namen() -> Namen:
    """Liest die deutschen Entitätsnamen. Dateizugriff - im Executor aufrufen."""
    daten = json.loads(DEUTSCH.read_text(encoding="utf-8"))
    return {
        plattform: {
            schluessel: eintrag["name"]
            for schluessel, eintrag in eintraege.items()
            if "name" in eintrag
        }
        for plattform, eintraege in daten["entity"].items()
    }


def feste_entity_id(
    namen: Namen, plattform: str, translation_key: str | None
) -> str | None:
    """Die ID, die eine deutschsprachige Installation für diese Entität bekäme."""
    name = namen.get(plattform, {}).get(translation_key or "")
    if name is None:
        return None
    return f"{plattform}.{slugify(f'{GERAETENAME} {name}')}"


def ids_vorschlagen(namen: Namen, plattform: str, entitaeten) -> None:
    """Setzt bei jeder Entität die sprachunabhängige ID als Vorschlag."""
    for entitaet in entitaeten:
        vorschlag = feste_entity_id(namen, plattform, entitaet.translation_key)
        if vorschlag:
            entitaet.entity_id = vorschlag
