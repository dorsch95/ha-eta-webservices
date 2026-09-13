import logging
from datetime import timedelta
import os
import base64
import xmltodict

from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    DOMAIN,
    STATIC_URIs,
    SCHEMAS,
    PUFFER_FUEHLER_FALLBACK_URIS,
    DISCOVERY_ONLY_SENSORS,
    puffer_fuehler_info,
)
from .images import IMAGES_DATA
from .uri_discovery import async_discover_uris

_LOGGER = logging.getLogger(__name__)


def _build_sensor_defs(discovered_uris, puffer_fuehler_indices):
    """Baut die endgültige Sensor-Definition für diesen Config Entry.

    Kombiniert die festen Basissensoren mit den dynamisch gefundenen
    Pufferfühlern (3 bis 8 Stück, Fühler 1 = oben, letzter = unten).
    """
    sensor_defs = dict(STATIC_URIs)

    for key, info in DISCOVERY_ONLY_SENSORS.items():
        if key in discovered_uris:
            entry_info = dict(info)
            entry_info["uri"] = discovered_uris[key]
            sensor_defs[key] = entry_info

    indices = puffer_fuehler_indices or list(range(1, len(PUFFER_FUEHLER_FALLBACK_URIS) + 1))
    last_index = indices[-1] if indices else None

    for index in indices:
        key = f"puffer_fuehler_{index}"
        if key in discovered_uris:
            uri = discovered_uris[key]
        elif index <= len(PUFFER_FUEHLER_FALLBACK_URIS):
            uri = PUFFER_FUEHLER_FALLBACK_URIS[index - 1]
        else:
            continue

        info = puffer_fuehler_info(index, index == last_index)
        info["uri"] = uri
        sensor_defs[key] = info

    return sensor_defs


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Setzt die Integration über einen Config Entry auf."""
    config = {**entry.data, **entry.options}
    host = config["host"]
    port = config["port"]
    selected_schema = config.get("schema", "Kessel + Puffer")
    fub_name_overrides = config.get("fub_names", {})
    session = async_get_clientsession(hass)

    try:
        target_dir = os.path.join(hass.config.path("www"), "community", "ha-eta-webservices")
        os.makedirs(target_dir, exist_ok=True)
        for bild_key, base64_string in IMAGES_DATA.items():
            target_file = os.path.join(target_dir, f"{bild_key}.png")
            decoded = base64.b64decode(base64_string)
            if os.path.exists(target_file) and os.path.getsize(target_file) == len(decoded):
                continue

            def write_image(data=decoded, path=target_file):
                with open(path, "wb") as f:
                    f.write(data)

            await hass.async_add_executor_job(write_image)
    except Exception as e:
        _LOGGER.error(f"Fehler bei der ETA Bildgenerierung: {e}")

    discovered_uris, puffer_fuehler_indices = await async_discover_uris(
        session, host, port, fub_name_overrides
    )
    sensor_defs = _build_sensor_defs(discovered_uris, puffer_fuehler_indices)

    async def async_update_data():
        previous_data = coordinator.data or {}
        data = {}
        success_count = 0

        for key, info in sensor_defs.items():
            uri = discovered_uris.get(key, info["uri"])
            url = f"http://{host}:{port}/user/var{uri}"
            try:
                async with session.get(url, timeout=4) as response:
                    if response.status != 200:
                        raise ValueError(f"HTTP {response.status}")

                    xml_text = await response.text()
                    parsed = xmltodict.parse(xml_text, process_namespaces=False)
                    root_key = next(iter(parsed))

                    if "value" not in parsed[root_key]:
                        raise ValueError("Antwort enthält kein <value>-Element")

                    val_node = parsed[root_key]["value"]

                    if info.get("is_string"):
                        data[key] = {
                            "value": val_node.get("@strValue", "Aus"),
                            "unit": "",
                            "is_string": True,
                        }
                    else:
                        scale = float(val_node.get("@scaleFactor", 1))
                        raw_val_str = val_node.get("@value") or val_node.get("#text")

                        if raw_val_str is not None and raw_val_str.strip() != "":
                            try:
                                data[key] = {
                                    "value": float(raw_val_str) / scale,
                                    "unit": val_node.get("@unit", ""),
                                    "is_string": False,
                                }
                            except ValueError:
                                data[key] = {
                                    "value": val_node.get("@strValue", raw_val_str),
                                    "unit": "",
                                    "is_string": True,
                                }
                        else:
                            data[key] = {
                                "value": val_node.get("@strValue", ""),
                                "unit": "",
                                "is_string": True,
                            }
                    success_count += 1
            except Exception as err:
                _LOGGER.debug("ETA: Abfrage von '%s' (%s) fehlgeschlagen: %s", key, url, err)
                if key in previous_data:
                    data[key] = previous_data[key]

        if success_count == 0 and sensor_defs:
            raise UpdateFailed(
                f"ETA Heizung unter {host}:{port} nicht erreichbar (0/{len(sensor_defs)} Werte gelesen)"
            )

        return data

    coordinator = DataUpdateCoordinator(
        hass, _LOGGER, name="ETA Service",
        update_method=async_update_data, update_interval=timedelta(seconds=30),
    )

    await coordinator.async_config_entry_first_refresh()

    dateiname = SCHEMAS.get(selected_schema, "kessel_puffer.png").replace(".png", "")
    coordinator.system_image_path = dateiname
    coordinator.sensor_defs = sensor_defs
    coordinator.device_info = DeviceInfo(
        identifiers={(DOMAIN, entry.entry_id)},
        name="ETA Heizung",
        manufacturer="ETA",
        model=selected_schema,
        configuration_url=f"http://{host}:{port}",
    )

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    entry.async_on_unload(entry.add_update_listener(async_update_options))
    await hass.config_entries.async_forward_entry_setups(entry, ["sensor"])
    return True


async def async_update_options(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Lädt die Integration neu, wenn die Optionen geändert wurden."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Wird aufgerufen, wenn die Integration gelöscht wird."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, ["sensor"])
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok
