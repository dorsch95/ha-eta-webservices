"""Tests für Setup, Koordinator und Sensor-Entitäten."""

from __future__ import annotations

import pytest

import eta_webservices
from eta_webservices import sensor as sensor_platform
from eta_webservices.const import DOMAIN, OPTIONAL_SENSORS


async def setup_integration(hass, entry):
    assert await eta_webservices.async_setup_entry(hass, entry) is True
    coordinator = hass.data[DOMAIN][entry.entry_id]
    entities: list = []
    await sensor_platform.async_setup_entry(hass, entry, entities.extend)
    return coordinator, {entity.name: entity for entity in entities}


async def test_setup_legt_entitaeten_an(hass, entry):
    coordinator, by_name = await setup_integration(hass, entry)
    assert coordinator.sensor_defs
    assert "Kesseltemperatur" in by_name
    assert "Aschebox Status" in by_name
    assert "Anlagenbild Pfad" in by_name


async def test_messwert_hat_feste_einheit_und_geraet(hass, entry):
    _, by_name = await setup_integration(hass, entry)
    kessel = by_name["Kesseltemperatur"]
    assert kessel.native_value == pytest.approx(55.5)
    assert kessel.native_unit_of_measurement == "°C"
    assert kessel.has_entity_name is True
    assert kessel.device_info is not None
    assert kessel.unique_id.endswith("kessel_temperatur")


async def test_unique_ids_sind_eindeutig(hass, entry):
    _, by_name = await setup_integration(hass, entry)
    ids = [entity.unique_id for entity in by_name.values()]
    assert len(ids) == len(set(ids))


async def test_aschebox_kombiniert_beide_werte(hass, entry):
    _, by_name = await setup_integration(hass, entry)
    assert by_name["Aschebox Status"].native_value == "24/1000kg"
    assert by_name["Aschebox Status"].native_unit_of_measurement is None


async def test_pufferfuehler_kennen_ihre_position(hass, entry):
    _, by_name = await setup_integration(hass, entry)
    fuehler = [name for name in by_name if name.startswith("Puffer Fühler")]
    assert len(fuehler) >= 3
    assert by_name["Puffer Fühler 1"].extra_state_attributes == {"position": "oben"}
    letzter = sorted(fuehler)[-1]
    assert by_name[letzter].extra_state_attributes == {"position": "unten"}


async def test_optionaler_sensor_zeigt_platzhalter_ohne_einheit(hass, entry, menu_xml):
    hass.session.menu = menu_xml.replace(
        '<object uri="/79/10531/0/11149/0" name="Zirkulation">', '<object uri="/79/10531/0/99999/0" name="Unbenutzt">'
    )
    _, by_name = await setup_integration(hass, entry)
    zirkulation = by_name["FWM Zirkulation"]
    assert zirkulation.native_value == "-"
    assert zirkulation.native_unit_of_measurement is None


async def test_optionaler_sensor_liefert_wert_wenn_vorhanden(hass, entry):
    _, by_name = await setup_integration(hass, entry)
    zirkulation = by_name["FWM Zirkulation"]
    assert zirkulation.native_value == pytest.approx(55.5)
    assert zirkulation.native_unit_of_measurement == "°C"


async def test_einzelner_ausfall_behaelt_letzten_wert(hass, entry):
    coordinator, _ = await setup_integration(hass, entry)
    vorher = coordinator.data["kessel_temperatur"].value

    kessel_uri = coordinator.sensor_defs["kessel_temperatur"]["uri"]
    hass.session.fail_uris = {kessel_uri}
    await coordinator.async_refresh()

    assert coordinator.data["kessel_temperatur"].value == vorher


async def test_kompletter_ausfall_meldet_update_failed(hass, entry):
    from homeassistant.helpers.update_coordinator import UpdateFailed

    coordinator, _ = await setup_integration(hass, entry)
    hass.session.fail_uris = {"/"}
    with pytest.raises(UpdateFailed):
        await coordinator._async_update_data()


async def test_anlagengrafiken_werden_geschrieben(hass, entry):
    import os

    await setup_integration(hass, entry)
    verzeichnis = hass.config.path("www", "community", "ha-eta-webservices")
    dateien = os.listdir(verzeichnis)
    assert dateien
    assert all(name.endswith(".png") for name in dateien)


async def test_zweiter_setup_schreibt_grafiken_nicht_erneut(hass, entry):
    import os

    await setup_integration(hass, entry)
    verzeichnis = hass.config.path("www", "community", "ha-eta-webservices")
    eine_datei = os.path.join(verzeichnis, os.listdir(verzeichnis)[0])
    vorher = os.stat(eine_datei).st_mtime_ns

    hass.data.clear()
    await setup_integration(hass, entry)
    assert os.stat(eine_datei).st_mtime_ns == vorher


async def test_alle_optionalen_sensoren_existieren_immer(hass, entry):
    coordinator, _ = await setup_integration(hass, entry)
    for key in OPTIONAL_SENSORS:
        assert key in coordinator.sensor_defs
