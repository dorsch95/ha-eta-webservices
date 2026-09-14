"""Zugriff auf die RESTful Webservices einer ETA-Heizung."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import aiohttp
import xmltodict
from homeassistant.core import HomeAssistant

from .const import MAX_PARALLEL_REQUESTS, REQUEST_TIMEOUT, MENU_TIMEOUT

_LOGGER = logging.getLogger(__name__)


class ETAApiError(Exception):
    """Fehler beim Zugriff auf die ETA-Webservices."""


class ETAValue:
    """Ein einzelner von der Anlage gelesener Messwert.

    Die Anlage liefert zu jedem Wert sowohl eine Zahl als auch einen
    formatierten Text. Beide werden behalten, weil erst die
    Sensordefinition entscheidet, welcher von beiden angezeigt wird.
    """

    __slots__ = ("value", "text", "unit", "is_text", "dec_places")

    def __init__(
        self,
        value: float | None,
        text: str,
        unit: str,
        is_text: bool,
        dec_places: int | None = None,
    ) -> None:
        self.value = value
        self.text = text
        self.unit = unit
        self.is_text = is_text
        self.dec_places = dec_places

    @property
    def display(self) -> float | str | None:
        """Der Wert in der Form, in der die Anlage ihn darstellt."""
        if self.is_text:
            return self.text
        return self.value


class ETAApiClient:
    """Kapselt alle HTTP-Aufrufe gegen eine ETA-Anlage."""

    def __init__(
        self,
        hass: HomeAssistant,
        session: aiohttp.ClientSession,
        host: str,
        port: int,
    ) -> None:
        self._hass = hass
        self._session = session
        self._host = host
        self._port = port
        self._semaphore = asyncio.Semaphore(MAX_PARALLEL_REQUESTS)

    @property
    def base_url(self) -> str:
        return f"http://{self._host}:{self._port}"

    async def _get_text(self, path: str, timeout: float) -> str:
        """Holt eine Ressource und gibt den Rohtext zurück."""
        url = f"{self.base_url}{path}"
        try:
            async with self._session.get(
                url, timeout=aiohttp.ClientTimeout(total=timeout)
            ) as response:
                if response.status != 200:
                    raise ETAApiError(f"HTTP {response.status} für {url}")
                return await response.text()
        except asyncio.TimeoutError as err:
            raise ETAApiError(f"Zeitüberschreitung bei {url}") from err
        except (aiohttp.ClientError, OSError) as err:
            raise ETAApiError(f"Verbindungsfehler bei {url}: {err}") from err

    async def _parse_xml(self, xml_text: str) -> dict[str, Any]:
        """Parst XML im Executor, damit der Event Loop frei bleibt.

        Der Menübaum einer Anlage kann mehrere hundert Kilobyte groß sein -
        das Parsen davon blockiert den Event Loop sonst spürbar.
        """
        try:
            return await self._hass.async_add_executor_job(
                lambda: xmltodict.parse(xml_text, process_namespaces=False)
            )
        except Exception as err:
            raise ETAApiError(f"XML konnte nicht geparst werden: {err}") from err

    async def async_test_connection(self) -> bool:
        """Prüft, ob die Anlage erreichbar ist und Webservices aktiv sind."""
        try:
            await self._get_text("/user/menu", MENU_TIMEOUT)
            return True
        except ETAApiError:
            return False

    async def async_get_menu(self) -> dict[str, Any]:
        """Lädt den kompletten Menübaum der Anlage."""
        xml_text = await self._get_text("/user/menu", MENU_TIMEOUT)
        return await self._parse_xml(xml_text)

    async def async_get_value(self, uri: str) -> ETAValue:
        """Liest einen einzelnen Messwert."""
        xml_text = await self._get_text(f"/user/var{uri}", REQUEST_TIMEOUT)
        parsed = await self._parse_xml(xml_text)

        root = next(iter(parsed.values()), None)
        if not isinstance(root, dict) or "value" not in root:
            raise ETAApiError("Antwort enthält kein <value>-Element")

        return _parse_value_node(root["value"])

    async def async_get_values(self, uris: dict[str, str]) -> dict[str, ETAValue]:
        """Liest mehrere Messwerte parallel (begrenzt durch ein Semaphor).

        Die ETA-Steuerung ist ein schwaches Embedded-Gerät, deshalb werden
        nicht alle Abfragen gleichzeitig gestellt, sondern maximal
        MAX_PARALLEL_REQUESTS auf einmal.
        """

        async def fetch(key: str, uri: str) -> tuple[str, ETAValue | None]:
            """Liest einen Wert und meldet Fehler als None zurück.

            Die Ausnahmebehandlung ist bewusst breit: ein einzelner Messwert,
            der unerwartete Daten liefert, darf den gesamten Abfragezyklus
            nicht scheitern lassen.
            """
            async with self._semaphore:
                try:
                    return key, await self.async_get_value(uri)
                except Exception as err:
                    _LOGGER.debug("ETA: '%s' (%s) fehlgeschlagen: %s", key, uri, err)
                    return key, None

        results = await asyncio.gather(
            *(fetch(key, uri) for key, uri in uris.items())
        )
        return {key: value for key, value in results if value is not None}


def _ganzzahl(node: dict, schluessel: str) -> int | None:
    try:
        return int(node[schluessel])
    except (KeyError, TypeError, ValueError):
        return None


def _parse_value_node(node: Any) -> ETAValue:
    """Wandelt einen <value>-Knoten in einen ETAValue um.

    Aufbau laut ETAtouch-Dokumentation (Abschnitt 4.1):

        <value uri="..." strValue="Off" unit="" decPlaces="0"
               scaleFactor="1" advTextOffset="1802">1802</value>

    Der Rohwert steht also im Element selbst, nicht in einem Attribut.
    Bei Textvariablen ist dieser Rohwert nur eine interne Kennzahl - die
    Anlage kennzeichnet sie über advTextOffset, und der lesbare Zustand
    steht in strValue. Wer das übersieht, zeigt dem Nutzer statt
    "Heizbetrieb" die Zahl 950 an.
    """
    if not isinstance(node, dict):
        return ETAValue(None, str(node), "", True)

    roh = node.get("#text")
    if roh is None:
        roh = node.get("@value")
    text = node.get("@strValue") or ""
    einheit = node.get("@unit", "") or ""
    dec_places = _ganzzahl(node, "@decPlaces")
    text_offset = _ganzzahl(node, "@advTextOffset")

    zahl = None
    if roh is not None and str(roh).strip():
        try:
            skalierung = float(node.get("@scaleFactor", 1) or 1) or 1.0
            zahl = float(roh) / skalierung
        except (TypeError, ValueError):
            zahl = None

    ist_text = bool(text_offset) or zahl is None
    if ist_text:
        return ETAValue(zahl, text, "", True, dec_places)
    return ETAValue(zahl, text, einheit, False, dec_places)
