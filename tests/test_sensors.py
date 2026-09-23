"""Tests für Setup, Koordinator und Sensor-Entitäten."""

from __future__ import annotations

import pytest

import eta_webservices
from eta_webservices import sensor as sensor_platform

from .conftest import entity_name


async def setup_integration(hass, entry):
    assert await eta_webservices.async_setup_entry(hass, entry) is True
    coordinator = entry.runtime_data
    entities: list = []
    await sensor_platform.async_setup_entry(hass, entry, entities.extend)
    return coordinator, {entity_name(entity): entity for entity in entities}


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


async def test_nachkommastellen_kommen_von_der_anlage(hass, entry):
    """Die Anlage nennt zu jedem Wert, wie genau er gemeint ist.

    Bis 0.20 wurde das gelesen, aber nie benutzt: Ein Kesseldruck von
    1,48 bar erschien als 1,5 bar.
    """
    from eta_webservices.sensor import ETAMeasurementSensor

    coordinator, by_name = await setup_integration(hass, entry)
    assert by_name["Kesseltemperatur"].suggested_display_precision == 1

    coordinator.data["kessel_druck"].dec_places = 2
    druck = ETAMeasurementSensor(
        coordinator, "kessel_druck", coordinator.sensor_defs["kessel_druck"]
    )
    assert druck.suggested_display_precision == 2

    coordinator.data["kessel_druck"].dec_places = None
    ohne_angabe = ETAMeasurementSensor(
        coordinator, "kessel_druck", coordinator.sensor_defs["kessel_druck"]
    )
    assert ohne_angabe.suggested_display_precision == 1


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
    assert by_name["Puffer Fühler 1"].extra_state_attributes["position"] == "oben"
    letzter = sorted(fuehler)[-1]
    assert by_name[letzter].extra_state_attributes["position"] == "unten"


async def test_ohne_zirkulationspumpe_ein_platzhalter(hass, entry, menu_xml):
    """Nicht jede Anlage hat eine Zirkulationspumpe."""
    hass.session.menu = menu_xml.replace(
        'name="Zirkulationspumpe"', 'name="Unbenutzt"'
    )
    _, by_name = await setup_integration(hass, entry)
    pumpe = by_name["FWM Zirkulationspumpe"]
    assert pumpe.native_value == "-"
    assert pumpe.native_unit_of_measurement is None


async def test_zirkulationspumpe_meldet_ihren_zustand(hass, entry):
    """Gefragt ist, ob die Pumpe läuft - nicht, wie warm das Wasser ist."""
    coordinator, by_name = await setup_integration(hass, entry)

    assert coordinator.sensor_defs["fwm_zirkulationspumpe"]["uri"].endswith("/2001")
    pumpe = by_name["FWM Zirkulationspumpe"]
    assert isinstance(pumpe.native_value, str)
    assert pumpe.native_unit_of_measurement is None
    assert pumpe.state_class is None


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


async def test_jeder_sensor_einer_komponente_existiert(hass, entry):
    """Auch ohne Fund im Menübaum entsteht die Entität - mit "-"."""
    from eta_webservices.const import SENSORS

    coordinator, _ = await setup_integration(hass, entry)
    aktiv = set(coordinator.components)
    for key, info in SENSORS.items():
        if info["component"] in aktiv:
            assert key in coordinator.sensor_defs, key


async def test_jede_uri_stammt_aus_dem_menuebaum(hass, entry, menu_xml):
    """Keine Adresse darf aus dem Code kommen, nur aus dieser Anlage."""
    abweichend = "/999/99999/0/11109/0"
    hass.session.menu = menu_xml.replace("/264/10891/0/11109/0", abweichend)
    coordinator, _ = await setup_integration(hass, entry)

    assert coordinator.sensor_defs["kessel_temperatur"]["uri"] == abweichend
    for key, info in coordinator.sensor_defs.items():
        if info.get("uri") and info.get("platform") != "switch":
            assert info["uri"] in coordinator.discovered_uris.values(), key


async def test_ohne_fund_zeigt_der_sensor_einen_strich(hass, entry, menu_xml):
    """Die Entität bleibt, nur eben ohne Adresse und ohne Wert."""
    hass.session.menu = menu_xml.replace('name="Eingänge"', 'name="Verschoben"')
    coordinator, by_name = await setup_integration(hass, entry)

    assert coordinator.sensor_defs["kessel_temperatur"]["uri"] is None
    sensor = by_name["Kesseltemperatur"]
    assert sensor.native_value == "-"


async def test_strich_sensor_meldet_keine_klassen(hass, entry, menu_xml):
    """Sonst meldet Home Assistant den Zustand "-" als Fehler.

    Eine numerische Geräteklasse verträgt keinen Text als Zustand - das
    stünde sonst in jedem Abfragezyklus im Protokoll.
    """
    hass.session.menu = menu_xml.replace('name="Eingänge"', 'name="Verschoben"')
    _, by_name = await setup_integration(hass, entry)

    sensor = by_name["Kesseltemperatur"]
    assert sensor.device_class is None
    assert sensor.state_class is None
    assert sensor.native_unit_of_measurement is None


async def test_diagnose_zeigt_erkennung_und_messwerte(hass, entry):
    from homeassistant.components.diagnostics import REDACTED

    from eta_webservices.diagnostics import async_get_config_entry_diagnostics

    coordinator, _ = await setup_integration(hass, entry)
    bericht = await async_get_config_entry_diagnostics(hass, entry)

    assert bericht["konfiguration"]["host"] == REDACTED
    assert "192.0.2" not in str(bericht)
    assert bericht["erkennung"]["ueber_menuebaum_gefunden"] > 0
    assert bericht["erkennung"]["pufferfuehler"]
    assert bericht["letzte_abfrage"]["erfolgreich"] is True

    kessel = bericht["messwerte"]["kessel_temperatur"]
    assert kessel["uri"] == coordinator.discovered_uris["kessel_temperatur"]
    assert kessel["rolle"] == "kessel"
    assert kessel["letzter_wert"] == pytest.approx(55.5)


async def test_diagnose_meldet_nicht_gefundene_werte(hass, entry, menu_xml):
    from eta_webservices.diagnostics import async_get_config_entry_diagnostics

    hass.session.menu = menu_xml.replace('name="Eingänge"', 'name="Verschoben"')
    await setup_integration(hass, entry)
    bericht = await async_get_config_entry_diagnostics(hass, entry)

    assert "kessel_temperatur" in bericht["erkennung"]["nicht_gefunden"]
    assert bericht["messwerte"]["kessel_temperatur"]["uri"] is None


async def test_diagnose_nennt_version_und_schreibzugriff(hass, entry):
    """Ohne diese Angaben lässt sich ein fehlender Schalter nicht beurteilen."""
    from eta_webservices.diagnostics import async_get_config_entry_diagnostics

    coordinator, _ = await setup_integration(hass, entry)
    bericht = await async_get_config_entry_diagnostics(hass, entry)

    assert bericht["erkennung"]["webservice_version"] == coordinator.api_version
    assert bericht["schreibzugriff"]["freigegeben"] is True
    assert bericht["schreibzugriff"]["schalter"] == sorted(coordinator.switch_defs)
    assert bericht["schreibzugriff"]["betriebsarten"] == sorted(
        coordinator.select_defs
    )


async def test_diagnose_ist_serialisierbar(hass, entry):
    import json

    from eta_webservices.diagnostics import async_get_config_entry_diagnostics

    await setup_integration(hass, entry)
    bericht = await async_get_config_entry_diagnostics(hass, entry)
    assert json.dumps(bericht)


async def test_ohne_menuebaum_ist_die_integration_nicht_bereit(hass, entry):
    """Ohne Menübaum gibt es nichts abzufragen - also lieber später wieder."""
    from homeassistant.exceptions import ConfigEntryNotReady

    hass.session.fail_uris = {"/user/menu"}
    with pytest.raises(ConfigEntryNotReady):
        await setup_integration(hass, entry)


