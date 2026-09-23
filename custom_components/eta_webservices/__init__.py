"""ETA Web-Services - Integration für Home Assistant."""

from __future__ import annotations

import logging
import re
from pathlib import Path

from homeassistant.components.http import StaticPathConfig
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.typing import ConfigType

from .api import ETAApiClient
from .const import (
    CONF_FUB_NAMES,
    CONF_ENABLE_ERRORS,
    CONF_ENABLE_SWITCHES,
    CONF_PELLET_KWH_PER_KG,
    CONF_SCAN_INTERVAL,
    DEFAULT_ENABLE_ERRORS,
    DEFAULT_ENABLE_SWITCHES,
    DEFAULT_PELLET_KWH_PER_KG,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    PLATFORMS,
    SELECTS,
    SENSORS,
    SWITCHES,
    URL_GRAFIKEN,
    components_from_config,
)
from .coordinator import ETAConfigEntry, ETADataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

GRAFIKEN = Path(__file__).parent / "grafiken"


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Stellt die Kachelgrafiken unter URL_GRAFIKEN bereit.

    Bis Version 0.20 wurden sie bei jedem Start in den www-Ordner des
    Nutzers geschrieben. Jetzt liefert Home Assistant sie direkt aus dem
    Ordner der Integration aus; ohne Zwischenspeicher im Browser, damit
    geänderte Grafiken nach einem Update sofort ankommen.
    """
    await hass.http.async_register_static_paths(
        [StaticPathConfig(URL_GRAFIKEN, str(GRAFIKEN), cache_headers=False)]
    )
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ETAConfigEntry) -> bool:
    """Setzt die Integration über einen Config Entry auf."""
    config = {**entry.data, **entry.options}
    host = config[CONF_HOST]
    port = config[CONF_PORT]
    components = components_from_config(config)
    fub_name_overrides = config.get(CONF_FUB_NAMES, {})
    scan_interval = config.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
    pellet_kwh_per_kg = config.get(
        CONF_PELLET_KWH_PER_KG, DEFAULT_PELLET_KWH_PER_KG
    )

    client = ETAApiClient(hass, async_get_clientsession(hass), host, port)
    coordinator = ETADataUpdateCoordinator(
        hass,
        entry,
        client,
        scan_interval,
        components,
        pellet_kwh_per_kg,
        enable_switches=config.get(CONF_ENABLE_SWITCHES, DEFAULT_ENABLE_SWITCHES),
        enable_errors=config.get(CONF_ENABLE_ERRORS, DEFAULT_ENABLE_ERRORS),
    )

    await coordinator.async_discover(fub_name_overrides)
    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    _verwaiste_entitaeten_entfernen(hass, entry, coordinator)
    return True


_EIGENE_ENTITAETEN = {
    "aschebox_status": "kessel",
    "aschebox_faellig": "kessel",
    "pellet_energie_gesamt": "kessel",
    "lager_niedrig": "lager",
}
_STOERUNG = {"aktive_fehler", "stoerung"}


def entitaet_vorgesehen(
    key: str, components: list[str], enable_switches: bool, enable_errors: bool
) -> bool | None:
    """Sagt, ob eine Entität mit dieser Einrichtung noch entstehen kann.

    Entscheidet allein nach der Einrichtung - Komponenten und Freigaben -,
    nie danach, was die Anlage gerade meldet. Ein kurzer Aussetzer beim
    Start darf keine Entität samt ihren Anpassungen löschen. None heißt:
    unbekannter Schlüssel, nicht anfassen.
    """
    aktiv = set(components)
    if key in SENSORS:
        return SENSORS[key]["component"] in aktiv
    if key in SWITCHES:
        definition = SWITCHES[key]
        return (
            enable_switches
            and definition["component"] in aktiv
            and not definition.get("nur_fuer_auswahl")
        )
    if key in SELECTS:
        return enable_switches and SELECTS[key]["component"] in aktiv
    if key in _STOERUNG:
        return enable_errors
    if key in _EIGENE_ENTITAETEN:
        return _EIGENE_ENTITAETEN[key] in aktiv
    if re.fullmatch(r"puffer_fuehler_\d+", key):
        return "puffer" in aktiv
    if key.startswith("komponente_"):
        return key.removeprefix("komponente_") in aktiv
    return None


def _verwaiste_entitaeten_entfernen(
    hass: HomeAssistant, entry: ETAConfigEntry, coordinator: ETADataUpdateCoordinator
) -> None:
    """Entfernt Entitäten, die diese Einrichtung nicht mehr hervorbringt.

    Wird eine Komponente abgewählt oder der Schreibzugriff entzogen, blieben
    ihre Entitäten sonst dauerhaft als "Nicht verfügbar" stehen.
    """
    registry = er.async_get(hass)
    praefixe = (f"eta_static_{entry.entry_id}_", f"eta_switch_{entry.entry_id}_")
    for eintrag in er.async_entries_for_config_entry(registry, entry.entry_id):
        praefix = next((p for p in praefixe if eintrag.unique_id.startswith(p)), None)
        if praefix is None:
            continue
        key = eintrag.unique_id.removeprefix(praefix)
        vorgesehen = entitaet_vorgesehen(
            key,
            coordinator.components,
            coordinator.enable_switches,
            coordinator.enable_errors,
        )
        if vorgesehen is False:
            _LOGGER.info(
                "ETA: %s wird nicht mehr bereitgestellt, entfernt", eintrag.entity_id
            )
            registry.async_remove(eintrag.entity_id)


async def async_migrate_entry(hass: HomeAssistant, entry: ETAConfigEntry) -> bool:
    """Holt IP-Adresse und Port aus den Optionen in die Daten des Eintrags.

    Bis Version 0.20 ließen sich beide sowohl über Konfigurieren (landet in
    den Optionen) als auch über Neu konfigurieren (landet in den Daten)
    ändern. Beim Start gewinnen die Optionen - eine Änderung über Neu
    konfigurieren blieb dadurch wirkungslos. Übernommen wird der Wert aus
    den Optionen, weil das der ist, mit dem die Integration bisher lief.
    """
    if entry.version > 1:
        return False
    if entry.minor_version >= 2:
        return True

    daten = dict(entry.data)
    optionen = dict(entry.options)
    for schluessel in (CONF_HOST, CONF_PORT):
        if schluessel in optionen:
            daten[schluessel] = optionen.pop(schluessel)

    unique_id = entry.unique_id
    neue_id = f"{daten[CONF_HOST]}:{daten[CONF_PORT]}"
    vergeben = hass.config_entries.async_entry_for_domain_unique_id(DOMAIN, neue_id)
    if vergeben is None or vergeben.entry_id == entry.entry_id:
        unique_id = neue_id

    hass.config_entries.async_update_entry(
        entry, data=daten, options=optionen, unique_id=unique_id, minor_version=2
    )
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ETAConfigEntry) -> bool:
    """Entlädt die Integration und gibt den Variablensatz frei.

    Die Anlage hält Variablensätze im Arbeitsspeicher.
    """
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        await entry.runtime_data.async_varset_aufraeumen()
    return unload_ok
