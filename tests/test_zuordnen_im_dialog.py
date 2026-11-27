"""Die Dialogschritte rund um ältere Anlagen: die Auswahl zum Schluss und das Zuordnen von Hand.

Gegen den Menübaum des Stückholzkessels aus Issue 11, siehe
test_fehlende_werte.py. Die Attrappe der Anlage meldet zu jeder Adresse,
die ein Test nicht eigens belegt, 55,5 °C.
"""

from __future__ import annotations

from eta_heating_ws import config_flow as modul
from eta_heating_ws.const import (
    CONF_FEHLENDE_AUSBLENDEN,
    CONF_WEITERE_INTERVALL,
    CONF_WEITERE_JE_ABFRAGE,
    CONF_WEITERE_WERTE,
    CONF_ZUORDNUNGEN,
    SENSORS,
)

from .conftest import FIXTURES
from .test_config_flow import config_flow_fuer, optionen, options_schritt
from .test_fehlende_werte import (
    FEHLT_AM_STUECKHOLZKESSEL,
    KESSEL,
    PUFFER,
    STUECKHOLZ,
    VERMUTET,
    VERMUTUNGEN,
    einrichtung,
)
from .test_sensors import setup_integration
from .test_weitere_werte import flow_fuer

LEISTUNG = f"{KESSEL}/0/0/12204"
"""Kessel > Kessel > Angeforderte Leistung - in den Tests der Eintrag, der einen Druck meldet."""
DRUCK = {"value": "16", "str_value": "1,6", "unit": "bar", "scale": "10"}
NAMEN = {"kessel": "Kessel", "pufferflex": "Puffer", "sys": "Sys"}
OHNE_KESSEL = (FIXTURES / "menu_warmwasser.xml").read_text(encoding="utf-8")
"""Der Menübaum einer Testanlage, die keinen Funktionsblock Kessel führt."""


def am_ende_der_einrichtung(monkeypatch, hass, menu=STUECKHOLZ, komponenten=("kessel", "puffer")):
    """Die Ersteinrichtung nach ihrem letzten Schritt der Anlage."""
    hass.session.menu = menu
    flow = config_flow_fuer(monkeypatch, hass)
    flow._online = True
    flow._data = {
        "host": "192.0.2.10",
        "port": 8080,
        "components": list(komponenten),
        "fub_names": dict(NAMEN),
        "scan_interval": 30,
    }
    return flow


def konfigurieren(monkeypatch, hass, entry, menu=STUECKHOLZ):
    """Der Dialog Konfigurieren zu dieser Einrichtung, mit deutschen Namen der Messwerte."""
    hass.session.menu = menu

    async def namen(_hass, schluessel):
        return {key: SENSORS[key]["name"] for key in schluessel}

    monkeypatch.setattr(modul, "_sensor_namen", namen)
    return flow_fuer(monkeypatch, hass, entry)


def felder(schritt) -> dict:
    return {str(feld): feld for feld in schritt["data_schema"].schema}


def zur_wahl(schritt, feld: str) -> dict[str, str]:
    """Adresse und Beschriftung der Einträge, die ein Feld des Schritts zur Wahl stellt."""
    auswahl = schritt["data_schema"].schema[felder(schritt)[feld]].config["options"]
    return {eintrag["value"]: eintrag["label"] for eintrag in auswahl}


def vorgewaehlt(schritt, feld: str):
    return felder(schritt)[feld].description["suggested_value"]


async def test_zum_schluss_steht_eine_auswahl(monkeypatch, hass):
    flow = am_ende_der_einrichtung(monkeypatch, hass)

    schritt = await flow._abschluss()

    assert schritt == {
        "type": "menu",
        "step_id": "abschluss",
        "menu_options": ["fertig", "weitere_werte", "fehlende_werte"],
    }
    fertig = await flow.async_step_fertig()
    assert fertig["type"] == "create_entry"
    assert fertig["title"] == "ETA Heizung"
    assert CONF_ZUORDNUNGEN not in fertig["data"]
    assert CONF_WEITERE_WERTE not in fertig["data"]


