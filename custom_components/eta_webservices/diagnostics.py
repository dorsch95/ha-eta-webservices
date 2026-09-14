"""Diagnosedaten zum Herunterladen aus der Geräteansicht.

Das häufigste Problem dieser Integration ist "ein Wert fehlt". Die Ursache
liegt fast immer im Menübaum der Anlage: ein umbenannter Funktionsblock,
eine abweichende Firmware oder schlicht nicht vorhandene Hardware. Der
Diagnose-Export zeigt deshalb für jeden Messwert, ob seine URI im Menübaum
gefunden wurde, welche URI tatsächlich abgefragt wird und ob zuletzt ein
Wert ankam - damit lässt sich ein Fehlerbericht ohne Rückfragen einordnen.
"""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant

from .const import CONF_COMPONENTS, CONF_FUB_NAMES, DOMAIN
from .coordinator import ETADataUpdateCoordinator
from .uri_discovery import DISCOVERY_PATHS

REDACTED = "**redigiert**"


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Stellt den Zustand einer eingerichteten Anlage zusammen."""
    coordinator: ETADataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    daten = coordinator.data or {}

    messwerte = {}
    for key, info in sorted(coordinator.sensor_defs.items()):
        reading = daten.get(key)
        messwerte[key] = {
            "name": info.get("name"),
            "uri": info.get("uri"),
            "quelle": "menuebaum" if key in coordinator.discovered_uris else "standard",
            "rolle": DISCOVERY_PATHS.get(key, (None, None))[0],
            "letzter_wert": None if reading is None else reading.value,
            "einheit": info.get("default_unit"),
        }

    return {
        "konfiguration": {
            CONF_HOST: REDACTED,
            CONF_COMPONENTS: coordinator.components,
            CONF_FUB_NAMES: {**entry.data, **entry.options}.get(CONF_FUB_NAMES, {}),
            "abfrageintervall": (
                coordinator.update_interval.total_seconds()
                if coordinator.update_interval
                else None
            ),
        },
        "erkennung": {
            "ueber_menuebaum_gefunden": len(coordinator.discovered_uris),
            "erwartet": len(DISCOVERY_PATHS),
            "nicht_gefunden": sorted(
                set(DISCOVERY_PATHS) - set(coordinator.discovered_uris)
            ),
            "pufferfuehler": sorted(
                int(key.rsplit("_", 1)[1])
                for key in coordinator.discovered_uris
                if key.startswith("puffer_fuehler_")
            ),
        },
        "letzte_abfrage": {
            "erfolgreich": coordinator.last_update_success,
            "gelesen": len(daten),
            "abgefragt": sum(
                1 for info in coordinator.sensor_defs.values() if info.get("uri")
            ),
        },
        "messwerte": messwerte,
    }
