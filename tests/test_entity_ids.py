"""Friert die Entity-IDs einer deutschsprachigen Installation ein.

Home Assistant leitet die Entity-ID aus dem Anzeigenamen ab, und der kommt
seit der Umstellung auf translation_key aus den Sprachdateien. Deutsch steht
in HAs Liste der Sprachen mit eigenen Entity-IDs, deshalb hängt die ID am
deutschen Namen. Ändert den jemand, ändert sich die Entity-ID - und jedes
Dashboard, jede Automatisierung und jede Statistik der bestehenden Nutzer
zeigt ins Leere. Dieser Test schlägt in dem Fall an.
"""

from __future__ import annotations

import json

import pytest
from homeassistant.util import slugify

from .conftest import UEBERSETZUNGEN

GERAET = "ETA Heizung"

ERWARTETE_IDS = {
    "aschebox_schwelle": "sensor.eta_heizung_aschebox_leeren_nach",
    "aschebox_status": "sensor.eta_heizung_aschebox_status",
    "aschebox_verbrauch": "sensor.eta_heizung_aschebox_verbrauch_seit_leerung",
    "aussentemperatur": "sensor.eta_heizung_aussentemperatur",
    "entaschung_verbrauch": "sensor.eta_heizung_verbrauch_seit_entaschung",
    "fwm_warmwasser": "sensor.eta_heizung_fwm_warmwassertemperatur",
    "fwm_zirkulation": "sensor.eta_heizung_fwm_zirkulation",
    "heizkreis2_anforderung": "sensor.eta_heizung_heizkreis_2_anforderung",
    "heizkreis2_vorlauf": "sensor.eta_heizung_heizkreis_2_vorlauftemperatur",
    "heizkreis_anforderung": "sensor.eta_heizung_heizkreis_anforderung",
    "heizkreis3_anforderung": "sensor.eta_heizung_heizkreis_3_anforderung",
    "heizkreis3_vorlauf": "sensor.eta_heizung_heizkreis_3_vorlauftemperatur",
    "heizkreis4_anforderung": "sensor.eta_heizung_heizkreis_4_anforderung",
    "heizkreis4_vorlauf": "sensor.eta_heizung_heizkreis_4_vorlauftemperatur",
    "heizkreis_vorlauf": "sensor.eta_heizung_heizkreis_vorlauftemperatur",
    "kessel_druck": "sensor.eta_heizung_kesseldruck",
    "kessel_soll": "sensor.eta_heizung_kessel_solltemperatur",
    "kessel_temperatur": "sensor.eta_heizung_kesseltemperatur",
    "kessel_zustand": "sensor.eta_heizung_kessel_zustand",
    "lager_maximum": "sensor.eta_heizung_lager_fassungsvermogen",
    "lager_vorrat": "sensor.eta_heizung_lager_vorrat",
    "lager_warngrenze": "sensor.eta_heizung_lager_warngrenze",
    "lager_zustand": "sensor.eta_heizung_lager_austragung",
    "aktive_fehler": "sensor.eta_heizung_aktive_fehler",
    "pellet_energie_gesamt": "sensor.eta_heizung_pellet_energieverbrauch_gesamt",
    "pellet_gesamtverbrauch": "sensor.eta_heizung_pellet_gesamtverbrauch",
    "pellet_tagesbehaelter": "sensor.eta_heizung_pellet_inhalt_tagesbehalter",
    "puffer_fuehler_1": "sensor.eta_heizung_puffer_fuhler_1",
    "puffer_ladezustand": "sensor.eta_heizung_puffer_ladezustand",
    "restsauerstoff": "sensor.eta_heizung_restsauerstoff",
    "ruecklauf_temperatur": "sensor.eta_heizung_rucklauftemperatur",
    "solar_ertrag_gestern": "sensor.eta_heizung_solar_ertrag_gestern",
    "solar_ertrag_heute": "sensor.eta_heizung_solar_ertrag_heute",
    "solar_kollektor": "sensor.eta_heizung_solar_kollektortemperatur",
    "solar_leistung": "sensor.eta_heizung_solar_leistung",
    "solar_waermemenge": "sensor.eta_heizung_solar_warmemenge",
}


def deutsche_namen() -> dict[str, str]:
    daten = json.loads((UEBERSETZUNGEN / "de.json").read_text(encoding="utf-8"))
    return {key: eintrag["name"] for key, eintrag in daten["entity"]["sensor"].items()}


@pytest.mark.parametrize("key, entity_id", sorted(ERWARTETE_IDS.items()))
def test_entity_id_bleibt_unveraendert(key, entity_id):
    name = deutsche_namen()[key]
    assert f"sensor.{slugify(f'{GERAET} {name}')}" == entity_id


def test_neue_entitaeten_sind_hier_eingetragen():
    from eta_webservices.const import (
        SENSORS,
    )

    bekannt = {
        info["translation_key"]
        for tabelle in (SENSORS,)
        for info in tabelle.values()
    }
    neu = sorted(bekannt - set(ERWARTETE_IDS))
    assert not neu, (
        f"Neue Entitäten ohne festgeschriebene Entity-ID: {neu}. "
        "Ergänze sie in ERWARTETE_IDS, damit spätere Umbenennungen auffallen."
    )
