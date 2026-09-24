"""Tests für Puffervolumen und Energieinhalt des Pufferspeichers."""

from __future__ import annotations

import pytest

from .test_sensors import setup_integration

GESAMTVOLUMEN = '<object uri="/120/10601/0/0/13520" name="Gesamtvolumen"/>'


def mit_gesamtvolumen(menu: str, name: str = "Gesamtvolumen") -> str:
    """PufferFlex mit eingestelltem Gesamtvolumen, wie es die Anlage führt."""
    return menu.replace(
        '<object uri="/120/10601/0/0/12528" name="Ladezustand"/>',
        '<object uri="/120/10601/0/0/12528" name="Ladezustand"/>'
        f'<object uri="/120/10601/0/0/13520" name="{name}"/>',
    )


def _wert(zahl):
    from eta_webservices.api import ETAValue

    return ETAValue(zahl, str(zahl), "°C", False, 1)


async def test_pufferflex_nennt_sein_volumen(hass, entry, menu_xml):
    hass.session.menu = mit_gesamtvolumen(menu_xml)
    coordinator, by_name = await setup_integration(hass, entry)
    assert coordinator.discovered_uris["puffer_gesamtvolumen"] == "/120/10601/0/0/13520"
    assert coordinator.puffer_volumen == 825
    assert coordinator.puffer_volumen_quelle == "Anlage"
    assert "Puffer Energieinhalt" in by_name


async def test_volumen_auch_ueber_die_kennung(hass, entry, menu_xml):
    hass.session.menu = mit_gesamtvolumen(menu_xml, name="Total volume")
    coordinator, _ = await setup_integration(hass, entry)
    assert coordinator.puffer_volumen == 825


async def test_ohne_volumen_kein_energieinhalt(hass, entry):
    coordinator, by_name = await setup_integration(hass, entry)
    assert "puffer_gesamtvolumen" not in coordinator.discovered_uris
    assert coordinator.puffer_volumen is None
    assert "Puffer Energieinhalt" not in by_name


async def test_eingetragenes_volumen_geht_vor(hass, entry, menu_xml):
    hass.session.menu = mit_gesamtvolumen(menu_xml)
    entry.data["puffer_volumen"] = 1000
    coordinator, _ = await setup_integration(hass, entry)
    assert coordinator.puffer_volumen == 1000
    assert coordinator.puffer_volumen_quelle == "Einstellung"


async def test_volumen_ist_kein_messwert(hass, entry, menu_xml):
    """Es wird einmal beim Start gelesen, nicht bei jeder Abfrage."""
    hass.session.menu = mit_gesamtvolumen(menu_xml)
    coordinator, _ = await setup_integration(hass, entry)
    assert "/120/10601/0/0/13520" not in coordinator.abfragbare_uris.values()


async def test_ohne_puffer_kein_volumen(hass, entry, menu_xml):
    hass.session.menu = mit_gesamtvolumen(menu_xml)
    entry.data["components"] = ["kessel", "fwm"]
    entry.data["puffer_volumen"] = 1000
    coordinator, by_name = await setup_integration(hass, entry)
    assert coordinator.puffer_volumen is None
    assert "Puffer Energieinhalt" not in by_name


@pytest.mark.parametrize("volumen", ["0", "12", "5000000"])
async def test_unplausibles_volumen_gilt_nicht(hass, entry, menu_xml, monkeypatch, volumen):
    from eta_webservices.api import ETAApiClient, ETAValue

    hass.session.menu = mit_gesamtvolumen(menu_xml)
    original = ETAApiClient.async_get_value

    async def wert(self, uri):
        if uri.endswith("/13520"):
            return ETAValue(volumen, volumen, "l", False, 0)
        return await original(self, uri)

    monkeypatch.setattr(ETAApiClient, "async_get_value", wert)
    coordinator, _ = await setup_integration(hass, entry)
    assert coordinator.puffer_volumen_anlage is None


async def test_energieinhalt_aus_volumen_und_fuehlern(hass, entry):
    entry.data["puffer_volumen"] = 1000
    coordinator, by_name = await setup_integration(hass, entry)
    energie = by_name["Puffer Energieinhalt"]
    fuehler = sorted(k for k in coordinator.sensor_defs if k.startswith("puffer_fuehler_"))
    for key, temperatur in zip(fuehler, (70, 60, 50, 40, 30, 20, 20, 20, 20)):
        coordinator.data[key] = _wert(temperatur)
    anzahl = len(fuehler)
    ueber = sum(max(0, t - 30) for t in (70, 60, 50, 40, 30, 20, 20, 20, 20)[:anzahl])
    assert energie.native_value == pytest.approx(round(ueber / anzahl * 1.163, 2))
    assert energie.native_unit_of_measurement == "kWh"
    assert energie.device_class == "energy_storage"
    assert energie.extra_state_attributes == {
        "volumen_liter": 1000,
        "volumen_quelle": "Einstellung",
        "ab_temperatur": 30.0,
    }
    coordinator.data.pop(fuehler[-1])
    assert energie.native_value is None, "mit fehlendem Fühler wäre das Mittel schief"


def test_energieinhalt_wird_mit_dem_volumen_aufgeraeumt():
    from eta_webservices import entitaet_vorgesehen

    assert entitaet_vorgesehen("puffer_energieinhalt", ["kessel", "puffer"], False, False, False, True)
    assert entitaet_vorgesehen("puffer_energieinhalt", ["kessel", "puffer"], False, False) is False
    assert entitaet_vorgesehen("puffer_energieinhalt", ["kessel"], False, False, False, True) is False


async def test_diagnose_nennt_das_volumen(hass, entry, menu_xml):
    from eta_webservices.diagnostics import async_get_config_entry_diagnostics

    hass.session.menu = mit_gesamtvolumen(menu_xml)
    await setup_integration(hass, entry)
    diagnose = await async_get_config_entry_diagnostics(hass, entry)
    assert diagnose["konfiguration"]["puffer_volumen"] == 825
    assert diagnose["konfiguration"]["puffer_volumen_quelle"] == "Anlage"
