"""Der Schalter "Kessel sperren".

Er lässt den Kessel pausieren, solange ein Gerät heizt, das die Regelung
nicht kennt - etwa ein Kaminofen: Er schaltet den Kessel über dessen
Ein/Aus-Taste aus und später wieder ein. An der Heizung ist dafür nichts
einzurichten, und im Notfall schaltet man den Kessel am Display wieder ein.

Der Schalter darf nie einen Kessel einschalten, den jemand von Hand
ausgeschaltet hat - etwa über den Sommer. Deshalb merkt er sich in den
Optionen der Einrichtung, was er selbst getan hat, und schaltet nur dann
wieder ein, wenn er auch ausgeschaltet hat.
"""

from __future__ import annotations

import pytest
from homeassistant.exceptions import HomeAssistantError

from eta_heating_ws import entitaet_vorgesehen
from eta_heating_ws import switch as switch_platform
from eta_heating_ws.config_flow import _options_schema
from eta_heating_ws.const import (
    CONF_KESSEL_GESPERRT,
    CONF_KESSEL_SPERRE,
    KESSEL_GESPERRT_AUSGESCHALTET,
    KESSEL_GESPERRT_WAR_AUS,
    kessel_sperre_gewaehlt,
)

from .test_config_flow import optionen, options_schritt
from .test_sensors import setup_integration

TASTE = "/264/10891/0/0/12080"
EIN, AUS = "950", "949"


async def schalter_von(hass, entry, angekreuzt=True, schreibzugriff=True, kessel_ein=True):
    """Richtet ein und gibt Koordinator, "Kessel sperren" und den Schalter "Kessel" zurück."""
    entry.data[CONF_KESSEL_SPERRE] = angekreuzt
    entry.data["enable_switches"] = schreibzugriff
    if not kessel_ein:
        hass.session.geschrieben[TASTE] = AUS
    coordinator, _ = await setup_integration(hass, entry)
    gesammelt: list = []
    await switch_platform.async_setup_entry(hass, entry, gesammelt.extend)
    for schalter in gesammelt:
        schalter.async_write_ha_state = lambda: None
    sperre = next((s for s in gesammelt if s.translation_key == "kessel_sperre"), None)
    kessel = next((s for s in gesammelt if s.translation_key == "kessel_schalter"), None)
    hass.session.gesetzte_werte.clear()
    return coordinator, sperre, kessel


async def test_schalter_entsteht_angekreuzt_und_mit_schreibzugriff(hass, entry):
    coordinator, sperre, kessel = await schalter_von(hass, entry)

    assert isinstance(sperre, switch_platform.ETAKesselSperre)
    assert sperre.entity_id == "switch.eta_heizung_kessel_sperren"
    assert sperre.unique_id == f"eta_switch_{entry.entry_id}_kessel_sperre"
    assert sperre.is_on is False
    assert kessel.is_on is True
    assert "kessel_sperre" not in coordinator.switch_defs, "keine eigene Taste der Anlage"


@pytest.mark.parametrize(
    "angekreuzt, schreibzugriff", [(False, True), (True, False), (False, False)]
)
async def test_kein_schalter_ohne_haekchen_oder_ohne_schreibzugriff(
    hass, entry, angekreuzt, schreibzugriff
):
    _, sperre, _ = await schalter_von(hass, entry, angekreuzt, schreibzugriff)
    assert sperre is None


def test_schalter_bleibt_nur_mit_haekchen_schreibzugriff_und_kessel():
    """Danach räumt die Integration auf, wenn das Häkchen wieder abgewählt wird."""
    def vorgesehen(schreibzugriff, angekreuzt, komponenten=("kessel",)):
        return entitaet_vorgesehen(
            "kessel_sperre", list(komponenten), schreibzugriff, True, kessel_sperre=angekreuzt
        )

    assert vorgesehen(True, True) is True
    assert vorgesehen(True, False) is False
    assert vorgesehen(False, True) is False
    assert vorgesehen(True, True, komponenten=("puffer",)) is False
    assert entitaet_vorgesehen("kessel_schalter", ["kessel"], True, True) is True, (
        "der Ein/Aus-Schalter braucht das Häkchen nicht"
    )


def test_formular_legt_den_schalter_ab_werk_nicht_an():
    feld = next(k for k in _options_schema({}).schema if k == CONF_KESSEL_SPERRE)
    assert feld.default() is False


