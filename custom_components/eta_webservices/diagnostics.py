"""Diagnosedaten zum Herunterladen aus der Geräteansicht.

Zeigt je Messwert die abgefragte URI und den zuletzt angekommenen Wert,
dazu unter "nicht_gefunden" alle Messwerte ohne Treffer im Menübaum.
Die IP-Adresse wird geschwärzt.
"""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant

from .const import CONF_COMPONENTS, CONF_FUB_NAMES
from .coordinator import ETAConfigEntry
from .uri_discovery import DISCOVERY_PATHS

TO_REDACT = {CONF_HOST}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ETAConfigEntry
) -> dict[str, Any]:
    """Stellt den Zustand einer eingerichteten Anlage zusammen."""
    coordinator = entry.runtime_data
    daten = coordinator.data or {}

    messwerte = {}
    for key, info in sorted(coordinator.sensor_defs.items()):
        reading = daten.get(key)
        messwerte[key] = {
            "name": info.get("name"),
            "uri": info.get("uri"),
            "rolle": DISCOVERY_PATHS.get(key, (None, None))[0],
            "letzter_wert": None if reading is None else reading.display,
            "einheit": info.get("default_unit"),
        }

    return {
        "konfiguration": async_redact_data(
            {
                CONF_HOST: {**entry.data, **entry.options}.get(CONF_HOST),
                CONF_COMPONENTS: coordinator.components,
                CONF_FUB_NAMES: {**entry.data, **entry.options}.get(
                    CONF_FUB_NAMES, {}
                ),
                "abfrageintervall": (
                    coordinator.update_interval.total_seconds()
                    if coordinator.update_interval
                    else None
                ),
            },
            TO_REDACT,
        ),
        "erkennung": {
            "webservice_version": coordinator.api_version,
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
        "schreibzugriff": {
            "freigegeben": coordinator.enable_switches,
            "schalter": sorted(coordinator.switch_defs),
            "betriebsarten": sorted(coordinator.select_defs),
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
