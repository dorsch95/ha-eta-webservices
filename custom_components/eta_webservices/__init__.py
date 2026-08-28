import logging
import asyncio
from datetime import timedelta
import os
import base64
import aiohttp
import xmltodict

from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import DOMAIN, STATIC_URIs, SCHEMAS
from .images import IMAGES_DATA

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    host = entry.data["host"]
    port = entry.data["port"]
    selected_schema = entry.data.get("schema", "Kessel + Puffer")
    session = async_get_clientsession(hass)

    # --- BILDER AUS BASE64 TEXT SCHREIBEN ---
    try:
        target_dir = os.path.join(hass.config.path("www"), "community", "ha-eta-webservices")
        os.makedirs(target_dir, exist_ok=True)
        for bild_key, base64_string in IMAGES_DATA.items():
            target_file = os.path.join(target_dir, f"{bild_key}.png")
            def write_image():
                with open(target_file, "wb") as f:
                    f.write(base64.b64decode(base64_string))
            await hass.async_add_executor_job(write_image)
    except Exception as e:
        _LOGGER.error(f"Fehler bei der ETA Bildgenerierung: {e}")

    # --- DATEN-ABRUF-KOORDINATOR ---
    async def async_update_data():
        data = {}
        for key, info in STATIC_URIs.items():
            url = f"http://{host}:{port}/user/var{info['uri']}"
            try:
                async with session.get(url, timeout=4) as response:
                    if response.status == 200:
                        xml_text = await response.text()
                        parsed = xmltodict.parse(xml_text, process_namespaces=False)
                        root_key = next(iter(parsed))
                        
                        if "value" in parsed[root_key]:
                            val_node = parsed[root_key]["value"]
                            scale = float(val_node.get("@scaleFactor", 1))
                            
                            # KORREKTUR: Wenn es sich um eine "Anforderung" oder einen Status handelt, 
                            # bevorzugen wir immer den Textwert (@strValue) statt des internen ETA-Zahlencodes.
                            if "anforderung" in key or val_node.get("@unit") == "" or val_node.get("@unit") is None:
                                data[key] = {
                                    "value": val_node.get("@strValue", val_node.get("#text", "Aus")),
                                    "unit": "",
                                    "text": val_node.get("@strValue", "")
                                }
                            else:
                                # Normaler numerischer Wert (z.B. Temperaturen)
                                raw_val_str = val_node.get("@value") or val_node.get("#text")
                                if raw_val_str is not None and raw_val_str.strip() != "":
                                    try:
                                        data[key] = {
                                            "value": float(raw_val_str) / scale,
                                            "unit": val_node.get("@unit", ""),
                                            "text": val_node.get("@strValue", "")
                                        }
                                    except ValueError:
                                        data[key] = {
                                            "value": val_node.get("@strValue", raw_val_str),
                                            "unit": "",
                                            "text": val_node.get("@strValue", "")
                                        }
            except Exception:
                pass
        return data

    coordinator = DataUpdateCoordinator(
        hass, _LOGGER, name="ETA Service",
        update_method=async_update_data, update_interval=timedelta(seconds=30),
    )
    
    await coordinator.async_config_entry_first_refresh()

    dateiname = SCHEMAS.get(selected_schema, "kessel_puffer.png").replace(".png", "")
    coordinator.system_image_path = dateiname

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, ["sensor"])
    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, ["sensor"])
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok
