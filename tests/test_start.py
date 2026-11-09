"""Was beim Start passiert - und was in den Hintergrund rückt, damit er schnell geht.

Eine echte Steuerung beantwortet eine Anfrage nach der anderen, an der
Anlage des Nutzers dauerte das Laden 24 Sekunden. Die meisten Anfragen
galten der Prüfung der Zeitprogramme und dem Anlegen des Variablensatzes.
"""

from __future__ import annotations

import eta_heating_ws
from eta_heating_ws.api import ETAApiClient
from eta_heating_ws.zeitprogramm import _ws_zeitprogramme

from .conftest import FakeConfigEntry
from .test_sensors import setup_integration
from .test_zeitplan import anlage_mit_fenstern, mit_zeitprogramm
from .test_zeitprogramm_karte import befehl


async def test_zeitprogramme_werden_nach_dem_laden_geprueft(hass, entry, menu_xml):
    hass.session.menu = mit_zeitprogramm(menu_xml)
    anlage_mit_fenstern(hass.session)

    assert await eta_heating_ws.async_setup_entry(hass, entry)
    coordinator = entry.runtime_data
    gestartet: list[str] = []
    coordinator.bei_neuem_zeitprogramm = gestartet.append

    assert coordinator.zeitprogramm_defs == {}, "das Laden wartet nicht auf die Prüfung"
    await coordinator.zeitprogramme_bereit()
    assert set(coordinator.zeitprogramm_defs) == {"hk1"}
    assert gestartet == ["hk1"], "danach startet der Zeitplan-Abgleich"


async def test_karte_wartet_auf_die_pruefung(hass, entry, menu_xml):
    hass.session.menu = mit_zeitprogramm(menu_xml)
    anlage_mit_fenstern(hass.session)
    assert await eta_heating_ws.async_setup_entry(hass, entry)
    hass.config_entries.geladen.append(entry)

    verbindung = await befehl(hass, _ws_zeitprogramme, type="eta_heating_ws/zeitprogramme")

    assert [p["programm"] for p in verbindung.ergebnisse[0][1]["programme"]] == ["hk1"]


async def anlegen_zaehlen(monkeypatch) -> list[str]:
    angelegt: list[str] = []
    original = ETAApiClient.async_create_varset

    async def zaehlen(self, name, uris):
        angelegt.append(name)
        await original(self, name, uris)

    monkeypatch.setattr(ETAApiClient, "async_create_varset", zaehlen)
    return angelegt


async def test_variablensatz_wird_nach_neustart_weiter_benutzt(hass, entry, monkeypatch):
    """Startet nur Home Assistant neu, steht der Satz noch auf der Anlage."""
    angelegt = await anlegen_zaehlen(monkeypatch)
    await setup_integration(hass, entry)
    assert len(angelegt) == 1

    zweiter_start = FakeConfigEntry(dict(entry.data))
    coordinator, _ = await setup_integration(hass, zweiter_start)

    assert len(angelegt) == 1, "kein zweites Anlegen mit einer Anfrage je Wert"
    assert coordinator.data["kessel_temperatur"].value is not None


async def test_veraenderter_variablensatz_wird_neu_angelegt(hass, entry, monkeypatch):
    angelegt = await anlegen_zaehlen(monkeypatch)
    coordinator, _ = await setup_integration(hass, entry)
    name = coordinator._varset_name
    hass.session.varsets[name] = hass.session.varsets[name][:-1]

    await setup_integration(hass, FakeConfigEntry(dict(entry.data)))

    assert len(angelegt) == 2
    assert len(hass.session.varsets[name]) == len(coordinator.abfragbare_uris)


async def test_fehler_bei_der_pruefung_kostet_nur_die_zeitprogramme(hass, entry, menu_xml, monkeypatch, caplog):
    from eta_heating_ws.coordinator import ETADataUpdateCoordinator

    async def kaputt(self, nur=None):
        raise RuntimeError("unerwartet")

    monkeypatch.setattr(ETADataUpdateCoordinator, "_zeitprogramme_pruefen", kaputt)
    hass.session.menu = mit_zeitprogramm(menu_xml)

    coordinator, by_name = await setup_integration(hass, entry)

    assert coordinator.zeitprogramm_defs == {}
    assert by_name, "die Messwerte sind trotzdem da"
    assert "Prüfung der Zeitprogramme fehlgeschlagen" in caplog.text


async def test_hinweise_ohne_zeitplan_verschwinden_beim_start(hass, entry, reparaturen):
    """Ohne Zeitplan oder ohne Schreibzugriff läuft kein Abgleich, der sie entfernen könnte."""
    entry.data["enable_switches"] = False
    entry.data["hk1_zeitplan"] = "schedule.heizen"

    await setup_integration(hass, entry)

    assert "testeintrag_hk1_zeitplan_bestaetigen" in reparaturen["entfernt"]
    assert "testeintrag_hk1_zeitplan_zu_voll" in reparaturen["entfernt"]


async def test_entfernen_loescht_die_gespeicherten_daten(hass, entry, monkeypatch):
    from eta_heating_ws import aschebox, zeitplan

    geloescht: list[str] = []

    class Speicher:
        def __init__(self, hass, version, schluessel):
            self.schluessel = schluessel

        async def async_remove(self):
            geloescht.append(self.schluessel)

    monkeypatch.setattr(aschebox, "Store", Speicher)
    monkeypatch.setattr(zeitplan, "Store", Speicher)

    await eta_heating_ws.async_remove_entry(hass, entry)

    assert geloescht == [
        "eta_heating_ws.aschebox_testeintrag",
        "eta_heating_ws.zeitplan_testeintrag",
    ]


async def test_weiter_benutzter_variablensatz_wird_nur_einmal_gelesen(hass, entry, monkeypatch):
    """Die Prüfung, ob der Satz noch passt, liefert die Werte gleich mit."""
    await setup_integration(hass, entry)
    gelesen: list[str] = []
    original = ETAApiClient.async_get_varset

    async def zaehlen(self, name):
        gelesen.append(name)
        return await original(self, name)

    monkeypatch.setattr(ETAApiClient, "async_get_varset", zaehlen)
    coordinator, _ = await setup_integration(hass, FakeConfigEntry(dict(entry.data)))
    assert len(gelesen) == 1

    await coordinator.async_refresh()
    assert len(gelesen) == 2, "danach wieder bei jeder Abfrage"
