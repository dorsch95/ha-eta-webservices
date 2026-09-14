"""Koordiniert das regelmäßige Auslesen der ETA-Anlage."""

from __future__ import annotations

import logging
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import ETAApiClient, ETAApiError, ETAError, ETAValue
from .const import (
    BETRIEBSART_TASTEN,
    COMPONENTS,
    SELECTS,
    SWITCHES,
    DOMAIN,
    PUFFER_FUEHLER_MINDEST,
    SENSORS,
    normalize_components,
    puffer_fuehler_info,
)
from .repairs import async_check_components
from .uri_discovery import async_discover_uris

_LOGGER = logging.getLogger(__name__)

VERALTET_AB = 2
"""So viele Abfragen darf ein Wert am Stück ausbleiben.

Danach gilt der Sensor als nicht erreichbar, statt weiter den letzten
bekannten Wert zu zeigen. Ein einzelner Timeout soll nichts kippen -
ein Wert, der dauerhaft ausbleibt, aber auch nicht wochenlang eine alte
Zahl vortäuschen.
"""

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

    Jede URI stammt aus dem Menübaum dieser Anlage. Fest hinterlegte
    Adressen gibt es nicht: Die numerischen URIs unterscheiden sich von
    Anlage zu Anlage, eine Adresse von einer fremden Anlage wäre also
    geraten - im günstigen Fall läuft die Abfrage ins Leere, im
    ungünstigen zeigt der Sensor still den falschen Wert.

    Was der Menübaum nicht hergibt, bekommt trotzdem eine Entität, nur
    eben ohne URI: sie zeigt dann dauerhaft "-". Welche Werte eine
    Anlage hat, lässt sich nicht sauber vorhersagen - Restsauerstoff hat
    jeder Kessel, einen Kesseldruck nicht jeder -, und eine Entität, die
    mal da ist und mal nicht, bricht Dashboards und Automatisierungen.

    Messwerte von Komponenten, die der Nutzer nicht ausgewählt hat,
    entstehen weiterhin gar nicht.
    """
    aktiv = set(normalize_components(components))
    sensor_defs = {
        key: {**info, "uri": discovered_uris.get(key)}
        for key, info in SENSORS.items()
        if info["component"] in aktiv
    }

    if "puffer" not in aktiv:
        return sensor_defs

    indices = puffer_fuehler_indices or list(range(1, PUFFER_FUEHLER_MINDEST + 1))
    last_index = indices[-1]
    for index in indices:
        key = f"puffer_fuehler_{index}"
        sensor_defs[key] = {
            **puffer_fuehler_info(index, index == last_index),
            "uri": discovered_uris.get(key),
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
        enable_switches: bool = False,
        enable_errors: bool = True,
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
        self.enable_switches = enable_switches
        self.enable_errors = enable_errors
        self.sensor_defs: dict[str, dict] = {}
        self.discovered_uris: dict[str, str] = {}
        self.components_without_data: list[str] = []
        self.api_version: str | None = None
        self.errors: list[ETAError] = []
        self.varinfo: dict[str, dict] = {}
        self.switch_defs: dict[str, dict] = {}
        self.select_defs: dict[str, dict] = {}
        self.fehlzyklen: dict[str, int] = {}
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

    def sensor_status(self, key: str) -> str:
        """Sagt, warum ein Sensor gerade keinen frischen Wert hat.

        "nicht_vorhanden" heißt: Diese Anlage kennt den Wert nicht, er
        stand schon beim Einrichten nicht im Menübaum. "nicht_erreichbar"
        heißt: Es gibt ihn, er kam nur zuletzt nicht an. Ohne diese
        Unterscheidung sieht beides gleich aus.
        """
        info = self.sensor_defs.get(key)
        if info is None or not info.get("uri"):
            return "nicht_vorhanden"
        if self.fehlzyklen.get(key, 0) >= VERALTET_AB:
            return "nicht_erreichbar"
        return "ok"

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
        if not self.enable_switches:
            return

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

    async def _zweizustand_pruefen(self, key: str, uri: str) -> dict | None:
        """Prüft an der Anlage nach, ob sich eine Taste schalten lässt.

        Beschreibbar, genau zwei Zustände, und einer davon erkennbar
        "aus" - sonst wird nicht geschaltet. Welcher Rohwert wofür
        steht, sagt allein die Anlage; hier wird nichts geraten, weil
        ein falscher Wert in die Heizungssteuerung ginge.
        """
        info = await self.client.async_get_varinfo(uri)
        if not info or not info.get("writable"):
            _LOGGER.debug("ETA: %s ist nicht beschreibbar", key)
            return None

        roh = info.get("raw_values") or {}
        if len(roh) != 2:
            _LOGGER.debug("ETA: %s hat %d Zustände statt zwei", key, len(roh))
            return None

        aus_text = next((t for t in roh if t.strip().casefold() in AUS_BEGRIFFE), None)
        if aus_text is None:
            _LOGGER.debug(
                "ETA: bei %s ist unklar, welcher Zustand 'aus' bedeutet (%s)",
                key,
                list(roh),
            )
            return None
        ein_text = next(t for t in roh if t != aus_text)
        return {
            "ein_text": ein_text,
            "ein_roh": roh[ein_text],
            "aus_text": aus_text,
            "aus_roh": roh[aus_text],
        }

    async def _betriebsarten_pruefen(self) -> None:
        """Baut je Heizkreis eine Auswahl aus seinen drei Tasten.

        Die Anlage führt Auto, Heizen und Absenken als drei einzelne
        Tasten, von denen im Betrieb genau eine auf "Ein" steht. Für
        Home Assistant ist das eine Auswahl mit vier Einträgen - der
        vierte ist "Aus" und hängt an der Ein/Aus-Taste desselben
        Heizkreises. Ohne diese Taste gäbe es keinen Weg zurück aus
        "Aus", deshalb entsteht die Auswahl nur zusammen mit ihr.
        """
        if not self.enable_switches:
            return

        aktiv = set(self.components)
        for key, definition in SELECTS.items():
            if definition["component"] not in aktiv:
                continue
            if definition["schalter"] not in self.switch_defs:
                continue

            tasten = {}
            for modus in BETRIEBSART_TASTEN:
                uri = self.discovered_uris.get(f"{key}_{modus}")
                if not uri:
                    continue
                geprueft = await self._zweizustand_pruefen(f"{key}_{modus}", uri)
                if geprueft:
                    tasten[modus] = {**geprueft, "uri": uri}

            if not tasten:
                continue

            self.select_defs[key] = {**definition, "tasten": tasten}
            for modus, taste in tasten.items():
                self.sensor_defs[f"{key}_{modus}"] = {
                    "component": definition["component"],
                    "translation_key": definition["translation_key"],
                    "icon": definition["icon"],
                    "is_string": True,
                    "uri": taste["uri"],
                    "platform": "select",
                }
            _LOGGER.info(
                "ETA: Betriebsart %s erkannt (%s)", key, ", ".join(sorted(tasten))
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
        """Ermittelt einmalig die URIs aller Messwerte dieser Anlage.

        Ohne Menübaum gibt es nichts abzufragen, denn die numerischen
        URIs unterscheiden sich von Anlage zu Anlage. Home Assistant
        bekommt deshalb ConfigEntryNotReady und versucht es später
        wieder, statt eine Integration ganz ohne Entitäten aufzusetzen.
        """
        try:
            self.discovered_uris, indices = await async_discover_uris(
                self.client, fub_name_overrides
            )
        except ETAApiError as err:
            raise ConfigEntryNotReady(
                f"Menübaum der Anlage nicht lesbar: {err}"
            ) from err

        self.sensor_defs = build_sensor_defs(
            self.discovered_uris, indices, self.components
        )
        self.components_without_data = async_check_components(
            self.hass,
            self.config_entry.entry_id,
            self.components,
            set(self.discovered_uris),
        )
        self.api_version = await self.client.async_get_api_version()
        await self._varinfo_laden()
        await self._schalter_pruefen()
        await self._betriebsarten_pruefen()
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

        for key in uris:
            if key in values:
                self.fehlzyklen.pop(key, None)
            else:
                self.fehlzyklen[key] = self.fehlzyklen.get(key, 0) + 1

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
        if not self.enable_errors:
            return
        try:
            self.errors = await self.client.async_get_errors()
        except ETAApiError as err:
            _LOGGER.debug("ETA: Fehlerliste nicht lesbar: %s", err)
