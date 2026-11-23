"""Der ältere Funktionsblock "Puffer" mit und ohne zusätzliche Fühler.

Beide Blöcke stehen in fixtures/ so, wie ein Testaufbau sie unter
/user/menu meldet (Webservices 1.2). fub_puffer_2_fuehler.xml hat die zwei
Fühler ab Werk. In fub_puffer_5_fuehler.xml sind im
Konfigurations-Assistenten die drei zusätzlichen Fühler angehakt.

Mit zwei Fühlern führt der Block weder ein Volumen noch einen
Ladezustand. Sobald ein zusätzlicher Fühler dazukommt, stehen unter
"Puffer > geforderte Leistung" das "Effektive Puffervolumen" und der
"Ladezustand". Das Volumen ist dort ein Einstellwert, den die Anlage als
beschreibbar meldet, kein berechneter Wert wie beim PufferFlex. Die
Einrichtung zeigt ihn deshalb und nimmt eigene Liter an, die vorgehen.

Die Attrappe der Anlage meldet für jedes "Effektive Puffervolumen" 825 l.
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


async def einrichtung_prueft(hass, monkeypatch) -> tuple[list[str], dict[str, dict]]:
    """Was die Einrichtung an dieser Anlage fragt: Puffer ohne Volumen und gemeldete Einstellwerte."""
    from eta_heating_ws import config_flow as modul

    monkeypatch.setattr(modul, "async_get_clientsession", lambda _hass: hass.session)
    ohne_volumen, _, _, einstellwerte = await modul._anlage_pruefen(
        hass, "192.0.2.10", 8080, {"pufferflex": "Puffer"}, ["kessel", "puffer"], False
    )
    return ohne_volumen, einstellwerte


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
    assert coordinator.aeltere_puffer == {"puffer"}
    assert coordinator.puffer_volumen is None
    assert coordinator.puffer_mit_berechnetem_ladezustand == ["puffer"]
    assert by_name["Puffer Ladezustand"].extra_state_attributes["berechnet"] is True
    assert "Puffer effektives Volumen" not in by_name
    assert "Puffer Energieinhalt" not in by_name
    assert await einrichtung_prueft(hass, monkeypatch) == (["puffer"], {})


async def test_zwei_fuehler_mit_eingetragenen_litern(hass, entry):
    als_einziger_puffer(hass, entry, ZWEI_FUEHLER)
    entry.data["puffer_volumen"] = 1500
    coordinator, by_name = await setup_integration(hass, entry)
    assert coordinator.puffer_volumen == 1500
    assert coordinator.volumen_quelle("puffer") == "Einstellung"
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


async def test_mit_zusatzfuehlern_meldet_die_anlage_volumen_und_ladezustand(hass, entry, monkeypatch):
    """Ohne eingetragene Liter gilt der Wert der Anlage, und die Einrichtung zeigt ihn."""
    als_einziger_puffer(hass, entry, FUENF_FUEHLER)
    coordinator, by_name = await setup_integration(hass, entry)
    gefunden = coordinator.discovered_uris
    assert gefunden["puffer_volumen"] == f"{BLOCK}/0/0/12499"
    assert "puffer_volumen" not in coordinator.ueber_kennung
    assert gefunden["puffer_ladezustand"] == f"{BLOCK}/0/0/12528"
    assert "puffer_ladezustand" in coordinator.ueber_kennung, "steht unter geforderte Leistung"
    assert coordinator.aeltere_puffer == {"puffer"}
    assert coordinator.puffer_mit_berechnetem_ladezustand == []
    assert "berechnet" not in by_name["Puffer Ladezustand"].extra_state_attributes

    assert coordinator.puffer_volumen == 825
    assert coordinator.volumen_quelle("puffer") == "Anlage"
    assert by_name["Puffer effektives Volumen"].native_value == 825
    energie = by_name["Puffer Energieinhalt"]
    assert energie.extra_state_attributes["volumen_liter"] == 825
    assert energie.extra_state_attributes["volumen_quelle"] == "Anlage"
    assert energie.native_value == pytest.approx(energie_bei(825), rel=0.01)
    assert await einrichtung_prueft(hass, monkeypatch) == (
        [],
        {"puffer": {"name": "Puffer", "liter": 825}},
    )


async def test_eingetragene_liter_gehen_beim_aelteren_puffer_vor(hass, entry):
    """Der Sensor zeigt weiter den Wert der Anlage, gerechnet wird mit den eingetragenen Litern."""
    from eta_heating_ws.diagnostics import async_get_config_entry_diagnostics

    als_einziger_puffer(hass, entry, FUENF_FUEHLER)
    entry.data["puffer_volumen"] = 2000
    coordinator, by_name = await setup_integration(hass, entry)
    assert coordinator.puffer_volumen == 2000
    assert coordinator.volumen_quelle("puffer") == "Einstellung"
    assert by_name["Puffer effektives Volumen"].native_value == 825
    energie = by_name["Puffer Energieinhalt"]
    assert energie.extra_state_attributes["volumen_liter"] == 2000
    assert energie.extra_state_attributes["volumen_quelle"] == "Einstellung"
    assert energie.native_value == pytest.approx(energie_bei(2000), rel=0.01)

    diagnose = await async_get_config_entry_diagnostics(hass, entry)
    assert diagnose["konfiguration"]["puffer_volumen"] == {"puffer": 2000}
    assert diagnose["konfiguration"]["puffer_volumen_quelle"] == {"puffer": "Einstellung"}
    assert diagnose["konfiguration"]["aeltere_puffer"] == ["puffer"]


async def test_null_liter_nimmt_den_wert_der_anlage(hass, entry):
    als_einziger_puffer(hass, entry, FUENF_FUEHLER)
    entry.data["puffer_volumen"] = 0
    coordinator, _ = await setup_integration(hass, entry)
    assert coordinator.puffer_volumen == 825
    assert coordinator.volumen_quelle("puffer") == "Anlage"


@pytest.mark.parametrize("gemeldet", [0.0, 12.0])
async def test_unplausibler_wert_der_anlage(hass, entry, gemeldet):
    """Unter 50 l gilt der Wert der Anlage als unbekannt - dann zählen nur eingetragene Liter."""
    from eta_heating_ws.api import ETAValue

    als_einziger_puffer(hass, entry, FUENF_FUEHLER)
    coordinator, _ = await setup_integration(hass, entry)
    coordinator.data["puffer_volumen"] = ETAValue(gemeldet, str(gemeldet), "l", False, 0)
    assert coordinator.puffer_volumen is None
    coordinator.puffer_volumen_eingetragen["puffer"] = 1200.0
    assert coordinator.puffer_volumen == 1200
    assert coordinator.volumen_quelle("puffer") == "Einstellung"


async def test_pufferflex_bleibt_beim_wert_der_anlage(hass, entry, monkeypatch):
    """PufferFlex errechnet sein Volumen selbst - eingetragene Liter zählen dort nicht."""
    from eta_heating_ws import config_flow as modul

    entry.data["puffer_volumen"] = 2000
    coordinator, _ = await setup_integration(hass, entry)
    assert coordinator.aeltere_puffer == set()
    assert coordinator.puffer_volumen == 825
    assert coordinator.volumen_quelle("puffer") == "Anlage"

    monkeypatch.setattr(modul, "async_get_clientsession", lambda _hass: hass.session)
    ohne_volumen, _, _, einstellwerte = await modul._anlage_pruefen(
        hass, "192.0.2.10", 8080, {}, ["kessel", "puffer"], False
    )
    assert (ohne_volumen, einstellwerte) == ([], {})