async def test_marker_je_gewaehlter_komponente(hass, entry):
    coordinator, by_name = await setup_integration(hass, entry)
    for key in coordinator.components:
        marker = next(
            e for e in by_name.values() if e.translation_key == f"komponente_{key}"
        )
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


async def test_verbrauchszaehler_liefern_langzeitstatistik(hass, entry):
    from homeassistant.components.sensor import SensorStateClass

    _, by_name = await setup_integration(hass, entry)
    for name in ("Aschebox Verbrauch seit Leerung", "Verbrauch seit Entaschung"):
        sensor = by_name[name]
        assert sensor.state_class == SensorStateClass.TOTAL_INCREASING
        assert sensor.native_unit_of_measurement == "kg"


async def test_verbrauchszaehler_sind_mit_ihrer_geraeteklasse_vertraeglich(hass, entry):
    from homeassistant.components.sensor.const import (
        DEVICE_CLASS_STATE_CLASSES,
        DEVICE_CLASS_UNITS,
    )

    _, by_name = await setup_integration(hass, entry)
    for sensor in by_name.values():
        if sensor.device_class is None:
            continue
        erlaubte = DEVICE_CLASS_STATE_CLASSES.get(sensor.device_class)
        if erlaubte is not None and sensor.state_class is not None:
            assert sensor.state_class in erlaubte, sensor.translation_key
        einheiten = DEVICE_CLASS_UNITS.get(sensor.device_class)
        if einheiten and sensor.native_unit_of_measurement is not None:
            assert sensor.native_unit_of_measurement in einheiten, sensor.translation_key


async def test_pellet_energie_rechnet_kilogramm_in_kwh(hass, entry):
    from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass

    coordinator, by_name = await setup_integration(hass, entry)
    energie = by_name["Pellet Energieverbrauch gesamt"]

    kilogramm = coordinator.data["pellet_gesamtverbrauch"].value
    assert energie.native_value == pytest.approx(
        kilogramm * coordinator.pellet_kwh_per_kg
    )
    assert energie.device_class == SensorDeviceClass.ENERGY
    assert energie.state_class == SensorStateClass.TOTAL_INCREASING
    assert energie.native_unit_of_measurement == "kWh"


async def test_pellet_energie_folgt_dem_eingestellten_heizwert(hass, entry):
    entry.data["pellet_kwh_per_kg"] = 5.0
    coordinator, by_name = await setup_integration(hass, entry)
    assert coordinator.pellet_kwh_per_kg == 5.0
    assert by_name["Pellet Energieverbrauch gesamt"].native_value == pytest.approx(
        coordinator.data["pellet_gesamtverbrauch"].value * 5.0
    )


async def test_reparaturhinweis_bei_nicht_gefundener_komponente(
    hass, entry, menu_xml, reparaturen
):
    hass.session.menu = menu_xml.replace('name="FWM"', 'name="Warmwasser"')
    coordinator, _ = await setup_integration(hass, entry)

    assert "fwm" in coordinator.components_without_data
    angelegt = [i for i, _ in reparaturen["angelegt"]]
    assert "testeintrag_fwm_nicht_gefunden" in angelegt
    assert "testeintrag_kessel_nicht_gefunden" not in angelegt


async def test_kein_reparaturhinweis_wenn_alles_gefunden(hass, entry, reparaturen):
    coordinator, _ = await setup_integration(hass, entry)
    assert coordinator.components_without_data == []
    assert reparaturen["angelegt"] == []
    assert reparaturen["entfernt"]


async def test_kein_reparaturhinweis_ohne_lesbaren_menuebaum(hass, entry, reparaturen):
    """Ein unlesbarer Menübaum ist kein Namensproblem, also kein Hinweis."""
    from homeassistant.exceptions import ConfigEntryNotReady

    hass.session.fail_uris = {"/user/menu"}
    with pytest.raises(ConfigEntryNotReady):
        await setup_integration(hass, entry)

    assert reparaturen["angelegt"] == []


