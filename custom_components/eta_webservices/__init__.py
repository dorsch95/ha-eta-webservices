import logging
import asyncio
from datetime import timedelta
import os
import aiohttp
import xmltodict

from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.components.http import StaticPathConfig

from .const import DOMAIN, SENSOR_DEFINITIONS, SCHEMAS

_LOGGER = logging.getLogger(__name__)

def find_uris_in_menu(menu_dict, discovered_uris=None):
    if discovered_uris is None:
        discovered_uris = {}
    if isinstance(menu_dict, dict):
        if "@name" in menu_dict and "@uri" in menu_dict:
            name = menu_dict["@name"]
            uri = menu_dict["@uri"]
            for key, config in SENSOR_DEFINITIONS.items():
                if config["search_name"] == name and key not in discovered_uris:
                    if uri != "/user/menu" and not uri.endswith("/0"):
                        discovered_uris[key] = uri
                    elif uri.endswith("/0"):
                        discovered_uris[key] = uri
        for k, v in menu_dict.items():
            if isinstance(v, (dict, list)):
                find_uris_in_menu(v, discovered_uris)
    elif isinstance(menu_dict, list):
        for item in menu_dict:
            find_uris_in_menu(item, discovered_uris)
    return discovered_uris

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    host = entry.data["host"]
    port = entry.data["port"]
    selected_schema = entry.data.get("schema", "Kessel + Puffer")
    session = async_get_clientsession(hass)

    # --- KORREKTUR: Modernen, asynchronen Pfad-Registrierer nutzen ---
    www_dir = os.path.join(os.path.dirname(__file__), "www")
    await hass.http.async_register_static_paths([
        StaticPathConfig("/eta_bilder", www_dir, False)
    ])

    menu_url = f"http://{host}:{port}/user/menu"
    detected_uris = {}
    try:
        async with session.get(menu_url, timeout=10) as response:
            if response.status == 200:
                xml_text = await response.text()
                parsed_menu = xmltodict.parse(xml_text, process_namespaces=False)
                root_key = next(iter(parsed_menu))
                detected_uris = find_uris_in_menu(parsed_menu[root_key])
    except Exception as e:
        _LOGGER.error(f"Fehler beim ETA Menü-Scan: {e}")
        return False

    if not detected_uris:
        return False

    async def async_update_data():
        data = {}
        for key, uri in detected_uris.items():
            url = f"http://{host}:{port}/user/var{uri}"
            try:
                async with session.get(url, timeout=5) as response:
                    if response.status == 200:
                        xml_text = await response.text()
                        parsed = xmltodict.parse(xml_text, process_namespaces=False)
                        root_key = next(iter(parsed))
                        if "value" in parsed[root_key]:
                            val_node = parsed[root_key]["value"]
                            scale = float(val_node.get("@scaleFactor", 1))
                            raw_val_str = val_node.get("#text") or val_node.get("@value")
                            if raw_val_str is not None:
                                data[key] = {
                                    "value": float(raw_val_str) / scale,
                                    "unit": val_node.get("@unit", ""),
                                    "text": val_node.get("@strValue", "")
                                }
            except Exception as e:
                _LOGGER.warning(f"Fehler beim Abruf von {url}: {e}")
        return data

    coordinator = DataUpdateCoordinator(
        hass, _LOGGER, name="ETA Service",
        update_method=async_update_data, update_interval=timedelta(seconds=30),
    )
    await coordinator.async_config_entry_first_refresh()

    # Gibt den reinen Dateinamen ohne Endung aus
    coordinator.system_image_path = SCHEMAS.get(selected_schema, "kessel_puffer.png").replace(".png", "")

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "coordinator": coordinator,
        "detected_uris": detected_uris
    }

    await hass.config_entries.async_forward_entry_setups(entry, ["sensor"])
    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, ["sensor"])
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok
