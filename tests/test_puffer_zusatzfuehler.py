"""Der ältere Funktionsblock "Puffer" mit und ohne zusätzliche Fühler.

Beide Blöcke stehen in fixtures/ so, wie ein Testaufbau sie unter
/user/menu meldet (Webservices 1.2). fub_puffer_2_fuehler.xml hat die zwei
Fühler ab Werk. In fub_puffer_5_fuehler.xml sind im
Konfigurations-Assistenten die drei zusätzlichen Fühler angehakt.

Ein Gesamtvolumen führt der Block in keinem der beiden Fälle. Die
Einrichtung fragt deshalb nach den Litern, und das Zahlenfeld
"Puffervolumen" merkt sie sich in Home Assistant. Mit zusätzlichen
Fühlern stehen unter "Puffer > geforderte Leistung" ein "Effektives
Puffervolumen" und der "Ladezustand". Den Ladezustand nimmt die
Integration von der Anlage, das effektive Volumen liest sie nicht.
"""

from __future__ import annotations

import pytest

from .conftest import FIXTURES, load_menu
from .test_sensors import setup_integration

BLOCK = "/120/10251"
ZWEI_FUEHLER = (FIXTURES / "fub_puffer_2_fuehler.xml").read_text(encoding="utf-8")
FUENF_FUEHLER = (FIXTURES / "fub_puffer_5_fuehler.xml").read_text(encoding="utf-8")


def menu_mit(block: str) -> str:
    return load_menu().replace("</menu>", f"{block}</menu>")


def als_einziger_puffer(hass, entry, block: str) -> None:
    hass.session.menu = menu_mit(block)
    entry.data["components"] = ["kessel", "puffer"]
    entry.data["fub_names"] = {"pufferflex": "Puffer"}


async def einrichtung_fragt(hass, monkeypatch, namen=None) -> list[str]:
    """Für welche Puffer die Einrichtung an dieser Anlage nach Litern fragt."""
    from eta_heating_ws import config_flow as modul

    monkeypatch.setattr(modul, "async_get_clientsession", lambda _hass: hass.session)
    ohne_volumen, _, _ = await modul._anlage_pruefen(
        hass,
        "192.0.2.10",
        8080,
        {"pufferflex": "Puffer"} if namen is None else namen,
        ["kessel", "puffer"],
        False,
    )
    return ohne_volumen


def energie_bei(liter: float) -> float:
    """Wärme über 30 °C bei 55,5 °C an allen Fühlern, in kWh."""
    return liter * (55.5 - 30.0) * 4.186 / 3600


async def test_zwei_fuehler_ohne_volumen_und_ohne_ladezustand(hass, entry, monkeypatch):
    als_einziger_puffer(hass, entry, ZWEI_FUEHLER)
    coordinator, by_name = await setup_integration(hass, entry)
    gefunden = coordinator.discovered_uris
    assert gefunden["puffer_fuehler_1"] == f"{BLOCK}/0/11153/0"
    assert gefunden["puffer_fuehler_2"] == f"{BLOCK}/0/11155/0"
    assert "puffer_fuehler_3" not in gefunden
    assert "puffer_volumen" not in gefunden
    assert "puffer_ladezustand" not in gefunden
    assert coordinator.puffer_volumen is None
    assert coordinator.puffer_mit_berechnetem_ladezustand == ["puffer"]
    assert by_name["Puffer Ladezustand"].extra_state_attributes["berechnet"] is True
    assert "Puffer Energieinhalt" not in by_name
    assert await einrichtung_fragt(hass, monkeypatch) == ["puffer"]


async def test_zwei_fuehler_mit_eingetragenen_litern(hass, entry):
    als_einziger_puffer(hass, entry, ZWEI_FUEHLER)
    entry.data["puffer_volumen"] = 1500
    coordinator, by_name = await setup_integration(hass, entry)
    assert coordinator.puffer_volumen == 1500
    assert coordinator.volumen_quelle("puffer") == "Home Assistant"
    assert by_name["Puffer Energieinhalt"].native_value == pytest.approx(energie_bei(1500), rel=0.01)


