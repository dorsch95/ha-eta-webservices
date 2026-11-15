"""Der Fremderzeuger: eine Wärmequelle, von der die ETA-Regelung nichts weiß.

Etwa ein Kaminofen mit eigener Regelung. Ob er heizt, sagt eine Entität aus
Home Assistant, die der Nutzer beim Einrichten wählt. Solange er heizt,
hält die Integration die gewählten Kessel gesperrt - über dieselbe
Kesselsperre wie der Schalter "Kessel sperren" - und gibt sie danach
wieder frei.

Anders als "fremdwaerme" (Funktionsblock "F.Wärme" der Anlage) hat er
keinen Funktionsblock und keine Messwerte.
"""

from __future__ import annotations

from datetime import timedelta
from types import SimpleNamespace

import pytest

from eta_heating_ws import switch as switch_platform
from eta_heating_ws.config_flow import _fremderzeuger_schema
from eta_heating_ws.const import (
    BILD_AUSWAHLEN,
    COMPONENTS,
    CONF_FREMDERZEUGER_ENTITAET,
    CONF_FREMDERZEUGER_FREIGEBEN_NACH,
    CONF_FREMDERZEUGER_FUEHLER,
    CONF_FREMDERZEUGER_NAME,
    CONF_FREMDERZEUGER_SCHWELLE,
    CONF_FREMDERZEUGER_SPERREN_NACH,
    CONF_FREMDERZEUGER_SPERRT,
    CONF_KESSEL_GESPERRT,
    CONF_KESSEL_SPERRE,
    KESSEL_GESPERRT_AUSGESCHALTET,
    fremderzeuger_sperrt,
)
from eta_heating_ws.uebersicht import anlage
from eta_heating_ws.verbindungen import verbindungen

from .test_config_flow import optionen, options_schritt
from .test_sensors import setup_integration

OFEN = "input_boolean.kaminofen"
TASTE = "/264/10891/0/0/12080"
EIN, AUS = "950", "949"


async def mit_ofen(
    hass, entry, sperrt=("kessel",), schreibzugriff=True, zustand="off", haekchen=False, **mehr
):
    """Richtet Kessel und Fremderzeuger ein und gibt Koordinator und Fremderzeuger zurück."""
    hass.states.zustaende[OFEN] = zustand
    entry.data["components"] = [*entry.data["components"], "fremderzeuger"]
    entry.data["enable_switches"] = schreibzugriff
    entry.data[CONF_KESSEL_SPERRE] = haekchen
    entry.data[CONF_FREMDERZEUGER_ENTITAET] = OFEN
    entry.data[CONF_FREMDERZEUGER_SPERRT] = list(sperrt)
    entry.data.update(mehr)
    coordinator, _ = await setup_integration(hass, entry)
    hass.session.gesetzte_werte.clear()
    return coordinator, coordinator.fremderzeuger


def wechsel(hass, protokoll, neu, alt="unknown"):
    """Die Entität des Ofens wechselt ihren Zustand - wie Home Assistant es meldet."""
    hass.states.zustaende[OFEN] = neu
    [(_, rueckruf)] = protokoll.beobachtet
    rueckruf(
        SimpleNamespace(
            data={
                "old_state": SimpleNamespace(state=alt),
                "new_state": SimpleNamespace(state=neu),
            }
        )
    )


async def zeit_um(protokoll):
    """Lässt den zuletzt bestellten Zeitgeber ablaufen, wenn er nicht abbestellt ist."""
    bestellung = protokoll.zeitgeber[-1]
    if not bestellung.abbestellt:
        await bestellung.rueckruf(None)
    return bestellung


def test_komponente_ohne_funktionsblock():
    assert COMPONENTS["fremderzeuger"]["roles"] == []
    assert COMPONENTS["fremderzeuger"]["discovery_prefixes"] == []
    assert COMPONENTS["fremderzeuger"]["image"] is None, "eine Kachel nur in der Karte ETA Übersicht"
    assert BILD_AUSWAHLEN["fremderzeuger_bild"]["vorgabe"] == "ofen"


@pytest.mark.parametrize(
    "einstellungen, komponenten, erwartet",
    [
        ({CONF_FREMDERZEUGER_ENTITAET: OFEN, CONF_FREMDERZEUGER_SPERRT: ["kessel"]}, ["kessel", "fremderzeuger"], ["kessel"]),
        ({CONF_FREMDERZEUGER_ENTITAET: OFEN, CONF_FREMDERZEUGER_SPERRT: []}, ["kessel", "fremderzeuger"], []),
        ({CONF_FREMDERZEUGER_ENTITAET: OFEN}, ["kessel", "fremderzeuger"], []),
        ({CONF_FREMDERZEUGER_SPERRT: ["kessel"]}, ["kessel", "fremderzeuger"], []),
        ({CONF_FREMDERZEUGER_FUEHLER: "sensor.ofen", CONF_FREMDERZEUGER_SPERRT: ["kessel"]}, ["kessel", "fremderzeuger"], ["kessel"]),
        ({CONF_FREMDERZEUGER_ENTITAET: OFEN, CONF_FREMDERZEUGER_SPERRT: ["kessel"]}, ["kessel"], []),
        ({CONF_FREMDERZEUGER_ENTITAET: OFEN, CONF_FREMDERZEUGER_SPERRT: ["kessel2"]}, ["kessel", "fremderzeuger"], []),
    ],
    ids=["sperrt den Kessel", "nichts gewählt", "ohne Angabe", "ohne Entität und Fühler", "nur Fühler", "abgewählt", "unbekannter Kessel"],
)
def test_welche_kessel_der_fremderzeuger_sperrt(einstellungen, komponenten, erwartet):
    assert fremderzeuger_sperrt(einstellungen, komponenten) == erwartet


