"""Weitere Werte: frei aus dem Menübaum gewählte Werte, nur gelesen.

Der Nutzer wählt sie unter Konfigurieren. Jeder wird ein Sensor, dessen
Name der Weg im Menübaum ist und dessen Art und Einheit die Anlage beim
Auswählen genannt hat. Gelesen werden sie getrennt von den festen
Werten, in Portionen von höchstens 25, reihum eine je Abfragezyklus.
"""

from __future__ import annotations

import pytest

from eta_heating_ws import entitaet_vorgesehen
from eta_heating_ws import weitere_werte as weitere
from eta_heating_ws.api import ETAValue
from eta_heating_ws.const import CONF_WEITERE_WERTE

from .test_config_flow import optionen, options_schritt
from .test_sensors import setup_integration

EFFEKTIV = "/120/10601/0/0/12499"
ZUSTAND = "/120/10601/0/0/77777"

VOLUMEN = {
    "uri": EFFEKTIV,
    "fub": "PufferFlex",
    "pfad": ["Einstellungen", "Leistungsregelung", "Effektives Puffervolumen"],
    "zahl": True,
    "einheit": "l",
    "stellen": 0,
}
TEXT = {"uri": ZUSTAND, "fub": "PufferFlex", "pfad": ["Sonstiges", "Ergänzung"], "zahl": False}


def viele(anzahl: int) -> list[dict]:
    """So viele gewählte Zahlenwerte mit ausgedachten Adressen - die Attrappe meldet für jede 55,5 °C."""
    return [
        {"uri": f"/9/9/0/0/{nummer}", "fub": "Test", "pfad": [f"Wert {nummer}"], "zahl": True, "einheit": "°C", "stellen": 1}
        for nummer in range(1, anzahl + 1)
    ]


def flow_fuer(monkeypatch, hass, entry):
    """Der Dialog Konfigurieren zu dieser Einrichtung, ohne laufendes Home Assistant."""
    from eta_heating_ws import config_flow as modul

    flow = modul.ETAOptionsFlow()
    flow.hass = hass
    monkeypatch.setattr(modul.ETAOptionsFlow, "config_entry", property(lambda self: entry))
    monkeypatch.setattr(modul, "async_get_clientsession", lambda _hass: hass.session)
    for name, art in (
        ("async_show_form", "form"),
        ("async_show_menu", "menu"),
        ("async_create_entry", "create_entry"),
        ("async_abort", "abort"),
    ):
        monkeypatch.setattr(
            modul.ETAOptionsFlow, name, lambda self, _art=art, **angaben: {"type": _art, **angaben}
        )
    return flow


def angebot(schritt) -> dict[str, str]:
    """Adresse und Name der Werte, die der Schritt zur Wahl stellt."""
    [feld] = schritt["data_schema"].schema.values()
    return {eintrag["value"]: eintrag["label"] for eintrag in feld.config["options"]}


def vorgabe(schritt) -> list[str]:
    [feld] = schritt["data_schema"].schema
    return feld.default()


async def test_menuebaum_nennt_jedes_objekt_mit_seinem_weg(hass, entry):
    coordinator, _ = await setup_integration(hass, entry)

    werte = weitere.menue_werte(await coordinator.client.async_get_menu())

    assert werte[EFFEKTIV] == {
        "fub": "PufferFlex",
        "pfad": ["Einstellungen", "Leistungsregelung", "Effektives Puffervolumen"],
    }
    assert weitere.bezeichnung(werte[EFFEKTIV]) == (
        "PufferFlex › Einstellungen › Leistungsregelung › Effektives Puffervolumen"
    )
    assert len(werte) > 50
    assert all(eintrag["fub"] and eintrag["pfad"] for eintrag in werte.values())


def test_menuebaum_ohne_inhalt_gibt_nichts_zur_wahl():
    assert weitere.menue_werte({}) == {}
    assert weitere.menue_werte({"eta": {"menu": {"fub": {"@name": "Kessel", "@uri": "/1/2"}}}}) == {}
    assert weitere.menue_werte(None) == {}


