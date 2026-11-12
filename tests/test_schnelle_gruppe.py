"""Die schnelle Gruppe: wenige Werte öfter lesen als den Rest.

Ein Dashboard soll sofort zeigen, dass gezapft wird oder dass ein Schalter
umgelegt wurde. Dafür liest die Integration alles Schaltbare, den
Kessel-Zustand, die Raumtemperatur und das Frischwassermodul in einem
eigenen kurzen Takt - mit einer Anfrage über einen eigenen Variablensatz.
"""

from __future__ import annotations

from datetime import timedelta

import eta_heating_ws
from eta_heating_ws.coordinator import SCHNELL_PAUSE, SCHNELL_PLATTFORMEN

from . import test_puffer_ohne_kombi as nutzeranlage
from .test_sensors import setup_integration


async def test_vom_frischwassermodul_nur_woran_sich_das_zapfen_zeigt(hass, entry):
    """Die Gruppe soll klein bleiben: Durchfluss und Drehzahl ja, Temperatur und Zustand nein."""
    coordinator = await nutzeranlage.aufbauen(hass, entry)

    schnell = set(coordinator.schnelle_uris)

    assert {"fwm_durchfluss", "fwm_pufferpumpe_drehzahl"} <= schnell
    assert not {
        "fwm_warmwasser",
        "fwm_zustand",
        "fwm_pufferpumpe",
        "kessel_temperatur",
        "puffer_fuehler_1",
        "aussentemperatur",
    } & schnell


async def test_zirkulationspumpe_gehoert_dazu(hass, entry):
    """Zapfen heißt: Es fließt Wasser, und die Zirkulation läuft nicht."""
    coordinator, _ = await setup_integration(hass, entry)

    assert "fwm_zirkulationspumpe" in coordinator.abfragbare_uris
    assert "fwm_zirkulationspumpe" in coordinator.schnelle_uris


async def test_alles_schaltbare_und_die_raumtemperatur_gehoeren_dazu(hass, entry):
    coordinator, _ = await setup_integration(hass, entry)

    schnell = set(coordinator.schnelle_uris)
    schaltbar = {
        key
        for key, info in coordinator.sensor_defs.items()
        if info.get("platform") in SCHNELL_PLATTFORMEN
    }

    assert schaltbar, "die Testanlage hat Schalter"
    assert schaltbar <= schnell
    assert "kessel_zustand" in schnell, "die Wirkung von Kessel ein/aus und Entaschen"
    assert {info["platform"] for info in coordinator.sensor_defs.values() if "platform" in info} >= {
        "switch",
        "select",
    }
    assert "heizkreis_raum" in schnell or "heizkreis_raum" not in coordinator.abfragbare_uris
    assert len(schnell) < len(coordinator.abfragbare_uris) / 2, "die Gruppe bleibt klein"


async def aufgebaut(hass, entry):
    """Die Anlage des Nutzers, dazu eine Liste, die jedes Weitergeben an die Entitäten festhält."""
    coordinator = await nutzeranlage.aufbauen(hass, entry)
    weitergegeben: list[bool] = []
    coordinator.async_update_listeners = lambda: weitergegeben.append(coordinator.volle_abfrage)
    return coordinator, weitergegeben


async def test_schnelle_abfrage_gibt_nur_geaendertes_weiter(hass, entry):
    coordinator, weitergegeben = await aufgebaut(hass, entry)

    await coordinator.async_schnell_lesen()

    assert set(hass.session.varsets[coordinator._schnell_name]) == set(
        coordinator.schnelle_uris.values()
    )
    assert weitergegeben == [], "nichts Neues, also bleibt es still"

    hass.session.texte[coordinator.sensor_defs["fwm_durchfluss"]["uri"]] = "8,5"
    anfragen = hass.session.count
    await coordinator.async_schnell_lesen()

    assert hass.session.count == anfragen + 1, "ein Takt ist eine Anfrage"
    assert coordinator.data["fwm_durchfluss"].text == "8,5"
    assert weitergegeben == [False], "die Entitäten erfahren, dass es keine volle Abfrage war"
    assert coordinator.volle_abfrage is True


async def test_schnelle_abfrage_ruht_waehrend_der_vollen(hass, entry):
    """Sonst könnte ein älterer Wert einen neueren überschreiben."""
    coordinator, weitergegeben = await aufgebaut(hass, entry)
    hass.session.texte[coordinator.sensor_defs["fwm_durchfluss"]["uri"]] = "8,5"

    async with coordinator._lese_sperre:
        anfragen = hass.session.count
        await coordinator.async_schnell_lesen()

    assert hass.session.count == anfragen
    assert weitergegeben == []


async def test_volle_abfrage_bleibt_wie_sie_war(hass, entry):
    """Die schnelle Gruppe ändert nichts an dem, was die volle Abfrage liest."""
    coordinator, _ = await aufgebaut(hass, entry)
    await coordinator.async_schnell_lesen()
    hass.session.texte[coordinator.sensor_defs["fwm_durchfluss"]["uri"]] = "8,5"

    daten = await coordinator._async_update_data()

    assert daten["fwm_durchfluss"].text == "8,5"
    assert set(hass.session.varsets) == {coordinator._varset_name, coordinator._schnell_name}