async def test_keine_meldung_ueber_fehlende_messwerte(hass, entry, reparaturen):
    """Der Fremderzeuger steht nicht im Menübaum - das ist kein Fehler bei den Funktionsblock-Namen."""
    coordinator, _ = await mit_ofen(hass, entry)

    assert "fremderzeuger" not in coordinator.components_without_data
    assert not [issue_id for issue_id, _ in reparaturen["angelegt"] if "fremderzeuger" in issue_id]
    assert coordinator.funktionsblock("fremderzeuger") == "Fremderzeuger"


async def test_mit_gewaehltem_kessel_gibt_es_sperre_und_schalter_auch_ohne_haekchen(hass, entry):
    coordinator, ofen = await mit_ofen(hass, entry)
    gesammelt: list = []
    await switch_platform.async_setup_entry(hass, entry, gesammelt.extend)

    assert coordinator.kesselsperre is not None
    assert ofen.sperrt == ["kessel"]
    assert "kessel_sperre" in {schalter.translation_key for schalter in gesammelt}


@pytest.mark.parametrize(
    "sperrt, schreibzugriff", [((), True), (("kessel",), False)], ids=["nichts gewählt", "ohne Schreibzugriff"]
)
async def test_ohne_auswahl_oder_schreibzugriff_wird_nur_angezeigt(
    hass, entry, fremderzeuger_ohne_hass, sperrt, schreibzugriff
):
    coordinator, ofen = await mit_ofen(hass, entry, sperrt, schreibzugriff)

    assert coordinator.kesselsperre is None
    await fremderzeuger_ohne_hass.gestartet[0](hass)
    wechsel(hass, fremderzeuger_ohne_hass, "on", alt="off")
    await zeit_um(fremderzeuger_ohne_hass)

    assert ofen.heizt is True, "angezeigt wird er trotzdem"
    assert hass.session.gesetzte_werte == []


async def test_beobachtet_seine_entitaet_und_den_start(hass, entry, fremderzeuger_ohne_hass):
    _, ofen = await mit_ofen(hass, entry)

    assert [entitaeten for entitaeten, _ in fremderzeuger_ohne_hass.beobachtet] == [[OFEN]]
    assert len(fremderzeuger_ohne_hass.gestartet) == 1
    assert ofen.heizt is False

    ofen.beenden()
    assert sorted(fremderzeuger_ohne_hass.abgemeldet) == ["start", "zustand"]


async def test_heizt_er_wird_nach_der_wartezeit_gesperrt(hass, entry, fremderzeuger_ohne_hass):
    coordinator, _ = await mit_ofen(hass, entry)

    wechsel(hass, fremderzeuger_ohne_hass, "on", alt="off")

    assert hass.session.gesetzte_werte == [], "erst nach der Wartezeit"
    bestellung = await zeit_um(fremderzeuger_ohne_hass)
    assert bestellung.wartezeit == timedelta(minutes=1)
    assert hass.session.gesetzte_werte == [(TASTE, AUS)]
    assert coordinator.kesselsperre.gesperrt is True
    assert entry.options[CONF_KESSEL_GESPERRT] == KESSEL_GESPERRT_AUSGESCHALTET


async def test_ist_er_aus_wird_nach_der_wartezeit_freigegeben(hass, entry, fremderzeuger_ohne_hass):
    coordinator, _ = await mit_ofen(hass, entry)
    wechsel(hass, fremderzeuger_ohne_hass, "on", alt="off")
    await zeit_um(fremderzeuger_ohne_hass)
    hass.session.gesetzte_werte.clear()

    wechsel(hass, fremderzeuger_ohne_hass, "off", alt="on")
    bestellung = await zeit_um(fremderzeuger_ohne_hass)

    assert bestellung.wartezeit == timedelta(minutes=5)
    assert hass.session.gesetzte_werte == [(TASTE, EIN)]
    assert coordinator.kesselsperre.gesperrt is False