@pytest.mark.parametrize("gespeichert", [None, False, "", "taste", "verriegelung", 1])
def test_nur_ein_echtes_haekchen_legt_den_schalter_an(gespeichert):
    """Ein Rest aus einer Zwischenfassung - dort war es eine Auswahl - zählt nicht."""
    assert kessel_sperre_gewaehlt({CONF_KESSEL_SPERRE: gespeichert}) is False
    assert kessel_sperre_gewaehlt({}) is False
    assert kessel_sperre_gewaehlt({CONF_KESSEL_SPERRE: True}) is True
    feld = next(
        k for k in _options_schema({CONF_KESSEL_SPERRE: gespeichert}).schema if k == CONF_KESSEL_SPERRE
    )
    assert feld.default() is False


async def test_kein_schalter_wenn_die_taste_nicht_schaltbar_ist(hass, entry):
    hass.session.schreibbar = False
    _, sperre, kessel = await schalter_von(hass, entry)
    assert kessel is None and sperre is None


async def test_sperren_schaltet_den_kessel_aus_und_merkt_es_sich(hass, entry):
    coordinator, sperre, kessel = await schalter_von(hass, entry)

    await sperre.async_turn_on()

    assert hass.session.gesetzte_werte == [(TASTE, AUS)]
    assert sperre.is_on is True
    assert entry.options[CONF_KESSEL_GESPERRT] == KESSEL_GESPERRT_AUSGESCHALTET
    assert sperre.extra_state_attributes == {"schaltet_kessel_wieder_ein": True}
    kessel._handle_coordinator_update()
    assert kessel.is_on is False, "der Schalter Kessel zeigt, was die Anlage meldet"


async def test_freigeben_schaltet_den_kessel_wieder_ein(hass, entry):
    _, sperre, _ = await schalter_von(hass, entry)
    await sperre.async_turn_on()
    hass.session.gesetzte_werte.clear()

    await sperre.async_turn_off()

    assert hass.session.gesetzte_werte == [(TASTE, EIN)]
    assert sperre.is_on is False
    assert CONF_KESSEL_GESPERRT not in entry.options


async def test_war_der_kessel_schon_aus_bleibt_er_es(hass, entry):
    """Wer den Kessel über den Sommer ausschaltet, findet ihn nach dem Ofenabend nicht eingeschaltet vor."""
    _, sperre, _ = await schalter_von(hass, entry, kessel_ein=False)

    await sperre.async_turn_on()

    assert hass.session.gesetzte_werte == []
    assert sperre.is_on is True
    assert entry.options[CONF_KESSEL_GESPERRT] == KESSEL_GESPERRT_WAR_AUS
    assert sperre.extra_state_attributes == {"schaltet_kessel_wieder_ein": False}

    await sperre.async_turn_off()

    assert hass.session.gesetzte_werte == [], "freigegeben, aber nicht eingeschaltet"
    assert sperre.is_on is False
    assert CONF_KESSEL_GESPERRT not in entry.options


@pytest.mark.parametrize("kessel_ein", [True, False])
async def test_freigeben_ohne_sperre_schreibt_nichts(hass, entry, kessel_ein):
    """Aus heißt nicht "Kessel ein": Ohne eigene Sperre fasst der Schalter die Taste nicht an."""
    _, sperre, _ = await schalter_von(hass, entry, kessel_ein=kessel_ein)

    await sperre.async_turn_off()

    assert hass.session.gesetzte_werte == []
    assert sperre.is_on is False


async def test_zweimal_sperren_schreibt_einmal(hass, entry):
    _, sperre, _ = await schalter_von(hass, entry)

    await sperre.async_turn_on()
    await sperre.async_turn_on()

    assert hass.session.gesetzte_werte == [(TASTE, AUS)]
    assert entry.options[CONF_KESSEL_GESPERRT] == KESSEL_GESPERRT_AUSGESCHALTET


async def test_sperre_uebersteht_den_neustart(hass, entry):
    """Was der Schalter sich gemerkt hat, steht in den Optionen der Einrichtung."""
    entry.options = {CONF_KESSEL_GESPERRT: KESSEL_GESPERRT_AUSGESCHALTET}
    coordinator, sperre, _ = await schalter_von(hass, entry, kessel_ein=False)

    assert sperre.is_on is True
    await coordinator.async_refresh()
    assert sperre.is_on is True

    await sperre.async_turn_off()

    assert hass.session.gesetzte_werte == [(TASTE, EIN)]
    assert sperre.is_on is False


