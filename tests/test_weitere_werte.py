"""Weitere Werte: frei aus dem Menübaum gewählte Werte, nur gelesen.

Der Nutzer wählt sie unter Konfigurieren. Jeder wird ein Sensor, dessen
Name der Weg im Menübaum ist und dessen Art und Einheit die Anlage beim
Auswählen genannt hat. Gelesen werden sie getrennt von den festen
Werten, im eigenen Takt und in Portionen, reihum eine je Abfrage. Wie
viele Werte eine Abfrage liest und in welchem Abstand, stellt der Nutzer
mit zwei Schiebereglern ein - ab Werk 25 Werte im Abstand des
Abfrageintervalls.
"""

from __future__ import annotations

import pytest

from eta_heating_ws import entitaet_vorgesehen
from eta_heating_ws import weitere_werte as weitere
from eta_heating_ws.api import ETAValue
from eta_heating_ws.const import (
    CONF_WEITERE_INTERVALL,
    CONF_WEITERE_JE_ABFRAGE,
    CONF_WEITERE_SCHNELL,
    CONF_WEITERE_WERTE,
)

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


def angebot(schritt) -> dict[str, dict[str, str]]:
    """Je Auswahlfeld des Schritts Adresse und Name der Werte, die es zur Wahl stellt."""
    return {
        str(feld): {eintrag["value"]: eintrag["label"] for eintrag in auswahl.config["options"]}
        for feld, auswahl in schritt["data_schema"].schema.items()
        if "options" in auswahl.config
    }


def vorgabe(schritt, name: str):
    """Womit ein Feld des Schritts vorbelegt ist."""
    [feld] = [feld for feld in schritt["data_schema"].schema if feld == name]
    return feld.default()


def vorgaben(schritt) -> dict:
    """Die Vorbelegung aller Felder eines Schritts - so, als bestätigte man ihn unverändert."""
    return {str(feld): feld.default() for feld in schritt["data_schema"].schema}


def regler(schritt, name: str) -> dict:
    """Grenzen, Schritt und Art eines der beiden Schieberegler."""
    return dict(schritt["data_schema"].schema[name].config)


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


def test_gleiche_namen_an_derselben_stelle_bekommen_eine_nummer():
    """Sonst hießen zwei Sensoren gleich - der Menübaum einer echten Anlage führt solche Paare."""
    baum = {
        "eta": {
            "menu": {
                "fub": {
                    "@name": "Solar",
                    "object": {
                        "@name": "Vorlauf",
                        "@uri": "/1/2/0/7/0",
                        "object": [
                            {"@name": "Sensor Typ", "@uri": "/1/2/0/7/1"},
                            {"@name": "Sensor Typ", "@uri": "/1/2/0/7/2"},
                            {"@name": "Sensor Typ", "@uri": "/1/2/0/7/3"},
                        ],
                    },
                }
            }
        }
    }
    werte = weitere.menue_werte(baum)
    assert [weitere.bezeichnung(eintrag) for eintrag in werte.values()] == [
        "Solar › Vorlauf",
        "Solar › Vorlauf › Sensor Typ",
        "Solar › Vorlauf › Sensor Typ (2)",
        "Solar › Vorlauf › Sensor Typ (3)",
    ]


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


def test_groesse_der_portion_und_abstand_sind_einstellbar():
    werte = {f"wert_{n}": f"/1/{n}" for n in range(60)}
    assert [len(portion) for portion in weitere.portionen(werte, 50)] == [50, 10]
    assert weitere.abfrage_alle(60, 20, 50) == 40
    assert weitere.abfrage_alle(60, 120, 100) == 120


@pytest.mark.parametrize("eingestellt, erwartet", [(None, 25), (50, 50), (5, 20), (500, 100), ("x", 25), (47.0, 47)])
def test_werte_je_abfrage_bleiben_in_ihren_grenzen(eingestellt, erwartet):
    assert weitere.je_abfrage(eingestellt) == erwartet