async def test_sammelabfrage_braucht_nur_eine_anfrage_pro_zyklus(hass, entry):
    """Statt einer Anfrage je Messwert genügt der Anlage eine einzige."""
    coordinator, _ = await setup_integration(hass, entry)
    assert len(coordinator.abfragbare_uris) > 15

    vorher = hass.session.count
    await coordinator.async_refresh()
    anfragen = hass.session.count - vorher

    assert anfragen <= 2, f"{anfragen} Anfragen statt Sammelabfrage plus Fehlerliste"
    assert coordinator.data["kessel_temperatur"].display == pytest.approx(55.5)


async def test_neustart_der_anlage_legt_den_variablensatz_neu_an(hass, entry):
    """Variablensätze überleben keinen Neustart der Heizung.

    Danach muss die Integration den Satz neu anlegen und darf in der
    Zwischenzeit keine Werte verlieren.
    """
    coordinator, _ = await setup_integration(hass, entry)
    assert hass.session.varsets

    hass.session.varsets.clear()
    await coordinator.async_refresh()

    assert hass.session.varsets, "Variablensatz wurde nicht neu angelegt"
    assert coordinator.data["kessel_temperatur"].display == pytest.approx(55.5)


async def test_nach_einem_ausfall_kehrt_die_sammelabfrage_zurueck(hass, entry):
    """Ein einziger Aussetzer darf die Sammelabfrage nicht dauerhaft abschalten.

    Bis 0.20 las die Integration danach bis zum nächsten Neustart von Home
    Assistant jeden Wert einzeln - 30 Anfragen je Abfrage statt 2.
    """
    from eta_webservices.coordinator import VARSET_WARTEZYKLEN

    coordinator, _ = await setup_integration(hass, entry)

    hass.session.fail_uris = {"/user/"}
    await coordinator.async_refresh()
    assert coordinator.last_update_success is False

    hass.session.fail_uris = set()
    for _ in range(VARSET_WARTEZYKLEN + 1):
        await coordinator.async_refresh()

    vorher = hass.session.count
    await coordinator.async_refresh()
    assert hass.session.count - vorher <= 2
    assert coordinator.data["kessel_temperatur"].display == pytest.approx(55.5)


async def test_ohne_variablensaetze_wird_nicht_bei_jeder_abfrage_neu_versucht(
    hass, entry
):
    """Kennt die Anlage keine Variablensätze, bleibt es bei seltenen Versuchen."""
    from eta_webservices.coordinator import VARSET_WARTEZYKLEN

    hass.session.varset_unterstuetzt = False
    coordinator, _ = await setup_integration(hass, entry)
    einzeln = len(coordinator.abfragbare_uris)

    vorher = hass.session.count
    for _ in range(VARSET_WARTEZYKLEN):
        await coordinator.async_refresh()
    anfragen = hass.session.count - vorher

    fehlerliste = VARSET_WARTEZYKLEN
    versuche = anfragen - fehlerliste - VARSET_WARTEZYKLEN * einzeln
    assert versuche <= 3, f"{versuche} zusätzliche Anfragen für Variablensätze"


async def test_ohne_variablensaetze_wird_einzeln_gelesen(hass, entry):
    """Ältere Anlagen kennen keine Variablensätze - dann eben einzeln."""
    hass.session.varset_unterstuetzt = False
    coordinator, by_name = await setup_integration(hass, entry)

    assert coordinator.data["kessel_temperatur"].display == pytest.approx(55.5)
    assert by_name["Kesseltemperatur"].native_value == pytest.approx(55.5)


async def test_variablensatz_wird_beim_entladen_freigegeben(hass, entry):
    import eta_webservices

    await setup_integration(hass, entry)
    assert hass.session.varsets

    await eta_webservices.async_unload_entry(hass, entry)
    assert not hass.session.varsets, "Variablensatz blieb auf der Anlage liegen"