async def test_schaltet_jemand_den_kessel_ein_ist_die_sperre_aufgehoben(hass, entry):
    """An der Heizung oder über den Schalter Kessel - geschrieben wird dann nichts."""
    coordinator, sperre, _ = await schalter_von(hass, entry)
    await sperre.async_turn_on()
    assert sperre.is_on is True and coordinator.kesselsperre._erwartet is None, (
        "die Anlage hat das Ausschalten bestätigt"
    )
    hass.session.gesetzte_werte.clear()

    hass.session.geschrieben[TASTE] = EIN
    await coordinator.async_refresh()

    assert sperre.is_on is False
    assert CONF_KESSEL_GESPERRT not in entry.options
    assert hass.session.gesetzte_werte == []

    await sperre.async_turn_off()
    assert hass.session.gesetzte_werte == []


async def test_traege_anlage_hebt_die_sperre_nicht_gleich_auf(hass, entry, monkeypatch):
    """Nach dem Ausschalten meldet die Anlage noch eine Weile "Ein" - das zählt nicht als Einschalten."""
    from eta_heating_ws.switch import VERWERFEN_NACH

    monkeypatch.setattr(switch_platform, "SPERRE_VERWERFEN_FRUEHESTENS", 0)
    coordinator, sperre, _ = await schalter_von(hass, entry)
    hass.session.traege = True
    await sperre.async_turn_on()
    assert sperre.is_on is True, "die erste Abfrage nach dem Schalten meldet noch Ein"

    for _ in range(VERWERFEN_NACH - 2):
        await coordinator.async_refresh()
        assert sperre.is_on is True

    hass.session.traege = False
    await coordinator.async_refresh()
    assert sperre.is_on is True and coordinator.kesselsperre._erwartet is None


async def test_fuehrt_die_anlage_das_ausschalten_nie_aus_gilt_keine_sperre(hass, entry, monkeypatch):
    from eta_heating_ws.switch import VERWERFEN_NACH

    monkeypatch.setattr(switch_platform, "SPERRE_VERWERFEN_FRUEHESTENS", 0)
    coordinator, sperre, _ = await schalter_von(hass, entry)
    hass.session.traege = True
    await sperre.async_turn_on()

    for _ in range(VERWERFEN_NACH):
        await coordinator.async_refresh()

    assert sperre.is_on is False
    assert CONF_KESSEL_GESPERRT not in entry.options


async def test_gleich_nach_dem_freigeben_wieder_sperren_schaltet_aus(hass, entry):
    """Die Anlage meldet noch "Aus" - trotzdem gilt der eigene Einschaltbefehl."""
    _, sperre, _ = await schalter_von(hass, entry)
    await sperre.async_turn_on()
    hass.session.traege = True
    hass.session.geschrieben[TASTE] = AUS
    await sperre.async_turn_off()
    hass.session.gesetzte_werte.clear()

    await sperre.async_turn_on()

    assert hass.session.gesetzte_werte == [(TASTE, AUS)]
    assert entry.options[CONF_KESSEL_GESPERRT] == KESSEL_GESPERRT_AUSGESCHALTET


async def test_ablehnung_der_anlage_wird_gemeldet_und_nichts_gemerkt(hass, entry):
    _, sperre, _ = await schalter_von(hass, entry)
    hass.session.fail_uris.add("0/0/12080")

    with pytest.raises(HomeAssistantError):
        await sperre.async_turn_on()

    assert sperre.is_on is False
    assert CONF_KESSEL_GESPERRT not in entry.options


async def test_scheitert_das_einschalten_bleibt_die_sperre_bestehen(hass, entry):
    """Sonst vergäße der Schalter, dass der Kessel noch seinetwegen aus ist."""
    _, sperre, _ = await schalter_von(hass, entry)
    await sperre.async_turn_on()
    hass.session.fail_uris.add("0/0/12080")

    with pytest.raises(HomeAssistantError):
        await sperre.async_turn_off()

    assert sperre.is_on is True
    assert entry.options[CONF_KESSEL_GESPERRT] == KESSEL_GESPERRT_AUSGESCHALTET