async def test_eigene_wartezeiten(hass, entry, fremderzeuger_ohne_hass):
    await mit_ofen(
        hass,
        entry,
        **{CONF_FREMDERZEUGER_SPERREN_NACH: 10, CONF_FREMDERZEUGER_FREIGEBEN_NACH: 30},
    )

    wechsel(hass, fremderzeuger_ohne_hass, "on", alt="off")
    wechsel(hass, fremderzeuger_ohne_hass, "off", alt="on")

    assert [b.wartezeit for b in fremderzeuger_ohne_hass.zeitgeber] == [
        timedelta(minutes=10),
        timedelta(minutes=30),
    ]


async def test_kurz_aus_und_wieder_an_gibt_nicht_frei(hass, entry, fremderzeuger_ohne_hass):
    """Ein neuer Wechsel verwirft die laufende Wartezeit."""
    coordinator, _ = await mit_ofen(hass, entry)
    wechsel(hass, fremderzeuger_ohne_hass, "on", alt="off")
    await zeit_um(fremderzeuger_ohne_hass)
    hass.session.gesetzte_werte.clear()

    wechsel(hass, fremderzeuger_ohne_hass, "off", alt="on")
    freigeben = fremderzeuger_ohne_hass.zeitgeber[-1]
    wechsel(hass, fremderzeuger_ohne_hass, "on", alt="off")

    assert freigeben.abbestellt is True
    await zeit_um(fremderzeuger_ohne_hass)
    assert hass.session.gesetzte_werte == []
    assert coordinator.kesselsperre.gesperrt is True


@pytest.mark.parametrize("zustand", ["unavailable", "unknown"])
async def test_laesst_es_sich_nicht_mehr_sagen_wird_nach_der_wartezeit_freigegeben(
    hass, entry, fremderzeuger_ohne_hass, zustand
):
    """Etwa eine leere Batterie: Ein gesperrter Kessel in einem kalten Haus wäre schlimmer als einer, der mitläuft."""
    coordinator, ofen = await mit_ofen(hass, entry)
    wechsel(hass, fremderzeuger_ohne_hass, "on", alt="off")
    await zeit_um(fremderzeuger_ohne_hass)
    hass.session.gesetzte_werte.clear()

    wechsel(hass, fremderzeuger_ohne_hass, zustand, alt="on")

    assert ofen.heizt is None
    assert fremderzeuger_ohne_hass.zeitgeber[-1].wartezeit == timedelta(minutes=5)
    assert hass.session.gesetzte_werte == [], "erst nach der Wartezeit"
    assert coordinator.kesselsperre.gesperrt is True

    await zeit_um(fremderzeuger_ohne_hass)

    assert hass.session.gesetzte_werte == [(TASTE, EIN)]
    assert coordinator.kesselsperre.gesperrt is False


async def test_kommt_die_entitaet_rechtzeitig_zurueck_bleibt_gesperrt(
    hass, entry, fremderzeuger_ohne_hass
):
    """Ein Neustart des Ofen-Fühlers gibt den Kessel nicht frei."""
    coordinator, _ = await mit_ofen(hass, entry)
    wechsel(hass, fremderzeuger_ohne_hass, "on", alt="off")
    await zeit_um(fremderzeuger_ohne_hass)
    hass.session.gesetzte_werte.clear()

    wechsel(hass, fremderzeuger_ohne_hass, "unavailable", alt="on")
    freigeben = fremderzeuger_ohne_hass.zeitgeber[-1]
    wechsel(hass, fremderzeuger_ohne_hass, "on", alt="unavailable")

    assert freigeben.abbestellt is True
    await zeit_um(fremderzeuger_ohne_hass)
    assert hass.session.gesetzte_werte == []
    assert coordinator.kesselsperre.gesperrt is True


async def test_aus_dem_unbekannten_heraus_wird_nie_gesperrt(hass, entry, fremderzeuger_ohne_hass):
    coordinator, ofen = await mit_ofen(hass, entry, zustand="unavailable")

    await fremderzeuger_ohne_hass.gestartet[0](hass)
    await zeit_um(fremderzeuger_ohne_hass)

    assert ofen.heizt is None
    assert hass.session.gesetzte_werte == []
    assert coordinator.kesselsperre.gesperrt is False


async def test_nur_geaenderte_attribute_bestellen_keine_wartezeit(hass, entry, fremderzeuger_ohne_hass):
    await mit_ofen(hass, entry, zustand="on")

    wechsel(hass, fremderzeuger_ohne_hass, "on", alt="on")

    assert fremderzeuger_ohne_hass.zeitgeber == []


async def test_beim_start_wird_gesperrt_wenn_er_schon_heizt(hass, entry, fremderzeuger_ohne_hass):
    coordinator, _ = await mit_ofen(hass, entry, zustand="on")

    await fremderzeuger_ohne_hass.gestartet[0](hass)

    assert hass.session.gesetzte_werte == [(TASTE, AUS)]
    assert coordinator.kesselsperre.gesperrt is True