async def test_fehlersensor_zaehlt_und_beschreibt(hass, entry):
    from .test_api import FEHLER_XML

    hass.session.errors_xml = FEHLER_XML
    coordinator, by_name = await setup_integration(hass, entry)
    await coordinator.async_refresh()

    sensor = by_name["Aktive Fehler"]
    assert sensor.native_value == 2
    assert sensor.icon == "mdi:alert-circle"
    meldungen = [f["meldung"] for f in sensor.extra_state_attributes["fehler"]]
    assert "Wasserdruck zu niedrig 0,00 bar" in meldungen


async def test_fehlersensor_ohne_fehler(hass, entry):
    _, by_name = await setup_integration(hass, entry)
    sensor = by_name["Aktive Fehler"]
    assert sensor.native_value == 0
    assert sensor.icon == "mdi:check-circle"


async def test_unlesbare_fehlerliste_kippt_den_zyklus_nicht(hass, entry):
    coordinator, _ = await setup_integration(hass, entry)
    hass.session.fail_uris = {"/user/errors"}

    await coordinator.async_refresh()

    assert coordinator.data["kessel_temperatur"].display == pytest.approx(55.5)


async def test_api_version_steht_am_geraet(hass, entry):
    coordinator, _ = await setup_integration(hass, entry)
    assert coordinator.api_version == "1.2"
    assert coordinator.device_info["sw_version"] == "Webservices 1.2"


async def test_gueltige_zustaende_werden_erfasst(hass, entry):
    """Zu Textwerten hält die Integration fest, was die Anlage dazu sagt."""
    coordinator, _ = await setup_integration(hass, entry)
    assert "heizkreis_anforderung" in coordinator.varinfo
    assert coordinator.varinfo["heizkreis_anforderung"]["writable"] is False


async def test_stoerungsmeldungen_lassen_sich_abschalten(hass, entry):
    entry.data["enable_errors"] = False
    coordinator, by_name = await setup_integration(hass, entry)
    await coordinator.async_refresh()

    assert "Aktive Fehler" not in by_name
    assert coordinator.errors == []


async def test_abgeschaltete_stoerungsmeldungen_kosten_keine_abfrage(hass, entry):
    entry.data["enable_errors"] = False
    coordinator, _ = await setup_integration(hass, entry)

    vorher = hass.session.count
    await coordinator.async_refresh()
    assert hass.session.count - vorher <= 1


async def test_kesselzustand_wird_als_text_gelesen(hass, entry):
    """Der Kesselzustand ist ein Text wie "Heizen", keine Kennzahl."""
    coordinator, by_name = await setup_integration(hass, entry)
    assert "kessel_zustand" in coordinator.sensor_defs

    sensor = by_name["Kessel Zustand"]
    assert sensor.native_value == "Heizen"
    assert sensor.native_unit_of_measurement is None
    assert sensor.state_class is None


async def test_solar_entsteht_nur_bei_angekreuzter_komponente(hass, entry):
    _, by_name = await setup_integration(hass, entry)
    assert "Solar Kollektortemperatur" not in by_name
    assert "Komponente Solar" not in by_name


async def test_solar_mit_waermemengenmessung(hass, entry):
    entry.data["components"] = ["kessel", "solar"]
    coordinator, by_name = await setup_integration(hass, entry)

    assert "Solar Kollektortemperatur" in by_name
    assert "Komponente Solar" in by_name
    for name in (
        "Solar Leistung",
        "Solar Wärmemenge",
        "Solar Ertrag heute",
        "Solar Ertrag gestern",
    ):
        assert name in by_name, name

    assert by_name["Solar Wärmemenge"].native_unit_of_measurement == "kWh"
    assert by_name["Solar Leistung"].native_unit_of_measurement == "kW"
    assert coordinator.sensor_defs["solar_kollektor"]["uri"] == "/120/10221/0/11139/0"


