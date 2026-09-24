"""Tests für die Aktion "Dashboard-Karte erzeugen"."""

from __future__ import annotations

import json
import re

import pytest
from homeassistant.exceptions import ServiceValidationError

from eta_webservices import binary_sensor, select, sensor, switch
from eta_webservices.aktionen import (
    _eintrag_waehlen,
    karte_anpassen,
    karte_fuer_eintrag,
)

from .test_sensors import setup_integration

ENTITAET = re.compile(
    r"\b(?:sensor|binary_sensor|switch|select)\.eta_heizung_[a-z0-9_]+"
)


async def eingerichtet(hass, entry, umbenannt=None):
    """Richtet die Anlage ein und trägt ihre Entitäten ins Register ein.

    So, wie Home Assistant es beim Hinzufügen täte - mit der vorgeschlagenen
    ID, außer der Nutzer hat eine umbenannt.
    """
    umbenannt = umbenannt or {}
    await setup_integration(hass, entry)
    for plattform in (sensor, binary_sensor, switch, select):
        entitaeten: list = []
        await plattform.async_setup_entry(hass, entry, entitaeten.extend)
        for e in entitaeten:
            hass.entity_registry.anlegen(
                umbenannt.get(e.entity_id, e.entity_id),
                e.unique_id,
                entry.entry_id,
                e.translation_key,
            )
    hass.config_entries.geladen = [entry]
    return entry


def genannte(karte) -> set[str]:
    return set(ENTITAET.findall(json.dumps(karte)))


async def test_karte_nennt_nur_vorhandene_entitaeten(hass, entry):
    """Genau die Entitäten dieser Anlage - Spook findet nichts Unbekanntes."""
    await eingerichtet(hass, entry)
    karte = karte_fuer_eintrag(hass, entry)

    assert genannte(karte)
    assert genannte(karte) <= set(hass.entity_registry.eintraege)
    assert "sensor.eta_heizung_komponente_solar" not in json.dumps(karte)


async def test_umbenannte_entitaet_wird_eingesetzt(hass, entry):
    await eingerichtet(
        hass,
        entry,
        umbenannt={"sensor.eta_heizung_kesseltemperatur": "sensor.mein_kessel"},
    )
    text = json.dumps(karte_fuer_eintrag(hass, entry))

    assert "sensor.mein_kessel" in text
    assert "sensor.eta_heizung_kesseltemperatur" not in text


async def test_ohne_schreibzugriff_fehlen_die_bedienelemente(hass, entry):
    entry.data["enable_switches"] = False
    await eingerichtet(hass, entry)
    text = json.dumps(karte_fuer_eintrag(hass, entry))

    assert "switch.eta_heizung_animationen" in text, "gehört zur Anzeige, nicht zur Anlage"
    assert "switch." not in text.replace("switch.eta_heizung_animationen", "")
    assert "select." not in text
    assert "sensor.eta_heizung_kesseltemperatur" in text


async def test_pufferfuehler_wie_an_der_anlage(hass, entry):
    await eingerichtet(hass, entry)
    fuehler = {
        n for n in genannte(karte_fuer_eintrag(hass, entry)) if "_puffer_fuhler_" in n
    }
    vorhanden = {
        key
        for key in entry.runtime_data.sensor_defs
        if key.startswith("puffer_fuehler_")
    }
    assert len(fuehler) == len(vorhanden)


def test_anpassen_laesst_elemente_mit_fehlender_entitaet_weg():
    karte = {
        "type": "picture-elements",
        "elements": [
            {"type": "state-label", "entity": "sensor.eta_heizung_da"},
            {"type": "state-label", "entity": "sensor.eta_heizung_weg"},
            {
                "type": "conditional",
                "conditions": [
                    {"entity": "switch.eta_heizung_kessel", "state_not": "unknown"}
                ],
                "elements": [
                    {"type": "state-icon", "entity": "switch.eta_heizung_kessel"}
                ],
            },
        ],
    }
    ergebnis = karte_anpassen(
        karte, {"sensor.eta_heizung_da": "sensor.eta_heizung_da"}
    )
    assert ergebnis["elements"] == [
        {"type": "state-label", "entity": "sensor.eta_heizung_da"}
    ]


async def test_bei_einer_anlage_muss_niemand_waehlen(hass, entry):
    await eingerichtet(hass, entry)
    assert _eintrag_waehlen(hass, None) is entry
    assert _eintrag_waehlen(hass, entry.entry_id) is entry


def test_ohne_geladene_anlage_eine_verstaendliche_meldung(hass):
    with pytest.raises(ServiceValidationError):
        _eintrag_waehlen(hass, None)
    with pytest.raises(ServiceValidationError):
        _eintrag_waehlen(hass, "gibtesnicht")


async def test_die_antwort_ist_eine_karte(hass, entry):
    """Die Antwort wird so, wie sie ist, als manuelle Karte eingefügt."""
    await eingerichtet(hass, entry)
    karte = karte_fuer_eintrag(hass, entry)

    assert karte["type"] == "vertical-stack"
    json.dumps(karte)


async def test_kessel_wechselt_das_bild_mit_dem_zustand(hass, entry):
    await eingerichtet(hass, entry)
    karte = karte_fuer_eintrag(hass, entry)
    kessel = [
        kachel["card"]
        for variante in karte["cards"]
        for kachel in variante["card"]["cards"]
        if kachel["card"]["image"].endswith("/kessel.png")
    ]
    assert len(kessel) == 3
    for kachel in kessel:
        assert kachel["entity"] == "sensor.eta_heizung_kessel_zustand"
        assert kachel["state_image"]["Heizen"].endswith("kessel_flamme.png")
        assert "kessel_flamme.webp" in json.dumps(kachel["elements"])


def test_ohne_kessel_zustand_bleibt_das_grundbild():
    """Fehlt die Zustands-Entität, darf die Karte sie nicht nennen.

    Sonst meldet Spook eine unbekannte Entität. Das Grundbild bleibt.
    """
    from eta_webservices.karte import responsive_karte

    karte = responsive_karte(["kessel"])
    ohne = {
        entitaet: entitaet
        for entitaet in genannte(karte)
        if entitaet != "sensor.eta_heizung_kessel_zustand"
    }
    angepasst = karte_anpassen(karte, ohne)

    assert "state_image" not in json.dumps(angepasst)
    assert "sensor.eta_heizung_kessel_zustand" not in json.dumps(angepasst)
    assert "/kessel.png" in json.dumps(angepasst)
