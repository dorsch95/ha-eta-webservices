"""Koordiniert das regelmäßige Auslesen der ETA-Anlage."""

from __future__ import annotations

import logging
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import ETAApiClient, ETAApiError, ETAError, ETAValue
from .const import (
    COMPONENTS,
    DISCOVERY_ONLY_SENSORS,
    SWITCHES,
    DOMAIN,
    OPTIONAL_SENSORS,
    PUFFER_FUEHLER_FALLBACK_URIS,
    STATIC_URIs,
    normalize_components,
    puffer_fuehler_info,
)
from .repairs import async_check_components
from .uri_discovery import async_discover_uris

_LOGGER = logging.getLogger(__name__)

AUS_BEGRIFFE = {"aus", "off", "0", "nein", "no", "ausgeschaltet"}
"""Zustandsnamen, die eine ausgeschaltete Funktion bezeichnen.

Welcher der beiden Zustände "aus" ist, lässt sich nicht am Rohwert
ablesen - er ist bei ETA je nach Variable mal der kleinere, mal der
größere. Deshalb wird der Klartext ausgewertet.
"""

type ETAConfigEntry = ConfigEntry["ETADataUpdateCoordinator"]
"""Config Entry, der seinen Koordinator in runtime_data trägt."""


def build_sensor_defs(discovered_uris, puffer_fuehler_indices, components):
    """Stellt zusammen, welche Sensoren diese Anlage hat und unter welcher URI.

    Für die Basissensoren hat eine im Menübaum gefundene URI immer Vorrang
    vor der fest hinterlegten - letztere gilt nur als Rückfallebene, denn die
    numerischen URIs unterscheiden sich von Anlage zu Anlage. Pufferfühler
    werden dynamisch erkannt (3 bis 8 Stück), und optionale Sensoren werden
    immer angelegt - auch ohne URI, damit Dashboard-Karten sie gefahrlos
    referenzieren können. Messwerte von Komponenten, die der Nutzer nicht
    ausgewählt hat, entstehen erst gar nicht - sonst stünden auf jeder
    Anlage Entitäten herum, die dauerhaft nichts liefern.
    """
    aktiv = set(normalize_components(components))
    sensor_defs = {
        key: {**info, "uri": discovered_uris.get(key) or info["uri"]}
        for key, info in STATIC_URIs.items()
        if info["component"] in aktiv
    }

    for key, info in DISCOVERY_ONLY_SENSORS.items():
        if info["component"] in aktiv and key in discovered_uris:
            sensor_defs[key] = {**info, "uri": discovered_uris[key]}

    for key, info in OPTIONAL_SENSORS.items():
        if info["component"] in aktiv:
            sensor_defs[key] = {**info, "uri": discovered_uris.get(key)}

    if "puffer" not in aktiv:
        return sensor_defs

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
        entry: ETAConfigEntry,
        client: ETAApiClient,
        scan_interval: int,
        components: list[str],
        pellet_kwh_per_kg: float,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            config_entry=entry,
            update_interval=timedelta(seconds=scan_interval),
        )
        self.client = client
        self.components = normalize_components(components)
        self.pellet_kwh_per_kg = pellet_kwh_per_kg
        self.sensor_defs: dict[str, dict] = {}
        self.discovered_uris: dict[str, str] = {}
        self.components_without_data: list[str] = []
        self.api_version: str | None = None
        self.errors: list[ETAError] = []
        self.varinfo: dict[str, dict] = {}
        self.switch_defs: dict[str, dict] = {}
        self._varset_name = f"ha{entry.entry_id}"[:32]
        self._varset_bereit = False

        self._device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name="ETA Heizung",
            manufacturer="ETA",
            model=" + ".join(self.components),
            configuration_url=client.base_url,
        )

    @property
    def device_info(self) -> DeviceInfo:
        """Gerätedaten samt gemeldeter Webservice-Version."""
        info = dict(self._device_info)
        if self.api_version:
            info["sw_version"] = f"Webservices {self.api_version}"
        return DeviceInfo(**info)

    @property
    def component_images(self) -> list[str]:
        """Bildschlüssel der aktiven Komponenten, in Anzeigereihenfolge."""
        return [COMPONENTS[key]["image"] for key in self.components]

    @property
    def abfragbare_uris(self) -> dict[str, str]:
        """Alle Messwerte, zu denen eine URI bekannt ist."""
        return {
            key: info["uri"]
            for key, info in self.sensor_defs.items()
            if info.get("uri")
        }

    async def _varset_anlegen(self) -> None:
        """Legt den Variablensatz für die Sammelabfrage an.

        Die Anlage hält Variablensätze nur im Arbeitsspeicher. Nach einem
        Neustart sind sie weg, deshalb wird das hier bei Bedarf wiederholt.
        """
        uris = list(self.abfragbare_uris.values())
        if not uris:
            return
        try:
            await self.client.async_delete_varset(self._varset_name)
            await self.client.async_create_varset(self._varset_name, uris)
            self._varset_bereit = True
            _LOGGER.debug(
                "ETA: Variablensatz %s mit %d Messwerten angelegt",
                self._varset_name,
                len(uris),
            )
        except ETAApiError as err:
            self._varset_bereit = False
            _LOGGER.info(
                "ETA: Sammelabfrage nicht möglich, lese einzeln weiter: %s", err
            )

    async def async_varset_aufraeumen(self) -> None:
        """Gibt den Variablensatz auf der Anlage wieder frei."""
        if self._varset_bereit:
            await self.client.async_delete_varset(self._varset_name)
            self._varset_bereit = False

    async def _schalter_pruefen(self) -> None:
        """Prüft die gefundenen Schalt-Kandidaten an der Anlage nach.

        Erkannte Schalter wandern zusätzlich in die Sensordefinitionen -
        aber mit dem Vermerk, dass sie zur switch-Plattform gehören. So
        wird ihr Zustand im selben Abfragezyklus mitgelesen, ohne dass
        daneben noch ein Sensor mit demselben Wert entsteht.

        Ein Kandidat wird nur dann zum Schalter, wenn die Anlage ihn als
        beschreibbar meldet und genau zwei Zustände kennt. Welcher davon
        "aus" bedeutet, sagt ebenfalls die Anlage - der Rohwert wird
        nirgends geraten, weil ein falscher Wert hier in die
        Heizungssteuerung geschrieben würde.
        """
        aktiv = set(self.components)
        for key, definition in SWITCHES.items():
            if definition["component"] not in aktiv:
                continue
            uri = self.discovered_uris.get(key)
            if not uri:
                continue

            info = await self.client.async_get_varinfo(uri)
            if not info or not info.get("writable"):
                _LOGGER.debug("ETA: %s ist nicht beschreibbar, kein Schalter", key)
                continue

            roh = info.get("raw_values") or {}
            if len(roh) != 2:
                _LOGGER.debug(
                    "ETA: %s hat %d Zustände statt zwei, kein Schalter",
                    key,
                    len(roh),
                )
                continue

            aus_text = next(
                (t for t in roh if t.strip().casefold() in AUS_BEGRIFFE), None
            )
            if aus_text is None:
                _LOGGER.debug(
                    "ETA: bei %s ist unklar, welcher Zustand 'aus' bedeutet (%s)",
                    key,
                    list(roh),
                )
                continue
            ein_text = next(t for t in roh if t != aus_text)

            self.switch_defs[key] = {
                **definition,
                "uri": uri,
                "ein_text": ein_text,
                "ein_roh": roh[ein_text],
                "aus_roh": roh[aus_text],
            }
            self.sensor_defs[key] = {
                "component": definition["component"],
                "translation_key": definition["translation_key"],
                "icon": definition["icon"],
                "is_string": True,
                "uri": uri,
                "platform": "switch",
            }
            _LOGGER.info(
                "ETA: Schalter %s erkannt (%s -> %s / %s -> %s)",
                key,
                ein_text,
                roh[ein_text],
                aus_text,
                roh[aus_text],
            )

    async def _varinfo_laden(self) -> None:
        """Holt zu den Textwerten ihre gültigen Zustände.

        Erst ab Webservice-Version 1.2 verfügbar; ältere Anlagen liefern
        nichts, dann bleibt die Zusatzinfo einfach leer.
        """
        for key, info in self.sensor_defs.items():
            if not info.get("is_string") or not info.get("uri"):
                continue
            beschreibung = await self.client.async_get_varinfo(info["uri"])
            if beschreibung:
                self.varinfo[key] = beschreibung

    async def async_discover(self, fub_name_overrides: dict[str, str]) -> None:
        """Ermittelt einmalig die URIs aller Messwerte dieser Anlage."""
        self.discovered_uris, indices = await async_discover_uris(
            self.client, fub_name_overrides
        )
        self.sensor_defs = build_sensor_defs(
            self.discovered_uris, indices, self.components
        )
        self.components_without_data = async_check_components(
            self.hass,
            self.config_entry.entry_id,
            self.components,
            set(self.discovered_uris),
            menu_readable=bool(self.discovered_uris),
        )
        self.api_version = await self.client.async_get_api_version()
        await self._varinfo_laden()
        await self._schalter_pruefen()
        await self._varset_anlegen()

    async def _async_update_data(self) -> dict[str, ETAValue]:
        """Liest alle bekannten Messwerte und mischt sie in den Bestand.

        Werte einzeln fehlgeschlagener Abfragen bleiben erhalten, damit ein
        einzelner Timeout einen Sensor nicht kurzzeitig auf "Unbekannt"
        springen lässt.
        """
        uris = self.abfragbare_uris
        if not uris:
            raise UpdateFailed("Keine abfragbaren Messwerte bekannt")

        values = await self._werte_lesen(uris)

        if not values:
            raise UpdateFailed(
                f"ETA Heizung unter {self.client.base_url} nicht erreichbar "
                f"(0/{len(uris)} Werte gelesen)"
            )

        await self._fehler_lesen()

        merged = dict(self.data or {})
        merged.update(values)
        return merged

    async def _werte_lesen(self, uris: dict[str, str]) -> dict[str, ETAValue]:
        """Liest alle Messwerte, wenn möglich mit einer einzigen Anfrage.

        Über einen Variablensatz genügt ein Aufruf statt einem je
        Messwert. Ist der Satz verschwunden - etwa weil die Anlage neu
        gestartet wurde - wird er neu angelegt und für diesen Durchgang
        einzeln gelesen.
        """
        if self._varset_bereit:
            try:
                nach_uri = await self.client.async_get_varset(self._varset_name)
            except ETAApiError as err:
                _LOGGER.info("ETA: Variablensatz neu anlegen (%s)", err)
                self._varset_bereit = False
                await self._varset_anlegen()
            else:
                werte = {
                    key: nach_uri[uri] for key, uri in uris.items() if uri in nach_uri
                }
                if werte:
                    return werte
                _LOGGER.info("ETA: Variablensatz lieferte nichts, lese einzeln")
                self._varset_bereit = False

        return await self.client.async_get_values(uris)

    async def _fehler_lesen(self) -> None:
        """Holt die aktiven Fehler der Anlage.

        Ein Fehlschlag hier darf den Abfragezyklus nicht kippen - die
        Messwerte sind wichtiger als die Fehlerliste.
        """
        try:
            self.errors = await self.client.async_get_errors()
        except ETAApiError as err:
            _LOGGER.debug("ETA: Fehlerliste nicht lesbar: %s", err)