async def test_ohne_zustand_des_kessels_wird_nicht_gesperrt(hass, entry):
    coordinator, sperre, _ = await schalter_von(hass, entry)
    coordinator.data.pop("kessel_schalter")

    with pytest.raises(HomeAssistantError):
        await sperre.async_turn_on()

    assert hass.session.gesetzte_werte == []
    assert sperre.is_on is False


async def test_geschrieben_wird_nur_die_ein_aus_taste_des_kessels(hass, entry):
    _, sperre, _ = await schalter_von(hass, entry)

    await sperre.async_turn_on()
    await sperre.async_turn_off()

    assert {uri for uri, _ in hass.session.gesetzte_werte} == {TASTE}


async def test_ankreuzen_braucht_keinen_eigenen_warnschritt(monkeypatch):
    """Die Ein/Aus-Taste deckt schon die Warnung zum Schreibzugriff ab."""
    bisher = {**optionen(), "enable_switches": True, CONF_KESSEL_SPERRE: False}
    _, ergebnis = await options_schritt(
        monkeypatch, bisher, {**optionen(), "enable_switches": True, CONF_KESSEL_SPERRE: True}
    )

    assert ergebnis["step_id"] == "fub_names"


async def speichern(monkeypatch, bisher, eingabe):
    """Geht Konfigurieren bis zum Speichern durch und gibt die neuen Optionen zurück."""
    flow, ergebnis = await options_schritt(monkeypatch, bisher, eingabe)
    for _ in range(6):
        if ergebnis["type"] == "create_entry":
            break
        schema = ergebnis.get("data_schema")
        vorgaben = {str(feld): feld.default() for feld in schema.schema} if schema else {}
        ergebnis = await getattr(flow, f"async_step_{ergebnis['step_id']}")(vorgaben)
    assert ergebnis["type"] == "create_entry"
    return ergebnis["data"]


async def test_konfigurieren_behaelt_die_sperre(monkeypatch):
    """Die Optionen werden beim Speichern ersetzt - der Kessel bliebe sonst für immer aus."""
    gewaehlt = {**optionen(), "enable_switches": True, CONF_KESSEL_SPERRE: True}
    bisher = {**gewaehlt, CONF_KESSEL_GESPERRT: KESSEL_GESPERRT_AUSGESCHALTET}

    daten = await speichern(monkeypatch, bisher, gewaehlt)

    assert daten[CONF_KESSEL_GESPERRT] == KESSEL_GESPERRT_AUSGESCHALTET


@pytest.mark.parametrize(
    "neu",
    [
        {"enable_switches": True, CONF_KESSEL_SPERRE: False},
        {"enable_switches": False, CONF_KESSEL_SPERRE: True},
    ],
    ids=["abgewählt", "ohne Schreibzugriff"],
)
async def test_konfigurieren_behaelt_das_gemerkte_auch_ohne_den_schalter(monkeypatch, neu):
    """Das Formular weiß nicht, ob es danach noch eine Sperre gibt - etwa durch den Fremderzeuger.

    Aufgeräumt wird beim Einrichten, siehe die folgenden Prüfungen.
    """
    bisher = {
        **optionen(),
        "enable_switches": True,
        CONF_KESSEL_SPERRE: True,
        CONF_KESSEL_GESPERRT: KESSEL_GESPERRT_AUSGESCHALTET,
    }

    daten = await speichern(monkeypatch, bisher, {**optionen(), **neu})

    assert daten[CONF_KESSEL_GESPERRT] == KESSEL_GESPERRT_AUSGESCHALTET


async def test_abgewaehlt_waehrend_gesperrt_geht_der_kessel_wieder_an(hass, entry, sperre_meldungen):
    """Sonst bliebe der Kessel aus, und kein Schalter zeigte mehr, warum."""
    entry.options = {CONF_KESSEL_GESPERRT: KESSEL_GESPERRT_AUSGESCHALTET}
    hass.session.geschrieben[TASTE] = AUS
    entry.data[CONF_KESSEL_SPERRE] = False
    entry.data["enable_switches"] = True

    coordinator, _ = await setup_integration(hass, entry)

    assert coordinator.kesselsperre is None
    assert (TASTE, EIN) in hass.session.gesetzte_werte
    assert CONF_KESSEL_GESPERRT not in entry.options
    assert "wieder eingeschaltet" in sperre_meldungen[-1]


