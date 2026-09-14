"""Gemeinsame Test-Hilfsmittel.

Die Tests laufen gegen ein echtes Home Assistant, aber ohne laufende
Instanz: `hass`, `ConfigEntry` und die aiohttp-Session werden durch schlanke
Attrappen ersetzt, die genau die Teile der API nachbilden, die die
Integration benutzt. Die ETA-Anlage wird durch eine Attrappe ersetzt, die
denselben Menübaum und dieselben Messwert-Antworten liefert wie echte
Hardware.
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

import pytest
from homeassistant.core import callback

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "custom_components"))

FIXTURES = Path(__file__).parent / "fixtures"
UEBERSETZUNGEN = (
    Path(__file__).resolve().parents[1]
    / "custom_components"
    / "eta_webservices"
    / "translations"
)


def entity_name(entity, sprache: str = "de") -> str:
    """Löst den Anzeigenamen einer Entität aus den Übersetzungen auf.

    Home Assistant setzt den Namen zur Laufzeit aus translation_key und der
    Sprachdatei zusammen. Die Tests laufen ohne laufende Instanz, bilden das
    hier also nach - sonst ließe sich nicht prüfen, welche Entity-IDs bei
    einer Installation tatsächlich entstehen.
    """
    import json

    daten = json.loads(
        (UEBERSETZUNGEN / f"{sprache}.json").read_text(encoding="utf-8")
    )
    return daten["entity"]["sensor"][entity.translation_key]["name"]

RESPONSE_LATENCY = 0.01


def load_menu() -> str:
    """Menübaum einer echten Anlage (Kessel + Puffer + HK1 + FWM)."""
    return (FIXTURES / "menu.xml").read_text(encoding="utf-8")


def var_xml(
    value=None,
    str_value=None,
    unit="",
    scale="1",
    dec_places="1",
    text_offset="0",
) -> str:
    """Baut eine Antwort, wie sie /user/var{uri} liefert.

    Aufbau exakt wie in der ETAtouch-Dokumentation, Abschnitt 4.1: Der
    Rohwert steht im Element selbst, nicht in einem Attribut, und
    Textvariablen sind an einem advTextOffset ungleich null zu erkennen.
    Eine Attrappe, die stattdessen ein value-Attribut liefert, verdeckt
    genau die Fehler, um die es hier geht.
    """
    attrs = (
        f'uri="/user/var/1/2/3/4/5" strValue="{str_value or ""}" '
        f'unit="{unit}" decPlaces="{dec_places}" scaleFactor="{scale}" '
        f'advTextOffset="{text_offset}"'
    )
    roh = "" if value is None else value
    return f'<eta version="1.0"><value {attrs}>{roh}</value></eta>'


class FakeResponse:
    def __init__(self, text: str, status: int = 200) -> None:
        self._text = text
        self.status = status

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def text(self) -> str:
        await asyncio.sleep(RESPONSE_LATENCY)
        return self._text


class FakeSession:
    """Antwortet wie die Webservices einer ETA-Anlage.

    Zählt außerdem mit, wie viele Abfragen gestellt wurden und wie viele
    davon gleichzeitig liefen - damit lässt sich die Parallelisierung prüfen.
    """

    LEERE_FEHLER = (
        '<eta version="1.0"><errors uri="/user/errors">'
        '<fub uri="/264/10891" name="Kessel"/></errors></eta>'
    )

    def __init__(self, menu: str) -> None:
        self.menu = menu
        self.count = 0
        self.peak_parallel = 0
        self._inflight = 0
        self.fail_uris: set[str] = set()
        self.varsets: dict[str, list[str]] = {}
        self.varset_unterstuetzt = True
        self.errors_xml = self.LEERE_FEHLER
        self.varinfo_unterstuetzt = True
        self.schreiben_erlaubt = True
        self.gesetzte_werte: list[tuple[str, str]] = []
        self.schreibbar = True

    def _ausfall_pruefen(self, url: str) -> None:
        """Simuliert Netzwerkfehler - für jeden Endpunkt gleichermaßen."""
        for fragment in self.fail_uris:
            if fragment in url:
                raise ConnectionError(f"simulierter Netzwerkfehler für {url}")

    def request(self, methode: str, url: str, data=None, timeout=None):
        """Bildet aiohttp.ClientSession.request nach.

        Alle Anfragen der Integration laufen hier durch, deshalb wird nur
        an dieser Stelle gezählt - sonst käme je nach Endpunkt eine
        andere Zahl heraus.
        """
        self.count += 1
        self._ausfall_pruefen(url)
        if methode == "POST":
            return self._wert_setzen(url, data or {})
        if methode in ("PUT", "DELETE"):
            return self._varset_aendern(methode, url)
        return self.get(url, timeout)

    def _wert_setzen(self, url: str, daten: dict):
        """Nimmt einen gesetzten Rohwert entgegen und merkt ihn sich."""
        uri = url.split("/user/var", 1)[1]
        if not self.schreiben_erlaubt:
            return FakeResponse("", status=403)
        self.gesetzte_werte.append((uri, daten.get("value")))
        return self._tracked(f'<eta version="1.0"><success uri="{uri}"/></eta>')

    def _varset_aendern(self, methode: str, url: str):
        pfad = url.split("/user/vars/", 1)[1]
        name, _, uri = pfad.partition("/")
        if methode == "PUT":
            if uri:
                self.varsets.setdefault(name, []).append(f"/{uri}")
            else:
                self.varsets[name] = []
        else:
            self.varsets.pop(name, None)
        return self._tracked('<eta version="1.0"><success uri="/u"/></eta>')

    def get(self, url: str, timeout=None):
        self._ausfall_pruefen(url)
        if "/user/vars/" in url:
            return self._varset_lesen(url)
        if "/user/varinfo" in url:
            return self._varinfo(url)
        if url.endswith("/user/errors"):
            return self._tracked(self.errors_xml)
        if url.endswith("/user/api"):
            return self._tracked(
                '<eta version="1.0"><api version="1.2"/></eta>'
            )
        if "/user/menu" in url:
            return self._tracked(self.menu)
        return self._tracked(var_xml(**self._wert_fuer(url)))

    @staticmethod
    def _wert_fuer(uri: str) -> dict:
        """Der Messwert, den die Anlage zu dieser URI liefert.

        Wird sowohl für die Einzelabfrage als auch für den Variablensatz
        benutzt, damit beide Wege dieselben Werte liefern - sonst würde
        ein Test je nach Abfrageart etwas anderes sehen.
        """
        if "12013" in uri:
            return {"value": "2370", "str_value": "23,70", "unit": "kg", "scale": "100"}
        if "12120" in uri:
            return {"value": "1000", "str_value": "1000", "unit": "kg"}
        if "2001" in uri or "12080" in uri:
            return {"value": "950", "str_value": "Heizbetrieb", "text_offset": "950"}
        if "12000" in uri:
            return {"value": "1803", "str_value": "Heizen", "text_offset": "1802"}
        return {"value": "555", "str_value": "55,5", "unit": "°C", "scale": "10"}

    def _varset_lesen(self, url: str):
        name = url.split("/user/vars/", 1)[1]
        if not self.varset_unterstuetzt or name not in self.varsets:
            return FakeResponse("", status=404)
        eintraege = ""
        for uri in self.varsets[name]:
            w = self._wert_fuer(uri)
            eintraege += (
                f'<variable uri="{uri.lstrip("/")}" '
                f'strValue="{w.get("str_value", "")}" unit="{w.get("unit", "")}" '
                f'decPlaces="1" scaleFactor="{w.get("scale", "1")}" '
                f'advTextOffset="{w.get("text_offset", "0")}">'
                f'{w.get("value", "")}</variable>'
            )
        return self._tracked(
            f'<eta version="1.0"><vars uri="/user/vars/{name}">'
            f"{eintraege}</vars></eta>"
        )

    def _varinfo(self, url: str):
        """Nur echte Schalt-URIs melden sich als beschreibbar.

        Sonst würde jeder Messwert wie ein Schalter aussehen, und die
        Tests könnten nicht zeigen, dass die Prüfung tatsächlich greift.
        """
        if not self.varinfo_unterstuetzt:
            return FakeResponse("", status=404)
        if "12080" not in url:
            return self._tracked(
                '<eta version="1.0"><varInfo uri="/u"><variable uri="/u" '
                'name="Messwert" fullName="x" unit="°C" decPlaces="1" '
                'scaleFactor="10" advTextOffset="0" isWritable="0">'
                "<type>DEFAULT</type></variable></varInfo></eta>"
            )
        return self._tracked(
            '<eta version="1.0"><varInfo uri="/u">'
            '<variable uri="/u" name="Anforderung" fullName="HK > Anforderung" '
            'unit="" decPlaces="0" scaleFactor="1" advTextOffset="950" '
            f'isWritable="{1 if self.schreibbar else 0}">'
            "<type>TEXT</type><validValues>"
            '<value strValue="Aus">949</value>'
            '<value strValue="Heizbetrieb">950</value>'
            "</validValues></variable></varInfo></eta>"
        )

    def _tracked(self, text: str):
        session = self

        class Tracked(FakeResponse):
            async def __aenter__(self):
                session._inflight += 1
                session.peak_parallel = max(
                    session.peak_parallel, session._inflight
                )
                return await super().__aenter__()

            async def __aexit__(self, *exc):
                session._inflight -= 1
                return False

        return Tracked(text)


class FakeConfigEntry:
    """Nachbildung der ConfigEntry-Teile, die die Integration benutzt."""

    def __init__(self, data: dict, options: dict | None = None) -> None:
        from homeassistant.config_entries import ConfigEntryState

        self.state = ConfigEntryState.SETUP_IN_PROGRESS
        self.data = data
        self.options = options or {}
        self.entry_id = "testeintrag"
        self.title = "ETA Heizung"
        self.runtime_data = None
        self._unload_callbacks: list = []

    def add_update_listener(self, listener):
        return lambda: None

    def async_on_unload(self, callback):
        self._unload_callbacks.append(callback)


class FakeHass:
    """Nachbildung der HomeAssistant-Teile, die die Integration benutzt."""

    class Config:
        def __init__(self, root: str) -> None:
            self._root = root

        def path(self, *parts) -> str:
            return os.path.join(self._root, *parts)

    class ConfigEntries:
        def __init__(self) -> None:
            self.forwarded: list = []

        async def async_forward_entry_setups(self, entry, platforms):
            self.forwarded.append((entry, platforms))
            return True

        async def async_unload_platforms(self, entry, platforms):
            return True

        async def async_reload(self, entry_id):
            return True

    def __init__(self, menu: str, root: str) -> None:
        self.config = self.Config(root)
        self.config_entries = self.ConfigEntries()
        self.data: dict = {}
        self.session = FakeSession(menu)

    async def async_add_executor_job(self, func, *args):
        return func(*args)

    @property
    def loop(self):
        return asyncio.get_running_loop()

    @callback
    def async_run_hass_job(self, hassjob, *args, background: bool = False):
        """Bildet den Aufruf eines HassJob nach.

        Wird vom Debouncer hinter async_request_refresh gebraucht - also
        immer dann, wenn ein Schalter nach dem Schreiben den echten
        Zustand nachlesen will. "background" steuert in Home Assistant
        nur, wie die Aufgabe eingeplant wird, und gehört nicht an die
        aufgerufene Funktion weitergereicht.
        """
        ergebnis = hassjob.target(*args)
        if asyncio.iscoroutine(ergebnis):
            return asyncio.get_running_loop().create_task(ergebnis)
        return ergebnis

    def async_create_task(self, ziel, name=None, eager_start=True):
        return asyncio.get_running_loop().create_task(ziel)

    def async_create_background_task(self, ziel, name=None, eager_start=True):
        return asyncio.get_running_loop().create_task(ziel)


@pytest.fixture
def menu_xml() -> str:
    return load_menu()


@pytest.fixture
def hass(menu_xml, tmp_path, monkeypatch) -> FakeHass:
    instance = FakeHass(menu_xml, str(tmp_path))
    monkeypatch.setattr(
        "homeassistant.helpers.aiohttp_client.async_get_clientsession",
        lambda _hass, *args, **kwargs: instance.session,
    )
    monkeypatch.setattr(
        "eta_webservices.async_get_clientsession",
        lambda _hass, *args, **kwargs: instance.session,
    )
    return instance


@pytest.fixture(autouse=True)
def reparaturen(monkeypatch) -> dict[str, list]:
    """Fängt die Reparatur-Hinweise ab.

    Die Issue-Registry von Home Assistant braucht eine laufende Instanz mit
    Speicher. Für die Tests genügt es festzuhalten, welche Hinweise angelegt
    und welche wieder entfernt werden - genau das ist die Logik dieser
    Integration.
    """
    protokoll: dict[str, list] = {"angelegt": [], "entfernt": []}

    def anlegen(hass, domain, issue_id, **kwargs):
        protokoll["angelegt"].append((issue_id, kwargs.get("translation_placeholders")))

    def entfernen(hass, domain, issue_id):
        protokoll["entfernt"].append(issue_id)

    monkeypatch.setattr(
        "eta_webservices.repairs.issue_registry.async_create_issue", anlegen
    )
    monkeypatch.setattr(
        "eta_webservices.repairs.issue_registry.async_delete_issue", entfernen
    )
    return protokoll


@pytest.fixture
def entry() -> FakeConfigEntry:
    return FakeConfigEntry(
        {
            "host": "192.0.2.10",
            "port": 8080,
            "components": ["kessel", "puffer", "hk1", "hk2", "fwm"],
            "enable_switches": True,
            "enable_errors": True,
            "scan_interval": 30,
        }
    )