def test_dieselbe_adresse_zaehlt_an_ihrer_ersten_stelle():
    baum = {
        "eta": {
            "menu": {
                "fub": {
                    "@name": "Puffer",
                    "object": [
                        {"@name": "Eingänge", "@uri": "/1/2/0/0/1", "object": {"@name": "Puffer oben", "@uri": "/1/2/0/7/0"}},
                        {"@name": "Puffer", "@uri": "/1/2/0/0/2", "object": {"@name": "Puffer oben", "@uri": "/1/2/0/7/0"}},
                    ],
                }
            }
        }
    }
    werte = weitere.menue_werte(baum)
    assert list(werte) == ["/1/2/0/0/1", "/1/2/0/7/0", "/1/2/0/0/2"]
    assert werte["/1/2/0/7/0"]["pfad"] == ["Eingänge", "Puffer oben"]


@pytest.mark.parametrize(
    "wert, erwartet",
    [
        (ETAValue(55.5, "55,5", "°C", False, 1), {"zahl": True, "einheit": "°C", "stellen": 1}),
        (ETAValue(12.0, "12", "", False, 0), {"zahl": True, "einheit": "", "stellen": 0}),
        (ETAValue(None, "---", "°C", False, 1), {"zahl": True, "einheit": "°C", "stellen": 1}),
        (ETAValue(1044.0, "Ein", "", True), {"zahl": False}),
        (ETAValue(810.0, "13:30", "", False, 0), {"zahl": False}),
        (ETAValue(1795000000.0, "24.11.2026", "", False, 0), {"zahl": False}),
        (ETAValue(None, "---", "", False, 0), None),
        (ETAValue(None, "", "", True), None),
        (None, None),
    ],
)
def test_einordnen_nach_dem_was_die_anlage_meldet(wert, erwartet):
    """Zahl mit Einheit oder Text - Uhrzeit und Datum zeigt der Sensor so, wie die Anlage sie anzeigt."""
    assert weitere.einordnen(wert) == erwartet


def test_zustand_bleibt_bei_der_art_des_sensors():
    assert weitere.zustand(ETAValue(55.5, "55,5", "°C", False, 1), True) == 55.5
    assert weitere.zustand(ETAValue(None, "---", "°C", False, 1), True) is None
    assert weitere.zustand(ETAValue(3.0, "Störung", "", True), True) is None
    assert weitere.zustand(ETAValue(1044.0, "Ein", "", True), False) == "Ein"
    assert weitere.zustand(ETAValue(810.0, "13:30", "", False, 0), False) == "13:30"
    assert weitere.zustand(ETAValue(None, " ", "", True), False) is None
    assert weitere.zustand(None, True) is None
    assert len(weitere.zustand(ETAValue(None, "x" * 400, "", True), False)) == 255


@pytest.mark.parametrize(
    "anzahl, portionen, sekunden", [(0, 0, 30), (1, 1, 30), (25, 1, 30), (26, 2, 60), (100, 4, 120)]
)
def test_portionen_und_wie_oft_ein_wert_drankommt(anzahl, portionen, sekunden):
    werte = {f"wert_{n}": f"/1/{n}" for n in range(anzahl)}
    geteilt = weitere.portionen(werte)
    assert len(geteilt) == portionen
    assert all(len(portion) <= weitere.JE_ABFRAGE for portion in geteilt)
    assert {key for portion in geteilt for key in portion} == set(werte)
    assert weitere.abfrage_alle(anzahl, 30) == sekunden


async def test_gewaehlte_werte_werden_sensoren(hass, entry):
    hass.session.texte[ZUSTAND] = "Bereit"
    entry.options = {CONF_WEITERE_WERTE: [VOLUMEN, TEXT]}

    coordinator, by_name = await setup_integration(hass, entry)

    zahl = by_name["PufferFlex › Einstellungen › Leistungsregelung › Effektives Puffervolumen"]
    assert zahl.native_value == 825
    assert zahl.native_unit_of_measurement == "l"
    assert zahl.state_class == "measurement"
    assert zahl.suggested_display_precision == 0
    assert zahl.unique_id == "eta_static_testeintrag_wert_120_10601_0_0_12499"
    assert zahl.has_entity_name is True
    assert zahl.available is True
    assert zahl.extra_state_attributes == {"status": "ok", "adresse": EFFEKTIV, "abfrage_alle": 30.0}

    text = by_name["PufferFlex › Sonstiges › Ergänzung"]
    assert text.native_value == "Bereit"
    assert text.native_unit_of_measurement is None
    assert text.state_class is None
    assert coordinator.weitere_abfrage_alle == 30