async def test_solar_ohne_waermemengenmessung(hass, entry, menu_xml):
    """Ohne Wärmemengenmessung darf keine leere Entität entstehen."""
    zweig = (
        '<object uri="/120/10221/0/0/12379" name="Leistung">\n'
        '<object uri="/120/10221/0/0/12349" name="Wärmemenge"/>\n'
        '<object uri="/120/10221/0/0/12350" name="Ertrag heute"/>\n'
        '<object uri="/120/10221/0/0/12769" name="Ertrag gestern"/>\n'
        "</object>\n"
    )
    assert zweig in menu_xml
    hass.session.menu = menu_xml.replace(zweig, "")
    entry.data["components"] = ["kessel", "solar"]
    _, by_name = await setup_integration(hass, entry)

    assert isinstance(by_name["Solar Kollektortemperatur"].native_value, float)
    for name in (
        "Solar Leistung",
        "Solar Wärmemenge",
        "Solar Ertrag heute",
        "Solar Ertrag gestern",
    ):
        assert by_name[name].native_value == "-", name
        assert by_name[name].state_class is None, name


async def test_status_unterscheidet_fehlend_von_unerreichbar(hass, entry, menu_xml):
    """"-" heißt "hat die Anlage nicht", nicht "gerade nicht lesbar"."""
    from eta_webservices.coordinator import VERALTET_AB

    hass.session.menu = menu_xml.replace('name="Kesseldruck"', 'name="Anlagendruck"')
    hass.session.varset_unterstuetzt = False
    coordinator, by_name = await setup_integration(hass, entry)

    fehlt = by_name["Kesseldruck"]
    assert fehlt.extra_state_attributes["status"] == "nicht_vorhanden"
    assert fehlt.native_value == "-"
    assert fehlt.available is True

    kessel = by_name["Kesseltemperatur"]
    assert kessel.extra_state_attributes["status"] == "ok"
    assert kessel.available is True

    hass.session.fail_uris = {coordinator.sensor_defs["kessel_temperatur"]["uri"]}
    for _ in range(VERALTET_AB):
        await coordinator.async_refresh()

    assert kessel.extra_state_attributes["status"] == "nicht_erreichbar"
    assert kessel.available is False
    assert fehlt.extra_state_attributes["status"] == "nicht_vorhanden"


async def test_ein_einzelner_aussetzer_kippt_nichts(hass, entry):
    """Ein einzelner Timeout darf den Sensor nicht sofort abschalten."""
    hass.session.varset_unterstuetzt = False
    coordinator, by_name = await setup_integration(hass, entry)
    kessel = by_name["Kesseltemperatur"]
    wert = kessel.native_value

    hass.session.fail_uris = {coordinator.sensor_defs["kessel_temperatur"]["uri"]}
    await coordinator.async_refresh()

    assert kessel.available is True
    assert kessel.native_value == wert


async def test_stoerungsmelder_haengt_an_den_fehlern(hass, entry):
    from .test_api import FEHLER_XML

    from eta_webservices import binary_sensor as bs

    hass.session.errors_xml = FEHLER_XML
    coordinator, _ = await setup_integration(hass, entry)
    await coordinator.async_refresh()
    entities: list = []
    await bs.async_setup_entry(hass, entry, entities.extend)
    melder = next(e for e in entities if e.translation_key == "stoerung")
    assert melder.is_on is True
    assert melder.extra_state_attributes["anzahl"] == len(coordinator.errors)

    coordinator.errors = []
    assert melder.is_on is False


async def test_ohne_stoerungsmeldungen_kein_melder(hass, entry):
    from eta_webservices import binary_sensor as bs

    entry.data["enable_errors"] = False
    await setup_integration(hass, entry)
    entities: list = []
    await bs.async_setup_entry(hass, entry, entities.extend)
    assert not [e for e in entities if e.translation_key == "stoerung"]


async def test_aschebox_erinnerung_vergleicht_die_werte_der_anlage(hass, entry):
    """Die Schwelle kommt von der Anlage, nicht aus einer Annahme."""
    from eta_webservices import binary_sensor as bs

    coordinator, _ = await setup_integration(hass, entry)
    entities: list = []
    await bs.async_setup_entry(hass, entry, entities.extend)
    melder = next(e for e in entities if e.translation_key == "aschebox_faellig")

    verbrauch = melder.extra_state_attributes["verbrauch"]
    schwelle = melder.extra_state_attributes["schwelle"]
    assert verbrauch is not None and schwelle is not None
    assert melder.is_on is (verbrauch >= schwelle)