async def test_gibt_es_nichts_zuzuordnen_steht_das_zuordnen_nicht_zur_wahl(monkeypatch, hass):
    """Eine Anlage ohne den Funktionsblock Kessel: Wo kein Block ist, gibt es keine Einträge."""
    flow = am_ende_der_einrichtung(monkeypatch, hass, OHNE_KESSEL, ("ww",))
    flow._data["fub_names"] = {}

    schritt = await flow._abschluss()

    assert schritt["step_id"] == "abschluss"
    assert flow._kandidaten == {}
    assert schritt["menu_options"] == ["fertig", "weitere_werte"]


async def test_antwortet_die_anlage_nicht_ist_die_einrichtung_gleich_fertig(monkeypatch, hass):
    flow = am_ende_der_einrichtung(monkeypatch, hass)
    flow._online = False
    assert (await flow._abschluss())["type"] == "create_entry"
    assert hass.session.count == 0, "gefragt wird die Anlage dann gar nicht"

    flow = am_ende_der_einrichtung(monkeypatch, hass)
    hass.session.fail_uris = ["/user/menu"]
    assert (await flow._abschluss())["type"] == "create_entry"


async def test_fehlende_werte_von_hand_zuordnen(monkeypatch, hass):
    hass.session.werte[LEISTUNG] = DRUCK
    flow = am_ende_der_einrichtung(monkeypatch, hass)
    await flow._abschluss()

    auswahl = await flow.async_step_fehlende_werte()

    assert auswahl["step_id"] == "fehlende_werte"
    assert auswahl["last_step"] is False
    assert zur_wahl(auswahl, "werte") == {
        **FEHLT_AM_STUECKHOLZKESSEL,
        "puffer_ladepumpe": "Puffer Ladepumpe",
        "puffer_warmwasser": "Puffer Warmwasser",
        "puffer_warmwasser_zustand": "Puffer Warmwasser Zustand",
    }
    assert felder(auswahl)["werte"].default() == [], "kein Vorschlag, nichts zugeordnet"
    gelesen = hass.session.count

    zuordnen = await flow.async_step_fehlende_werte(
        {"werte": ["kessel_druck", "pellet_gesamtverbrauch", "kessel_schalter"]}
    )

    assert zuordnen["step_id"] == "werte_zuordnen"
    assert list(felder(zuordnen)) == ["Kesseldruck"]
    assert zur_wahl(zuordnen, "Kesseldruck") == {
        LEISTUNG: "Kessel › Kessel › Angeforderte Leistung (1,6 bar)"
    }
    assert vorgewaehlt(zuordnen, "Kesseldruck") is None
    assert zuordnen["errors"] == {"base": "ohne_passenden_eintrag"}
    assert zuordnen["description_placeholders"] == {"ohne": "Pellet Gesamtverbrauch"}
    assert hass.session.count - gelesen == 25, "der Block Kessel ohne die 9 schon genutzten Adressen"

    zurueck = await flow.async_step_werte_zuordnen({"Kesseldruck": LEISTUNG})

    assert zurueck["step_id"] == "abschluss"
    assert flow._data[CONF_ZUORDNUNGEN] == {"kessel_druck": LEISTUNG}
    assert "kessel_druck" in flow._kandidaten, "eine Zuordnung lässt sich wieder ändern"
    fertig = await flow.async_step_fertig()
    assert fertig["data"][CONF_ZUORDNUNGEN] == {"kessel_druck": LEISTUNG}


