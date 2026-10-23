"""Übernimmt Einrichtungen aus der Zeit, als die Integration eta_webservices hieß.

Bis 0.25 hieß sie intern eta_webservices, wie seit 2022 schon eine andere
ETA-Integration. Seit 0.26 heißt sie eta_heating_ws. Home Assistant kann
einen Eintrag nicht von einem Namen auf den anderen umhängen, und eine
Integration ohne Eintrag lädt es gar nicht erst. Deshalb fügt man sie nach
dem Update einmal neu hinzu: Der Dialog findet die alte Einrichtung
(alte_einrichtungen) und legt einen neuen Eintrag mit denselben Daten und
Optionen an, vermerkt unter UEBERNOMMEN_VON. Beim ersten Start dieses
Eintrags zieht async_uebernehmen den Rest um - Entitäten samt ihrer IDs,
das Gerät mit Raum und Namen, den Aschebox-Plan - und entfernt die alte
Einrichtung. Weil die Entity-IDs bleiben, laufen Verlauf, Statistik,
Energie-Dashboard, Karten und Automatisierungen einfach weiter.
"""

from __future__ import annotations

import inspect
import json
import logging
import shutil
from pathlib import Path
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import device_registry as dr, entity_registry as er

from .aschebox import speicher
from .const import ALTE_DOMAIN, CONF_COMPONENTS, DOMAIN

_LOGGER = logging.getLogger(__name__)

UEBERNOMMEN_VON = "uebernommen_von"
"""Steht in den Daten eines neuen Eintrags, bis der alte umgezogen ist."""

UNSER_REPO = "https://github.com/dorsch95/ha-eta-webservices"
"""So steht es im Manifest dieser Integration, auch in dem von 0.25."""


def ist_alte_einrichtung(eintrag: ConfigEntry) -> bool:
    """Ob ein Eintrag unter dem alten Namen von dieser Integration stammt.

    Die andere ETA-Integration unter demselben Namen führt ihre Einträge
    in Version 9 und mit ganz anderen Schlüsseln. Unsere haben Version 1
    und die gewählten Komponenten.
    """
    return (
        eintrag.domain == ALTE_DOMAIN
        and eintrag.version == 1
        and CONF_COMPONENTS in {**eintrag.data, **eintrag.options}
    )


@callback
def alte_einrichtungen(hass: HomeAssistant) -> list[ConfigEntry]:
    """Alte Einrichtungen, für die es noch keinen neuen Eintrag gibt.

    Abgeschaltete bleiben außen vor; wer eine übernehmen will, schaltet
    sie vorher wieder ein.
    """
    vergeben = {e.unique_id for e in hass.config_entries.async_entries(DOMAIN)}
    return [
        e
        for e in hass.config_entries.async_entries(ALTE_DOMAIN, include_disabled=False)
        if ist_alte_einrichtung(e) and e.unique_id not in vergeben
    ]


def daten_und_optionen(alt: ConfigEntry) -> tuple[dict[str, Any], dict[str, Any]]:
    """Daten und Optionen für den neuen Eintrag.

    IP-Adresse und Port gehören in die Daten. Bei Einträgen von vor 0.21
    standen sie mitunter noch in den Optionen, siehe async_migrate_entry.
    """
    daten = dict(alt.data)
    optionen = dict(alt.options)
    for schluessel in (CONF_HOST, CONF_PORT):
        if schluessel in optionen:
            daten[schluessel] = optionen.pop(schluessel)
    return daten, optionen


async def async_uebernehmen(hass: HomeAssistant, neu: ConfigEntry) -> None:
    """Zieht die alte Einrichtung in den neuen Eintrag um und entfernt sie.

    Die alte wird zuerst angehalten: Entitäten lassen sich nur umhängen,
    solange keine Integration sie gerade bedient. Gibt es den alten Eintrag
    nicht mehr, bleibt nur der Vermerk zu löschen.
    """
    alt_id = neu.data[UEBERNOMMEN_VON]
    alt = hass.config_entries.async_get_entry(alt_id)
    if alt is not None and ist_alte_einrichtung(alt):
        if not alt.state.recoverable or not await hass.config_entries.async_unload(
            alt_id
        ):
            raise ConfigEntryNotReady(
                f"Die alte Einrichtung {alt.title} ließ sich nicht anhalten"
            )
        _register_umziehen(hass, alt_id, neu.entry_id)
        await _aschebox_umziehen(hass, alt_id, neu.entry_id)
        await hass.config_entries.async_remove(alt_id)
        _LOGGER.info("Einrichtung %s aus %s übernommen", alt.title, ALTE_DOMAIN)
        await _alten_ordner_entfernen(hass)

    hass.config_entries.async_update_entry(
        neu, data={k: v for k, v in neu.data.items() if k != UEBERNOMMEN_VON}
    )