async def test_beim_start_wird_freigegeben_wenn_er_inzwischen_aus_ist(
    hass, entry, fremderzeuger_ohne_hass
):
    """Home Assistant war aus, als der Ofen ausging - der Kessel bliebe sonst gesperrt."""
    entry.options = {CONF_KESSEL_GESPERRT: KESSEL_GESPERRT_AUSGESCHALTET}
    hass.session.geschrieben[TASTE] = AUS
    coordinator, _ = await mit_ofen(hass, entry, zustand="off")
    assert coordinator.kesselsperre.gesperrt is True

    await fremderzeuger_ohne_hass.gestartet[0](hass)

    assert hass.session.gesetzte_werte == [(TASTE, EIN)]
    assert coordinator.kesselsperre.gesperrt is False


async def test_beim_start_schreibt_er_nichts_wenn_alles_passt(hass, entry, fremderzeuger_ohne_hass):
    await mit_ofen(hass, entry, zustand="off")

    await fremderzeuger_ohne_hass.gestartet[0](hass)

    assert hass.session.gesetzte_werte == []


async def test_nach_einer_unterbrechung_wird_das_freigeben_nachgeholt(
    hass, entry, fremderzeuger_ohne_hass
):
    """Der Ofen ging aus, während die Anlage nicht erreichbar war."""
    coordinator, ofen = await mit_ofen(hass, entry)
    wechsel(hass, fremderzeuger_ohne_hass, "on", alt="off")
    await zeit_um(fremderzeuger_ohne_hass)
    hass.session.gesetzte_werte.clear()

    coordinator.last_update_success = False
    ofen._anlage_gemeldet()
    hass.session.fail_uris.add("0/0/12080")
    wechsel(hass, fremderzeuger_ohne_hass, "off", alt="on")
    await zeit_um(fremderzeuger_ohne_hass)
    assert coordinator.kesselsperre.gesperrt is True, "die Anlage hat das Einschalten nicht angenommen"

    hass.session.fail_uris.clear()
    hass.session.gesetzte_werte.clear()
    coordinator.last_update_success = True
    aufgaben: list = []
    hass.async_create_task = lambda ziel, *a, **k: aufgaben.append(ziel)
    ofen._anlage_gemeldet()
    [nachholen] = aufgaben
    await nachholen

    assert hass.session.gesetzte_werte == [(TASTE, EIN)]
    assert coordinator.kesselsperre.gesperrt is False


async def test_war_der_kessel_von_hand_aus_bleibt_er_es(hass, entry, fremderzeuger_ohne_hass):
    hass.session.geschrieben[TASTE] = AUS
    coordinator, _ = await mit_ofen(hass, entry)

    wechsel(hass, fremderzeuger_ohne_hass, "on", alt="off")
    await zeit_um(fremderzeuger_ohne_hass)
    assert coordinator.kesselsperre.gesperrt is True
    wechsel(hass, fremderzeuger_ohne_hass, "off", alt="on")
    await zeit_um(fremderzeuger_ohne_hass)

    assert hass.session.gesetzte_werte == []
    assert coordinator.kesselsperre.gesperrt is False


async def test_der_schalter_folgt_wenn_der_fremderzeuger_sperrt(hass, entry, fremderzeuger_ohne_hass):
    coordinator, _ = await mit_ofen(hass, entry)
    gesammelt: list = []
    await switch_platform.async_setup_entry(hass, entry, gesammelt.extend)
    schalter = next(s for s in gesammelt if s.translation_key == "kessel_sperre")
    geschrieben: list = []
    coordinator.kesselsperre.beobachten(lambda: geschrieben.append(schalter.is_on))

    wechsel(hass, fremderzeuger_ohne_hass, "on", alt="off")
    await zeit_um(fremderzeuger_ohne_hass)

    assert geschrieben == [True]
    assert schalter.is_on is True


async def test_karte_erfaehrt_name_entitaet_und_gesperrte_kessel(hass, entry):
    coordinator, _ = await mit_ofen(hass, entry, **{CONF_FREMDERZEUGER_NAME: "Kachelofen"})
    entry.runtime_data = coordinator

    teil = next(t for t in anlage(hass, entry)["teile"] if t["id"] == "fremderzeuger")

    assert teil["art"] == "fremderzeuger"
    assert teil["bezeichnung"] == "Kachelofen"
    assert teil["entitaet"] == OFEN
    assert teil["fuehler"] is None
    assert teil["sperrt"] == ["kessel"]
    assert teil["von"] == "puffer", "wie Brenner und Fremdwärme lädt er in den ersten Puffer"


async def test_karte_nennt_keine_gesperrten_kessel_ohne_sperre(hass, entry):
    coordinator, _ = await mit_ofen(hass, entry, schreibzugriff=False)
    entry.runtime_data = coordinator

    teil = next(t for t in anlage(hass, entry)["teile"] if t["id"] == "fremderzeuger")

    assert teil["bezeichnung"] == "Ofen"
    assert teil["sperrt"] == []


