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
    SELECTS,
    SWITCHES,
    DOMAIN,
    PUFFER_FUEHLER_MINDEST,
    PUFFER_SPEICHER,
    SENSORS,
    normalize_components,
    puffer_fuehler_info,
)
from .entitaets_ids import Namen
from .repairs import async_check_components
from .uri_discovery import async_discover_uris

_LOGGER = logging.getLogger(__name__)

VERALTET_AB = 2
"""So viele Abfragen darf ein Wert am Stück ausbleiben.

Danach gilt der Sensor als nicht erreichbar, statt weiter den letzten
bekannten Wert zu zeigen.
"""

VARSET_WARTEZYKLEN = 10
"""Nach so vielen Abfragen wird ein gescheiterter Variablensatz neu angelegt.

Scheitert das Anlegen - die Anlage startet gerade neu, das Netz hakt oder
sie kennt gar keine Variablensätze -, wird so lange einzeln gelesen. Ohne
neuen Versuch bliebe es dabei bis zum nächsten Neustart von Home
Assistant, mit einer Anfrage je Messwert statt einer für alle.
"""

AUS_BEGRIFFE = {"aus", "off", "0", "nein", "no", "ausgeschaltet"}
"""Zustandsnamen, die eine ausgeschaltete Funktion bezeichnen.

Am Rohwert ist nicht ablesbar, welcher der beiden Zustände "aus" ist;
ausgewertet wird deshalb der Klartext.
"""

type ETAConfigEntry = ConfigEntry["ETADataUpdateCoordinator"]
"""Config Entry, der seinen Koordinator in runtime_data trägt."""


def build_sensor_defs(discovered_uris, puffer_fuehler_indices, components):
    """Stellt zusammen, welche Sensoren diese Anlage hat und unter welcher URI.

    Jede URI stammt aus dem Menübaum dieser Anlage; feste Adressen gibt es
    nicht. Was der Menübaum nicht hergibt, bekommt trotzdem eine Entität,
    nur ohne URI - sie zeigt dann dauerhaft "-". Ausgenommen ist, was als
    "nur_wenn_vorhanden" markiert ist. Für nicht ausgewählte Komponenten
    entsteht nichts.
    """
    aktiv = set(normalize_components(components))
    sensor_defs = {
        key: {**info, "uri": discovered_uris.get(key)}
        for key, info in SENSORS.items()
        if info["component"] in aktiv
        and (discovered_uris.get(key) or not info.get("nur_wenn_vorhanden"))
    }

    for komponente in PUFFER_SPEICHER:
        if komponente not in aktiv:
            continue
        praefix = f"{komponente}_fuehler_"
        indices = sorted(
            int(key.removeprefix(praefix))
            for key in discovered_uris
            if key.startswith(praefix)
        )
        if komponente == "puffer" and puffer_fuehler_indices:
            indices = puffer_fuehler_indices
        indices = indices or list(range(1, PUFFER_FUEHLER_MINDEST + 1))
        last_index = indices[-1]
        for index in indices:
            key = f"{praefix}{index}"
            sensor_defs[key] = {
                **puffer_fuehler_info(index, index == last_index, komponente),
                "uri": discovered_uris.get(key),
            }

    return sensor_defs


