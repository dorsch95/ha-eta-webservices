"""Tests für Setup, Koordinator und Sensor-Entitäten."""

from __future__ import annotations

import pytest

import eta_webservices
from eta_webservices import sensor as sensor_platform
from eta_webservices.const import OPTIONAL_SENSORS


async def setup_integration(hass, entry):
    assert await eta_webservices.async_setup_entry(hass, entry) is True
    coordinator = entry.runtime_data
    entities: list = []
    await sensor_platform.async_setup_entry(hass, entry, entities.extend)
    return coordinator, {entity.name: entity for entity in entities}


async def test_setup_legt_entitaeten_an(hass, entry):
    coordinator, by_name = await setup_integration(hass, entry)
    assert coordinator.sensor_defs
    assert "Kesseltemperatur" in by_name
    assert "Aschebox Status" in by_name
    assert "Komponente Kessel" in by_name


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

    await setup_integration(hass, entry)
    assert os.stat(eine_datei).st_mtime_ns == vorher


async def test_alle_optionalen_sensoren_existieren_immer(hass, entry):
    coordinator, _ = await setup_integration(hass, entry)
    for key in OPTIONAL_SENSORS:
        assert key in coordinator.sensor_defs


async def test_gefundene_uri_schlaegt_die_fest_hinterlegte(hass, entry, menu_xml):
    from eta_webservices.const import STATIC_URIs

    abweichend = "/999/99999/0/11109/0"
    hass.session.menu = menu_xml.replace(
        STATIC_URIs["kessel_temperatur"]["uri"], abweichend
    )
    coordinator, _ = await setup_integration(hass, entry)
    assert coordinator.sensor_defs["kessel_temperatur"]["uri"] == abweichend


async def test_fest_hinterlegte_uri_greift_ohne_fund(hass, entry, menu_xml):
    from eta_webservices.const import STATIC_URIs

    hass.session.menu = menu_xml.replace('name="Eingänge"', 'name="Verschoben"')
    coordinator, _ = await setup_integration(hass, entry)
    assert (
        coordinator.sensor_defs["kessel_temperatur"]["uri"]
        == STATIC_URIs["kessel_temperatur"]["uri"]
    )


async def test_diagnose_zeigt_erkennung_und_messwerte(hass, entry):
    from homeassistant.components.diagnostics import REDACTED

    from eta_webservices.diagnostics import async_get_config_entry_diagnostics

    await setup_integration(hass, entry)
    bericht = await async_get_config_entry_diagnostics(hass, entry)

    assert bericht["konfiguration"]["host"] == REDACTED
    assert "192.0.2" not in str(bericht)
    assert bericht["erkennung"]["ueber_menuebaum_gefunden"] > 0
    assert bericht["erkennung"]["pufferfuehler"]
    assert bericht["letzte_abfrage"]["erfolgreich"] is True

    kessel = bericht["messwerte"]["kessel_temperatur"]
    assert kessel["quelle"] == "menuebaum"
    assert kessel["rolle"] == "kessel"
    assert kessel["letzter_wert"] == pytest.approx(55.5)


async def test_diagnose_meldet_nicht_gefundene_werte(hass, entry, menu_xml):
    from eta_webservices.diagnostics import async_get_config_entry_diagnostics

    hass.session.menu = menu_xml.replace('name="Eingänge"', 'name="Verschoben"')
    await setup_integration(hass, entry)
    bericht = await async_get_config_entry_diagnostics(hass, entry)

    assert "kessel_temperatur" in bericht["erkennung"]["nicht_gefunden"]
    assert bericht["messwerte"]["kessel_temperatur"]["quelle"] == "standard"


async def test_diagnose_ist_serialisierbar(hass, entry):
    import json

    from eta_webservices.diagnostics import async_get_config_entry_diagnostics

    await setup_integration(hass, entry)
    bericht = await async_get_config_entry_diagnostics(hass, entry)
    assert json.dumps(bericht)


async def test_ohne_menuebaum_entstehen_nur_die_drei_sicheren_fuehler(hass, entry):
    hass.session.fail_uris = {"/user/menu"}
    coordinator, by_name = await setup_integration(hass, entry)
    fuehler = [name for name in by_name if name.startswith("Puffer Fühler")]
    assert len(fuehler) == 3
    ohne_uri = [
        key
        for key, info in coordinator.sensor_defs.items()
        if not info.get("uri") and key not in OPTIONAL_SENSORS
    ]
    assert not ohne_uri


async def test_marker_je_gewaehlter_komponente(hass, entry):
    from eta_webservices.const import COMPONENTS

    coordinator, by_name = await setup_integration(hass, entry)
    for key in coordinator.components:
        marker = by_name[f"Komponente {COMPONENTS[key]['name']}"]
        assert marker.native_value == key
        assert marker.entity_category == "diagnostic"


async def test_marker_bleibt_bei_stoerung_verfuegbar(hass, entry):
    coordinator, by_name = await setup_integration(hass, entry)
    marker = by_name["Komponente FWM"]
    coordinator.last_update_success = False
    assert marker.available is True


async def test_abgewaehlte_komponente_erzeugt_keine_entitaeten(hass, entry):
    entry.data["components"] = ["kessel", "puffer"]
    coordinator, by_name = await setup_integration(hass, entry)

    assert "Komponente FWM" not in by_name
    assert not [n for n in by_name if n.startswith("FWM")]
    assert not [n for n in by_name if n.startswith("Heizkreis")]
    assert not [k for k in coordinator.sensor_defs if k.startswith("fwm")]
    assert "Puffer Fühler 1" in by_name


async def test_ohne_puffer_keine_fuehler(hass, entry):
    entry.data["components"] = ["kessel"]
    coordinator, by_name = await setup_integration(hass, entry)

    assert not [n for n in by_name if n.startswith("Puffer")]
    assert "Kesseltemperatur" in by_name


async def test_altes_anlagenschema_laeuft_weiter(hass, entry):
    entry.data.pop("components")
    entry.data["schema"] = "Kessel + Puffer + 1x Heizkreis + FWM"
    coordinator, by_name = await setup_integration(hass, entry)

    assert coordinator.components == ["kessel", "puffer", "fwm", "hk1"]
    assert "Heizkreis Vorlauftemperatur" in by_name
    assert "Komponente Heizkreis 2" not in by_name