async def test_gelesen_wird_ueber_einen_eigenen_variablensatz(hass, entry):
    """Die festen Werte hängen nicht daran: Ihr Variablensatz bleibt, wie er war."""
    entry.options = {CONF_WEITERE_WERTE: [VOLUMEN, TEXT]}

    await setup_integration(hass, entry)

    assert hass.session.varsets["hw0testeintrag"] == [EFFEKTIV, ZUSTAND]
    assert EFFEKTIV not in hass.session.varsets["hatesteintrag"]
    assert ZUSTAND not in hass.session.varsets["hatesteintrag"]


async def test_ohne_gewaehlte_werte_gibt_es_keinen_weiteren_variablensatz(hass, entry):
    coordinator, _ = await setup_integration(hass, entry)

    assert not [name for name in hass.session.varsets if name.startswith("hw")]
    assert coordinator.weitere_werte == {}


async def test_mehr_als_eine_portion_kommt_reihum_dran(hass, entry):
    """Je Abfragezyklus eine Portion - die Last für die Anlage wächst nicht mit der Zahl der Werte."""
    entry.options = {CONF_WEITERE_WERTE: viele(30)}
    coordinator, _ = await setup_integration(hass, entry)
    schluessel = list(coordinator.weitere_werte)
    assert coordinator.weitere_abfrage_alle == 60

    assert all(key in coordinator.data for key in schluessel[:25])
    assert not any(key in coordinator.data for key in schluessel[25:]), "die zweite Portion ist noch nicht dran"

    vorher = hass.session.count
    await coordinator.async_refresh()
    assert all(key in coordinator.data for key in schluessel)
    assert len(hass.session.varsets["hw1testeintrag"]) == 5

    hass.session.count = 0
    await coordinator.async_refresh()
    await coordinator.async_refresh()
    assert vorher > 0
    assert hass.session.count <= 6, "je Zyklus eine Anfrage für die festen Werte, eine für die Portion, dazu die Störungen"


async def test_bleibt_ein_wert_aus_gilt_er_nach_dem_zweiten_mal_als_nicht_erreichbar(hass, entry):
    entry.options = {CONF_WEITERE_WERTE: [VOLUMEN, TEXT]}
    hass.session.texte[ZUSTAND] = "Bereit"
    coordinator, by_name = await setup_integration(hass, entry)
    text = by_name["PufferFlex › Sonstiges › Ergänzung"]
    hass.session.varsets["hw0testeintrag"].remove(ZUSTAND)

    await coordinator.async_refresh()
    assert text.available is True
    assert text.native_value == "Bereit", "der letzte Wert bleibt stehen"

    await coordinator.async_refresh()
    assert text.available is False
    assert text.extra_state_attributes["status"] == "nicht_erreichbar"
    assert by_name["Kesseltemperatur"].available is True, "die festen Werte betrifft das nicht"


async def test_ohne_variablensaetze_wird_die_portion_einzeln_gelesen(hass, entry):
    """Ältere Regelungen kennen keine Variablensätze."""
    hass.session.varset_unterstuetzt = False
    entry.options = {CONF_WEITERE_WERTE: [VOLUMEN]}

    coordinator, by_name = await setup_integration(hass, entry)

    wert = by_name["PufferFlex › Einstellungen › Leistungsregelung › Effektives Puffervolumen"]
    assert wert.native_value == 825
    await coordinator.async_refresh()
    assert wert.available is True


async def test_kennt_die_anlage_den_variablensatz_nicht_mehr_wird_er_neu_angelegt(hass, entry):
    """Sie hält ihn nur im Arbeitsspeicher - nach ihrem Neustart ist er weg."""
    entry.options = {CONF_WEITERE_WERTE: [VOLUMEN]}
    coordinator, by_name = await setup_integration(hass, entry)
    del hass.session.varsets["hw0testeintrag"]

    await coordinator.async_refresh()

    assert hass.session.varsets["hw0testeintrag"] == [EFFEKTIV]
    wert = by_name["PufferFlex › Einstellungen › Leistungsregelung › Effektives Puffervolumen"]
    assert wert.available is True


async def test_beim_entladen_verschwinden_die_variablensaetze(hass, entry):
    entry.options = {CONF_WEITERE_WERTE: viele(30)}
    coordinator, _ = await setup_integration(hass, entry)
    await coordinator.async_refresh()
    assert {"hw0testeintrag", "hw1testeintrag"} <= set(hass.session.varsets)

    await coordinator.async_varset_aufraeumen()

    assert not [name for name in hass.session.varsets if name.startswith("hw")]


