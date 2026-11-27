"""Tests für Entaschen-Knopf und Aschebox-Plan."""

from __future__ import annotations

from datetime import timedelta

import pytest
from homeassistant.exceptions import HomeAssistantError

from eta_heating_ws import aschebox, karte
from eta_heating_ws import button as button_platform
from eta_heating_ws import datetime as datetime_platform
from eta_heating_ws import sensor as sensor_platform

from .conftest import ohne_objekt
from .test_sensors import setup_integration

KESSEL = "/264/10891/0/0/12080"
TASTE = "/264/10891/0/0/12112"


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


async def test_ereignis_unter_neuem_und_altem_namen(hass, entry, uhr, aschebox_ohne_hass):
    """Automatisierungen aus 0.25 hören noch auf eta_webservices_aschebox."""
    _, plan = await aufbauen(hass, entry)
    await plan.planen(uhr.jetzt + timedelta(hours=2))

    neu = [daten for art, daten in hass.ereignisse if art == "eta_heating_ws_aschebox"]
    alt = [daten for art, daten in hass.ereignisse if art == "eta_webservices_aschebox"]
    assert neu, "kein Ereignis"
    assert neu == alt
    assert neu[-1]["phase"] == "geplant"


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


VERBRAUCH_SEIT_LEEREN = "/264/10891/0/0/12013"
LEEREN_NACH = "/264/10891/0/0/12120"


async def test_ohne_aschebox_an_der_anlage_gibt_es_den_knopf_aber_keinen_plan(hass, entry, menu_xml):
    """Die Entaschentaste allein belegt keine Aschebox - ein Stückholzkessel hat die Taste auch."""
    hass.session.menu = ohne_objekt(menu_xml, VERBRAUCH_SEIT_LEEREN, LEEREN_NACH)
    coordinator, _ = await setup_integration(hass, entry)

    assert coordinator.entaschen_def is not None
    assert "kessel_schalter" in coordinator.switch_defs
    assert coordinator.aschebox is None

    gesammelt = []
    await datetime_platform.async_setup_entry(hass, entry, gesammelt.extend)
    assert gesammelt == [], "auch kein Feld für den Zeitpunkt"


@pytest.mark.parametrize("fehlt", [VERBRAUCH_SEIT_LEEREN, LEEREN_NACH])
async def test_einer_der_beiden_aschebox_werte_genuegt(hass, entry, menu_xml, fehlt):
    hass.session.menu = ohne_objekt(menu_xml, fehlt)
    coordinator, _ = await setup_integration(hass, entry)

    assert coordinator.aschebox is not None


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
    from eta_heating_ws import entitaet_vorgesehen

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
    from eta_heating_ws.api import ETAValue

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


async def test_abbrechen_ohne_antwort_laesst_den_plan_bestehen(hass, entry, uhr, aschebox_ohne_hass):
    """Sonst wäre der Kessel aus, und kein Plan schaltete ihn mehr ein."""
    coordinator, plan = await aufbauen(hass, entry)
    await plan.planen(uhr.jetzt + timedelta(minutes=10))
    await ausfuehren(hass, aschebox_ohne_hass)
    assert plan.phase == "glutabbrand"

    hass.session.schreiben_erlaubt = False
    with pytest.raises(HomeAssistantError):
        await plan.abbrechen()
    assert plan.phase == "glutabbrand"

    hass.session.schreiben_erlaubt = True
    await plan.abbrechen()
    assert plan.phase == "aus"
    assert hass.session.gesetzte_werte[-1] == (KESSEL, "950")


async def plan_mitten_im_lauf(hass, entry, uhr, aschebox_ohne_hass) -> None:
    coordinator, plan = await aufbauen(hass, entry)
    await plan.planen(uhr.jetzt + timedelta(minutes=10))
    await ausfuehren(hass, aschebox_ohne_hass)
    assert plan.phase == "glutabbrand"
    aschebox_ohne_hass.meldungen.clear()


