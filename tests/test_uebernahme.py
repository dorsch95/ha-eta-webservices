"""Übernahme von Einrichtungen aus der Zeit, als die Integration eta_webservices hieß.

Läuft gegen ein echtes Home Assistant mit echten Registern und echtem
Einrichtungsdialog, nicht gegen die Attrappen aus conftest.py: Gerade das
Umhängen von Entitäten und Gerät hängt an Regeln der Register, die eine
Attrappe nicht kennt. Die alte Integration ist eine schlanke Nachbildung
mit einer Entität und einem Gerät, so wie 0.25 sie anlegte.
"""

from __future__ import annotations

import json
import shutil
import socket
import sys
from pathlib import Path
from types import MappingProxyType, SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from homeassistant import bootstrap, config_entries, loader
from homeassistant.core import CoreState, HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.helpers.storage import Store


INTEGRATION = Path(__file__).resolve().parents[1] / "custom_components" / "eta_heating_ws"
UNSER_REPO = "https://github.com/dorsch95/ha-eta-webservices"

ALTE_INTEGRATION = {
    "manifest.json": json.dumps(
        {
            "domain": "eta_webservices",
            "name": "ETA Web-Services",
            "version": "0.25.0",
            "documentation": UNSER_REPO,
            "codeowners": [],
            "config_flow": True,
            "iot_class": "local_polling",
        }
    ),
    "config_flow.py": '''
from homeassistant.config_entries import ConfigFlow

class Ablauf(ConfigFlow, domain="eta_webservices"):
    VERSION = 1
    MINOR_VERSION = 2
''',
    "__init__.py": '''
from homeassistant.const import Platform

async def async_setup_entry(hass, entry):
    await hass.config_entries.async_forward_entry_setups(entry, [Platform.SENSOR])
    return True

async def async_unload_entry(hass, entry):
    return await hass.config_entries.async_unload_platforms(entry, [Platform.SENSOR])
''',
    "sensor.py": '''
from homeassistant.components.sensor import SensorEntity
from homeassistant.helpers.device_registry import DeviceInfo

async def async_setup_entry(hass, entry, async_add_entities):
    sensor = SensorEntity()
    sensor._attr_has_entity_name = True
    sensor._attr_name = "Kesseltemperatur"
    sensor._attr_native_value = 70
    sensor._attr_unique_id = f"eta_static_{entry.entry_id}_kessel_temperatur"
    sensor._attr_device_info = DeviceInfo(
        identifiers={("eta_webservices", entry.entry_id)}, name="ETA Heizung"
    )
    async_add_entities([sensor])
''',
}
"""So legte 0.25 Entität und Gerät an: Kennungen mit der ID des Eintrags."""


def freier_port() -> int:
    """Ein Port, an dem niemand lauscht - die Anlage ist im Test nicht erreichbar."""
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _module_vergessen() -> None:
    for name in [n for n in sys.modules if n.split(".")[0] == "custom_components"]:
        del sys.modules[name]


@pytest.fixture
async def echtes_hass(tmp_path):
    """Ein echtes Home Assistant mit beiden Integrationen in custom_components."""
    ordner = tmp_path / "custom_components"
    (ordner / "eta_webservices").mkdir(parents=True)
    for datei, inhalt in ALTE_INTEGRATION.items():
        (ordner / "eta_webservices" / datei).write_text(inhalt, encoding="utf-8")
    (ordner / "eta_heating_ws").symlink_to(INTEGRATION, target_is_directory=True)

    _module_vergessen()
    sys.path.insert(0, str(tmp_path))
    hass = HomeAssistant(str(tmp_path))
    hass.config.skip_pip = True
    loader.async_setup(hass)
    hass.config_entries = config_entries.ConfigEntries(hass, {})
    await bootstrap.async_load_base_functionality(hass)
    hass.config.components.add("http")
    hass.http = SimpleNamespace(async_register_static_paths=AsyncMock())
    hass.set_state(CoreState.running)
    try:
        yield hass
    finally:
        await hass.async_stop(force=True)
        sys.path.remove(str(tmp_path))
        _module_vergessen()