async def test_diagnose_nennt_die_gewaehlten_werte(hass, entry):
    from eta_heating_ws.diagnostics import async_get_config_entry_diagnostics

    hass.session.texte[ZUSTAND] = "Bereit"
    entry.options = {CONF_WEITERE_WERTE: [VOLUMEN, TEXT]}
    await setup_integration(hass, entry)

    diagnose = await async_get_config_entry_diagnostics(hass, entry)

    assert diagnose["weitere_werte"] == {
        "abfrage_alle": 30.0,
        "werte": [
            {
                "name": "PufferFlex › Einstellungen › Leistungsregelung › Effektives Puffervolumen",
                "adresse": EFFEKTIV,
                "art": "Zahl",
                "einheit": "l",
                "wert": 825.0,
                "status": "ok",
            },
            {
                "name": "PufferFlex › Sonstiges › Ergänzung",
                "adresse": ZUSTAND,
                "art": "Text",
                "einheit": "",
                "wert": "Bereit",
                "status": "ok",
            },
        ],
    }


def test_abgewaehlte_werte_werden_aufgeraeumt():
    """Danach räumt die Integration auf, wenn ein Wert nicht mehr gewählt ist."""
    key = weitere.schluessel(EFFEKTIV)
    assert key == "wert_120_10601_0_0_12499"
    assert entitaet_vorgesehen(key, ["kessel"], False, False, weitere={key}) is True
    assert entitaet_vorgesehen(key, ["kessel"], False, False) is False
    assert entitaet_vorgesehen("wert_der_anlage", ["kessel"], False, False) is False
    assert entitaet_vorgesehen("kessel_temperatur", ["kessel"], False, False) is True


async def test_konfigurieren_beginnt_mit_einer_wahl(monkeypatch, hass, entry):
    flow = flow_fuer(monkeypatch, hass, entry)

    schritt = await flow.async_step_init()

    assert schritt == {"type": "menu", "step_id": "init", "menu_options": ["einstellungen", "weitere_werte"]}

    from eta_heating_ws import config_flow as modul

    monkeypatch.setattr(modul, "wetter_vorschlag", lambda *_: None)
    einstellungen = await flow.async_step_einstellungen()
    assert einstellungen["step_id"] == "einstellungen"


async def test_schritt_bietet_den_menuebaum_ohne_die_festen_sensoren(monkeypatch, hass, entry):
    coordinator, _ = await setup_integration(hass, entry)
    flow = flow_fuer(monkeypatch, hass, entry)

    schritt = await flow.async_step_weitere_werte()

    assert schritt["step_id"] == "weitere_werte"
    zur_wahl = angebot(schritt)
    assert zur_wahl[EFFEKTIV] == "PufferFlex › Einstellungen › Leistungsregelung › Effektives Puffervolumen"
    assert coordinator.discovered_uris["kessel_temperatur"] not in zur_wahl
    assert coordinator.discovered_uris["puffer_volumen"] not in zur_wahl
    assert vorgabe(schritt) == []
    assert schritt["description_placeholders"] == {
        "je_abfrage": "25",
        "hoechstens": "100",
        "intervall": "30",
        "ohne": "",
    }


async def test_auswahl_merkt_sich_art_und_einheit_und_laesst_alles_andere_stehen(monkeypatch, hass, entry):
    hass.session.texte[ZUSTAND] = "Bereit"
    hass.session.menu = hass.session.menu.replace(
        '<object uri="/120/10601/0/0/12421" name="Einstellungen">',
        f'<object uri="{ZUSTAND}" name="Ergänzung"/><object uri="/120/10601/0/0/12421" name="Einstellungen">',
    )
    entry.options = {"puffer_volumen": 900.0, "scan_interval": 60}
    flow = flow_fuer(monkeypatch, hass, entry)
    schritt = await flow.async_step_weitere_werte()
    assert schritt["description_placeholders"]["intervall"] == "60"

    fertig = await flow.async_step_weitere_werte({CONF_WEITERE_WERTE: [EFFEKTIV, ZUSTAND]})

    assert fertig["type"] == "create_entry"
    assert fertig["data"] == {
        "puffer_volumen": 900.0,
        "scan_interval": 60,
        CONF_WEITERE_WERTE: [
            {
                "uri": EFFEKTIV,
                "fub": "PufferFlex",
                "pfad": ["Einstellungen", "Leistungsregelung", "Effektives Puffervolumen"],
                "zahl": True,
                "einheit": "l",
                "stellen": 1,
            },
            {"uri": ZUSTAND, "fub": "PufferFlex", "pfad": ["Ergänzung"], "zahl": False},
        ],
    }