async def test_plan_ohne_bestaetigte_tasten_wird_gemeldet(hass, entry, uhr, aschebox_ohne_hass, monkeypatch):
    """Neustart mitten im Plan, und die Anlage bestätigt die Tasten nicht: Der Kessel bliebe unbemerkt aus."""
    from eta_heating_ws.api import ETAApiClient

    from .conftest import FakeConfigEntry

    await plan_mitten_im_lauf(hass, entry, uhr, aschebox_ohne_hass)

    async def keine_antwort(self, uri):
        return None

    echt = ETAApiClient.async_get_varinfo
    monkeypatch.setattr(ETAApiClient, "async_get_varinfo", keine_antwort)
    uhr.weiter(minutes=5)
    coordinator, _ = await setup_integration(hass, FakeConfigEntry(dict(entry.data)))
    assert coordinator.aschebox is None
    assert "Kessel selbst wieder einschalten" in aschebox_ohne_hass.meldungen[-1]

    monkeypatch.setattr(ETAApiClient, "async_get_varinfo", echt)
    coordinator, _ = await setup_integration(hass, FakeConfigEntry(dict(entry.data)))
    assert coordinator.aschebox.phase == "glutabbrand", "beim nächsten Start läuft er weiter"


async def test_plan_ohne_schreibzugriff_wird_gemeldet_und_verworfen(hass, entry, uhr, aschebox_ohne_hass):
    from .conftest import FakeConfigEntry

    await plan_mitten_im_lauf(hass, entry, uhr, aschebox_ohne_hass)

    ohne = FakeConfigEntry({**entry.data, "enable_switches": False})
    await setup_integration(hass, ohne)
    assert "Der Plan ist beendet" in aschebox_ohne_hass.meldungen[-1]

    aschebox_ohne_hass.meldungen.clear()
    await setup_integration(hass, FakeConfigEntry({**entry.data, "enable_switches": False}))
    assert aschebox_ohne_hass.meldungen == [], "nur einmal"
    coordinator, _ = await setup_integration(hass, FakeConfigEntry(dict(entry.data)))
    assert coordinator.aschebox.phase == "aus"


async def test_eine_ausgebliebene_antwort_kostet_keinen_schalter(hass, entry, monkeypatch):
    """Die Beschreibung einer Taste wird einmal nachgefragt."""
    from eta_heating_ws.api import ETAApiClient

    echt = ETAApiClient.async_get_varinfo
    gefragt: dict[str, int] = {}

    async def erst_beim_zweiten_mal(self, uri):
        gefragt[uri] = gefragt.get(uri, 0) + 1
        return None if gefragt[uri] == 1 else await echt(self, uri)

    monkeypatch.setattr(ETAApiClient, "async_get_varinfo", erst_beim_zweiten_mal)
    coordinator, _ = await setup_integration(hass, entry)

    assert "kessel_schalter" in coordinator.switch_defs
    assert coordinator.entaschen_def is not None
    assert coordinator.aschebox is not None


async def bis_zum_entaschen(hass, entry, uhr, aschebox_ohne_hass):
    """Führt den Plan bis kurz nach dem Drücken der Entaschentaste."""
    coordinator, plan = await aufbauen(hass, entry)
    await plan.planen(uhr.jetzt + timedelta(minutes=10))
    await ausfuehren(hass, aschebox_ohne_hass)
    uhr.weiter(minutes=5)
    await abfrage(coordinator, plan, "Bereit")
    assert plan.phase == "entaschen"
    assert hass.session.gesetzte_werte[-1] == (TASTE, "1803")
    hass.session.gesetzte_werte.clear()
    return coordinator, plan


async def ruhige_minute(coordinator, plan, uhr, zustand="Heizen"):
    """Zwei Abfragen im Abstand einer Minute, beide ohne Entaschung - erst dann gilt sie als durch."""
    await abfrage(coordinator, plan, zustand)
    uhr.weiter(minutes=1)
    await abfrage(coordinator, plan, zustand)


