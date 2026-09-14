"""ETA Heiztechnik Web Service Integration für Home Assistant."""

from __future__ import annotations

import base64
import logging
import os

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import ETAApiClient
from .const import (
    CONF_FUB_NAMES,
    CONF_SCAN_INTERVAL,
    CONF_SCHEMA,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    PLATFORMS,
)
from .coordinator import ETADataUpdateCoordinator
from .images import IMAGES_DATA

_LOGGER = logging.getLogger(__name__)

WWW_SUBDIR = ("community", "ha-eta-webservices")


def _write_schema_images(www_root: str) -> None:
    """Schreibt die Anlagengrafiken nach www/ - läuft komplett im Executor.

    Dateisystemzugriffe und das Dekodieren von rund 2 MB Base64 dürfen den
    Event Loop nicht blockieren, deshalb liegt hier alles in einer Funktion.
    """
    target_dir = os.path.join(www_root, *WWW_SUBDIR)
    os.makedirs(target_dir, exist_ok=True)

    for image_key, base64_string in IMAGES_DATA.items():
        target_file = os.path.join(target_dir, f"{image_key}.png")
        decoded = base64.b64decode(base64_string)
        if (
            os.path.exists(target_file)
            and os.path.getsize(target_file) == len(decoded)
        ):
            continue
        with open(target_file, "wb") as file:
            file.write(decoded)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Setzt die Integration über einen Config Entry auf."""
    config = {**entry.data, **entry.options}
    host = config[CONF_HOST]
    port = config[CONF_PORT]
    schema = config.get(CONF_SCHEMA, "Kessel + Puffer")
    fub_name_overrides = config.get(CONF_FUB_NAMES, {})
    scan_interval = config.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)

    try:
        await hass.async_add_executor_job(
            _write_schema_images, hass.config.path("www")
        )
    except OSError as err:
        _LOGGER.error("Anlagengrafiken konnten nicht geschrieben werden: %s", err)

    client = ETAApiClient(hass, async_get_clientsession(hass), host, port)
    coordinator = ETADataUpdateCoordinator(hass, entry, client, scan_interval, schema)

    await coordinator.async_discover(fub_name_overrides)
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    entry.async_on_unload(entry.add_update_listener(async_update_options))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_update_options(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Lädt die Integration neu, wenn die Optionen geändert wurden."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Wird aufgerufen, wenn die Integration entfernt wird."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
        if not hass.data[DOMAIN]:
            hass.data.pop(DOMAIN)
    return unload_ok