def test_fremderzeuger_laedt_wie_die_anderen_erzeuger_in_den_ersten_puffer():
    assert verbindungen(["kessel", "puffer", "puffer2", "fremderzeuger"])["fremderzeuger"] == "puffer"
    assert verbindungen(["kessel", "fremderzeuger"])["fremderzeuger"] is None


def test_schritt_fragt_mit_schreibzugriff_auch_nach_den_kesseln():
    mit = [str(feld) for feld in _fremderzeuger_schema({}, True).schema]
    ohne = [str(feld) for feld in _fremderzeuger_schema({}, False).schema]

    assert mit == [
        CONF_FREMDERZEUGER_NAME,
        CONF_FREMDERZEUGER_ENTITAET,
        CONF_FREMDERZEUGER_FUEHLER,
        CONF_FREMDERZEUGER_SPERRT,
        CONF_FREMDERZEUGER_SPERREN_NACH,
        CONF_FREMDERZEUGER_FREIGEBEN_NACH,
    ]
    assert ohne == [CONF_FREMDERZEUGER_NAME, CONF_FREMDERZEUGER_ENTITAET, CONF_FREMDERZEUGER_FUEHLER]
    freiwillig = (CONF_FREMDERZEUGER_ENTITAET, CONF_FREMDERZEUGER_FUEHLER)
    vorgaben = {str(feld): feld.default() for feld in _fremderzeuger_schema({}, True).schema if str(feld) not in freiwillig}
    assert vorgaben == {
        CONF_FREMDERZEUGER_NAME: "Ofen",
        CONF_FREMDERZEUGER_SPERRT: [],
        CONF_FREMDERZEUGER_SPERREN_NACH: 1,
        CONF_FREMDERZEUGER_FREIGEBEN_NACH: 5,
    }, "ab Werk wird nichts gesperrt"


async def test_konfigurieren_fragt_nach_dem_fremderzeuger_und_speichert_ihn(monkeypatch):
    eingabe = {**optionen(components=["fremderzeuger"]), "enable_switches": True}
    flow, ergebnis = await options_schritt(monkeypatch, {**eingabe}, eingabe)
    assert ergebnis["step_id"] == "fub_names"
    ergebnis = await flow.async_step_fub_names(
        {str(feld): feld.default() for feld in ergebnis["data_schema"].schema}
    )

    assert ergebnis["step_id"] == "fremderzeuger"
    angaben = {
        CONF_FREMDERZEUGER_NAME: "Kachelofen",
        CONF_FREMDERZEUGER_ENTITAET: OFEN,
        CONF_FREMDERZEUGER_SPERRT: ["kessel"],
        CONF_FREMDERZEUGER_SPERREN_NACH: 2,
        CONF_FREMDERZEUGER_FREIGEBEN_NACH: 10,
    }
    ergebnis = await flow.async_step_fremderzeuger(angaben)
    for _ in range(6):
        if ergebnis["type"] == "create_entry":
            break
        schema = ergebnis.get("data_schema")
        vorgaben = {str(feld): feld.default() for feld in schema.schema} if schema else {}
        ergebnis = await getattr(flow, f"async_step_{ergebnis['step_id']}")(vorgaben)

    assert ergebnis["type"] == "create_entry"
    assert {feld: ergebnis["data"][feld] for feld in angaben} == angaben


async def test_ohne_die_komponente_gibt_es_den_schritt_nicht_und_nichts_bleibt_gespeichert(monkeypatch):
    bisher = {
        **optionen(components=["fremderzeuger"]),
        "enable_switches": True,
        CONF_FREMDERZEUGER_ENTITAET: OFEN,
        CONF_FREMDERZEUGER_SPERRT: ["kessel"],
    }
    flow, ergebnis = await options_schritt(monkeypatch, bisher, {**optionen(), "enable_switches": True})
    for _ in range(6):
        if ergebnis["type"] == "create_entry":
            break
        assert ergebnis["step_id"] != "fremderzeuger"
        schema = ergebnis.get("data_schema")
        vorgaben = {str(feld): feld.default() for feld in schema.schema} if schema else {}
        ergebnis = await getattr(flow, f"async_step_{ergebnis['step_id']}")(vorgaben)

    assert ergebnis["type"] == "create_entry"
    assert CONF_FREMDERZEUGER_ENTITAET not in ergebnis["data"]
    assert CONF_FREMDERZEUGER_SPERRT not in ergebnis["data"]


FUEHLER = "sensor.ofen_temperatur"


async def mit_fuehler(hass, entry, temperatur, mit_entitaet=False, zustand="off", **mehr):
    """Fremderzeuger mit Temperaturfühler - allein oder zusammen mit der Entität."""
    hass.states.zustaende[FUEHLER] = str(temperatur)
    hass.states.zustaende[OFEN] = zustand
    entry.data["components"] = [*entry.data["components"], "fremderzeuger"]
    entry.data["enable_switches"] = True
    entry.data[CONF_FREMDERZEUGER_FUEHLER] = FUEHLER
    if mit_entitaet:
        entry.data[CONF_FREMDERZEUGER_ENTITAET] = OFEN
    entry.data[CONF_FREMDERZEUGER_SPERRT] = ["kessel"]
    entry.data.update(mehr)
    coordinator, _ = await setup_integration(hass, entry)
    hass.session.gesetzte_werte.clear()
    return coordinator, coordinator.fremderzeuger