async def test_abgewaehlt_und_schon_wieder_ein_schreibt_nichts(hass, entry, sperre_meldungen):
    entry.options = {CONF_KESSEL_GESPERRT: KESSEL_GESPERRT_AUSGESCHALTET}
    entry.data[CONF_KESSEL_SPERRE] = False
    entry.data["enable_switches"] = True

    await setup_integration(hass, entry)

    assert hass.session.gesetzte_werte == []
    assert CONF_KESSEL_GESPERRT not in entry.options
    assert sperre_meldungen == []


async def test_ohne_schreibzugriff_waehrend_gesperrt_wird_gemeldet(hass, entry, sperre_meldungen):
    entry.options = {CONF_KESSEL_GESPERRT: KESSEL_GESPERRT_AUSGESCHALTET}
    hass.session.geschrieben[TASTE] = AUS
    entry.data[CONF_KESSEL_SPERRE] = True
    entry.data["enable_switches"] = False

    await setup_integration(hass, entry)

    assert hass.session.gesetzte_werte == []
    assert CONF_KESSEL_GESPERRT not in entry.options
    assert "an der Heizung wieder einschalten" in sperre_meldungen[-1]

    sperre_meldungen.clear()
    await setup_integration(hass, entry)
    assert sperre_meldungen == [], "nur einmal"


async def test_war_der_kessel_schon_aus_verfaellt_das_gemerkte_still(hass, entry, sperre_meldungen):
    """Ein alter Merker dürfte später keinen von Hand ausgeschalteten Kessel einschalten."""
    entry.options = {CONF_KESSEL_GESPERRT: KESSEL_GESPERRT_WAR_AUS}
    hass.session.geschrieben[TASTE] = AUS
    entry.data[CONF_KESSEL_SPERRE] = False
    entry.data["enable_switches"] = True

    await setup_integration(hass, entry)

    assert hass.session.gesetzte_werte == []
    assert CONF_KESSEL_GESPERRT not in entry.options
    assert sperre_meldungen == []


async def test_bestaetigt_die_anlage_die_taste_nicht_bleibt_das_gemerkte(
    hass, entry, sperre_meldungen, monkeypatch
):
    """Neustart, und die Anlage beschreibt die Ein/Aus-Taste nicht: Der Kessel bliebe unbemerkt aus."""
    from eta_heating_ws.api import ETAApiClient

    entry.options = {CONF_KESSEL_GESPERRT: KESSEL_GESPERRT_AUSGESCHALTET}
    hass.session.geschrieben[TASTE] = AUS
    entry.data[CONF_KESSEL_SPERRE] = True
    entry.data["enable_switches"] = True

    async def keine_antwort(self, uri):
        return None

    echt = ETAApiClient.async_get_varinfo
    monkeypatch.setattr(ETAApiClient, "async_get_varinfo", keine_antwort)
    coordinator, _ = await setup_integration(hass, entry)

    assert coordinator.kesselsperre is None
    assert entry.options[CONF_KESSEL_GESPERRT] == KESSEL_GESPERRT_AUSGESCHALTET
    assert hass.session.gesetzte_werte == []
    assert "nicht bestätigt" in sperre_meldungen[-1]

    monkeypatch.setattr(ETAApiClient, "async_get_varinfo", echt)
    coordinator, _ = await setup_integration(hass, entry)
    assert coordinator.kesselsperre.gesperrt is True, "beim nächsten Start gilt die Sperre wieder"
    await coordinator.kesselsperre.async_freigeben()
    assert hass.session.gesetzte_werte == [(TASTE, EIN)]


async def test_der_schalter_kessel_sagt_der_sperre_was_er_geschaltet_hat(hass, entry):
    """Von Hand aus, und gleich darauf gesperrt: Die Anlage meldet noch "Ein", die Sperre weiß es besser."""
    coordinator, sperre, kessel = await schalter_von(hass, entry)
    hass.session.traege = True
    await kessel.async_turn_off()
    hass.session.gesetzte_werte.clear()

    await sperre.async_turn_on()

    assert hass.session.gesetzte_werte == [], "der Kessel ist schon aus"
    assert entry.options[CONF_KESSEL_GESPERRT] == KESSEL_GESPERRT_WAR_AUS
    hass.session.traege = False
    await coordinator.async_refresh()
    await sperre.async_turn_off()
    assert hass.session.gesetzte_werte == [], "von Hand ausgeschaltet bleibt aus"