async def test_eine_zuordnung_laesst_sich_aendern_und_aufheben(monkeypatch, hass):
    hass.session.werte[LEISTUNG] = DRUCK
    hass.session.werte[f"{KESSEL}/0/0/12006"] = {**DRUCK, "str_value": "2,0"}
    flow = am_ende_der_einrichtung(monkeypatch, hass)
    flow._data[CONF_ZUORDNUNGEN] = {
        "kessel_druck": LEISTUNG,
        "ruecklauf_temperatur": f"{KESSEL}/0/11163/2121",
    }
    await flow._abschluss()

    auswahl = await flow.async_step_fehlende_werte()
    assert felder(auswahl)["werte"].default() == ["ruecklauf_temperatur", "kessel_druck"]
    assert zur_wahl(auswahl, "werte")["ruecklauf_temperatur"] == "Rücklauftemperatur"

    zuordnen = await flow.async_step_fehlende_werte({"werte": ["kessel_druck"]})
    assert vorgewaehlt(zuordnen, "Kesseldruck") == LEISTUNG
    assert list(zur_wahl(zuordnen, "Kesseldruck")) == [LEISTUNG, f"{KESSEL}/0/0/12006"]

    await flow.async_step_werte_zuordnen({"Kesseldruck": f"{KESSEL}/0/0/12006"})
    assert flow._data[CONF_ZUORDNUNGEN] == {
        "ruecklauf_temperatur": f"{KESSEL}/0/11163/2121",
        "kessel_druck": f"{KESSEL}/0/0/12006",
    }, "was nicht gewählt war, behält seine Zuordnung"

    await flow.async_step_fehlende_werte({"werte": ["kessel_druck", "ruecklauf_temperatur"]})
    await flow.async_step_werte_zuordnen({})
    assert CONF_ZUORDNUNGEN not in flow._data, "ein leeres Feld hebt die Zuordnung auf"
    fertig = await flow.async_step_fertig()
    assert CONF_ZUORDNUNGEN not in fertig["data"]


async def test_zur_wahl_stehen_nur_passende_und_noch_freie_eintraege(monkeypatch, hass):
    """Eine Temperatur bekommt Temperaturen - ohne die, die schon ein fester Sensor liest."""
    hass.session.texte[f"{PUFFER}/0/0/12668"] = "Unten"
    flow = am_ende_der_einrichtung(monkeypatch, hass)
    await flow._abschluss()

    zuordnen = await flow.async_step_fehlende_werte(
        {"werte": ["puffer_warmwasser", "puffer_warmwasser_zustand"]}
    )

    temperaturen = zur_wahl(zuordnen, "Puffer Warmwasser")
    assert temperaturen[f"{PUFFER}/0/0/12211"] == "Puffer › Puffer oben › Puffer oben Min (55,5 °C)"
    for belegt in ("12242", "12522", "12244", "12528", "12207"):
        assert f"{PUFFER}/0/0/{belegt}" not in temperaturen, "Fühler, Ladezustand und Zustand"
    assert f"{PUFFER}/0/0/12668" not in temperaturen, "ein Text"
    assert not any("/12130/0/10" in uri for uri in temperaturen), "die Zeitfenster"
    assert zur_wahl(zuordnen, "Puffer Warmwasser Zustand") == {
        f"{PUFFER}/0/0/12668": "Puffer › Anfahrentlastung (Unten)"
    }
    assert zuordnen["errors"] == {}