def meldet(hass, protokoll, entitaet, wert):
    """Entität oder Fühler melden einen neuen Zustand."""
    hass.states.zustaende[entitaet] = str(wert)
    [(_, rueckruf)] = protokoll.beobachtet
    rueckruf(SimpleNamespace(data={}))


async def test_nur_mit_fuehler_heizt_er_ab_der_sperrtemperatur(hass, entry, fremderzeuger_ohne_hass):
    coordinator, ofen = await mit_fuehler(hass, entry, 35)

    assert fremderzeuger_ohne_hass.beobachtet[0][0] == [FUEHLER]
    assert ofen.heizt is False and ofen.schwelle == 60

    meldet(hass, fremderzeuger_ohne_hass, FUEHLER, 59.9)
    assert ofen.heizt is False and fremderzeuger_ohne_hass.zeitgeber == []

    meldet(hass, fremderzeuger_ohne_hass, FUEHLER, 60)
    assert ofen.heizt is True
    bestellung = await zeit_um(fremderzeuger_ohne_hass)

    assert bestellung.wartezeit == timedelta(0), "die Temperatur ersetzt die Wartezeit"
    assert hass.session.gesetzte_werte == [(TASTE, AUS)]
    assert coordinator.kesselsperre.gesperrt is True


async def test_freigegeben_wird_erst_fuenf_grad_unter_der_sperrtemperatur(
    hass, entry, fremderzeuger_ohne_hass
):
    """Sonst flatterte die Sperre um die Sperrtemperatur."""
    coordinator, ofen = await mit_fuehler(hass, entry, 35)
    meldet(hass, fremderzeuger_ohne_hass, FUEHLER, 72)
    await zeit_um(fremderzeuger_ohne_hass)
    hass.session.gesetzte_werte.clear()
    bestellt = len(fremderzeuger_ohne_hass.zeitgeber)

    meldet(hass, fremderzeuger_ohne_hass, FUEHLER, 56)
    assert ofen.heizt is True and len(fremderzeuger_ohne_hass.zeitgeber) == bestellt

    meldet(hass, fremderzeuger_ohne_hass, FUEHLER, 54.9)
    assert ofen.heizt is False
    bestellung = await zeit_um(fremderzeuger_ohne_hass)

    assert bestellung.wartezeit == timedelta(minutes=5)
    assert hass.session.gesetzte_werte == [(TASTE, EIN)]
    assert coordinator.kesselsperre.gesperrt is False


async def test_mit_entitaet_und_fuehler_muss_beides_stimmen(hass, entry, fremderzeuger_ohne_hass):
    coordinator, ofen = await mit_fuehler(hass, entry, 80, mit_entitaet=True)

    assert sorted(fremderzeuger_ohne_hass.beobachtet[0][0]) == sorted([OFEN, FUEHLER])
    assert ofen.heizt is False, "heiß, aber die Entität ist aus"

    meldet(hass, fremderzeuger_ohne_hass, OFEN, "on")
    assert ofen.heizt is True
    await zeit_um(fremderzeuger_ohne_hass)
    assert hass.session.gesetzte_werte == [(TASTE, AUS)]

    meldet(hass, fremderzeuger_ohne_hass, OFEN, "off")
    assert ofen.heizt is False
    await zeit_um(fremderzeuger_ohne_hass)
    assert hass.session.gesetzte_werte == [(TASTE, AUS), (TASTE, EIN)]


async def test_an_aber_noch_kalt_sperrt_nicht(hass, entry, fremderzeuger_ohne_hass):
    coordinator, ofen = await mit_fuehler(hass, entry, 30, mit_entitaet=True, zustand="on")

    await fremderzeuger_ohne_hass.gestartet[0](hass)

    assert ofen.heizt is False
    assert hass.session.gesetzte_werte == []


async def test_faellt_der_fuehler_aus_wird_nach_der_wartezeit_freigegeben(
    hass, entry, fremderzeuger_ohne_hass
):
    coordinator, ofen = await mit_fuehler(hass, entry, 35)
    meldet(hass, fremderzeuger_ohne_hass, FUEHLER, 72)
    await zeit_um(fremderzeuger_ohne_hass)
    hass.session.gesetzte_werte.clear()

    meldet(hass, fremderzeuger_ohne_hass, FUEHLER, "unavailable")
    assert ofen.heizt is None and coordinator.kesselsperre.gesperrt is True
    await zeit_um(fremderzeuger_ohne_hass)

    assert hass.session.gesetzte_werte == [(TASTE, EIN)]