async def test_fuenf_fuehler_von_oben_nach_unten(hass, entry):
    als_einziger_puffer(hass, entry, FUENF_FUEHLER)
    coordinator, by_name = await setup_integration(hass, entry)
    gefunden = coordinator.discovered_uris
    assert [gefunden[f"puffer_fuehler_{nummer}"] for nummer in range(1, 6)] == [
        f"{BLOCK}/0/11153/0",
        f"{BLOCK}/0/11052/0",
        f"{BLOCK}/0/11053/0",
        f"{BLOCK}/0/11054/0",
        f"{BLOCK}/0/11155/0",
    ]
    assert "puffer_fuehler_6" not in gefunden
    assert sorted(name for name in by_name if name.startswith("Puffer Fühler")) == [
        f"Puffer Fühler {nummer}" for nummer in range(1, 6)
    ]


async def test_mit_zusatzfuehlern_kommt_nur_der_ladezustand_von_der_anlage(hass, entry, monkeypatch):
    """Das "Effektive Puffervolumen" steht im Menübaum, gelesen wird es nicht."""
    assert f'{BLOCK}/0/0/12499' in FUENF_FUEHLER
    als_einziger_puffer(hass, entry, FUENF_FUEHLER)
    coordinator, by_name = await setup_integration(hass, entry)
    gefunden = coordinator.discovered_uris
    assert "puffer_volumen" not in gefunden
    assert f"{BLOCK}/0/0/12499" not in coordinator.abfragbare_uris.values()
    assert gefunden["puffer_ladezustand"] == f"{BLOCK}/0/0/12528"
    assert "puffer_ladezustand" in coordinator.ueber_kennung, "steht unter geforderte Leistung"
    assert coordinator.puffer_mit_berechnetem_ladezustand == []
    assert "berechnet" not in by_name["Puffer Ladezustand"].extra_state_attributes

    assert coordinator.puffer_volumen is None
    assert "Puffer Energieinhalt" not in by_name
    assert await einrichtung_fragt(hass, monkeypatch) == ["puffer"]


async def test_mit_zusatzfuehlern_zaehlen_die_eingetragenen_liter(hass, entry):
    from eta_heating_ws.diagnostics import async_get_config_entry_diagnostics

    als_einziger_puffer(hass, entry, FUENF_FUEHLER)
    entry.data["puffer_volumen"] = 2000
    coordinator, by_name = await setup_integration(hass, entry)
    assert not coordinator.puffer_volumen_an_der_anlage("puffer")
    assert coordinator.puffer_volumen == 2000
    assert coordinator.volumen_quelle("puffer") == "Home Assistant"
    energie = by_name["Puffer Energieinhalt"]
    assert energie.extra_state_attributes["volumen_liter"] == 2000
    assert energie.extra_state_attributes["volumen_quelle"] == "Home Assistant"
    assert energie.native_value == pytest.approx(energie_bei(2000), rel=0.01)

    diagnose = await async_get_config_entry_diagnostics(hass, entry)
    assert diagnose["konfiguration"]["puffer_volumen"] == {"puffer": 2000}
    assert diagnose["konfiguration"]["puffer_volumen_quelle"] == {"puffer": "Home Assistant"}


async def test_null_liter_heisst_unbekannt(hass, entry):
    als_einziger_puffer(hass, entry, FUENF_FUEHLER)
    entry.data["puffer_volumen"] = 0
    coordinator, by_name = await setup_integration(hass, entry)
    assert coordinator.puffer_volumen is None
    assert coordinator.volumen_quelle("puffer") is None
    assert "Puffer Energieinhalt" not in by_name


async def test_beim_pufferflex_fragt_die_einrichtung_nicht(hass, monkeypatch):
    """Er führt sein Gesamtvolumen selbst."""
    assert await einrichtung_fragt(hass, monkeypatch, {}) == []
