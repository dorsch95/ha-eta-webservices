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


class ETANotFoundError(ETAApiError):
    """Die Anlage kennt die angefragte Ressource nicht.

    Tritt zum Beispiel auf, wenn ein Variablensatz nach einem Neustart der
    Anlage verschwunden ist oder die Firmware /user/varinfo noch nicht
    unterstützt.
    """


class ETAError:
    """Ein aktiver Fehler der Anlage."""

    __slots__ = ("fub", "msg", "priority", "time", "text")

    def __init__(self, fub: str, msg: str, priority: str, time: str, text: str) -> None:
        self.fub = fub
        self.msg = msg
        self.priority = priority
        self.time = time
        self.text = text

    def as_dict(self) -> dict[str, str]:
        return {
            "funktionsblock": self.fub,
            "meldung": self.msg,
            "prioritaet": self.priority,
            "zeit": self.time,
            "hinweis": self.text,
        }


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
        return await self._request("GET", path, timeout)

    async def _request(
        self,
        methode: str,
        path: str,
        timeout: float,
        daten: dict[str, str] | None = None,
    ) -> str:
        """Führt eine HTTP-Anfrage aus und gibt den Rohtext zurück."""
        url = f"{self.base_url}{path}"
        try:
            async with self._session.request(
                methode,
                url,
                data=daten,
                timeout=aiohttp.ClientTimeout(total=timeout),
            ) as response:
                if response.status == 404:
                    raise ETANotFoundError(f"{url} ist der Anlage nicht bekannt")
                if response.status not in (200, 201):
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

    async def async_get_api_version(self) -> str | None:
        """Liest die Version der Webservice-Schnittstelle.

        Daran hängt, was die Anlage kann: Zeitfenster lassen sich ab 1.1
        setzen, /user/varinfo gibt es ab 1.2.
        """
        try:
            xml_text = await self._get_text("/user/api", REQUEST_TIMEOUT)
            parsed = await self._parse_xml(xml_text)
        except ETAApiError as err:
            _LOGGER.debug("ETA: API-Version nicht lesbar: %s", err)
            return None

        root = next(iter(parsed.values()), None)
        if isinstance(root, dict):
            api = root.get("api")
            if isinstance(api, dict):
                return api.get("@version")
        return None

    async def async_get_errors(self) -> list[ETAError]:
        """Liest die aktuell anstehenden Fehler der Anlage."""
        xml_text = await self._get_text("/user/errors", REQUEST_TIMEOUT)
        parsed = await self._parse_xml(xml_text)

        root = next(iter(parsed.values()), None)
        if not isinstance(root, dict):
            return []
        errors_node = root.get("errors")
        if not isinstance(errors_node, dict):
            return []

        gefunden: list[ETAError] = []
        for fub in _as_list(errors_node.get("fub")):
            if not isinstance(fub, dict):
                continue
            name = fub.get("@name", "")
            for eintrag in _as_list(fub.get("error")):
                if not isinstance(eintrag, dict):
                    continue
                gefunden.append(
                    ETAError(
                        fub=name,
                        msg=eintrag.get("@msg", ""),
                        priority=eintrag.get("@priority", ""),
                        time=eintrag.get("@time", ""),
                        text=(eintrag.get("#text") or "").strip(),
                    )
                )
        return gefunden

    async def async_get_varinfo(self, uri: str) -> dict[str, Any] | None:
        """Liest die Beschreibung einer Variable.

        Liefert unter anderem die gültigen Werte einer Textvariable und ob
        sie überhaupt geschrieben werden darf. Ältere Anlagen kennen die
        Ressource nicht - dann ist das Ergebnis None.
        """
        try:
            xml_text = await self._get_text(f"/user/varinfo{uri}", REQUEST_TIMEOUT)
            parsed = await self._parse_xml(xml_text)
        except ETAApiError as err:
            _LOGGER.debug("ETA: varinfo für %s nicht verfügbar: %s", uri, err)
            return None

        root = next(iter(parsed.values()), None)
        if not isinstance(root, dict):
            return None
        var_info = root.get("varInfo")
        if not isinstance(var_info, dict):
            return None
        variable = var_info.get("variable")
        if not isinstance(variable, dict):
            return None

        gueltige: dict[str, str] = {}
        grenzen: dict[str, float | None] = {"min": None, "max": None}
        werte = variable.get("validValues")
        if isinstance(werte, dict):
            for eintrag in _as_list(werte.get("value")):
                if isinstance(eintrag, dict) and eintrag.get("@strValue"):
                    gueltige[eintrag["@strValue"]] = (eintrag.get("#text") or "").strip()
            for grenze in grenzen:
                grenzen[grenze] = _zahl(werte.get(grenze))

        return {
            "name": variable.get("@name"),
            "full_name": variable.get("@fullName"),
            "unit": variable.get("@unit", ""),
            "type": variable.get("type"),
            "writable": variable.get("@isWritable") == "1",
            "valid_values": list(gueltige),
            "raw_values": gueltige,
            "scale": _zahl(variable.get("@scaleFactor")) or 1.0,
            "min_roh": grenzen["min"],
            "max_roh": grenzen["max"],
        }

    async def async_set_value(self, uri: str, raw_value: str) -> None:
        """Setzt eine Variable auf einen Rohwert.

        Die Anlage erwartet laut Dokumentation (Abschnitt 4.2) den
        unskalierten Rohwert als Formularfeld - also genau die Zahl, die
        /user/varinfo unter validValues zu einem Zustand nennt.
        """
        antwort = await self._request(
            "POST", f"/user/var{uri}", REQUEST_TIMEOUT, {"value": raw_value}
        )
        if "<success" not in antwort:
            raise ETAApiError(f"Setzen von {uri} auf {raw_value} wurde abgelehnt")

    async def async_create_varset(self, name: str, uris: list[str]) -> None:
        """Legt einen Variablensatz an und füllt ihn.

        Darüber lassen sich anschließend alle Werte mit einer einzigen
        Anfrage lesen.
        """
        await self._request("PUT", f"/user/vars/{name}", REQUEST_TIMEOUT)
        for uri in uris:
            await self._request("PUT", f"/user/vars/{name}{uri}", REQUEST_TIMEOUT)

    async def async_delete_varset(self, name: str) -> None:
        """Räumt einen Variablensatz wieder ab."""
        try:
            await self._request("DELETE", f"/user/vars/{name}", REQUEST_TIMEOUT)
        except ETAApiError as err:
            _LOGGER.debug("ETA: Variablensatz %s nicht entfernt: %s", name, err)

    async def async_get_varset(self, name: str) -> dict[str, ETAValue]:
        """Liest alle Werte eines Variablensatzes auf einmal.

        Der Schlüssel ist die URI der Variable, so wie die Anlage sie im
        Attribut uri zurückmeldet.
        """
        xml_text = await self._get_text(f"/user/vars/{name}", MENU_TIMEOUT)
        parsed = await self._parse_xml(xml_text)

        root = next(iter(parsed.values()), None)
        if not isinstance(root, dict):
            raise ETAApiError("Antwort enthält kein <vars>-Element")
        vars_node = root.get("vars")
        if not isinstance(vars_node, dict):
            raise ETAApiError("Antwort enthält kein <vars>-Element")

        werte: dict[str, ETAValue] = {}
        for variable in _as_list(vars_node.get("variable")):
            if not isinstance(variable, dict):
                continue
            uri = variable.get("@uri", "")
            if uri:
                werte[_normalisierte_uri(uri)] = _parse_value_node(variable)
        return werte

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
        """Liest mehrere Messwerte parallel.

        Höchstens MAX_PARALLEL_REQUESTS auf einmal, um die Steuerung nicht
        zu überlasten.
        """

        async def fetch(key: str, uri: str) -> tuple[str, ETAValue | None]:
            """Liest einen Wert; ein Fehlschlag ergibt None.

            Die Ausnahmebehandlung ist bewusst breit, damit ein einzelner
            Messwert den Abfragezyklus nicht scheitern lässt.
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


def _as_list(node: Any) -> list:
    """Macht aus einem einzelnen Knoten oder einer Liste immer eine Liste."""
    if node is None:
        return []
    if isinstance(node, list):
        return node
    return [node]


def _normalisierte_uri(uri: str) -> str:
    """Bringt eine URI auf die Form, die auch im Menübaum steht.

    Der Menübaum liefert "/120/10101/0/11109/0", ein Variablensatz
    dieselbe Adresse ohne führenden Schrägstrich.
    """
    return uri if uri.startswith("/") else f"/{uri}"


def _ganzzahl(node: dict, schluessel: str) -> int | None:
    try:
        return int(node[schluessel])
    except (KeyError, TypeError, ValueError):
        return None


def _zahl(knoten) -> float | None:
    """Eine Zahl aus einem Attribut oder einem Element wie <min>-200.0</min>."""
    if isinstance(knoten, dict):
        knoten = knoten.get("#text")
    try:
        return float(str(knoten).strip())
    except (TypeError, ValueError):
        return None


def _ohne_messwert(text: str) -> bool:
    """Zeigt die Anlage statt eines Werts nur Striche?

    So meldet sie einen Fühler mit Unterbrechung oder Kurzschluss und
    einen Wert, den gerade niemand liefert (etwa einen Raumfühler über
    eine Schnittstelle). Der Rohwert daneben ist dann ein alter oder
    erfundener Wert - bei einem abgerissenen Pufferfühler etwa 60,0 °C.
    """
    kern = text.replace(" ", "").replace(",", "").replace(".", "")
    return bool(kern) and set(kern) == {"-"}


def _parse_value_node(node: Any) -> ETAValue:
    """Wandelt einen <value>-Knoten in einen ETAValue um.

    Aufbau laut ETAtouch-Dokumentation (Abschnitt 4.1):

        <value uri="..." strValue="Off" unit="" decPlaces="0"
               scaleFactor="1" advTextOffset="1802">1802</value>

    Der Rohwert steht im Element selbst, nicht in einem Attribut. Bei
    Textvariablen ist er nur eine interne Kennzahl; erkennbar sind sie an
    einem advTextOffset ungleich null, der lesbare Zustand steht in
    strValue.
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

    if _ohne_messwert(text) and not text_offset:
        return ETAValue(None, text, einheit, False, dec_places)

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