async def test_abbrechen_beim_entaschen_stellt_die_taste_erst_nach_der_entaschung_zurueck(
    hass, entry, uhr, aschebox_ohne_hass
):
    """Sonst bliebe die Entaschentaste auf "Ein" stehen - mitten in der Entaschung wird sie aber nicht angefasst."""
    coordinator, plan = await bis_zum_entaschen(hass, entry, uhr, aschebox_ohne_hass)
    uhr.weiter(minutes=2)
    await abfrage(coordinator, plan, "Entaschen")

    await plan.abbrechen()
    assert plan.phase == "aus"
    assert hass.session.gesetzte_werte == [(KESSEL, "950")], "die Taste bleibt vorerst, wie sie ist"

    uhr.weiter(minutes=1)
    await abfrage(coordinator, plan, "Entaschen")
    assert (TASTE, "1802") not in hass.session.gesetzte_werte, "die Entaschung läuft noch"

    uhr.weiter(minutes=3)
    await abfrage(coordinator, plan, "Heizen")
    assert (TASTE, "1802") not in hass.session.gesetzte_werte, "erst eine Minute ohne Entaschung abwarten"
    uhr.weiter(minutes=1)
    await abfrage(coordinator, plan, "Heizen")
    assert hass.session.gesetzte_werte[-1] == (TASTE, "1802")

    hass.session.gesetzte_werte.clear()
    uhr.weiter(minutes=1)
    await abfrage(coordinator, plan, "Heizen")
    assert hass.session.gesetzte_werte == [], "nur einmal"


@pytest.mark.parametrize(
    "zustand",
    ["Entaschen", "Glutabbrand wegen Entaschung", "Entaschung läuft", None],
    ids=["entascht", "Glutabbrand dafür", "unbekannter Text mit Entaschung", "kein Zustand"],
)
async def test_solange_der_kessel_entascht_oder_nichts_meldet_bleibt_die_taste(
    hass, entry, uhr, aschebox_ohne_hass, zustand
):
    """Auch ein Zustand, den die Integration nicht kennt, zählt als Entaschung, wenn er davon spricht."""
    coordinator, plan = await bis_zum_entaschen(hass, entry, uhr, aschebox_ohne_hass)
    uhr.weiter(minutes=2)
    await abfrage(coordinator, plan, "Entaschen")
    await plan.abbrechen()
    hass.session.gesetzte_werte.clear()

    for _ in range(4):
        uhr.weiter(minutes=1)
        if zustand is None:
            hass.session.kessel_zustand = ""
            await coordinator.async_refresh()
            await plan.weiter()
        else:
            await abfrage(coordinator, plan, zustand)

    assert hass.session.gesetzte_werte == []


async def test_meldet_der_kessel_zwischendurch_wieder_entaschung_beginnt_die_ruhige_minute_neu(
    hass, entry, uhr, aschebox_ohne_hass
):
    coordinator, plan = await bis_zum_entaschen(hass, entry, uhr, aschebox_ohne_hass)
    uhr.weiter(minutes=2)
    await abfrage(coordinator, plan, "Entaschen")
    await plan.abbrechen()
    hass.session.gesetzte_werte.clear()

    uhr.weiter(minutes=1)
    await abfrage(coordinator, plan, "Heizen")
    uhr.weiter(minutes=1)
    await abfrage(coordinator, plan, "Entaschen")
    uhr.weiter(minutes=1)
    await abfrage(coordinator, plan, "Heizen")
    assert hass.session.gesetzte_werte == []

    uhr.weiter(minutes=1)
    await abfrage(coordinator, plan, "Heizen")
    assert hass.session.gesetzte_werte == [(TASTE, "1802")]