async def test_die_sperre_gibt_einer_traegen_anlage_laenger_zeit_als_der_schalter(
    hass, entry, monkeypatch
):
    """Gäbe sie zu früh auf, ginge der Kessel danach aus, und nichts schaltete ihn wieder ein."""
    from eta_heating_ws.switch import VERWERFEN_NACH

    monkeypatch.setattr(switch_platform, "VERWERFEN_FRUEHESTENS", 0)
    coordinator, sperre, _ = await schalter_von(hass, entry)
    hass.session.traege = True
    await sperre.async_turn_on()

    for _ in range(VERWERFEN_NACH + 2):
        await coordinator.async_refresh()

    assert sperre.is_on is True
    hass.session.traege = False
    await coordinator.async_refresh()
    hass.session.gesetzte_werte.clear()
    await sperre.async_turn_off()
    assert hass.session.gesetzte_werte == [(TASTE, EIN)]


async def test_sperren_und_freigeben_zugleich_der_letzte_befehl_gilt(hass, entry):
    import asyncio

    coordinator, _, _ = await schalter_von(hass, entry)
    sperre = coordinator.kesselsperre

    await asyncio.gather(sperre.async_sperren(), sperre.async_freigeben())
    assert sperre.gesperrt is False

    await asyncio.gather(sperre.async_freigeben(), sperre.async_sperren())
    assert sperre.gesperrt is True


async def gesperrt_mit_plan(hass, entry):
    """Kessel gesperrt, dazu ein Aschebox-Plan, den der Test von Hand weiterführt."""
    from .test_aschebox import aufbauen

    entry.data[CONF_KESSEL_SPERRE] = True
    entry.data["enable_switches"] = True
    coordinator, plan = await aufbauen(hass, entry)
    await coordinator.kesselsperre.async_sperren()
    await coordinator.async_refresh()
    return coordinator, plan


async def bis_zum_leeren(hass, coordinator, plan, uhr, aschebox_ohne_hass):
    """Führt den Plan bis zu dem Schritt, in dem die Aschebox geleert wird."""
    from datetime import timedelta

    from .test_aschebox import abfrage, ausfuehren

    await plan.planen(uhr.jetzt + timedelta(minutes=10))
    await ausfuehren(hass, aschebox_ohne_hass)
    uhr.weiter(minutes=5)
    await abfrage(coordinator, plan, "Ausgeschaltet")
    assert plan.phase == "entaschen"
    uhr.weiter(minutes=2)
    await abfrage(coordinator, plan, "Entaschen")
    uhr.weiter(minutes=8)
    await abfrage(coordinator, plan, "Ausgeschaltet")
    assert plan.phase == "leeren"


async def test_endet_der_aschebox_plan_bleibt_der_gesperrte_kessel_aus(
    hass, entry, uhr, aschebox_ohne_hass
):
    """Der Plan schaltete sonst ein, und die Sperre gälte als von Hand aufgehoben."""
    from .test_aschebox import abfrage

    coordinator, plan = await gesperrt_mit_plan(hass, entry)
    await bis_zum_leeren(hass, coordinator, plan, uhr, aschebox_ohne_hass)
    hass.session.gesetzte_werte.clear()

    await abfrage(coordinator, plan, "Aschebox fehlt")
    await abfrage(coordinator, plan, "Ausgeschaltet")

    assert plan.phase == "aus"
    assert (TASTE, EIN) not in hass.session.gesetzte_werte
    assert coordinator.kesselsperre.gesperrt is True
    assert "bleibt aus, weil er gesperrt ist" in aschebox_ohne_hass.meldungen[-1]

    await coordinator.kesselsperre.async_freigeben()
    assert hass.session.gesetzte_werte[-1] == (TASTE, EIN)


