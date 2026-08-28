import logging
import asyncio
from datetime import timedelta
import aiohttp
import xmltodict

from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DOMAIN, TRACKED_URIs

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Setzt die Integration über einen Config Entry auf."""
    host = entry.data["host"]
    port = entry.data["port"]
    session = async_get_clientsession(hass)

    async def async_update_data():
        data = {}
        for key, info in TRACKED_URIs.items():
            url = f"http://{host}:{port}/user/var{info['uri']}"
            try:
                async with session.get(url, timeout=5) as response:
                    if response.status == 200:
                        xml_text = await response.text()
                        
                        # Namespaces deaktivieren löscht das störende "eta:" Präfix
                        parsed = xmltodict.parse(xml_text, process_namespaces=False)
                        
                        # Flexibler Zugriff auf das Root-Element (egal ob "eta" oder "eta:eta")
                        root_key = next(iter(parsed))
                        
                        # Prüfen, ob der Kessel ein gültiges <value> Element geliefert hat
                        if "value" in parsed[root_key]:
                            val_node = parsed[root_key]["value"]
                            
                            scale = float(val_node.get("@scaleFactor", 1))
                            raw_val = float(val_node.get("@value", 0))
                            
                            data[key] = {
                                "value": raw_val / scale,
                                "unit": val_node.get("@unit", ""),
                                "text": val_node.get("@strValue", "")
                            }
                        else:
                            _LOGGER.warning(f"Pfad {info['uri']} lieferte kein value-Element.")
            except Exception as e:
                _LOGGER.warning(f"Fehler beim Abruf von {url}: {e}")
        
        # Nur wenn absolut gar kein Sensor geladen werden konnte, Fehler werfen
        if not data:
            raise UpdateFailed("Keine gültigen Sensordaten von der ETA Heizung empfangen. Prüfe deine URIs.")
        return data

    coordinator = DataUpdateCoordinator(
        hass,
        _LOGGER,
        name="ETA Web Service",
        update_method=async_update_data,
        update_interval=timedelta(seconds=30),
    )

    await coordinator.async_config_entry_first_refresh()
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, ["sensor"])
    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Wird aufgerufen, wenn die Integration gelöscht wird."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, ["sensor"])
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok
