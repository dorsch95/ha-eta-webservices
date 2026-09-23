"""Diagnosedaten zum Herunterladen aus der Geräteansicht.

Zeigt je Messwert die abgefragte URI und den zuletzt angekommenen Wert,
dazu unter "nicht_gefunden" alle Messwerte ohne Treffer im Menübaum und
unter "menuebaum" den vollständigen Menübaum der Anlage. Unter
"zustandstexte" stehen alle Texte, die die Zustands-Sensoren annehmen
können - so lässt sich etwa die Kessel-Kachel auf einen anderen
Kesseltyp abstimmen. Mit dieser einen
Datei lässt sich die Integration an eine abweichende Anlage anpassen -
ohne dass jemand eta_bericht.py starten muss. Die IP-Adresse wird
geschwärzt; im Menübaum steht sie nicht.
"""

from __future__ import annotations

import asyncio
from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant

from .api import ETAApiError
from .const import CONF_COMPONENTS, CONF_FUB_NAMES
from .coordinator import ETAConfigEntry
from .uri_discovery import DISCOVERY_PATHS, _as_list

TO_REDACT = {CONF_HOST}


def menue_als_text(parsed: dict[str, Any]) -> list[str]:
    """Der Menübaum als eingerückte Zeilen: Name, dahinter die URI.

    Eine Zeile je Objekt liest sich im Diagnose-Export deutlich besser als
    das verschachtelte XML, und die Einrückung zeigt den Pfad.
    """
    zeilen: list[str] = []

    def ablaufen(knoten: dict, tiefe: int) -> None:
        for kind in _as_list(knoten.get("object")):
            if isinstance(kind, dict):
                zeilen.append(
                    f"{'  ' * tiefe}{kind.get('@name', '?')}  {kind.get('@uri', '')}"
                )
                ablaufen(kind, tiefe + 1)

    wurzel = parsed.get("eta", {}).get("menu", {}) if isinstance(parsed, dict) else {}
    for fub in _as_list(wurzel.get("fub") if isinstance(wurzel, dict) else None):
        if isinstance(fub, dict):
            zeilen.append(f"{fub.get('@name', '?')}  {fub.get('@uri', '')}")
            ablaufen(fub, 1)
    return zeilen


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

    try:
        menuebaum = menue_als_text(await coordinator.client.async_get_menu())
    except ETAApiError as err:
        menuebaum = [f"Menübaum nicht lesbar: {err}"]

    texte = {
        key: info["uri"]
        for key, info in sorted(coordinator.sensor_defs.items())
        if info.get("is_string") and info.get("uri")
    }
    beschreibungen = await asyncio.gather(
        *(coordinator.client.async_get_varinfo(uri) for uri in texte.values())
    )
    zustandstexte = {
        key: beschreibung["valid_values"]
        for key, beschreibung in zip(texte, beschreibungen)
        if beschreibung and beschreibung.get("valid_values")
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
            "ueber_kennung_gefunden": sorted(coordinator.ueber_kennung),
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
        "zustandstexte": zustandstexte,
        "menuebaum": menuebaum,
    }