async def test_ein_vorschlag_ist_vorgewaehlt_wenn_seine_einheit_passt(monkeypatch, hass):
    """Die Vermutung aus FLEXIBLE_PFAD_MUSTER: vorgewählt, aber erst mit dem Absenden übernommen."""
    hass.session.texte[VERMUTET["kessel_zustand"]] = "Heizen"
    hass.session.werte[VERMUTET["restsauerstoff"]] = {
        "value": "50",
        "str_value": "5,0",
        "unit": "%",
        "scale": "10",
    }
    flow = am_ende_der_einrichtung(monkeypatch, hass, VERMUTUNGEN, ("kessel",))
    flow._data["fub_names"] = {"kessel": "Kessel", "sys": "Sys"}
    await flow._abschluss()

    auswahl = await flow.async_step_fehlende_werte()
    assert set(felder(auswahl)["werte"].default()) == set(VERMUTET)

    zuordnen = await flow.async_step_fehlende_werte({"werte": list(VERMUTET)})

    assert vorgewaehlt(zuordnen, "Kesseltemperatur") == VERMUTET["kessel_temperatur"]
    assert vorgewaehlt(zuordnen, "Rücklauftemperatur") == VERMUTET["ruecklauf_temperatur"]
    assert vorgewaehlt(zuordnen, "Restsauerstoff") == VERMUTET["restsauerstoff"]
    assert vorgewaehlt(zuordnen, "Kessel Zustand") == VERMUTET["kessel_zustand"]
    assert "Kesseldruck" not in felder(zuordnen), "der Vorschlag meldet °C statt bar"
    assert zuordnen["description_placeholders"] == {"ohne": "Kesseldruck"}
    assert CONF_ZUORDNUNGEN not in flow._data

    eingabe = {name: vorgewaehlt(zuordnen, name) for name in felder(zuordnen)}
    await flow.async_step_werte_zuordnen(eingabe)
    assert flow._data[CONF_ZUORDNUNGEN] == {
        key: uri for key, uri in VERMUTET.items() if key != "kessel_druck"
    }


async def test_ohne_gewaehlten_wert_geht_es_zurueck_zur_auswahl(monkeypatch, hass):
    flow = am_ende_der_einrichtung(monkeypatch, hass)
    await flow._abschluss()
    gelesen = hass.session.count

    zurueck = await flow.async_step_fehlende_werte({"werte": []})

    assert zurueck["step_id"] == "abschluss"
    assert hass.session.count == gelesen, "gelesen wird dafür nichts"


async def test_weitere_werte_schon_beim_einrichten(monkeypatch, hass):
    geblaese = f"{KESSEL}/0/0/12165"
    flow = am_ende_der_einrichtung(monkeypatch, hass)
    await flow._abschluss()

    auswahl = await flow.async_step_weitere_werte()

    assert auswahl["step_id"] == "weitere_werte"
    assert list(felder(auswahl)) == ["Puffer", "Kessel", "Sys"]
    assert zur_wahl(auswahl, "Kessel")[geblaese] == "Kessel › Abgasgebläse"
    assert f"{KESSEL}/0/0/12161" not in zur_wahl(auswahl, "Kessel"), "die Kesseltemperatur ist ein fester Sensor"
    assert f"{PUFFER}/12130/0/1082" in zur_wahl(auswahl, "Puffer"), "Zeitfenster stehen zur Wahl wie unter Konfigurieren"

    leer = await flow.async_step_weitere_werte({})
    assert leer["step_id"] == "abschluss"
    assert CONF_WEITERE_WERTE not in flow._data

    takt = await flow.async_step_weitere_werte({"Kessel": [geblaese]})
    assert takt["step_id"] == "weitere_takt"
    zurueck = await flow.async_step_weitere_takt(
        {"weitere_je_abfrage": 30, "weitere_intervall": 60, "weitere_schnell": [geblaese]}
    )
    assert zurueck["step_id"] == "abschluss"

    fertig = await flow.async_step_fertig()
    (gewaehlt,) = fertig["data"][CONF_WEITERE_WERTE]
    assert gewaehlt == {
        "uri": geblaese,
        "fub": "Kessel",
        "pfad": ["Kessel", "Abgasgebläse"],
        "zahl": True,
        "einheit": "°C",
        "stellen": 1,
        "schnell": True,
    }
    assert fertig["data"][CONF_WEITERE_JE_ABFRAGE] == 30
    assert fertig["data"][CONF_WEITERE_INTERVALL] == 60

    nochmal = await flow.async_step_weitere_werte()
    assert felder(nochmal)["Kessel"].default() == [geblaese], "die Auswahl steht wieder vorbelegt"
    await flow.async_step_weitere_werte({})
    assert CONF_WEITERE_WERTE not in flow._data