@pytest.mark.parametrize(
    "eingestellt, abfrageintervall, erwartet",
    [(None, 30, 30), (None, 3, 10), (None, 900, 600), (45, 30, 45), (1000, 30, 600), (2, 30, 10)],
)
def test_abstand_folgt_ohne_einstellung_dem_abfrageintervall(eingestellt, abfrageintervall, erwartet):
    assert weitere.intervall(eingestellt, abfrageintervall) == erwartet


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
    """Je Abfrage eine Portion - die Last für die Anlage wächst nicht mit der Zahl der Werte."""
    entry.options = {CONF_WEITERE_WERTE: viele(30)}
    coordinator, _ = await setup_integration(hass, entry)
    schluessel = list(coordinator.weitere_werte)
    assert coordinator.weitere_abfrage_alle == 60

    assert all(key in coordinator.data for key in schluessel[:25])
    assert not any(key in coordinator.data for key in schluessel[25:]), "die zweite Portion ist noch nicht dran"
    assert hass.weitere_abstaende == [5.0], "nach dem Start kommt sie schon nach 5 Sekunden"

    hass.session.count = 0
    await hass.weitere_takt(None)
    assert all(key in coordinator.data for key in schluessel)
    assert len(hass.session.varsets["hw1testeintrag"]) == 5
    assert hass.weitere_abstaende == [5.0, 30.0], "danach im eingestellten Abstand"

    hass.session.count = 0
    await hass.weitere_takt(None)
    assert hass.session.count == 1, "eine Anfrage je Portion"

    hass.session.count = 0
    await coordinator.async_refresh()
    assert hass.session.count <= 2, "die volle Abfrage liest die weiteren Werte nicht mit"


async def test_eingestellte_groesse_und_eingestellter_abstand_gelten(hass, entry):
    entry.options = {
        CONF_WEITERE_WERTE: viele(60),
        CONF_WEITERE_JE_ABFRAGE: 50,
        CONF_WEITERE_INTERVALL: 120,
    }

    coordinator, by_name = await setup_integration(hass, entry)

    assert coordinator.weitere_je_abfrage == 50
    assert coordinator.weitere_intervall == 120
    assert coordinator.weitere_abfrage_alle == 240
    assert len(hass.session.varsets["hw0testeintrag"]) == 50
    assert by_name["Test › Wert 1"].extra_state_attributes["abfrage_alle"] == 240
    await hass.weitere_takt(None)
    assert hass.weitere_abstaende == [5.0, 120.0]


async def test_ohne_gewaehlte_werte_laeuft_kein_eigener_takt(hass, entry):
    await setup_integration(hass, entry)

    assert hass.weitere_takt is None
    assert hass.weitere_abstaende == []


async def test_beim_entladen_endet_der_takt(hass, entry):
    entry.options = {CONF_WEITERE_WERTE: [VOLUMEN]}
    await setup_integration(hass, entry)
    assert hass.weitere_abstaende == [30.0], "eine Portion, schon gelesen - also gleich der eingestellte Abstand"

    for abmelden in entry._unload_callbacks:
        abmelden()

    assert hass.weitere_abbestellt == [30.0]


async def test_ein_unerwarteter_fehler_beendet_den_takt(hass, entry, monkeypatch):
    """Sonst stünde er bei jedem Takt im Protokoll."""
    entry.options = {CONF_WEITERE_WERTE: [VOLUMEN]}
    coordinator, _ = await setup_integration(hass, entry)

    async def kaputt():
        raise RuntimeError("unerwartet")

    monkeypatch.setattr(coordinator, "async_weitere_lesen", kaputt)
    await hass.weitere_takt(None)

    assert hass.weitere_abstaende == [30.0], "nicht neu bestellt"


async def test_ist_die_anlage_nicht_erreichbar_ruht_die_abfrage(hass, entry):
    entry.options = {CONF_WEITERE_WERTE: [VOLUMEN]}
    coordinator, _ = await setup_integration(hass, entry)
    coordinator.last_update_success = False
    hass.session.count = 0

    await hass.weitere_takt(None)

    assert hass.session.count == 0
    assert hass.weitere_abstaende == [30.0, 30.0], "der Takt läuft weiter"


async def test_bleibt_ein_wert_aus_gilt_er_nach_dem_zweiten_mal_als_nicht_erreichbar(hass, entry):
    entry.options = {CONF_WEITERE_WERTE: [VOLUMEN, TEXT]}
    hass.session.texte[ZUSTAND] = "Bereit"
    coordinator, by_name = await setup_integration(hass, entry)
    text = by_name["PufferFlex › Sonstiges › Ergänzung"]
    hass.session.varsets["hw0testeintrag"].remove(ZUSTAND)

    await hass.weitere_takt(None)
    assert text.available is True
    assert text.native_value == "Bereit", "der letzte Wert bleibt stehen"

    await hass.weitere_takt(None)
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
    await hass.weitere_takt(None)
    assert wert.available is True


