"""Koordiniert das regelmäßige Auslesen der ETA-Anlage."""

from __future__ import annotations

import logging
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import ETAApiClient, ETAValue
from .const import (
    CONF_SCHEMA,
    DISCOVERY_ONLY_SENSORS,
    DOMAIN,
    OPTIONAL_SENSORS,
    PUFFER_FUEHLER_FALLBACK_URIS,
    SCHEMAS,
    STATIC_URIs,
    puffer_fuehler_info,
)
from .uri_discovery import async_discover_uris

_LOGGER = logging.getLogger(__name__)


def build_sensor_defs(discovered_uris, puffer_fuehler_indices):
    """Stellt zusammen, welche Sensoren diese Anlage hat und unter welcher URI.

    Für die Basissensoren hat eine im Menübaum gefundene URI immer Vorrang
    vor der fest hinterlegten - letztere gilt nur als Rückfallebene, denn die
    numerischen URIs unterscheiden sich von Anlage zu Anlage. Pufferfühler
    werden dynamisch erkannt (3 bis 8 Stück), und optionale Sensoren werden
    immer angelegt - auch ohne URI, damit Dashboard-Karten sie gefahrlos
    referenzieren können.
    """
    sensor_defs = {
        key: {**info, "uri": discovered_uris.get(key) or info["uri"]}
        for key, info in STATIC_URIs.items()
    }

    for key, info in DISCOVERY_ONLY_SENSORS.items():
        if key in discovered_uris:
            sensor_defs[key] = {**info, "uri": discovered_uris[key]}

    for key, info in OPTIONAL_SENSORS.items():
        sensor_defs[key] = {**info, "uri": discovered_uris.get(key)}

    indices = puffer_fuehler_indices or list(
        range(1, len(PUFFER_FUEHLER_FALLBACK_URIS) + 1)
    )
    last_index = indices[-1] if indices else None

    for index in indices:
        key = f"puffer_fuehler_{index}"
        if key in discovered_uris:
            uri = discovered_uris[key]
        elif index <= len(PUFFER_FUEHLER_FALLBACK_URIS):
            uri = PUFFER_FUEHLER_FALLBACK_URIS[index - 1]
        else:
            continue

        sensor_defs[key] = {
            **puffer_fuehler_info(index, index == last_index),
            "uri": uri,
        }

    return sensor_defs


class ETADataUpdateCoordinator(DataUpdateCoordinator[dict[str, ETAValue]]):
    """Liest alle bekannten Messwerte der Anlage in einem Rutsch aus."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        client: ETAApiClient,
        scan_interval: int,
        schema: str,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            config_entry=entry,
            update_interval=timedelta(seconds=scan_interval),
        )
        self.client = client
        self.schema = schema
        self.sensor_defs: dict[str, dict] = {}
        self.discovered_uris: dict[str, str] = {}

        self.device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name="ETA Heizung",
            manufacturer="ETA",
            model=schema,
            configuration_url=client.base_url,
        )

    @property
    def system_image_path(self) -> str:
        """Bildschlüssel des gewählten Anlagenschemas (ohne Dateiendung)."""
        return SCHEMAS.get(self.schema, "kessel_puffer")

    async def async_discover(self, fub_name_overrides: dict[str, str]) -> None:
        """Ermittelt einmalig die URIs aller Messwerte dieser Anlage."""
        self.discovered_uris, indices = await async_discover_uris(
            self.client, fub_name_overrides
        )
        self.sensor_defs = build_sensor_defs(self.discovered_uris, indices)

    async def _async_update_data(self) -> dict[str, ETAValue]:
        """Liest alle bekannten Messwerte und mischt sie in den Bestand.

        Werte einzeln fehlgeschlagener Abfragen bleiben erhalten, damit ein
        einzelner Timeout einen Sensor nicht kurzzeitig auf "Unbekannt"
        springen lässt.
        """
        uris = {
            key: info["uri"]
            for key, info in self.sensor_defs.items()
            if info.get("uri")
        }
        if not uris:
            raise UpdateFailed("Keine abfragbaren Messwerte bekannt")

        values = await self.client.async_get_values(uris)

        if not values:
            raise UpdateFailed(
                f"ETA Heizung unter {self.client.base_url} nicht erreichbar "
                f"(0/{len(uris)} Werte gelesen)"
            )

        merged = dict(self.data or {})
        merged.update(values)
        return merged