async def test_nach_dem_neustart_haelt_die_sperre_bis_fuenf_grad_darunter(
    hass, entry, fremderzeuger_ohne_hass
):
    """Der Kessel war vor dem Neustart gesperrt - 57 °C geben ihn nicht frei."""
    entry.options = {CONF_KESSEL_GESPERRT: KESSEL_GESPERRT_AUSGESCHALTET}
    hass.session.geschrieben[TASTE] = AUS
    coordinator, ofen = await mit_fuehler(hass, entry, 57)

    await fremderzeuger_ohne_hass.gestartet[0](hass)

    assert ofen.heizt is True
    assert hass.session.gesetzte_werte == []
    assert coordinator.kesselsperre.gesperrt is True


async def test_eigener_schalter_nur_ohne_entitaet(hass, entry, fremderzeuger_ohne_hass):
    coordinator, ofen = await mit_fuehler(hass, entry, 72)
    gesammelt: list = []
    await switch_platform.async_setup_entry(hass, entry, gesammelt.extend)
    schalter = next(s for s in gesammelt if s.translation_key == "fremderzeuger_schalter")
    schalter.async_write_ha_state = lambda: None

    assert ofen.eigener_schalter is True
    assert schalter.entity_id == "switch.eta_heizung_fremderzeuger"
    assert schalter.is_on is True and ofen.heizt is True

    await schalter.async_turn_off()
    assert ofen.heizt is False, "aus: der Fremderzeuger wird nicht beachtet"
    await zeit_um(fremderzeuger_ohne_hass)
    assert coordinator.kesselsperre.gesperrt is False

    await schalter.async_turn_on()
    assert ofen.heizt is True
    await zeit_um(fremderzeuger_ohne_hass)
    assert hass.session.gesetzte_werte == [(TASTE, AUS)]
    assert coordinator.kesselsperre.gesperrt is True


async def test_mit_entitaet_gibt_es_keinen_eigenen_schalter(hass, entry):
    coordinator, ofen = await mit_fuehler(hass, entry, 72, mit_entitaet=True)
    gesammelt: list = []
    await switch_platform.async_setup_entry(hass, entry, gesammelt.extend)

    assert ofen.eigener_schalter is False
    assert "fremderzeuger_schalter" not in {s.translation_key for s in gesammelt}


async def test_sperrtemperatur_ist_ein_zahlenfeld_nur_mit_fuehler(hass, entry, fremderzeuger_ohne_hass):
    from eta_heating_ws import number as number_platform

    coordinator, ofen = await mit_fuehler(hass, entry, 50)
    gesammelt: list = []
    await number_platform.async_setup_entry(hass, entry, gesammelt.extend)
    zahl = next(z for z in gesammelt if z.translation_key == "fremderzeuger_schwelle")
    zahl.async_write_ha_state = lambda: None

    assert zahl.entity_id == "number.eta_heizung_fremderzeuger_sperrtemperatur"
    assert zahl.native_value == 60 and zahl.native_unit_of_measurement == "°C"
    assert zahl.available is True

    await zahl.async_set_native_value(45)

    assert entry.options[CONF_FREMDERZEUGER_SCHWELLE] == 45
    assert ofen.schwelle == 45 and ofen.heizt is True, "50 °C liegen jetzt über der Sperrtemperatur"
    await zeit_um(fremderzeuger_ohne_hass)
    assert hass.session.gesetzte_werte == [(TASTE, AUS)]


async def test_ohne_fuehler_kein_zahlenfeld(hass, entry):
    from eta_heating_ws import number as number_platform

    await mit_ofen(hass, entry)
    gesammelt: list = []
    await number_platform.async_setup_entry(hass, entry, gesammelt.extend)

    assert "fremderzeuger_schwelle" not in {z.translation_key for z in gesammelt}


async def test_gemerkte_sperrtemperatur_gilt_nach_dem_neustart(hass, entry):
    entry.options = {CONF_FREMDERZEUGER_SCHWELLE: 85.0}
    _, ofen = await mit_fuehler(hass, entry, 70)

    assert ofen.schwelle == 85 and ofen.heizt is False


async def test_binaersensor_sagt_ob_er_heizt(hass, entry, fremderzeuger_ohne_hass):
    from eta_heating_ws import binary_sensor as binary_sensor_platform

    coordinator, ofen = await mit_fuehler(hass, entry, 35, mit_entitaet=True)
    gesammelt: list = []
    await binary_sensor_platform.async_setup_entry(hass, entry, gesammelt.extend)
    heizt = next(b for b in gesammelt if b.translation_key == "fremderzeuger_heizt")
    geschrieben: list = []
    ofen.beobachten(lambda: geschrieben.append(heizt.is_on))

    assert heizt.entity_id == "binary_sensor.eta_heizung_fremderzeuger_heizt"
    assert heizt.is_on is False
    assert heizt.extra_state_attributes == {
        "entitaet": OFEN,
        "temperaturfuehler": FUEHLER,
        "sperrtemperatur": 60,
    }

    meldet(hass, fremderzeuger_ohne_hass, OFEN, "on")
    meldet(hass, fremderzeuger_ohne_hass, FUEHLER, 75)

    assert geschrieben == [True]