async def test_kennt_die_anlage_den_variablensatz_nicht_mehr_wird_er_neu_angelegt(hass, entry):
    """Sie hält ihn nur im Arbeitsspeicher - nach ihrem Neustart ist er weg."""
    entry.options = {CONF_WEITERE_WERTE: [VOLUMEN]}
    coordinator, by_name = await setup_integration(hass, entry)
    del hass.session.varsets["hw0testeintrag"]

    await hass.weitere_takt(None)

    assert hass.session.varsets["hw0testeintrag"] == [EFFEKTIV]
    wert = by_name["PufferFlex › Einstellungen › Leistungsregelung › Effektives Puffervolumen"]
    assert wert.available is True


async def test_beim_entladen_verschwinden_die_variablensaetze(hass, entry):
    entry.options = {CONF_WEITERE_WERTE: viele(30)}
    coordinator, _ = await setup_integration(hass, entry)
    await hass.weitere_takt(None)
    assert {"hw0testeintrag", "hw1testeintrag"} <= set(hass.session.varsets)

    await coordinator.async_varset_aufraeumen()

    assert not [name for name in hass.session.varsets if name.startswith("hw")]
    hass.session.count = 0
    await hass.weitere_takt(None)
    assert hass.session.count == 0, "danach liest der Takt nicht mehr"


async def test_schnell_gewaehlte_werte_liest_zusaetzlich_die_schnelle_abfrage(hass, entry):
    """Sie bleiben in ihrer Portion und werden dazwischen im schnellen Takt aufgefrischt."""
    hass.session.texte[ZUSTAND] = "Bereit"
    entry.options = {CONF_WEITERE_WERTE: [{**VOLUMEN, "schnell": True}, TEXT]}

    coordinator, by_name = await setup_integration(hass, entry)

    schnell = by_name["PufferFlex › Einstellungen › Leistungsregelung › Effektives Puffervolumen"]
    normal = by_name["PufferFlex › Sonstiges › Ergänzung"]
    assert coordinator.schnelle_uris["wert_120_10601_0_0_12499"] == EFFEKTIV
    assert "wert_120_10601_0_0_77777" not in coordinator.schnelle_uris
    assert schnell.extra_state_attributes["abfrage_alle"] == 3
    assert normal.extra_state_attributes["abfrage_alle"] == 30
    assert hass.session.varsets["hw0testeintrag"] == [EFFEKTIV, ZUSTAND], "die Portion bleibt vollständig"

    await hass.schnelltakt(None)
    assert EFFEKTIV in hass.session.varsets["hstesteintrag"]
    assert ZUSTAND not in hass.session.varsets["hstesteintrag"]
    assert schnell.native_value == 825


async def test_ohne_schnelle_abfrage_bleibt_es_beim_eigenen_takt(hass, entry):
    entry.data["schnell_intervall"] = 0
    entry.options = {CONF_WEITERE_WERTE: [{**VOLUMEN, "schnell": True}]}

    _, by_name = await setup_integration(hass, entry)

    wert = by_name["PufferFlex › Einstellungen › Leistungsregelung › Effektives Puffervolumen"]
    assert wert.extra_state_attributes["abfrage_alle"] == 30
    assert hass.schnelltakt is None


