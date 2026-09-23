"""Friert die Entity-IDs ein - sie sind in jeder Spracheinstellung dieselben.

Jede Entität schlägt die ID vor, die eine deutschsprachige Installation
bekäme (entitaets_ids.py) - unabhängig von der Spracheinstellung. Die ID
hängt damit am deutschen Namen. Ändert den jemand, ändert sich die ID bei
jeder neuen Installation, und Karte, README und geteilte
Automatisierungen zeigen ins Leere. Dieser Test schlägt in dem Fall an.
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
    "fwm_zirkulationspumpe": "sensor.eta_heizung_fwm_zirkulationspumpe",
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
    "lager_fuellstand": "sensor.eta_heizung_lager_fullstand",
    "lager_bestellen_bis": "sensor.eta_heizung_lager_bestellen_bis",
    "lager_maximum": "sensor.eta_heizung_lager_fassungsvermogen",
    "lager_reicht_bis": "sensor.eta_heizung_lager_reicht_bis",
    "lager_reichweite": "sensor.eta_heizung_lager_reichweite",
    "lager_vorrat": "sensor.eta_heizung_lager_vorrat",
    "lager_warngrenze": "sensor.eta_heizung_lager_warngrenze",
    "lager_zustand": "sensor.eta_heizung_lager_austragung",
    "aktive_fehler": "sensor.eta_heizung_aktive_fehler",
    "pellet_energie_gesamt": "sensor.eta_heizung_pellet_energieverbrauch_gesamt",
    "pellet_gesamtverbrauch": "sensor.eta_heizung_pellet_gesamtverbrauch",
    "pellet_kosten_heute": "sensor.eta_heizung_pelletkosten_heute",
    "pellet_kosten_jahr": "sensor.eta_heizung_pelletkosten_dieses_jahr",
    "pellet_kosten_woche": "sensor.eta_heizung_pelletkosten_diese_woche",
    "pellet_verbrauch_heute": "sensor.eta_heizung_pelletverbrauch_heute",
    "pellet_verbrauch_jahr": "sensor.eta_heizung_pelletverbrauch_dieses_jahr",
    "pellet_verbrauch_woche": "sensor.eta_heizung_pelletverbrauch_diese_woche",
    "pellet_prognose_morgen": "sensor.eta_heizung_pelletprognose_morgen",
    "pellet_prognose_status": "sensor.eta_heizung_pelletprognose_status",
    "pellet_prognose_treffsicherheit": "sensor.eta_heizung_pelletprognose_treffsicherheit",
    "pellet_tagesbehaelter": "sensor.eta_heizung_pellet_inhalt_tagesbehalter",
    "puffer_fuehler_1": "sensor.eta_heizung_puffer_fuhler_1",
    "puffer_ladezustand": "sensor.eta_heizung_puffer_ladezustand",
    "pvm_ertrag_gestern": "sensor.eta_heizung_pv_heizmodul_ertrag_gestern",
    "pvm_ertrag_heute": "sensor.eta_heizung_pv_heizmodul_ertrag_heute",
    "pvm_gesamtenergie": "sensor.eta_heizung_pv_heizmodul_gesamtenergie",
    "pvm_heizstab": "sensor.eta_heizung_pv_heizmodul_heizstab",
    "pvm_temperatur_mitte": "sensor.eta_heizung_pv_heizmodul_temperatur_mitte",
    "pvm_temperatur_oben": "sensor.eta_heizung_pv_heizmodul_temperatur_oben",
    "pvm_temperatur_unten": "sensor.eta_heizung_pv_heizmodul_temperatur_unten",
    "pvm_zustand": "sensor.eta_heizung_pv_heizmodul_zustand",
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


async def test_jede_entitaet_schlaegt_ihre_deutsche_id_vor(hass, entry):
    """Die ID darf nicht an der Spracheinstellung hängen.

    Home Assistant leitet sie beim ersten Anlegen aus dem übersetzten Namen
    ab - bei englischer Einstellung wäre es sensor.eta_heizung_boiler_temperature,
    und Karte und README zeigten ins Leere. Deshalb schlägt jede Entität die
    ID einer deutschsprachigen Installation selbst vor.
    """
    from eta_webservices import binary_sensor, select, sensor, switch

    from .test_sensors import setup_integration

    await setup_integration(hass, entry)
    for plattform in (sensor, binary_sensor, switch, select):
        entitaeten: list = []
        await plattform.async_setup_entry(hass, entry, entitaeten.extend)
        assert entitaeten, plattform.__name__
        for entitaet in entitaeten:
            domain = plattform.__name__.rsplit(".", 1)[1]
            name = json.loads(
                (UEBERSETZUNGEN / "de.json").read_text(encoding="utf-8")
            )["entity"][domain][entitaet.translation_key]["name"]
            assert entitaet.entity_id == f"{domain}.{slugify(f'{GERAET} {name}')}"


async def test_vorschlag_passt_zu_den_eingefrorenen_ids(hass, entry):
    from eta_webservices import sensor

    from .test_sensors import setup_integration

    await setup_integration(hass, entry)
    entitaeten: list = []
    await sensor.async_setup_entry(hass, entry, entitaeten.extend)
    vorgeschlagen = {e.translation_key: e.entity_id for e in entitaeten}
    for key, entity_id in ERWARTETE_IDS.items():
        if key in vorgeschlagen:
            assert vorgeschlagen[key] == entity_id, key


def test_hacs_nennt_die_laender_der_anlagen():
    """Laut HACS-Regeln Pflicht für Repos, die nur einige Länder betreffen.

    Die Suche arbeitet mit den deutschen Menünamen der Anlage; praktisch
    alle Anlagen stehen in Deutschland, Österreich und der Schweiz.
    """
    from pathlib import Path

    hacs = json.loads(
        (Path(__file__).resolve().parents[1] / "hacs.json").read_text(encoding="utf-8")
    )
    assert hacs["country"] == ["DE", "AT", "CH"]