@callback
def _register_umziehen(hass: HomeAssistant, alt_id: str, neu_id: str) -> None:
    """Hängt Gerät und Entitäten an den neuen Eintrag.

    Die Kennungen enthalten die ID des Eintrags; sie bekommen die neue.
    Zieht das Gerät um, solange noch Entitäten des alten Eintrags daran
    hängen, räumt Home Assistant diese weg. Neuere Versionen ziehen ein
    Gerät in einem Schritt um (new_config_entry_id), das geht also erst
    nach den Entitäten. Ältere kennen das nicht: Dort bekommt das Gerät
    vorher den neuen Eintrag dazu und verliert den alten danach. Sie lassen
    eine Entität auch nur umziehen, solange sie keinen Zustand hat; nach dem
    Anhalten steht dort „nicht verfügbar“. Der Zustand verschwindet deshalb
    kurz, bis der neue Eintrag ihn schreibt.
    """
    geraete = dr.async_get(hass)
    entitaeten = er.async_get(hass)
    in_einem_schritt = "new_config_entry_id" in inspect.signature(
        geraete.async_update_device
    ).parameters

    def neue_kennung(kennung: str) -> str:
        return kennung.replace(alt_id, neu_id)

    def neue_kennungen(geraet: dr.DeviceEntry) -> set[tuple[str, str]]:
        return {
            (DOMAIN, neue_kennung(kennung)) if domain == ALTE_DOMAIN else (domain, kennung)
            for domain, kennung in geraet.identifiers
        }

    alte_geraete = dr.async_entries_for_config_entry(geraete, alt_id)
    if not in_einem_schritt:
        for geraet in alte_geraete:
            geraete.async_update_device(geraet.id, add_config_entry_id=neu_id)
    for eintrag in er.async_entries_for_config_entry(entitaeten, alt_id):
        hass.states.async_remove(eintrag.entity_id)
        entitaeten.async_update_entity_platform(
            eintrag.entity_id,
            DOMAIN,
            new_config_entry_id=neu_id,
            new_unique_id=neue_kennung(eintrag.unique_id),
        )
    for geraet in alte_geraete:
        umzug = (
            {"new_config_entry_id": neu_id}
            if in_einem_schritt
            else {"remove_config_entry_id": alt_id}
        )
        geraete.async_update_device(
            geraet.id, new_identifiers=neue_kennungen(geraet), **umzug
        )


async def _aschebox_umziehen(hass: HomeAssistant, alt_id: str, neu_id: str) -> None:
    """Gelernte Dauer und laufenden Plan mitnehmen."""
    alter_speicher = speicher(hass, alt_id, ALTE_DOMAIN)
    if (daten := await alter_speicher.async_load()) is not None:
        await speicher(hass, neu_id).async_save(daten)
    await alter_speicher.async_remove()


async def _alten_ordner_entfernen(hass: HomeAssistant) -> None:
    """Löscht custom_components/eta_webservices, wenn er von hier stammt.

    HACS legt beim Update den neuen Ordner an und lässt den alten liegen.
    Bliebe er, stünde „ETA Web-Services“ doppelt in der Liste der
    Integrationen. Gelöscht wird nur, wenn keine alte Einrichtung von hier
    mehr übrig ist und das Manifest auf dieses Repo zeigt - den Ordner der
    anderen ETA-Integration rührt das nie an.
    """
    if any(
        ist_alte_einrichtung(e) for e in hass.config_entries.async_entries(ALTE_DOMAIN)
    ):
        return
    ordner = Path(hass.config.path("custom_components", ALTE_DOMAIN))

    def entfernen() -> bool:
        try:
            manifest = json.loads((ordner / "manifest.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return False
        if manifest.get("documentation") != UNSER_REPO:
            return False
        try:
            shutil.rmtree(ordner)
        except OSError as err:
            _LOGGER.warning("Alten Ordner %s nicht entfernt: %s", ordner, err)
            return False
        return True

    if await hass.async_add_executor_job(entfernen):
        _LOGGER.info("Alten Ordner %s entfernt", ordner)