async def test_diagnose_nennt_die_gewaehlten_werte(hass, entry):
    from eta_heating_ws.diagnostics import async_get_config_entry_diagnostics

    hass.session.texte[ZUSTAND] = "Bereit"
    entry.options = {CONF_WEITERE_WERTE: [{**VOLUMEN, "schnell": True}, TEXT]}
    await setup_integration(hass, entry)

    diagnose = await async_get_config_entry_diagnostics(hass, entry)

    assert diagnose["weitere_werte"] == {
        "je_abfrage": 25,
        "abstand": 30.0,
        "abfrage_alle": 30.0,
        "werte": [
            {
                "name": "PufferFlex › Einstellungen › Leistungsregelung › Effektives Puffervolumen",
                "adresse": EFFEKTIV,
                "art": "Zahl",
                "einheit": "l",
                "schnell": True,
                "wert": 825.0,
                "status": "ok",
            },
            {
                "name": "PufferFlex › Sonstiges › Ergänzung",
                "adresse": ZUSTAND,
                "art": "Text",
                "einheit": "",
                "schnell": False,
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


async def test_schritt_zeigt_je_funktionsblock_ein_feld_ohne_die_festen_sensoren(monkeypatch, hass, entry):
    """Das Feld heißt wie der Funktionsblock, die Werte darin wie ihr Weg im Menübaum."""
    coordinator, _ = await setup_integration(hass, entry)
    flow = flow_fuer(monkeypatch, hass, entry)

    schritt = await flow.async_step_weitere_werte()

    assert schritt["step_id"] == "weitere_werte"
    assert schritt["last_step"] is False
    zur_wahl = angebot(schritt)
    assert "PufferFlex" in zur_wahl and "Kessel" in zur_wahl
    assert zur_wahl["PufferFlex"][EFFEKTIV] == "Einstellungen › Leistungsregelung › Effektives Puffervolumen"
    alle = {uri for werte in zur_wahl.values() for uri in werte}
    assert coordinator.discovered_uris["kessel_temperatur"] not in alle
    assert coordinator.discovered_uris["puffer_volumen"] not in alle
    assert all(wert == [] for wert in vorgaben(schritt).values())
    assert schritt["description_placeholders"] == {"hoechstens": "100", "ohne": ""}


async def test_auswahl_fuehrt_zum_takt_und_merkt_sich_art_und_einheit(monkeypatch, hass, entry):
    """Gespeichert wird erst im zweiten Schritt - alle anderen Einstellungen bleiben, wie sie sind."""
    hass.session.texte[ZUSTAND] = "Bereit"
    hass.session.menu = hass.session.menu.replace(
        '<object uri="/120/10601/0/0/12421" name="Einstellungen">',
        f'<object uri="{ZUSTAND}" name="Ergänzung"/><object uri="/120/10601/0/0/12421" name="Einstellungen">',
    )
    entry.options = {"puffer_volumen": 900.0, "scan_interval": 60}
    flow = flow_fuer(monkeypatch, hass, entry)
    await flow.async_step_weitere_werte()

    takt = await flow.async_step_weitere_werte({"PufferFlex": [EFFEKTIV, ZUSTAND]})

    assert takt["step_id"] == "weitere_takt"
    assert takt["description_placeholders"] == {"gewaehlt": "2", "dauer": "60", "schnell_hoechstens": "10"}
    assert angebot(takt) == {
        CONF_WEITERE_SCHNELL: {
            EFFEKTIV: "PufferFlex › Einstellungen › Leistungsregelung › Effektives Puffervolumen",
            ZUSTAND: "PufferFlex › Ergänzung",
        }
    }, "für die schnelle Abfrage stehen nur die eben gewählten Werte zur Wahl"
    assert vorgaben(takt) == {
        CONF_WEITERE_SCHNELL: [],
        CONF_WEITERE_JE_ABFRAGE: 25,
        CONF_WEITERE_INTERVALL: 60,
    }, "ab Werk 25 Werte im Abstand der festen Werte"
    je_abfrage = regler(takt, CONF_WEITERE_JE_ABFRAGE)
    assert (je_abfrage["min"], je_abfrage["max"], je_abfrage["step"], je_abfrage["mode"]) == (20, 100, 5, "slider")
    abstand = regler(takt, CONF_WEITERE_INTERVALL)
    assert (abstand["min"], abstand["max"], abstand["step"], abstand["mode"]) == (10, 600, 5, "slider")
    assert abstand["unit_of_measurement"] == "s"

    fertig = await flow.async_step_weitere_takt(vorgaben(takt))

    assert fertig["type"] == "create_entry"
    assert fertig["data"] == {
        "puffer_volumen": 900.0,
        "scan_interval": 60,
        CONF_WEITERE_JE_ABFRAGE: 25,
        CONF_WEITERE_INTERVALL: 60,
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


async def test_die_regler_werden_gespeichert_und_stehen_danach_vorbelegt(monkeypatch, hass, entry):
    entry.options = {CONF_WEITERE_WERTE: viele(60)}
    flow = flow_fuer(monkeypatch, hass, entry)
    auswahl = await flow.async_step_weitere_werte()
    takt = await flow.async_step_weitere_werte(vorgaben(auswahl))
    assert takt["description_placeholders"]["gewaehlt"] == "60"
    assert takt["description_placeholders"]["dauer"] == "90", "drei Portionen zu 25 im Abstand von 30 Sekunden"

    fertig = await flow.async_step_weitere_takt(
        {CONF_WEITERE_SCHNELL: [], CONF_WEITERE_JE_ABFRAGE: 50.0, CONF_WEITERE_INTERVALL: 120.0}
    )

    assert fertig["data"][CONF_WEITERE_JE_ABFRAGE] == 50
    assert fertig["data"][CONF_WEITERE_INTERVALL] == 120
    assert len(fertig["data"][CONF_WEITERE_WERTE]) == 60

    entry.options = fertig["data"]
    wieder = flow_fuer(monkeypatch, hass, entry)
    auswahl = await wieder.async_step_weitere_werte()
    takt = await wieder.async_step_weitere_werte(vorgaben(auswahl))
    assert vorgabe(takt, CONF_WEITERE_JE_ABFRAGE) == 50
    assert vorgabe(takt, CONF_WEITERE_INTERVALL) == 120
    assert takt["description_placeholders"]["dauer"] == "240"


async def test_schnell_waehlen_merkt_es_am_wert(monkeypatch, hass, entry):
    entry.options = {CONF_WEITERE_WERTE: [{**VOLUMEN, "schnell": True}, viele(1)[0]]}
    flow = flow_fuer(monkeypatch, hass, entry)
    auswahl = await flow.async_step_weitere_werte()
    assert vorgaben(auswahl)["PufferFlex"] == [EFFEKTIV]
    assert vorgaben(auswahl)["Test"] == ["/9/9/0/0/1"]

    takt = await flow.async_step_weitere_werte(vorgaben(auswahl))
    assert vorgabe(takt, CONF_WEITERE_SCHNELL) == [EFFEKTIV]

    fertig = await flow.async_step_weitere_takt(
        {**vorgaben(takt), CONF_WEITERE_SCHNELL: ["/9/9/0/0/1", "/nicht/gewaehlt"]}
    )

    gespeichert = {eintrag["uri"]: eintrag for eintrag in fertig["data"][CONF_WEITERE_WERTE]}
    assert list(gespeichert) == [EFFEKTIV, "/9/9/0/0/1"]
    assert "schnell" not in gespeichert[EFFEKTIV], "abgewählt"
    assert gespeichert["/9/9/0/0/1"]["schnell"] is True
    assert CONF_WEITERE_SCHNELL not in fertig["data"], "steht an den Werten, nicht eigens"


async def test_mehr_als_zehn_schnelle_werte_werden_nicht_angenommen(monkeypatch, hass, entry):
    entry.options = {CONF_WEITERE_WERTE: viele(20)}
    flow = flow_fuer(monkeypatch, hass, entry)
    auswahl = await flow.async_step_weitere_werte()
    takt = await flow.async_step_weitere_werte(vorgaben(auswahl))
    alle = [eintrag["uri"] for eintrag in viele(20)]

    schritt = await flow.async_step_weitere_takt({**vorgaben(takt), CONF_WEITERE_SCHNELL: alle[:11]})
    assert schritt["errors"] == {"base": "zu_viele_schnelle_werte"}
    assert vorgabe(schritt, CONF_WEITERE_SCHNELL) == alle[:11], "die Auswahl bleibt zum Kürzen stehen"

    fertig = await flow.async_step_weitere_takt({**vorgaben(takt), CONF_WEITERE_SCHNELL: alle[:10]})
    assert fertig["type"] == "create_entry"
    assert sum(1 for eintrag in fertig["data"][CONF_WEITERE_WERTE] if eintrag.get("schnell")) == 10


async def test_bisher_gewaehlte_werte_stehen_vorbelegt_und_werden_nicht_neu_gelesen(monkeypatch, hass, entry):
    """Auch ein Wert, den der Menübaum nicht mehr führt, bleibt gewählt, bis man ihn abwählt."""
    verschwunden = {"uri": "/9/9/0/0/1", "fub": "Alt", "pfad": ["Früher"], "zahl": True, "einheit": "kg", "stellen": 0}
    entry.options = {CONF_WEITERE_WERTE: [VOLUMEN, verschwunden]}
    flow = flow_fuer(monkeypatch, hass, entry)

    schritt = await flow.async_step_weitere_werte()
    assert vorgaben(schritt)["PufferFlex"] == [EFFEKTIV]
    assert vorgaben(schritt)["Alt"] == ["/9/9/0/0/1"], "sein Funktionsblock bekommt ein eigenes Feld"
    assert angebot(schritt)["Alt"] == {"/9/9/0/0/1": "Früher"}

    hass.session.count = 0
    takt = await flow.async_step_weitere_werte(vorgaben(schritt))
    fertig = await flow.async_step_weitere_takt(vorgaben(takt))
    assert hass.session.count == 0
    assert fertig["data"][CONF_WEITERE_WERTE] == [VOLUMEN, verschwunden]


async def test_ohne_auswahl_wird_gleich_gespeichert(monkeypatch, hass, entry):
    """Ohne Werte gibt es keinen Takt zu stellen - der bisherige bleibt für später stehen."""
    entry.options = {CONF_WEITERE_WERTE: [VOLUMEN], CONF_WEITERE_JE_ABFRAGE: 50, CONF_WEITERE_INTERVALL: 120}
    flow = flow_fuer(monkeypatch, hass, entry)
    schritt = await flow.async_step_weitere_werte()

    leer = await flow.async_step_weitere_werte({fub: [] for fub in vorgaben(schritt)})

    assert leer["type"] == "create_entry"
    assert leer["data"] == {CONF_WEITERE_WERTE: [], CONF_WEITERE_JE_ABFRAGE: 50, CONF_WEITERE_INTERVALL: 120}


async def test_was_die_anlage_nicht_lesbar_liefert_wird_nicht_angenommen(monkeypatch, hass, entry):
    flow = flow_fuer(monkeypatch, hass, entry)
    await flow.async_step_weitere_werte()
    hass.session.fail_uris = ["/user/var/120/10601/0/0/12421"]

    schritt = await flow.async_step_weitere_werte({"PufferFlex": [EFFEKTIV, "/120/10601/0/0/12421"]})

    assert schritt["type"] == "form"
    assert schritt["step_id"] == "weitere_werte"
    assert schritt["errors"] == {"base": "werte_nicht_lesbar"}
    assert schritt["description_placeholders"]["ohne"] == "PufferFlex › Einstellungen"
    assert vorgaben(schritt)["PufferFlex"] == [EFFEKTIV], "der lesbare Wert bleibt gewählt"


async def test_mehr_als_hundert_werte_werden_nicht_angenommen(monkeypatch, hass, entry):
    entry.options = {CONF_WEITERE_WERTE: viele(100)}
    flow = flow_fuer(monkeypatch, hass, entry)
    schritt = await flow.async_step_weitere_werte()
    hass.session.count = 0

    zu_viele = await flow.async_step_weitere_werte({**vorgaben(schritt), "PufferFlex": [EFFEKTIV]})

    assert zu_viele["errors"] == {"base": "zu_viele_werte"}
    assert hass.session.count == 0, "gelesen wird dann gar nichts"


async def test_ist_die_anlage_nicht_erreichbar_bricht_der_schritt_ab(monkeypatch, hass, entry):
    hass.session.fail_uris = ["/user/menu"]
    flow = flow_fuer(monkeypatch, hass, entry)

    schritt = await flow.async_step_weitere_werte()

    assert schritt == {"type": "abort", "reason": "cannot_connect"}


async def test_einstellungen_speichern_behaelt_die_gewaehlten_werte(monkeypatch):
    """Die Optionen werden beim Speichern ersetzt - die Auswahl steht in keinem der anderen Formulare."""
    bisher = {
        **optionen(),
        CONF_WEITERE_WERTE: [VOLUMEN],
        CONF_WEITERE_JE_ABFRAGE: 50,
        CONF_WEITERE_INTERVALL: 120,
    }
    flow, ergebnis = await options_schritt(monkeypatch, bisher, optionen())
    for _ in range(4):
        if ergebnis["type"] == "create_entry":
            break
        ergebnis = await getattr(flow, f"async_step_{ergebnis['step_id']}")(
            {str(feld): feld.default() for feld in ergebnis["data_schema"].schema}
        )

    assert ergebnis["type"] == "create_entry"
    assert ergebnis["data"][CONF_WEITERE_WERTE] == [VOLUMEN]
    assert ergebnis["data"][CONF_WEITERE_JE_ABFRAGE] == 50
    assert ergebnis["data"][CONF_WEITERE_INTERVALL] == 120