async def test_konfigurieren_ordnet_zu_und_speichert_sonst_nichts_neu(monkeypatch, hass):
    hass.session.werte[LEISTUNG] = DRUCK
    entry = einrichtung()
    entry.options = {"scan_interval": 45}
    flow = konfigurieren(monkeypatch, hass, entry)

    auswahl = await flow.async_step_fehlende_werte()
    assert auswahl["step_id"] == "fehlende_werte"
    assert "kessel_druck" in zur_wahl(auswahl, "werte")

    zuordnen = await flow.async_step_fehlende_werte({"werte": ["kessel_druck"]})
    ergebnis = await flow.async_step_werte_zuordnen({"Kesseldruck": LEISTUNG})

    assert ergebnis["type"] == "create_entry"
    assert ergebnis["data"] == {"scan_interval": 45, CONF_ZUORDNUNGEN: {"kessel_druck": LEISTUNG}}
    assert list(felder(zuordnen)) == ["Kesseldruck"]


async def test_konfigurieren_ohne_aenderung_speichert_nichts(monkeypatch, hass):
    hass.session.werte[LEISTUNG] = DRUCK
    entry = einrichtung(**{CONF_ZUORDNUNGEN: {"kessel_druck": LEISTUNG}})
    flow = konfigurieren(monkeypatch, hass, entry)

    await flow.async_step_fehlende_werte()
    assert await flow.async_step_fehlende_werte({"werte": []}) == {
        "type": "abort",
        "reason": "nichts_geaendert",
    }

    await flow.async_step_fehlende_werte({"werte": ["kessel_druck"]})
    assert await flow.async_step_werte_zuordnen({"Kesseldruck": LEISTUNG}) == {
        "type": "abort",
        "reason": "nichts_geaendert",
    }


async def test_konfigurieren_hebt_eine_zuordnung_aus_der_ersteinrichtung_auf(monkeypatch, hass):
    """Die Zuordnung steht dort in den Daten des Eintrags - gespeichert wird deshalb auch die leere."""
    hass.session.werte[LEISTUNG] = DRUCK
    entry = einrichtung(**{CONF_ZUORDNUNGEN: {"kessel_druck": LEISTUNG}})
    flow = konfigurieren(monkeypatch, hass, entry)
    abgemeldet = []
    monkeypatch.setattr(modul, "entitaeten_abmelden", lambda *angaben: abgemeldet.append(angaben))

    await flow.async_step_fehlende_werte()
    await flow.async_step_fehlende_werte({"werte": ["kessel_druck"]})
    ergebnis = await flow.async_step_werte_zuordnen({})

    assert ergebnis["data"] == {CONF_ZUORDNUNGEN: {}}
    assert {**entry.data, **ergebnis["data"]}[CONF_ZUORDNUNGEN] == {}
    assert abgemeldet == [], "ohne ausgeblendete Werte wird aus dem Sensor ein Platzhalter"


async def test_eine_aufgehobene_zuordnung_nimmt_ausgeblendet_ihren_sensor_mit(monkeypatch, hass):
    hass.session.werte[LEISTUNG] = DRUCK
    entry = einrichtung(
        **{
            CONF_FEHLENDE_AUSBLENDEN: True,
            CONF_ZUORDNUNGEN: {
                "aschebox_verbrauch": LEISTUNG,
                "ruecklauf_temperatur": f"{KESSEL}/0/11163/2121",
            },
        }
    )
    flow = konfigurieren(monkeypatch, hass, entry)
    abgemeldet = []
    monkeypatch.setattr(modul, "entitaeten_abmelden", lambda *angaben: abgemeldet.append(angaben))

    await flow.async_step_fehlende_werte()
    await flow.async_step_fehlende_werte({"werte": ["aschebox_verbrauch", "ruecklauf_temperatur"]})
    ergebnis = await flow.async_step_werte_zuordnen({})

    assert ergebnis["data"][CONF_ZUORDNUNGEN] == {}
    assert abgemeldet == [(hass, entry, {"aschebox_verbrauch", "aschebox_faellig", "aschebox_status"})], (
        "den Rücklauf findet die Erkennung selbst - sein Sensor bleibt"
    )


async def test_konfigurieren_bricht_ab_wenn_die_anlage_nicht_antwortet_oder_nichts_fehlt(monkeypatch, hass):
    entry = einrichtung()
    flow = konfigurieren(monkeypatch, hass, entry)
    hass.session.fail_uris = ["/user/menu"]
    assert await flow.async_step_fehlende_werte() == {"type": "abort", "reason": "cannot_connect"}

    hass.session.fail_uris = []
    flow = konfigurieren(monkeypatch, hass, einrichtung(("ww",)), OHNE_KESSEL)
    assert await flow.async_step_fehlende_werte() == {"type": "abort", "reason": "nichts_zuzuordnen"}


async def test_wer_fehlende_werte_ausblendet_wird_die_platzhalter_gleich_los(monkeypatch, hass):
    hass.session.menu = STUECKHOLZ
    entry = einrichtung()
    await setup_integration(hass, entry)
    for key in ("kessel_druck", "aschebox_status", "kessel_temperatur"):
        hass.entity_registry.anlegen(
            f"sensor.eta_{key}", f"eta_static_{entry.entry_id}_{key}", entry.entry_id
        )

    bisher = {**entry.data, **optionen(components=["puffer"])}
    flow, ergebnis = await options_schritt(
        monkeypatch, bisher, optionen(components=["puffer"], **{CONF_FEHLENDE_AUSBLENDEN: True})
    )
    flow.hass = hass
    monkeypatch.setattr(modul.ETAOptionsFlow, "config_entry", property(lambda self: entry))
    for _ in range(4):
        if ergebnis["type"] == "create_entry":
            break
        ergebnis = await getattr(flow, f"async_step_{ergebnis['step_id']}")(
            {str(feld): feld.default() for feld in ergebnis["data_schema"].schema}
        )

    assert ergebnis["type"] == "create_entry"
    assert ergebnis["data"][CONF_FEHLENDE_AUSBLENDEN] is True
    assert set(hass.entity_registry.eintraege) == {"sensor.eta_kessel_temperatur"}


async def test_einstellungen_speichern_behaelt_zuordnungen_und_geleerte_auswahl(monkeypatch):
    """Stammen sie aus der Ersteinrichtung, gälten nach dem Speichern sonst wieder die alten."""
    bisher = {
        **optionen(),
        CONF_ZUORDNUNGEN: {"kessel_druck": LEISTUNG},
        CONF_WEITERE_WERTE: [],
    }
    flow, ergebnis = await options_schritt(monkeypatch, bisher, optionen())
    for _ in range(4):
        if ergebnis["type"] == "create_entry":
            break
        ergebnis = await getattr(flow, f"async_step_{ergebnis['step_id']}")(
            {str(feld): feld.default() for feld in ergebnis["data_schema"].schema}
        )

    assert ergebnis["type"] == "create_entry"
    assert ergebnis["data"][CONF_ZUORDNUNGEN] == {"kessel_druck": LEISTUNG}
    assert ergebnis["data"][CONF_WEITERE_WERTE] == []


async def test_namen_der_messwerte_kommen_aus_der_sprache_von_home_assistant(monkeypatch):
    from types import SimpleNamespace

    async def texte(hass, sprache, kategorie, integrationen):
        assert (sprache, kategorie, list(integrationen)) == ("en", "entity", ["eta_heating_ws"])
        return {"component.eta_heating_ws.entity.sensor.kessel_druck.name": "Boiler pressure"}

    monkeypatch.setattr(modul, "async_get_translations", texte)
    hass = SimpleNamespace(config=SimpleNamespace(language="en"))

    assert await modul._sensor_namen(hass, ["kessel_druck", "ruecklauf_temperatur"]) == {
        "kessel_druck": "Boiler pressure",
        "ruecklauf_temperatur": "Rücklauftemperatur",
    }