async def test_bisher_gewaehlte_werte_stehen_vorbelegt_und_werden_nicht_neu_gelesen(monkeypatch, hass, entry):
    """Auch ein Wert, den der Menübaum nicht mehr führt, bleibt gewählt, bis man ihn abwählt."""
    verschwunden = {"uri": "/9/9/0/0/1", "fub": "Alt", "pfad": ["Früher"], "zahl": True, "einheit": "kg", "stellen": 0}
    entry.options = {CONF_WEITERE_WERTE: [VOLUMEN, verschwunden]}
    flow = flow_fuer(monkeypatch, hass, entry)

    schritt = await flow.async_step_weitere_werte()
    assert vorgabe(schritt) == [EFFEKTIV, "/9/9/0/0/1"]
    assert angebot(schritt)["/9/9/0/0/1"] == "Alt › Früher"

    hass.session.count = 0
    fertig = await flow.async_step_weitere_werte({CONF_WEITERE_WERTE: [EFFEKTIV, "/9/9/0/0/1"]})
    assert hass.session.count == 0
    assert fertig["data"][CONF_WEITERE_WERTE] == [VOLUMEN, verschwunden]

    leer = await flow.async_step_weitere_werte({CONF_WEITERE_WERTE: []})
    assert leer["data"][CONF_WEITERE_WERTE] == []


async def test_was_die_anlage_nicht_lesbar_liefert_wird_nicht_angenommen(monkeypatch, hass, entry):
    flow = flow_fuer(monkeypatch, hass, entry)
    await flow.async_step_weitere_werte()
    hass.session.fail_uris = ["/user/var/120/10601/0/0/12421"]

    schritt = await flow.async_step_weitere_werte(
        {CONF_WEITERE_WERTE: [EFFEKTIV, "/120/10601/0/0/12421"]}
    )

    assert schritt["type"] == "form"
    assert schritt["errors"] == {"base": "werte_nicht_lesbar"}
    assert schritt["description_placeholders"]["ohne"] == "PufferFlex › Einstellungen"
    assert vorgabe(schritt) == [EFFEKTIV], "der lesbare Wert bleibt gewählt"


async def test_mehr_als_hundert_werte_werden_nicht_angenommen(monkeypatch, hass, entry):
    entry.options = {CONF_WEITERE_WERTE: viele(100)}
    flow = flow_fuer(monkeypatch, hass, entry)
    await flow.async_step_weitere_werte()
    hass.session.count = 0

    schritt = await flow.async_step_weitere_werte(
        {CONF_WEITERE_WERTE: [*(eintrag["uri"] for eintrag in viele(100)), EFFEKTIV]}
    )

    assert schritt["errors"] == {"base": "zu_viele_werte"}
    assert hass.session.count == 0, "gelesen wird dann gar nichts"


async def test_ist_die_anlage_nicht_erreichbar_bricht_der_schritt_ab(monkeypatch, hass, entry):
    hass.session.fail_uris = ["/user/menu"]
    flow = flow_fuer(monkeypatch, hass, entry)

    schritt = await flow.async_step_weitere_werte()

    assert schritt == {"type": "abort", "reason": "cannot_connect"}


async def test_einstellungen_speichern_behaelt_die_gewaehlten_werte(monkeypatch):
    """Die Optionen werden beim Speichern ersetzt - die Auswahl steht in keinem der anderen Formulare."""
    bisher = {**optionen(), CONF_WEITERE_WERTE: [VOLUMEN]}
    flow, ergebnis = await options_schritt(monkeypatch, bisher, optionen())
    for _ in range(4):
        if ergebnis["type"] == "create_entry":
            break
        ergebnis = await getattr(flow, f"async_step_{ergebnis['step_id']}")(
            {str(feld): feld.default() for feld in ergebnis["data_schema"].schema}
        )

    assert ergebnis["type"] == "create_entry"
    assert ergebnis["data"][CONF_WEITERE_WERTE] == [VOLUMEN]