async def test_freigeben_mitten_im_aschebox_plan_schaltet_nicht_ein(
    hass, entry, uhr, aschebox_ohne_hass
):
    """Der Plan hält den Kessel aus und schaltet ihn an seinem Ende selbst ein."""
    from .test_aschebox import abfrage

    coordinator, plan = await gesperrt_mit_plan(hass, entry)
    await bis_zum_leeren(hass, coordinator, plan, uhr, aschebox_ohne_hass)
    hass.session.gesetzte_werte.clear()

    await coordinator.kesselsperre.async_freigeben()

    assert hass.session.gesetzte_werte == []
    assert coordinator.kesselsperre.gesperrt is False
    await abfrage(coordinator, plan, "Aschebox fehlt")
    await abfrage(coordinator, plan, "Ausgeschaltet")
    assert plan.phase == "aus"
    assert hass.session.gesetzte_werte[-1] == (TASTE, EIN)
    assert "wieder eingeschaltet" in aschebox_ohne_hass.meldungen[-1]


async def test_im_aschebox_plan_gesperrt_schaltet_das_freigeben_danach_ein(
    hass, entry, uhr, aschebox_ohne_hass
):
    """Beim Sperren war der Kessel durch den Plan schon aus - ohne Sperre hätte der Plan ihn eingeschaltet."""
    from .test_aschebox import abfrage, aufbauen

    entry.data[CONF_KESSEL_SPERRE] = True
    entry.data["enable_switches"] = True
    coordinator, plan = await aufbauen(hass, entry)
    await bis_zum_leeren(hass, coordinator, plan, uhr, aschebox_ohne_hass)
    await coordinator.kesselsperre.async_sperren()
    assert entry.options[CONF_KESSEL_GESPERRT] == KESSEL_GESPERRT_WAR_AUS

    await abfrage(coordinator, plan, "Aschebox fehlt")
    await abfrage(coordinator, plan, "Ausgeschaltet")

    assert plan.phase == "aus"
    assert entry.options[CONF_KESSEL_GESPERRT] == KESSEL_GESPERRT_AUSGESCHALTET
    hass.session.gesetzte_werte.clear()
    await coordinator.kesselsperre.async_freigeben()
    assert hass.session.gesetzte_werte == [(TASTE, EIN)]


async def test_aschebox_plan_abbrechen_laesst_den_gesperrten_kessel_aus(
    hass, entry, uhr, aschebox_ohne_hass
):
    coordinator, plan = await gesperrt_mit_plan(hass, entry)
    await bis_zum_leeren(hass, coordinator, plan, uhr, aschebox_ohne_hass)
    hass.session.gesetzte_werte.clear()

    await plan.abbrechen()

    assert plan.phase == "aus"
    assert hass.session.gesetzte_werte == []
    assert coordinator.kesselsperre.gesperrt is True
    assert "bleibt aus, weil er gesperrt ist" in aschebox_ohne_hass.meldungen[-1]


async def test_abgewaehlt_mitten_im_aschebox_plan_schaltet_nicht_ein(
    hass, entry, uhr, aschebox_ohne_hass, sperre_meldungen
):
    """Der Plan läuft nach dem Neuladen weiter und schaltet den Kessel an seinem Ende ein."""
    from .conftest import FakeConfigEntry

    coordinator, plan = await gesperrt_mit_plan(hass, entry)
    await bis_zum_leeren(hass, coordinator, plan, uhr, aschebox_ohne_hass)
    hass.session.gesetzte_werte.clear()

    ohne = FakeConfigEntry({**entry.data, CONF_KESSEL_SPERRE: False})
    ohne.options = dict(entry.options)
    coordinator, _ = await setup_integration(hass, ohne)

    assert coordinator.aschebox.phase == "leeren"
    assert hass.session.gesetzte_werte == []
    assert CONF_KESSEL_GESPERRT not in ohne.options
    assert sperre_meldungen == []


async def test_freigeben_schreibt_nichts_wenn_der_kessel_schon_ein_ist(hass, entry):
    """Nach einem Neustart steht noch "gesperrt" in den Optionen, der Kessel läuft aber längst wieder."""
    entry.options = {CONF_KESSEL_GESPERRT: KESSEL_GESPERRT_AUSGESCHALTET}
    entry.data[CONF_KESSEL_SPERRE] = True
    entry.data["enable_switches"] = True
    coordinator, _ = await setup_integration(hass, entry)
    hass.session.gesetzte_werte.clear()

    await coordinator.kesselsperre.async_freigeben()

    assert hass.session.gesetzte_werte == []
    assert CONF_KESSEL_GESPERRT not in entry.options