async def alte_einrichtung(hass: HomeAssistant, **anders) -> config_entries.ConfigEntry:
    """Eine Einrichtung, wie 0.25 sie hinterlassen hat, geladen."""
    port = freier_port()
    werte = {
        "domain": "eta_webservices",
        "title": "ETA Heizung",
        "data": {"host": "127.0.0.1", "port": port, "components": ["kessel"]},
        "options": {"scan_interval": 60, "pellet_preis": 400},
        "version": 1,
        "minor_version": 2,
        "source": config_entries.SOURCE_USER,
        "unique_id": f"127.0.0.1:{port}",
        "discovery_keys": MappingProxyType({}),
        "subentries_data": None,
    }
    werte.update(anders)
    eintrag = config_entries.ConfigEntry(**werte)
    await hass.config_entries.async_add(eintrag)
    await hass.async_block_till_done()
    return eintrag


async def uebernehmen(hass: HomeAssistant) -> dict:
    """Der Weg über „Integration hinzufügen“ bis zum fertigen Eintrag."""
    ergebnis = await hass.config_entries.flow.async_init(
        "eta_heating_ws", context={"source": config_entries.SOURCE_USER}
    )
    assert ergebnis["type"] == "menu"
    assert ergebnis["step_id"] == "wahl"
    assert ergebnis["menu_options"] == ["uebernahme", "neu"]
    ergebnis = await hass.config_entries.flow.async_configure(
        ergebnis["flow_id"], {"next_step_id": "uebernahme"}
    )
    assert ergebnis["type"] == "form"
    assert ergebnis["step_id"] == "uebernahme"
    ergebnis = await hass.config_entries.flow.async_configure(ergebnis["flow_id"], {})
    await hass.async_block_till_done()
    return ergebnis


async def test_uebernahme_behaelt_entitaeten_geraet_und_einstellungen(echtes_hass):
    hass = echtes_hass
    alt = await alte_einrichtung(hass)
    assert alt.state is config_entries.ConfigEntryState.LOADED

    entitaeten = er.async_get(hass)
    geraete = dr.async_get(hass)
    (entitaet,) = er.async_entries_for_config_entry(entitaeten, alt.entry_id)
    (geraet,) = dr.async_entries_for_config_entry(geraete, alt.entry_id)
    geraete.async_update_device(geraet.id, name_by_user="Kessel im Keller")
    await Store(hass, 1, f"eta_webservices.aschebox_{alt.entry_id}").async_save({"gelernt": 1800.0})

    ergebnis = await uebernehmen(hass)

    assert ergebnis["type"] == "create_entry"
    assert hass.config_entries.async_entries("eta_webservices") == []
    (neu,) = hass.config_entries.async_entries("eta_heating_ws")
    assert neu.title == "ETA Heizung"
    assert neu.unique_id == alt.unique_id
    assert dict(neu.data) == dict(alt.data), "ohne den Vermerk der Übernahme"
    assert dict(neu.options) == dict(alt.options)

    umgezogen = entitaeten.async_get(entitaet.entity_id)
    assert umgezogen.entity_id == entitaet.entity_id
    assert umgezogen.platform == "eta_heating_ws"
    assert umgezogen.config_entry_id == neu.entry_id
    assert umgezogen.unique_id == f"eta_static_{neu.entry_id}_kessel_temperatur"

    geraet = geraete.async_get(geraet.id)
    assert geraet.config_entries == {neu.entry_id}
    assert geraet.identifiers == {("eta_heating_ws", neu.entry_id)}
    assert geraet.name_by_user == "Kessel im Keller"
    assert umgezogen.device_id == geraet.id

    assert await Store(hass, 1, f"eta_heating_ws.aschebox_{neu.entry_id}").async_load() == {
        "gelernt": 1800.0
    }
    assert await Store(hass, 1, f"eta_webservices.aschebox_{alt.entry_id}").async_load() is None
    assert not Path(hass.config.path("custom_components", "eta_webservices")).exists()