async def test_aschebox_erinnerung_bleibt_aus_ohne_werte(hass, entry, menu_xml):
    """Lieber keine Erinnerung als eine, die auf Geratenem beruht."""
    from eta_webservices import binary_sensor as bs

    hass.session.menu = menu_xml.replace(
        'name="Aschebox leeren nach"', 'name="Verschoben"'
    )
    await setup_integration(hass, entry)
    entities: list = []
    await bs.async_setup_entry(hass, entry, entities.extend)
    melder = next(e for e in entities if e.translation_key == "aschebox_faellig")

    assert melder.extra_state_attributes["schwelle"] is None
    assert melder.is_on is False


async def test_es_gibt_genau_einen_energiesensor(hass, entry, menu_xml):
    """Zwei würden sich im Energie-Dashboard doppelt zählen lassen."""
    from homeassistant.components.sensor import SensorDeviceClass

    for menu in (menu_xml, menu_xml.replace('name="Gesamtverbrauch"', 'name="Weg"')):
        hass.session.menu = menu
        _, by_name = await setup_integration(hass, entry)
        energie = [
            e for e in by_name.values()
            if getattr(e, "device_class", None) == SensorDeviceClass.ENERGY
            and str(e.translation_key).startswith("pellet_")
        ]
        assert len(energie) <= 1, [e.translation_key for e in energie]


async def test_ohne_gesamtverbrauch_kein_energiewert(hass, entry, menu_xml):
    """Ohne Gesamtverbrauch gibt es keinen Energiewert.

    Die Aschebox misst ihren eigenen Füllstand, nicht den Verbrauch, und
    taugt deshalb nicht als Ersatzgrundlage.
    """
    hass.session.menu = menu_xml.replace('name="Gesamtverbrauch"', 'name="Weg"')
    _, by_name = await setup_integration(hass, entry)

    energie = by_name["Pellet Energieverbrauch gesamt"]
    assert energie.native_value == "-"
    assert energie.device_class is None
    assert energie.state_class is None


async def test_lager_entsteht_nur_bei_angekreuzter_komponente(hass, entry):
    _, by_name = await setup_integration(hass, entry)
    assert "Lager Vorrat" not in by_name


async def test_lagervorrat_und_warnung(hass, entry):
    from eta_webservices import binary_sensor as bs

    entry.data["components"] = ["kessel", "lager"]
    coordinator, by_name = await setup_integration(hass, entry)

    assert coordinator.sensor_defs["lager_vorrat"]["uri"] == "/264/10201/0/0/12015"
    assert by_name["Lager Vorrat"].native_unit_of_measurement == "kg"
    assert "Lager Austragung" in by_name

    entities: list = []
    await bs.async_setup_entry(hass, entry, entities.extend)
    warnung = next(e for e in entities if e.translation_key == "lager_niedrig")

    attribute = warnung.extra_state_attributes
    assert attribute["vorrat"] is not None
    assert warnung.is_on is (attribute["vorrat"] <= attribute["warngrenze"])


async def test_lagerwarnung_bleibt_aus_ohne_grenze(hass, entry, menu_xml):
    from eta_webservices import binary_sensor as bs

    hass.session.menu = menu_xml.replace('name="Vorrat Warngrenze"', 'name="Weg"')
    entry.data["components"] = ["kessel", "lager"]
    await setup_integration(hass, entry)
    entities: list = []
    await bs.async_setup_entry(hass, entry, entities.extend)
    warnung = next(e for e in entities if e.translation_key == "lager_niedrig")

    assert warnung.extra_state_attributes["warngrenze"] is None
    assert warnung.is_on is False


async def test_lager_austragung_ist_klartext(hass, entry):
    """Ein Zustand ist Text, keine Kennzahl."""
    entry.data["components"] = ["kessel", "lager"]
    _, by_name = await setup_integration(hass, entry)

    sensor = by_name["Lager Austragung"]
    assert sensor.native_value == "Bereit"
    assert sensor.native_unit_of_measurement is None
    assert sensor.state_class is None