async def test_schnelle_gruppe_uebersteht_den_neustart_der_anlage(hass, entry):
    """Die Anlage hält Variablensätze nur im Arbeitsspeicher."""
    coordinator, _ = await aufgebaut(hass, entry)
    await coordinator.async_schnell_lesen()

    del hass.session.varsets[coordinator._schnell_name]
    await coordinator.async_schnell_lesen()

    assert coordinator._schnell_pause == SCHNELL_PAUSE, "erst einmal Ruhe"
    anfragen = hass.session.count
    for _ in range(SCHNELL_PAUSE):
        await coordinator.async_schnell_lesen()
    assert hass.session.count == anfragen, "in der Pause keine Anfrage"

    await coordinator.async_schnell_lesen()

    assert coordinator._schnell_name in hass.session.varsets


async def test_anlage_ohne_variablensaetze_stoert_nicht(hass, entry):
    coordinator, weitergegeben = await aufgebaut(hass, entry)
    hass.session.varset_unterstuetzt = False

    await coordinator.async_schnell_lesen()

    assert weitergegeben == []
    assert coordinator._schnell_pause == SCHNELL_PAUSE


async def test_aufraeumen_gibt_beide_variablensaetze_frei(hass, entry):
    coordinator, _ = await aufgebaut(hass, entry)
    await coordinator.async_schnell_lesen()
    assert len(hass.session.varsets) == 2

    await coordinator.async_varset_aufraeumen()
    await coordinator.async_schnell_lesen()

    assert hass.session.varsets == {}, "ein letzter Takt legt den Satz nicht wieder an"


async def test_schnelle_abfrage_laeuft_ohne_angabe_alle_drei_sekunden(hass, entry):
    await setup_integration(hass, entry)

    assert hass.schnelltakte == [timedelta(seconds=3)]


async def test_takt_folgt_der_einstellung(hass, entry):
    entry.data["schnell_intervall"] = 5
    await setup_integration(hass, entry)

    assert hass.schnelltakte == [timedelta(seconds=5)]


async def test_null_schaltet_die_schnelle_abfrage_aus(hass, entry):
    entry.data["schnell_intervall"] = 0
    await setup_integration(hass, entry)

    assert hass.schnelltakte == []


async def test_takt_laeuft_nur_wenn_er_kuerzer_ist_als_das_abfrageintervall(hass, entry):
    """Sonst liest die volle Abfrage dieselben Werte ohnehin so oft."""
    entry.data["scan_interval"] = 3
    await setup_integration(hass, entry)
    entry.data["scan_interval"] = 1
    await setup_integration(hass, entry)

    assert hass.schnelltakte == []


def test_einstellung_steht_im_dialog():
    from eta_heating_ws.config_flow import _connection_schema, _options_schema
    from eta_heating_ws.const import DEFAULT_SCHNELL_INTERVALL, MIN_SCAN_INTERVAL

    for schema in (_connection_schema({}), _options_schema({})):
        felder = {str(k): k for k in schema.schema}
        assert felder["schnell_intervall"].default() == DEFAULT_SCHNELL_INTERVALL == 3

    assert _options_schema({"schnell_intervall": 5}).schema  # baut mit gespeichertem Wert
    assert MIN_SCAN_INTERVAL == 1


def test_beide_felder_sehen_gleich_aus():
    """Home Assistant zeigt ein Zahlenfeld mit einer Spanne unter 256 als Schieberegler."""
    from eta_heating_ws.const import MAX_SCAN_INTERVAL, MAX_SCHNELL_INTERVALL, MIN_SCAN_INTERVAL

    assert MAX_SCAN_INTERVAL - MIN_SCAN_INTERVAL >= 256
    assert MAX_SCHNELL_INTERVALL - 0 >= 256


async def test_stoerungsliste_bei_kurzem_intervall_nicht_in_jedem_zyklus(hass, entry):
    """Bei einer Sekunde Abfrageintervall müsste die Anlage sonst doppelt so oft antworten."""
    entry.data["scan_interval"] = 1
    coordinator, _ = await setup_integration(hass, entry)

    gelesen = []
    echt = coordinator.client.async_get_errors

    async def zaehlen():
        gelesen.append(1)
        return await echt()

    coordinator.client.async_get_errors = zaehlen
    for _ in range(4):
        await coordinator._async_update_data()

    assert gelesen == [], "die Liste wurde eben beim Einrichten gelesen"

    coordinator._fehler_gelesen -= 11
    await coordinator._async_update_data()
    await coordinator._async_update_data()

    assert gelesen == [1]


async def test_stoerungsliste_sonst_in_jedem_zyklus(hass, entry):
    coordinator, _ = await setup_integration(hass, entry)

    gelesen = []
    echt = coordinator.client.async_get_errors

    async def zaehlen():
        gelesen.append(1)
        return await echt()

    coordinator.client.async_get_errors = zaehlen
    for _ in range(3):
        await coordinator._async_update_data()

    assert gelesen == [1, 1, 1]