async def test_alter_ordner_schon_weg(echtes_hass):
    """Ohne den Code von 0.25 lädt die alte Einrichtung nicht mehr; übernommen wird trotzdem."""
    hass = echtes_hass
    alt = await alte_einrichtung(hass)
    (entitaet,) = er.async_entries_for_config_entry(er.async_get(hass), alt.entry_id)
    await hass.config_entries.async_unload(alt.entry_id)
    shutil.rmtree(hass.config.path("custom_components", "eta_webservices"))
    assert hass.states.get(entitaet.entity_id).state == "unavailable"

    assert (await uebernehmen(hass))["type"] == "create_entry"

    (neu,) = hass.config_entries.async_entries("eta_heating_ws")
    assert hass.config_entries.async_entries("eta_webservices") == []
    umgezogen = er.async_get(hass).async_get(entitaet.entity_id)
    assert umgezogen.platform == "eta_heating_ws"
    assert umgezogen.config_entry_id == neu.entry_id


async def test_fremder_alter_ordner_bleibt(echtes_hass):
    """Zeigt das Manifest nicht auf dieses Repo, gehört der Ordner jemand anderem."""
    hass = echtes_hass
    manifest = Path(hass.config.path("custom_components", "eta_webservices", "manifest.json"))
    daten = json.loads(manifest.read_text(encoding="utf-8"))
    daten["documentation"] = "https://github.com/meinETA/homeassistant-eta"
    manifest.write_text(json.dumps(daten), encoding="utf-8")
    await alte_einrichtung(hass)

    assert (await uebernehmen(hass))["type"] == "create_entry"
    assert manifest.exists()


async def test_mehrere_alte_einrichtungen_kommen_alle_mit(echtes_hass):
    hass = echtes_hass
    erste = await alte_einrichtung(hass)
    zweite = await alte_einrichtung(hass, title="ETA Zweitanlage")

    assert (await uebernehmen(hass))["type"] == "create_entry"

    assert hass.config_entries.async_entries("eta_webservices") == []
    neue = hass.config_entries.async_entries("eta_heating_ws")
    assert {e.unique_id for e in neue} == {erste.unique_id, zweite.unique_id}
    assert all("uebernommen_von" not in e.data for e in neue)
    assert {e.platform for e in er.async_get(hass).entities.values()} == {"eta_heating_ws"}
    assert not Path(hass.config.path("custom_components", "eta_webservices")).exists()


async def test_eintraege_der_anderen_eta_integration_bleiben_unberuehrt(echtes_hass):
    """Die Linie nigl/Tidone/meinETA nutzt denselben alten Namen, Version 9."""
    hass = echtes_hass
    fremd = await alte_einrichtung(
        hass, version=9, data={"host": "127.0.0.1", "port": 8080, "chosen_float_sensors": []}
    )

    ergebnis = await hass.config_entries.flow.async_init(
        "eta_heating_ws", context={"source": config_entries.SOURCE_USER}
    )

    assert ergebnis["type"] == "form"
    assert ergebnis["step_id"] == "user", "kein Angebot zur Übernahme"
    assert hass.config_entries.async_get_entry(fremd.entry_id) is not None


async def test_weitere_anlage_trotz_alter_einrichtung(echtes_hass):
    hass = echtes_hass
    await alte_einrichtung(hass)

    ergebnis = await hass.config_entries.flow.async_init(
        "eta_heating_ws", context={"source": config_entries.SOURCE_USER}
    )
    ergebnis = await hass.config_entries.flow.async_configure(
        ergebnis["flow_id"], {"next_step_id": "neu"}
    )

    assert ergebnis["type"] == "form"
    assert ergebnis["step_id"] == "user"
    assert len(hass.config_entries.async_entries("eta_webservices")) == 1