def puffer_fuehler_schluessel(sensor_defs, komponente="puffer"):
    """Die Fühler eines Puffers, oben zuerst."""
    praefix = f"{komponente}_fuehler_"
    return sorted(
        (key for key in sensor_defs if key.startswith(praefix)),
        key=lambda key: int(key.removeprefix(praefix)),
    )


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
        self.pellet_preis = 0.0
        self.prognose = None
        self.mit_prognose = True
        self.mit_zeitraeumen = True
        self.puffer_volumen_eingetragen: dict[str, float] = {}
        self.enable_switches = enable_switches
        self.enable_errors = enable_errors
        self.sensor_defs: dict[str, dict] = {}
        self.discovered_uris: dict[str, str] = {}
        self.ueber_kennung: set[str] = set()
        self.components_without_data: list[str] = []
        self.api_version: str | None = None
        self.errors: list[ETAError] = []
        self.varinfo: dict[str, dict] = {}
        self.switch_defs: dict[str, dict] = {}
        self.select_defs: dict[str, dict] = {}
        self.fehlzyklen: dict[str, int] = {}
        self.deutsche_namen: Namen = {}
        self._varset_name = f"ha{entry.entry_id}"[:32]
        self._varset_bereit = False
        self._varset_bewaehrt = False
        self._varset_wartezyklen = 0

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

    def sensor_status(self, key: str) -> str:
        """Sagt, warum ein Sensor gerade keinen frischen Wert hat.

        "nicht_vorhanden": stand schon beim Einrichten nicht im Menübaum.
        "nicht_erreichbar": vorhanden, kam zuletzt aber nicht an.
        "kein_messwert": kam an, die Anlage zeigt aber nur Striche - etwa
        bei einem Fühler mit Unterbrechung.
        """
        info = self.sensor_defs.get(key)
        if info is None or not info.get("uri"):
            return "nicht_vorhanden"
        if self.fehlzyklen.get(key, 0) >= VERALTET_AB:
            return "nicht_erreichbar"
        wert = (self.data or {}).get(key)
        if wert is not None and not wert.is_text and wert.value is None:
            return "kein_messwert"
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
            self._varset_bewaehrt = False
            _LOGGER.debug(
                "ETA: Variablensatz %s mit %d Messwerten angelegt",
                self._varset_name,
                len(uris),
            )
        except ETAApiError as err:
            self._varset_bereit = False
            self._varset_wartezyklen = VARSET_WARTEZYKLEN
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

        Ein Kandidat wird nur zum Schalter, wenn die Anlage ihn als
        beschreibbar meldet und genau zwei Zustände kennt. Erkannte
        Schalter kommen zusätzlich in die Sensordefinitionen, mit dem
        Vermerk "platform": "switch" - so wird ihr Zustand im selben
        Abfragezyklus mitgelesen.
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

            geprueft = await self._zweizustand_pruefen(key, uri)
            if geprueft is None:
                continue

            self.switch_defs[key] = {**definition, "uri": uri, **geprueft}
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
                geprueft["ein_text"],
                geprueft["ein_roh"],
                geprueft["aus_text"],
                geprueft["aus_roh"],
            )

    async def _zweizustand_pruefen(self, key: str, uri: str) -> dict | None:
        """Prüft an der Anlage nach, ob sich eine Taste schalten lässt.

        Bedingung: beschreibbar, genau zwei Zustände, einer davon
        erkennbar "aus". Die Rohwerte stammen aus /user/varinfo.
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

        Auto, Heizen und Absenken sind an der Anlage drei Tasten; der
        vierte Eintrag "Aus" hängt an der Ein/Aus-Taste desselben
        Heizkreises. Ohne diese Taste entsteht keine Auswahl.
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

        Ohne Menübaum gibt es nichts abzufragen; Home Assistant bekommt
        dann ConfigEntryNotReady und versucht es später erneut.
        """
        try:
            self.discovered_uris, indices = await async_discover_uris(
                self.client, fub_name_overrides, self.ueber_kennung
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

    def _volumen_der_anlage(self, komponente: str) -> float | None:
        """Das effektive Volumen, wie die Anlage es meldet, in Litern.

        Unplausible Werte - kein Puffer hat unter 50 oder über 100000
        Liter - gelten als unbekannt.
        """
        wert = (self.data or {}).get(f"{komponente}_volumen")
        try:
            liter = float(wert.value) if wert is not None else None
        except (TypeError, ValueError):
            return None
        return liter if liter is not None and 50 <= liter <= 100000 else None

    def volumen(self, komponente: str = "puffer") -> float | None:
        """Das Volumen eines Puffers in Litern: von der Anlage, sonst eingetragen.

        Eingetragen wird es nur beim älteren Funktionsblock "Puffer", der
        sein Volumen nicht an die Webservices gibt.
        """
        if komponente not in self.components:
            return None
        von_der_anlage = self._volumen_der_anlage(komponente)
        if von_der_anlage is not None:
            return von_der_anlage
        eingetragen = self.puffer_volumen_eingetragen.get(komponente, 0.0)
        return eingetragen if eingetragen > 0 else None

    def volumen_quelle(self, komponente: str = "puffer") -> str | None:
        if self.volumen(komponente) is None:
            return None
        return "Anlage" if self._volumen_der_anlage(komponente) is not None else "Einstellung"

    @property
    def puffer_volumen(self) -> float | None:
        """Das Volumen des ersten Puffers."""
        return self.volumen("puffer")

    @property
    def puffer_mit_volumen(self) -> set[str]:
        """Die angekreuzten Puffer mit Volumen - von der Anlage oder eingetragen."""
        return {
            k
            for k in PUFFER_SPEICHER
            if k in self.components
            and (
                self.sensor_defs.get(f"{k}_volumen", {}).get("uri")
                or self.puffer_volumen_eingetragen.get(k, 0.0) > 0
            )
        }

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

        Ist ein Variablensatz, der schon Werte geliefert hat, verschwunden -
        etwa nach einem Neustart der Anlage -, wird er sofort neu angelegt
        und dieser Durchgang einzeln gelesen. Scheitert das Anlegen oder
        liefert ein frisch angelegter Satz nichts, folgt der nächste Versuch
        erst nach VARSET_WARTEZYKLEN Abfragen.
        """
        if not self._varset_bereit:
            if self._varset_wartezyklen > 0:
                self._varset_wartezyklen -= 1
            else:
                await self._varset_anlegen()

        if self._varset_bereit:
            try:
                nach_uri = await self.client.async_get_varset(self._varset_name)
            except ETAApiError as err:
                self._varset_bereit = False
                if self._varset_bewaehrt:
                    _LOGGER.info("ETA: Variablensatz neu anlegen (%s)", err)
                    await self._varset_anlegen()
                else:
                    _LOGGER.info("ETA: Variablensatz nicht lesbar (%s)", err)
                    self._varset_wartezyklen = VARSET_WARTEZYKLEN
            else:
                werte = {
                    key: nach_uri[uri] for key, uri in uris.items() if uri in nach_uri
                }
                if werte:
                    self._varset_bewaehrt = True
                    return werte
                _LOGGER.info("ETA: Variablensatz lieferte nichts, lese einzeln")
                self._varset_bereit = False
                self._varset_wartezyklen = VARSET_WARTEZYKLEN

        return await self.client.async_get_values(uris)

    async def _fehler_lesen(self) -> None:
        """Holt die aktiven Fehler; ein Fehlschlag kippt den Zyklus nicht."""
        if not self.enable_errors:
            return
        try:
            self.errors = await self.client.async_get_errors()
        except ETAApiError as err:
            _LOGGER.debug("ETA: Fehlerliste nicht lesbar: %s", err)
