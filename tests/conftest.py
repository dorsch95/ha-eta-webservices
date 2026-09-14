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


def var_xml(value=None, str_value=None, unit="", scale="1") -> str:
    """Baut eine Antwort, wie sie /user/var{uri} liefert."""
    attrs = f'unit="{unit}" scaleFactor="{scale}"'
    if value is not None:
        attrs += f' value="{value}"'
    if str_value is not None:
        attrs += f' strValue="{str_value}"'
    return f'<eta version="1.0"><value {attrs}/></eta>'


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

    def __init__(self, menu: str) -> None:
        self.menu = menu
        self.count = 0
        self.peak_parallel = 0
        self._inflight = 0
        self.fail_uris: set[str] = set()

    def get(self, url: str, timeout=None):
        self.count += 1
        for fragment in self.fail_uris:
            if fragment in url:
                raise ConnectionError(f"simulierter Netzwerkfehler für {url}")
        if "/user/menu" in url:
            return self._tracked(self.menu)
        if "12013" in url:
            return self._tracked(var_xml(value="2370", unit="kg", scale="100"))
        if "12120" in url:
            return self._tracked(var_xml(value="1000", unit="kg"))
        if "2001" in url:
            return self._tracked(var_xml(str_value="Heizbetrieb"))
        return self._tracked(var_xml(value="555", unit="°C", scale="10"))

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
            "scan_interval": 30,
        }
    )