async def test_abbrechen_gleich_nach_dem_druecken_wartet_wie_der_plan(
    hass, entry, uhr, aschebox_ohne_hass
):
    """Zeigt sich die Entaschung nicht, gilt sie nach 20 Minuten als durch."""
    coordinator, plan = await bis_zum_entaschen(hass, entry, uhr, aschebox_ohne_hass)
    await plan.abbrechen()
    hass.session.gesetzte_werte.clear()

    uhr.weiter(minutes=10)
    await ruhige_minute(coordinator, plan, uhr)
    assert hass.session.gesetzte_werte == []

    uhr.weiter(minutes=11)
    await ruhige_minute(coordinator, plan, uhr)
    assert hass.session.gesetzte_werte == [(TASTE, "1802")]


async def test_von_hand_eingeschaltet_beendet_den_plan_auch_beim_entaschen(
    hass, entry, uhr, aschebox_ohne_hass
):
    """Sonst hieße es später "Aschebox kann jetzt geleert werden", obwohl der Kessel läuft."""
    coordinator, plan = await bis_zum_entaschen(hass, entry, uhr, aschebox_ohne_hass)
    hass.session.geschrieben[KESSEL] = "950"
    uhr.weiter(minutes=2)
    await abfrage(coordinator, plan, "Entaschen")

    assert plan.phase == "aus"
    assert "wieder eingeschaltet" in aschebox_ohne_hass.meldungen[-1]
    assert hass.session.gesetzte_werte == [], "nichts geschaltet"

    uhr.weiter(minutes=3)
    await abfrage(coordinator, plan, "Entaschen")
    await ruhige_minute(coordinator, plan, uhr, "Zünden")
    assert hass.session.gesetzte_werte == [(TASTE, "1802")]


async def test_stellt_die_anlage_die_taste_selbst_zurueck_wird_nichts_geschrieben(
    hass, entry, uhr, aschebox_ohne_hass
):
    coordinator, plan = await bis_zum_entaschen(hass, entry, uhr, aschebox_ohne_hass)
    uhr.weiter(minutes=2)
    await abfrage(coordinator, plan, "Entaschen")
    await plan.abbrechen()
    hass.session.gesetzte_werte.clear()
    hass.session.geschrieben[TASTE] = "1802"

    uhr.weiter(minutes=3)
    await ruhige_minute(coordinator, plan, uhr)

    assert hass.session.gesetzte_werte == []
    hass.session.geschrieben[TASTE] = "1803"
    uhr.weiter(minutes=1)
    await ruhige_minute(coordinator, plan, uhr)
    assert hass.session.gesetzte_werte == [], "erledigt ist erledigt"


async def test_das_zurueckstellen_uebersteht_einen_neustart(hass, entry, uhr, aschebox_ohne_hass):
    coordinator, plan = await bis_zum_entaschen(hass, entry, uhr, aschebox_ohne_hass)
    uhr.weiter(minutes=2)
    await abfrage(coordinator, plan, "Entaschen")
    await plan.abbrechen()

    coordinator, plan = await aufbauen(hass, entry)
    hass.session.gesetzte_werte.clear()
    assert plan.phase == "aus"
    uhr.weiter(minutes=3)
    await ruhige_minute(coordinator, plan, uhr)

    assert hass.session.gesetzte_werte == [(TASTE, "1802")]


async def test_nimmt_die_anlage_das_zurueckstellen_nicht_an_folgt_ein_neuer_versuch(
    hass, entry, uhr, aschebox_ohne_hass
):
    coordinator, plan = await bis_zum_entaschen(hass, entry, uhr, aschebox_ohne_hass)
    uhr.weiter(minutes=2)
    await abfrage(coordinator, plan, "Entaschen")
    await plan.abbrechen()
    hass.session.gesetzte_werte.clear()

    hass.session.schreiben_erlaubt = False
    uhr.weiter(minutes=3)
    await ruhige_minute(coordinator, plan, uhr)
    assert hass.session.gesetzte_werte == []

    hass.session.schreiben_erlaubt = True
    await abfrage(coordinator, plan, "Heizen")
    assert hass.session.gesetzte_werte == [(TASTE, "1802")]