def test_entitaeten_des_fremderzeugers_bleiben_nur_solange_es_sie_gibt():
    from eta_heating_ws import entitaet_vorgesehen

    def vorgesehen(key, komponenten=("kessel", "fremderzeuger"), **mehr):
        return entitaet_vorgesehen(key, list(komponenten), True, True, **mehr)

    assert vorgesehen("fremderzeuger_heizt") is True
    assert vorgesehen("fremderzeuger_heizt", komponenten=("kessel",)) is False
    assert vorgesehen("fremderzeuger_schwelle", ofenfuehler=True) is True
    assert vorgesehen("fremderzeuger_schwelle") is False
    assert vorgesehen("fremderzeuger_schalter", ofenschalter=True) is True
    assert vorgesehen("fremderzeuger_schalter") is False


async def test_schritt_verlangt_entitaet_oder_fuehler(monkeypatch):
    eingabe = {**optionen(components=["fremderzeuger"]), "enable_switches": True}
    flow, ergebnis = await options_schritt(monkeypatch, {**eingabe}, eingabe)
    ergebnis = await flow.async_step_fub_names(
        {str(feld): feld.default() for feld in ergebnis["data_schema"].schema}
    )
    assert ergebnis["step_id"] == "fremderzeuger"

    ergebnis = await flow.async_step_fremderzeuger({CONF_FREMDERZEUGER_NAME: "Ofen"})
    assert ergebnis["step_id"] == "fremderzeuger"
    assert ergebnis["errors"] == {"base": "fremderzeuger_ohne_quelle"}

    ergebnis = await flow.async_step_fremderzeuger(
        {CONF_FREMDERZEUGER_NAME: "Ofen", CONF_FREMDERZEUGER_FUEHLER: FUEHLER}
    )
    assert ergebnis.get("errors") in (None, {}), "nur der Fühler genügt"
    assert ergebnis.get("step_id") != "fremderzeuger"


async def test_konfigurieren_behaelt_die_sperrtemperatur(monkeypatch):
    """Die Optionen werden beim Speichern ersetzt - die Sperrtemperatur steht in keinem Formular."""
    eingabe = {**optionen(components=["fremderzeuger"]), "enable_switches": True}
    bisher = {**eingabe, CONF_FREMDERZEUGER_FUEHLER: FUEHLER, CONF_FREMDERZEUGER_SCHWELLE: 85.0}
    flow, ergebnis = await options_schritt(monkeypatch, bisher, eingabe)
    ergebnis = await flow.async_step_fub_names(
        {str(feld): feld.default() for feld in ergebnis["data_schema"].schema}
    )
    ergebnis = await flow.async_step_fremderzeuger(
        {CONF_FREMDERZEUGER_NAME: "Ofen", CONF_FREMDERZEUGER_FUEHLER: FUEHLER}
    )
    for _ in range(6):
        if ergebnis["type"] == "create_entry":
            break
        schema = ergebnis.get("data_schema")
        vorgaben = {str(feld): feld.default() for feld in schema.schema} if schema else {}
        ergebnis = await getattr(flow, f"async_step_{ergebnis['step_id']}")(vorgaben)

    assert ergebnis["type"] == "create_entry"
    assert ergebnis["data"][CONF_FREMDERZEUGER_SCHWELLE] == 85.0


async def test_binaersensor_kennt_den_zustand_gleich_nach_dem_einrichten(hass, entry):
    """Die Entitäten entstehen, bevor der Fremderzeuger startet - er meldet sich danach bei ihnen."""
    from eta_heating_ws.fremderzeuger import Fremderzeuger

    hass.states.zustaende[FUEHLER] = "30"
    ofen = Fremderzeuger(hass, SimpleNamespace(last_update_success=True, kesselsperre=None, async_add_listener=lambda r: (lambda: None)), None, [], 1, 5, FUEHLER)
    gemeldet: list = []
    ofen.beobachten(lambda: gemeldet.append(ofen.heizt))
    assert ofen.heizt is None

    ofen.starten()

    assert gemeldet == [False]


def test_jedes_feld_im_schritt_wer_haengt_woran_ist_beschriftet():
    """Mit zwei Puffern fragt der Dialog auch, wohin der Fremderzeuger lädt - das Feld braucht einen Namen."""
    import json

    from eta_heating_ws.verbindungen import feld, felder

    from .conftest import UEBERSETZUNGEN

    alle = felder(list(COMPONENTS))
    assert "fremderzeuger" in alle
    for datei in ("de.json", "en.json"):
        texte = json.loads((UEBERSETZUNGEN / datei).read_text(encoding="utf-8"))
        for bereich in ("config", "options"):
            beschriftet = texte[bereich]["step"]["verbindungen"]["data"]
            fehlend = [teil for teil in alle if feld(teil) not in beschriftet]
            assert not fehlend, (datei, bereich, fehlend)
