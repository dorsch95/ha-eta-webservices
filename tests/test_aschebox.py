"""Tests für Entaschen-Knopf und Aschebox-Plan."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from homeassistant.exceptions import HomeAssistantError
from homeassistant.util import dt as dt_util

from eta_webservices import aschebox, karte
from eta_webservices import button as button_platform
from eta_webservices import datetime as datetime_platform
from eta_webservices import sensor as sensor_platform

from .conftest import ohne_objekt
from .test_sensors import setup_integration

KESSEL = "/264/10891/0/0/12080"
TASTE = "/264/10891/0/0/12112"


class Uhr:
    """Die Zeit des Plans - im Test von Hand vorgestellt."""

    def __init__(self) -> None:
        self.jetzt = datetime(2026, 9, 25, 10, 0, tzinfo=UTC)

    def weiter(self, **dauer) -> None:
        self.jetzt += timedelta(**dauer)


@pytest.fixture
def uhr(monkeypatch) -> Uhr:
    uhr = Uhr()
    monkeypatch.setattr(
        aschebox,
        "dt_util",
        SimpleNamespace(
            utcnow=lambda: uhr.jetzt,
            parse_datetime=dt_util.parse_datetime,
            as_utc=dt_util.as_utc,
            as_local=dt_util.as_local,
        ),
    )
    return uhr


async def aufbauen(hass, entry):
    """Richtet ein und steuert den Plan danach von Hand statt über die Abfragen."""
    coordinator, _ = await setup_integration(hass, entry)
    plan = coordinator.aschebox
    plan.stoppen()
    aufgaben: list = []
    anlegen = hass.async_create_task

    def merken(ziel, *args, **kwargs):
        aufgabe = anlegen(ziel)
        aufgaben.append(aufgabe)
        return aufgabe

    hass.async_create_task = merken
    hass.data["aufgaben"] = aufgaben
    return coordinator, plan


async def abfrage(coordinator, plan, zustand=None) -> None:
    """Eine Abfrage der Anlage, danach ein Schritt des Plans."""
    if zustand is not None:
        coordinator.hass.session.kessel_zustand = zustand
    await coordinator.async_refresh()
    await plan.weiter()


async def ausfuehren(hass, stand) -> None:
    """Lässt den Zeitgeber auslösen und wartet, bis das Abschalten durch ist.

    Liegt der Zeitpunkt zum Abschalten schon zurück, gibt es keinen
    Zeitgeber - dann läuft das Abschalten bereits.
    """
    if stand.zeitgeber:
        zeitpunkt, aktion = stand.zeitgeber[-1]
        aktion(zeitpunkt)
    aufgaben = hass.data["aufgaben"]
    while aufgaben:
        await aufgaben.pop(0)


async def test_ganzer_ablauf_mit_lernwert(hass, entry, uhr, aschebox_ohne_hass):
    coordinator, plan = await aufbauen(hass, entry)
    ziel = uhr.jetzt + timedelta(hours=2)
    await plan.planen(ziel)
    assert plan.phase == "geplant"
    assert plan.abschalten_um == ziel - timedelta(minutes=30), "beim ersten Mal 30 Minuten"

    uhr.jetzt = plan.abschalten_um
    hass.session.gesetzte_werte.clear()
    await ausfuehren(hass, aschebox_ohne_hass)
    assert hass.session.gesetzte_werte == [(KESSEL, "949")]
    assert plan.phase == "glutabbrand"

    uhr.weiter(minutes=20)
    await abfrage(coordinator, plan, "Glutabbrand da ausgeschaltet")
    assert plan.phase == "glutabbrand"

    uhr.weiter(minutes=10)
    await abfrage(coordinator, plan, "Bereit")
    assert plan.phase == "entaschen"
    assert (TASTE, "1803") in hass.session.gesetzte_werte

    uhr.weiter(minutes=2)
    await abfrage(coordinator, plan, "Entaschen")
    uhr.weiter(minutes=8)
    await abfrage(coordinator, plan, "Bereit")
    assert plan.phase == "leeren"
    assert plan.gelernt == timedelta(minutes=40)
    assert (TASTE, "1802") in hass.session.gesetzte_werte, "Taste zurückgestellt"
    assert "kann jetzt geleert werden" in aschebox_ohne_hass.meldungen[-1]

    await abfrage(coordinator, plan, "Aschebox fehlt")
    assert plan.phase == "leeren", "mit abgenommener Box nicht einschalten"
    await abfrage(coordinator, plan, "Ausgeschaltet")
    assert hass.session.gesetzte_werte[-1] == (KESSEL, "950")
    assert plan.phase == "aus"
    assert "wieder eingeschaltet" in aschebox_ohne_hass.meldungen[-1]

    ziel = uhr.jetzt + timedelta(hours=3)
    await plan.planen(ziel)
    assert plan.abschalten_um == ziel - timedelta(minutes=45), "gemessen 40 plus 5 Minuten"


async def test_entascht_immer_auch_nach_eigener_entaschung(hass, entry, uhr, aschebox_ohne_hass):
    """Damit auch der Rest der Asche herauskommt."""
    coordinator, plan = await aufbauen(hass, entry)
    await plan.planen(uhr.jetzt + timedelta(minutes=10))
    await ausfuehren(hass, aschebox_ohne_hass)
    uhr.weiter(minutes=5)
    await abfrage(coordinator, plan, "Entaschen")
    assert plan.phase == "glutabbrand"
    uhr.weiter(minutes=5)
    await abfrage(coordinator, plan, "Bereit")
    assert plan.phase == "entaschen"
    assert (TASTE, "1803") in hass.session.gesetzte_werte


async def test_sofort_bereit_zaehlt_erst_nach_der_anlaufzeit(hass, entry, uhr, aschebox_ohne_hass):
    """Direkt nach dem Befehl meldet die Anlage womöglich noch den alten Zustand."""
    coordinator, plan = await aufbauen(hass, entry)
    await plan.planen(uhr.jetzt + timedelta(minutes=10))
    await ausfuehren(hass, aschebox_ohne_hass)
    await abfrage(coordinator, plan, "Bereit")
    assert plan.phase == "glutabbrand"
    hass.session.gesetzte_werte.clear()
    uhr.weiter(minutes=2)
    await abfrage(coordinator, plan)
    assert plan.phase == "entaschen"
    uhr.weiter(seconds=30)
    await abfrage(coordinator, plan, "Bereit")
    assert plan.phase == "entaschen", "Entaschung noch nicht gesehen"


async def test_ohne_sichtbare_entaschung_nach_20_minuten_weiter(hass, entry, uhr, aschebox_ohne_hass):
    coordinator, plan = await aufbauen(hass, entry)
    await plan.planen(uhr.jetzt + timedelta(minutes=10))
    await ausfuehren(hass, aschebox_ohne_hass)
    uhr.weiter(minutes=5)
    await abfrage(coordinator, plan, "Bereit")
    uhr.weiter(minutes=19)
    await abfrage(coordinator, plan)
    assert plan.phase == "entaschen"
    uhr.weiter(minutes=2)
    await abfrage(coordinator, plan)
    assert plan.phase == "leeren"
    assert plan.gelernt is None, "ohne gesehene Entaschung wird nichts gelernt"
    assert "nicht zu sehen" in aschebox_ohne_hass.meldungen[-1]


async def test_geleerte_box_am_zaehler_erkannt(hass, entry, uhr, aschebox_ohne_hass):
    """Manche Kessel melden die abgenommene Box nicht - der Zähler fällt aber auf 0."""
    coordinator, plan = await aufbauen(hass, entry)
    await plan.planen(uhr.jetzt + timedelta(minutes=10))
    await ausfuehren(hass, aschebox_ohne_hass)
    uhr.weiter(minutes=5)
    await abfrage(coordinator, plan, "Bereit")
    uhr.weiter(minutes=2)
    await abfrage(coordinator, plan, "Entaschen")
    uhr.weiter(minutes=5)
    await abfrage(coordinator, plan, "Bereit")
    assert plan.phase == "leeren"
    await abfrage(coordinator, plan)
    assert plan.phase == "leeren"
    hass.session.asche_roh = "0"
    await abfrage(coordinator, plan)
    assert plan.phase == "aus"
    assert hass.session.gesetzte_werte[-1] == (KESSEL, "950")


async def test_nach_zwei_stunden_ohne_leeren_wieder_an(hass, entry, uhr, aschebox_ohne_hass):
    coordinator, plan = await aufbauen(hass, entry)
    await plan.planen(uhr.jetzt + timedelta(minutes=10))
    await ausfuehren(hass, aschebox_ohne_hass)
    uhr.weiter(minutes=5)
    await abfrage(coordinator, plan, "Bereit")
    uhr.weiter(minutes=2)
    await abfrage(coordinator, plan, "Entaschen")
    uhr.weiter(minutes=5)
    await abfrage(coordinator, plan, "Bereit")
    uhr.weiter(hours=1, minutes=59)
    await abfrage(coordinator, plan)
    assert plan.phase == "leeren"
    uhr.weiter(minutes=2)
    await abfrage(coordinator, plan)
    assert plan.phase == "aus"
    assert hass.session.gesetzte_werte[-1] == (KESSEL, "950")
    assert "nicht geleert" in aschebox_ohne_hass.meldungen[-1]


async def test_abbrechen_schaltet_den_kessel_wieder_ein(hass, entry, uhr, aschebox_ohne_hass):
    coordinator, plan = await aufbauen(hass, entry)
    await plan.planen(uhr.jetzt + timedelta(minutes=10))
    await ausfuehren(hass, aschebox_ohne_hass)
    await plan.abbrechen()
    assert plan.phase == "aus"
    assert hass.session.gesetzte_werte[-1] == (KESSEL, "950")


async def test_abbrechen_vor_dem_abschalten_schreibt_nichts(hass, entry, uhr, aschebox_ohne_hass):
    coordinator, plan = await aufbauen(hass, entry)
    await plan.planen(uhr.jetzt + timedelta(hours=5))
    hass.session.gesetzte_werte.clear()
    await plan.abbrechen()
    assert hass.session.gesetzte_werte == []
    assert aschebox_ohne_hass.zeitgeber == [], "Zeitgeber gelöscht"


async def test_von_hand_eingeschaltet_beendet_den_plan(hass, entry, uhr, aschebox_ohne_hass):
    coordinator, plan = await aufbauen(hass, entry)
    await plan.planen(uhr.jetzt + timedelta(minutes=10))
    await ausfuehren(hass, aschebox_ohne_hass)
    hass.session.geschrieben[KESSEL] = "950"
    hass.session.gesetzte_werte.clear()
    uhr.weiter(minutes=5)
    await abfrage(coordinator, plan, "Bereit")
    assert plan.phase == "aus"
    assert hass.session.gesetzte_werte == [], "keine Entaschentaste mehr"


async def test_planen_nur_in_die_zukunft_und_nicht_doppelt(hass, entry, uhr, aschebox_ohne_hass):
    coordinator, plan = await aufbauen(hass, entry)
    with pytest.raises(HomeAssistantError):
        await plan.planen(uhr.jetzt - timedelta(minutes=1))
    await plan.planen(uhr.jetzt + timedelta(hours=4))
    await plan.planen(uhr.jetzt + timedelta(hours=5))
    assert plan.ziel == uhr.jetzt + timedelta(hours=5), "vor dem Abschalten verschiebbar"
    assert len(aschebox_ohne_hass.zeitgeber) == 1
    await ausfuehren(hass, aschebox_ohne_hass)
    with pytest.raises(HomeAssistantError):
        await plan.planen(uhr.jetzt + timedelta(hours=6))


async def test_knapp_geplant_schaltet_sofort_ab(hass, entry, uhr, aschebox_ohne_hass):
    coordinator, plan = await aufbauen(hass, entry)
    hass.session.gesetzte_werte.clear()
    await plan.planen(uhr.jetzt + timedelta(minutes=10))
    assert aschebox_ohne_hass.zeitgeber == []
    await ausfuehren(hass, aschebox_ohne_hass)
    assert plan.phase == "glutabbrand"
    assert hass.session.gesetzte_werte == [(KESSEL, "949")]


async def test_plan_uebersteht_einen_neustart(hass, entry, uhr, aschebox_ohne_hass):
    coordinator, plan = await aufbauen(hass, entry)
    ziel = uhr.jetzt + timedelta(hours=3)
    await plan.planen(ziel)
    neu = aschebox.AscheboxPlan(hass, coordinator)
    await neu.laden()
    assert (neu.phase, neu.ziel) == ("geplant", ziel)

    uhr.weiter(hours=4, minutes=1)
    abgelaufen = aschebox.AscheboxPlan(hass, coordinator)
    await abgelaufen.laden()
    assert abgelaufen.phase == "aus", "eine Stunde nach der Zeit verworfen"


async def test_ohne_entaschentaste_weder_knopf_noch_plan(hass, entry, menu_xml):
    hass.session.menu = ohne_objekt(menu_xml, TASTE)
    coordinator, _ = await setup_integration(hass, entry)
    assert coordinator.entaschen_def is None
    assert coordinator.aschebox is None


async def test_ohne_schreibzugriff_weder_knopf_noch_plan(hass, entry):
    entry.data["enable_switches"] = False
    coordinator, _ = await setup_integration(hass, entry)
    assert coordinator.entaschen_def is None
    assert coordinator.aschebox is None


async def test_entitaeten_und_ids(hass, entry, uhr):
    coordinator, plan = await aufbauen(hass, entry)
    knoepfe: list = []
    await button_platform.async_setup_entry(hass, entry, knoepfe.extend)
    zeiten: list = []
    await datetime_platform.async_setup_entry(hass, entry, zeiten.extend)
    sensoren: list = []
    await sensor_platform.async_setup_entry(hass, entry, sensoren.extend)
    ids = {e.entity_id for e in (*knoepfe, *zeiten, *sensoren)}
    assert {
        "button.eta_heizung_kessel_entaschen",
        "button.eta_heizung_aschebox_plan_abbrechen",
        "datetime.eta_heizung_aschebox_leeren_um",
        "sensor.eta_heizung_aschebox_plan",
    } <= ids

    entaschen = next(k for k in knoepfe if k.translation_key == "kessel_entaschen")
    hass.session.gesetzte_werte.clear()
    await entaschen.async_press()
    assert hass.session.gesetzte_werte == [(TASTE, "1803")]

    abbrechen = next(k for k in knoepfe if k.translation_key == "aschebox_plan_abbrechen")
    (zeit,) = zeiten
    status = next(s for s in sensoren if s.translation_key == "aschebox_plan")
    assert not abbrechen.available
    assert zeit.native_value is None
    assert status.native_value == "aus"
    await plan.planen(uhr.jetzt + timedelta(hours=2))
    assert abbrechen.available
    assert zeit.native_value == uhr.jetzt + timedelta(hours=2)
    assert status.native_value == "geplant"
    assert status.extra_state_attributes["vorlauf_minuten"] == 30


def test_aschebox_entitaeten_nur_mit_schreibzugriff():
    from eta_webservices import entitaet_vorgesehen

    for key in ("kessel_entaschen", "aschebox_leeren_um", "aschebox_plan", "aschebox_plan_abbrechen"):
        assert entitaet_vorgesehen(key, ["kessel"], True, False)
        assert entitaet_vorgesehen(key, ["kessel"], False, False) is False
        assert entitaet_vorgesehen(key, ["hk1"], True, False) is False


def test_kessel_knoepfe_leuchten_wie_am_heizkreis():
    knoepfe = karte.kessel_knoepfe()
    ein_aus = [k for k in knoepfe if k["elements"][0]["entity"] == "switch.eta_heizung_kessel"]
    assert len(ein_aus) == 4, "leuchtend und hell, je mit und ohne Entaschentaste"
    leuchtend, hell = ein_aus[:2]
    plan = "sensor.eta_heizung_aschebox_plan"
    mit = {"condition": "state", "entity": plan, "state_not": "unknown"}
    ohne = {"condition": "state", "entity": plan, "state": "unknown"}
    for knopf in ein_aus[:2]:
        assert mit in knopf["conditions"]
        assert knopf["elements"][0]["style"]["left"] == "70%"
    for knopf in ein_aus[2:]:
        assert ohne in knopf["conditions"], "ohne Plan allein in der Mitte"
        assert knopf["elements"][0]["style"]["left"] == "50%"
    assert {"condition": "state", "entity": "switch.eta_heizung_kessel", "state": "on"} in leuchtend["conditions"]
    assert {"condition": "state", "entity": "switch.eta_heizung_kessel", "state_not": "on"} in hell["conditions"]
    assert leuchtend["elements"][0]["style"]["color"] == karte.AKTIV
    assert "filter" in leuchtend["elements"][0]["style"]
    assert "filter" not in hell["elements"][0]["style"]

    entaschen = next(k for k in knoepfe if k["elements"][0]["icon"] == "mdi:delete-sweep")
    aktion = entaschen["elements"][0]["tap_action"]
    assert aktion["target"] == {"entity_id": "button.eta_heizung_kessel_entaschen"}
    assert "confirmation" in aktion, "fragt vorher nach"
    uhr = next(k for k in knoepfe if k["elements"][0]["icon"] == "mdi:delete-clock")
    assert uhr["elements"][0]["tap_action"] == {
        "action": "more-info",
        "entity": "datetime.eta_heizung_aschebox_leeren_um",
    }
    for knopf in (entaschen, uhr):
        assert {
            "condition": "state",
            "entity": "sensor.eta_heizung_aschebox_plan",
            "state_not": "unknown",
        } in knopf["conditions"], "Knopf und Uhrzeit melden sonst unknown"


async def test_ohne_messwert_zeigt_die_karte_einen_strich(hass, entry):
    """Die Lambdasonde ist bei "Bereit" aus - dann "-" statt "Unbekannt"."""
    from eta_webservices.api import ETAValue

    coordinator, by_name = await setup_integration(hass, entry)
    sensor = by_name["Restsauerstoff"]
    assert "anzeige" not in sensor.extra_state_attributes
    coordinator.data["restsauerstoff"] = ETAValue(None, "---", "%", False, 1)
    assert sensor.native_value is None
    assert sensor.extra_state_attributes["anzeige"] == "-"


def test_kessel_zeilen_mit_strich():
    gitter = karte.grid(spalten=4, schrift=100, kurz=False)
    kessel = next(
        k for k in gitter["cards"]
        if k["conditions"][0]["entity"] == "sensor.eta_heizung_komponente_kessel"
    )
    zeilen = [
        e for e in kessel["card"]["elements"]
        if e.get("elements") and e["elements"][0].get("entity") == "sensor.eta_heizung_restsauerstoff"
    ]
    normal, strich = zeilen
    assert "attribute" not in normal["elements"][0]
    assert strich["elements"][0]["attribute"] == "anzeige"
    assert strich["elements"][0]["prefix"] == normal["elements"][0]["prefix"]
    assert strich["conditions"] == [
        {
            "condition": "state",
            "entity": "sensor.eta_heizung_restsauerstoff",
            "attribute": "anzeige",
            "state_not": "unknown",
        }
    ]