async def test_scheitert_das_zurueckstellen_am_ende_des_schritts_wird_es_nachgeholt(
    hass, entry, uhr, aschebox_ohne_hass
):
    """Am regulären Ende des Entaschens: Nimmt die Anlage die Taste nicht an, bliebe sie sonst auf "Ein"."""
    coordinator, plan = await bis_zum_entaschen(hass, entry, uhr, aschebox_ohne_hass)
    uhr.weiter(minutes=2)
    await abfrage(coordinator, plan, "Entaschen")
    uhr.weiter(minutes=8)
    hass.session.schreiben_erlaubt = False
    await abfrage(coordinator, plan, "Bereit")
    assert plan.phase == "leeren"
    assert (TASTE, "1802") not in hass.session.gesetzte_werte

    hass.session.schreiben_erlaubt = True
    uhr.weiter(minutes=1)
    await ruhige_minute(coordinator, plan, uhr, "Bereit")

    assert plan.phase == "leeren"
    assert hass.session.gesetzte_werte.count((TASTE, "1802")) == 1


async def test_ein_vermerk_ohne_zeit_endet_trotzdem(hass, entry, uhr, aschebox_ohne_hass):
    """Fehlt im Vermerk, wann gedrückt wurde, zählt die Zeit ab der ersten Abfrage."""
    coordinator, plan = await aufbauen(hass, entry)
    plan._daten = {"phase": "aus", "taste": {"entascht": True}}
    hass.session.geschrieben[TASTE] = "1803"
    hass.session.gesetzte_werte.clear()

    await abfrage(coordinator, plan, "Heizen")
    uhr.weiter(minutes=2)
    await ruhige_minute(coordinator, plan, uhr)

    assert hass.session.gesetzte_werte == [(TASTE, "1802")]
    assert "taste" not in plan._daten


async def test_ein_neuer_plan_uebernimmt_die_taste(hass, entry, uhr, aschebox_ohne_hass):
    """Drückt der nächste Plan die Taste selbst, stellt er sie auch selbst zurück."""
    coordinator, plan = await bis_zum_entaschen(hass, entry, uhr, aschebox_ohne_hass)
    await plan.abbrechen()
    await plan.planen(uhr.jetzt + timedelta(minutes=10))
    await ausfuehren(hass, aschebox_ohne_hass)
    assert plan.phase == "glutabbrand"
    hass.session.gesetzte_werte.clear()

    uhr.weiter(minutes=5)
    await abfrage(coordinator, plan, "Bereit")
    assert plan.phase == "entaschen"
    uhr.weiter(minutes=2)
    await abfrage(coordinator, plan, "Entaschen")
    uhr.weiter(minutes=8)
    await abfrage(coordinator, plan, "Bereit")

    assert plan.phase == "leeren"
    assert hass.session.gesetzte_werte.count((TASTE, "1802")) == 1


async def test_der_vermerk_treibt_die_abfragen_auch_ohne_laufenden_plan(
    hass, entry, uhr, aschebox_ohne_hass
):
    """Nach dem Abbrechen läuft kein Schritt mehr - zurückgestellt wird trotzdem bei den nächsten vollen Abfragen."""
    coordinator, plan = await bis_zum_entaschen(hass, entry, uhr, aschebox_ohne_hass)
    await plan.abbrechen()
    hass.session.gesetzte_werte.clear()
    aufgaben = hass.data["aufgaben"]

    uhr.weiter(minutes=21)
    hass.session.kessel_zustand = "Heizen"
    for _ in range(2):
        await coordinator.async_refresh()
        plan._abgefragt()
        assert len(aufgaben) == 1
        while aufgaben:
            await aufgaben.pop(0)
        uhr.weiter(minutes=1)
    assert hass.session.gesetzte_werte == [(TASTE, "1802")]

    plan._abgefragt()
    assert aufgaben == [], "erledigt - der Plan ruht wieder"
