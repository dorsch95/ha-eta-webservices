"""Tests für den Einrichtungs-Dialog."""

from __future__ import annotations

import pytest
import voluptuous as vol

from eta_heating_ws.config_flow import _connection_schema, _fub_names_schema
from eta_heating_ws.const import (
    COMPONENTS,
    DEFAULT_SCAN_INTERVAL,
    LEGACY_SCHEMA_COMPONENTS,
    MAX_SCAN_INTERVAL,
    MIN_SCAN_INTERVAL,
    components_from_config,
    fub_roles_for_components,
    normalize_components,
)


def gueltige_eingabe(**overrides):
    daten = {
        "host": "192.0.2.10",
        "port": 8080,
        "components": [],
        "scan_interval": DEFAULT_SCAN_INTERVAL,
    }
    daten.update(overrides)
    return daten


def test_verbindungsformular_akzeptiert_gueltige_eingabe():
    assert _connection_schema({})(gueltige_eingabe())


@pytest.mark.parametrize(
    "intervall", [MIN_SCAN_INTERVAL - 1, MAX_SCAN_INTERVAL + 1, 0]
)
def test_verbindungsformular_lehnt_ungueltiges_intervall_ab(intervall):
    with pytest.raises(vol.Invalid):
        _connection_schema({})(gueltige_eingabe(scan_interval=intervall))


def test_einstellungen_haben_kein_blosses_zahlen_oder_textfeld():
    """Home Assistant setzt beim Öffnen die Schreibmarke ins erste bloße Zahlen- oder Textfeld und rollt dorthin.

    Unter Konfigurieren stehen die Anzahlen als Auswahlfelder ganz oben -
    mit einem bloßen Zahlenfeld weiter unten öffnete sich der Dialog schon
    nach unten gerollt, die Anzahlen standen oberhalb des Bildes.
    """
    import homeassistant.helpers.config_validation as cv
    from homeassistant.helpers.selector import Selector

    from eta_heating_ws.config_flow import _options_schema

    bloss = [
        str(feld)
        for feld, pruefer in _options_schema({}).schema.items()
        if not isinstance(pruefer, Selector) and pruefer is not cv.boolean
    ]
    assert bloss == []


def test_abfrageintervalle_werden_als_ganze_sekunden_gespeichert():
    """Das Zahlenfeld liefert Kommazahlen - gespeichert werden ganze Sekunden, der Heizwert bleibt genau."""
    from eta_heating_ws.config_flow import _einstellungen, _options_schema

    eingabe = _options_schema({})(
        {"scan_interval": 45, "schnell_intervall": 2, "pellet_kwh_per_kg": 4.85, "pellet_preis": 310}
    )
    daten = _einstellungen(eingabe, [])

    assert (daten["scan_interval"], type(daten["scan_interval"])) == (45, int)
    assert (daten["schnell_intervall"], type(daten["schnell_intervall"])) == (2, int)
    assert daten["pellet_kwh_per_kg"] == 4.85
    assert daten["pellet_preis"] == 310


@pytest.mark.parametrize(
    "eingabe",
    [
        {"schnell_intervall": -1},
        {"schnell_intervall": MAX_SCAN_INTERVAL + 1},
        {"pellet_kwh_per_kg": 2.9},
        {"pellet_kwh_per_kg": 6.1},
        {"pellet_preis": -1},
        {"pellet_preis": 2001},
        {"scan_interval": "viel"},
    ],
)
def test_zahlenfelder_lehnen_werte_ausserhalb_ihrer_grenzen_ab(eingabe):
    from eta_heating_ws.config_flow import _options_schema

    with pytest.raises(vol.Invalid):
        _options_schema({})(eingabe)


def test_verbindungsformular_lehnt_unbekannte_komponente_ab():
    with pytest.raises(vol.Invalid):
        _connection_schema({})(gueltige_eingabe(components=["gibt_es_nicht"]))


def test_kessel_ist_nicht_abwaehlbar():
    assert "kessel" in normalize_components([])
    assert "kessel" in normalize_components(["fwm"])


def test_komponenten_behalten_feste_reihenfolge():
    assert normalize_components(["hk2", "fwm", "puffer"]) == [
        "puffer",
        "fwm",
        "hk2",
    ] or normalize_components(["hk2", "fwm", "puffer"]) == [
        key for key in COMPONENTS if key in {"kessel", "puffer", "fwm", "hk2"}
    ]


@pytest.mark.parametrize("schema, erwartet", list(LEGACY_SCHEMA_COMPONENTS.items()))
def test_altes_anlagenschema_wird_uebersetzt(schema, erwartet):
    assert components_from_config({"schema": schema}) == normalize_components(erwartet)


def test_neue_auswahl_schlaegt_altes_schema():
    config = {"schema": "Kessel", "components": ["kessel", "fwm"]}
    assert components_from_config(config) == ["kessel", "fwm"]


def test_verbindungsformular_uebernimmt_bisherige_werte():
    schema = _connection_schema({"host": "192.0.2.20", "port": 8081})
    markers = {str(key): key for key in schema.schema}
    assert markers["host"].default() == "192.0.2.20"
    assert markers["port"].default() == 8081


@pytest.mark.parametrize("komponente", list(COMPONENTS))
def test_jede_komponente_hat_fub_rollen(komponente):
    assert fub_roles_for_components([komponente])


def test_twin_steht_in_der_auswahl_am_ende():
    """Nur wenige Anlagen sind ein SH TWIN - Puffer, Warmwasser und Heizkreise stehen als Anzahl davor."""
    from eta_heating_ws.config_flow import _WAEHLBARE_KOMPONENTEN

    assert _WAEHLBARE_KOMPONENTEN[0] == "lager"
    assert _WAEHLBARE_KOMPONENTEN[-1] == "twin"


def test_fub_formular_ist_mit_standardnamen_vorbelegt():
    schema = _fub_names_schema(["kessel", "sys", "hk", "hk2"], {})
    defaults = {str(key): key.default() for key in schema.schema}
    assert defaults["kessel"] == "Kessel"
    assert defaults["hk"] == "HK"
    assert defaults["hk2"] == "HK2"


def test_fub_formular_uebernimmt_eigene_namen():
    schema = _fub_names_schema(["kessel"], {"kessel": "Pelletskessel"})
    defaults = {str(key): key.default() for key in schema.schema}
    assert defaults["kessel"] == "Pelletskessel"


def test_formular_hat_beide_freigaben():
    felder = [str(k) for k in _connection_schema({}).schema]
    assert "enable_switches" in felder
    assert "enable_errors" in felder


def test_schalter_sind_standardmaessig_aus():
    """Ein Update darf niemandem ungefragt Schreibzugriff geben."""
    marker = {str(k): k for k in _connection_schema({}).schema}
    assert marker["enable_switches"].default() is False
    assert marker["enable_errors"].default() is True


def test_bestehende_einstellung_bleibt_erhalten():
    marker = {
        str(k): k
        for k in _connection_schema({"enable_switches": True}).schema
    }
    assert marker["enable_switches"].default() is True


def test_warnschritt_ist_in_allen_sprachen_beschrieben():
    import json
    from pathlib import Path

    basis = Path(__file__).resolve().parents[1] / "custom_components" / "eta_heating_ws"
    for datei in ("strings.json", "translations/de.json", "translations/en.json"):
        daten = json.loads((basis / datei).read_text(encoding="utf-8"))
        for bereich in ("config", "options"):
            schritt = daten[bereich]["step"]["switch_warning"]
            assert schritt["title"]
            assert len(schritt["description"]) > 200, datei


def test_warnung_nennt_die_wesentlichen_punkte():
    import json
    from pathlib import Path

    basis = Path(__file__).resolve().parents[1] / "custom_components" / "eta_heating_ws"
    text = json.loads(
        (basis / "translations" / "de.json").read_text(encoding="utf-8")
    )["config"]["step"]["switch_warning"]["description"].lower()

    assert "frostschutz" in text
    assert "auskühlen" in text
    assert "konfigurieren" in text


class FakeEintrag:
    """Ein bestehender Config Entry, wie ihn Neu-Konfigurieren vorfindet."""

    def __init__(self, options: dict | None = None, minor_version: int = 2, **daten):
        self.entry_id = "eintrag1"
        self.version = 1
        self.minor_version = minor_version
        self.data = {"host": "192.0.2.10", "port": 8080, **daten}
        self.options: dict = dict(options or {})
        self.unique_id = f"{self.data['host']}:{self.data['port']}"


class FakeEintraege:
    """Die Teile von hass.config_entries, die Flow und Migration benutzen."""

    def __init__(self, *eintraege: FakeEintrag) -> None:
        self.eintraege = list(eintraege)

    def async_entry_for_domain_unique_id(self, domain, unique_id):
        return next((e for e in self.eintraege if e.unique_id == unique_id), None)

    def async_update_entry(self, eintrag, **aenderungen):
        for name, wert in aenderungen.items():
            setattr(eintrag, name, wert)
        return True


class FakeHass:
    def __init__(self, *eintraege: FakeEintrag) -> None:
        self.config_entries = FakeEintraege(*eintraege)


async def reconfigure_schritt(monkeypatch, eintrag, eingabe, erreichbar=True, andere=()):
    """Führt Neu-Konfigurieren aus, ohne echte Anlage und ohne Instanz."""
    from eta_heating_ws import config_flow as modul

    async def verbindung(hass, host, port):
        return erreichbar

    monkeypatch.setattr(modul, "_test_connection", verbindung)

    from homeassistant.config_entries import SOURCE_RECONFIGURE

    flow = modul.ETAConfigFlow()
    flow.hass = FakeHass(eintrag, *andere)
    flow.context = {"source": SOURCE_RECONFIGURE}
    monkeypatch.setattr(
        modul.ETAConfigFlow, "_get_reconfigure_entry", lambda self: eintrag
    )
    monkeypatch.setattr(
        modul.ETAConfigFlow,
        "async_show_form",
        lambda self, **kwargs: {"type": "form", **kwargs},
    )
    monkeypatch.setattr(
        modul.ETAConfigFlow,
        "async_abort",
        lambda self, **kwargs: {"type": "abort", **kwargs},
    )
    monkeypatch.setattr(
        modul.ETAConfigFlow,
        "async_update_reload_and_abort",
        lambda self, entry, **kwargs: {"type": "abort", **kwargs},
    )
    return await flow.async_step_reconfigure(eingabe)


def feldnamen(schema) -> set[str]:
    return {str(k) for k in schema.schema}


async def test_neu_konfigurieren_fragt_nur_die_adresse(monkeypatch):
    """Alles andere steht unter Konfigurieren - an zwei Stellen überdeckte
    sonst die eine Einstellung still die andere."""
    ergebnis = await reconfigure_schritt(monkeypatch, FakeEintrag(), None)

    assert ergebnis["step_id"] == "reconfigure"
    assert feldnamen(ergebnis["data_schema"]) == {"host", "port"}


async def test_neu_konfigurieren_kann_keinen_schreibzugriff_freigeben(monkeypatch):
    """Die Freigabe geht nur über Konfigurieren, wo die Warnung erscheint."""
    ergebnis = await reconfigure_schritt(monkeypatch, FakeEintrag(), None)
    assert "enable_switches" not in feldnamen(ergebnis["data_schema"])


async def test_neu_konfigurieren_uebernimmt_adresse_und_kennung(monkeypatch):
    ergebnis = await reconfigure_schritt(
        monkeypatch, FakeEintrag(), {"host": "192.0.2.99", "port": 8081}
    )

    assert ergebnis["type"] == "abort"
    assert ergebnis["data_updates"] == {"host": "192.0.2.99", "port": 8081}
    assert ergebnis["unique_id"] == "192.0.2.99:8081"


async def test_neu_konfigurieren_ohne_verbindung_meldet_fehler(monkeypatch):
    ergebnis = await reconfigure_schritt(
        monkeypatch,
        FakeEintrag(),
        {"host": "192.0.2.99", "port": 8080},
        erreichbar=False,
    )
    assert ergebnis["type"] == "form"
    assert ergebnis["errors"] == {"base": "cannot_connect"}


async def test_neu_konfigurieren_auf_vergebene_adresse_bricht_ab(monkeypatch):
    andere = FakeEintrag(host="192.0.2.50")
    ergebnis = await reconfigure_schritt(
        monkeypatch,
        FakeEintrag(),
        {"host": "192.0.2.50", "port": 8080},
        andere=(andere,),
    )
    assert ergebnis == {"type": "abort", "reason": "already_configured"}


def test_optionen_fragen_nicht_nach_der_adresse():
    from eta_heating_ws.config_flow import _options_schema

    felder = feldnamen(_options_schema({}))
    assert "host" not in felder
    assert "port" not in felder
    assert {"components", "enable_switches", "enable_errors"} <= felder


async def _keiner_ohne_volumen(*_):
    return [], {}, {}, {}


async def _keine_namen(*_):
    return []


async def options_schritt(monkeypatch, bisher, eingabe):
    """Führt den ersten Schritt von Konfigurieren aus."""
    from eta_heating_ws import config_flow as modul

    flow = modul.ETAOptionsFlow()
    monkeypatch.setattr(modul.ETAOptionsFlow, "_current", property(lambda self: bisher))
    monkeypatch.setattr(modul, "_anlage_pruefen", _keiner_ohne_volumen)
    monkeypatch.setattr(modul, "_fub_namen_der_anlage", _keine_namen)
    monkeypatch.setattr(
        modul.ETAOptionsFlow,
        "async_show_form",
        lambda self, **kwargs: {"type": "form", **kwargs},
    )
    monkeypatch.setattr(
        modul.ETAOptionsFlow,
        "async_create_entry",
        lambda self, **kwargs: {"type": "create_entry", **kwargs},
    )
    return flow, await flow.async_step_init(eingabe)


async def verbindungen_bestaetigen(flow, schritt):
    """Mit zwei Puffern fragt der Dialog zuletzt, wer woran hängt - hier bleibt die Vorgabe."""
    assert schritt["step_id"] == "verbindungen"
    return await flow.async_step_verbindungen(
        {str(feld): feld.default() for feld in schritt["data_schema"].schema}
    )


def optionen(**overrides):
    daten = gueltige_eingabe(**overrides)
    daten.pop("host")
    daten.pop("port")
    return daten


async def test_konfigurieren_warnt_vor_dem_schreibzugriff(monkeypatch):
    """Ohne die Warnung ließe sich das Schalten hier ungefragt einschalten."""
    flow, ergebnis = await options_schritt(
        monkeypatch, {"enable_switches": False}, optionen(enable_switches=True)
    )
    assert ergebnis["step_id"] == "switch_warning"

    weiter = await flow.async_step_switch_warning({})
    assert weiter["step_id"] == "fub_names"


async def test_bereits_freigegebener_schreibzugriff_warnt_nicht_erneut(monkeypatch):
    _, ergebnis = await options_schritt(
        monkeypatch, {"enable_switches": True}, optionen(enable_switches=True)
    )
    assert ergebnis["step_id"] == "fub_names"


async def test_konfigurieren_speichert_keine_adresse(monkeypatch):
    flow, _ = await options_schritt(monkeypatch, {}, optionen())
    ergebnis = await flow.async_step_fub_names({"kessel": "Kessel", "sys": "Sys", "pufferflex": "PufferFlex"})

    assert ergebnis["type"] == "create_entry"
    assert "host" not in ergebnis["data"]
    assert "port" not in ergebnis["data"]


async def test_migration_holt_die_adresse_aus_den_optionen():
    """Die Optionen gewannen bisher - ihr Wert ist der, mit dem es lief."""
    from eta_heating_ws import async_migrate_entry

    eintrag = FakeEintrag(
        minor_version=1,
        options={"host": "192.0.2.77", "port": 8080, "scan_interval": 60},
    )
    hass = FakeHass(eintrag)

    assert await async_migrate_entry(hass, eintrag) is True
    assert eintrag.data["host"] == "192.0.2.77"
    assert eintrag.options == {"scan_interval": 60}
    assert eintrag.unique_id == "192.0.2.77:8080"
    assert eintrag.minor_version == 2


async def test_migration_laesst_eintraege_ohne_optionen_unveraendert():
    from eta_heating_ws import async_migrate_entry

    eintrag = FakeEintrag(minor_version=1)
    await async_migrate_entry(FakeHass(eintrag), eintrag)

    assert eintrag.data == {"host": "192.0.2.10", "port": 8080}
    assert eintrag.options == {}


async def test_migration_uebernimmt_keine_fremde_kennung():
    from eta_heating_ws import async_migrate_entry

    eintrag = FakeEintrag(minor_version=1, options={"host": "192.0.2.50"})
    anderer = FakeEintrag(host="192.0.2.50")
    anderer.entry_id = "eintrag2"
    await async_migrate_entry(FakeHass(eintrag, anderer), eintrag)

    assert eintrag.data["host"] == "192.0.2.50"
    assert eintrag.unique_id == "192.0.2.10:8080"


async def test_neu_konfigurieren_wirkt_auch_nach_gespeicherten_optionen(monkeypatch):
    """Der ursprüngliche Fehler, von Anfang bis Ende.

    Erst über Konfigurieren gespeichert, dann über Neu konfigurieren eine
    neue Adresse eingetragen: Beim Start muss die neue gelten. Bis 0.20
    überdeckten die Optionen sie still.
    """
    from eta_heating_ws import async_migrate_entry

    eintrag = FakeEintrag(
        minor_version=1,
        options={"host": "192.0.2.10", "port": 8080, "scan_interval": 60},
    )
    await async_migrate_entry(FakeHass(eintrag), eintrag)

    ergebnis = await reconfigure_schritt(
        monkeypatch, eintrag, {"host": "192.0.2.99", "port": 8080}
    )
    eintrag.data.update(ergebnis["data_updates"])

    beim_start = {**eintrag.data, **eintrag.options}
    assert beim_start["host"] == "192.0.2.99"
    assert beim_start["scan_interval"] == 60


async def test_geleertes_wetterfeld_bleibt_leer(monkeypatch):
    """Sonst gewänne beim Start die Wahl aus der ersten Einrichtung."""
    flow, _ = await options_schritt(monkeypatch, {"wetter": "weather.zuhause"}, optionen())
    assert flow._data["wetter"] == ""


async def test_gewaehltes_wetter_wird_gespeichert(monkeypatch):
    flow, _ = await options_schritt(monkeypatch, {}, optionen(wetter="weather.zuhause"))
    assert flow._data["wetter"] == "weather.zuhause"


def test_wetter_ist_freiwillig():
    felder = {str(k): k for k in _connection_schema({}).schema}
    assert isinstance(felder["wetter"], vol.Optional)
    assert _connection_schema({})(gueltige_eingabe())


def test_wetter_vorschlag():
    from types import SimpleNamespace

    from eta_heating_ws.config_flow import wetter_vorschlag

    def hass(*wetter):
        return SimpleNamespace(
            states=SimpleNamespace(async_entity_ids=lambda domain: list(wetter))
        )

    assert wetter_vorschlag(hass("weather.zuhause"), {}) == "weather.zuhause"
    assert wetter_vorschlag(hass("weather.a", "weather.b"), {}) is None
    assert wetter_vorschlag(hass("weather.zuhause"), {"wetter": ""}) is None
    assert wetter_vorschlag(hass("weather.zuhause"), {"wetter": "weather.a"}) == "weather.a"



async def test_puffer_mit_eigenem_volumen_wird_nicht_gefragt(monkeypatch):
    """PufferFlex meldet sein effektives Volumen - dann gibt es keinen Schritt dafür."""
    flow, _ = await options_schritt(monkeypatch, {}, optionen(components=["puffer", "puffer2"]))
    schritt = await flow.async_step_fub_names(
        {"kessel": "Kessel", "sys": "Sys", "pufferflex": "PufferFlex", "pufferflex2": "PufferFlex 2"}
    )
    fertig = await verbindungen_bestaetigen(flow, schritt)
    assert fertig["type"] == "create_entry"
    assert "puffer_volumen" not in fertig["data"]


async def test_alter_puffer_fragt_nach_seinen_litern(monkeypatch):
    """Nur für den Puffer, der sein Volumen nicht meldet; vorbelegt mit dem bisherigen Wert."""
    from eta_heating_ws import config_flow as modul

    bisher = {"host": "192.0.2.10", "port": 8080, "puffer2_volumen": 650}
    flow, _ = await options_schritt(monkeypatch, bisher, optionen(components=["puffer", "puffer2"]))

    async def nur_puffer2(*_):
        return ["puffer2"], {}, {}, {}

    monkeypatch.setattr(modul, "_anlage_pruefen", nur_puffer2)
    schritt = await flow.async_step_fub_names(
        {"kessel": "Kessel", "sys": "Sys", "pufferflex": "PufferFlex", "pufferflex2": "Puffer"}
    )
    assert schritt["step_id"] == "puffer"
    felder = {str(k): k.default() for k in schritt["data_schema"].schema}
    assert felder == {"puffer2_volumen": 650}
    with pytest.raises(vol.Invalid):
        schritt["data_schema"]({"puffer2_volumen": -5})
    fertig = await verbindungen_bestaetigen(
        flow, await flow.async_step_puffer({"puffer2_volumen": 800})
    )
    assert fertig["type"] == "create_entry"
    assert fertig["data"]["puffer2_volumen"] == 800
    assert fertig["data"]["fub_names"]["pufferflex2"] == "Puffer"


async def test_erkennung_der_puffer_ohne_volumen(monkeypatch):
    """Fühler gefunden, Volumen nicht: der ältere Funktionsblock "Puffer"."""
    from eta_heating_ws import config_flow as modul

    async def menue(client, fub_names, **_):
        return {
            "puffer_fuehler_1": "/1/2/0/11327/0",
            "puffer_volumen": "/1/2/0/0/12499",
            "puffer2_fuehler_1": "/1/3/0/11153/0",
        }, [1]

    monkeypatch.setattr(modul, "async_discover_uris", menue)
    monkeypatch.setattr(modul, "async_get_clientsession", lambda hass: None)
    komponenten = ["kessel", "puffer", "puffer2", "puffer3"]
    assert await modul._anlage_pruefen(None, "h", 8080, {}, komponenten, False) == (["puffer2"], {}, {}, {})
    assert await modul._anlage_pruefen(None, "h", 8080, {}, ["kessel", "puffer"], False) == ([], {}, {}, {})

    async def kaputt(client, fub_names, **_):
        raise modul.ETAApiError("kein Menübaum")

    monkeypatch.setattr(modul, "async_discover_uris", kaputt)
    assert await modul._anlage_pruefen(None, "h", 8080, {}, komponenten, True) is None


async def test_erkennung_der_aelteren_puffer_mit_gemeldetem_volumen(monkeypatch):
    """Älterer Puffer mit gemeldetem Volumen: Name seines Blocks und die Liter der Anlage."""
    from eta_heating_ws import config_flow as modul
    from eta_heating_ws.api import ETAApiClient, ETAValue

    async def menue(client, fub_names, fub_namen=None, aeltere_puffer=None):
        fub_namen.update({"pufferflex": "PufferFlex", "pufferflex2": "Puffer", "pufferflex3": "Puffer 2"})
        aeltere_puffer.update({"puffer2", "puffer3"})
        return {
            "puffer_fuehler_1": "/1/2/0/11327/0",
            "puffer_volumen": "/1/2/0/0/12499",
            "puffer2_fuehler_1": "/1/3/0/11153/0",
            "puffer2_volumen": "/1/3/0/0/12499",
            "puffer3_fuehler_1": "/1/4/0/11153/0",
        }, [1]

    gelesen = []

    async def wert(self, uri):
        gelesen.append(uri)
        return ETAValue(1000.0, "1000", "l", False, 0)

    monkeypatch.setattr(modul, "async_discover_uris", menue)
    monkeypatch.setattr(modul, "async_get_clientsession", lambda hass: None)
    monkeypatch.setattr(ETAApiClient, "async_get_value", wert)
    komponenten = ["kessel", "puffer", "puffer2", "puffer3"]
    assert await modul._anlage_pruefen(None, "h", 8080, {}, komponenten, False) == (
        ["puffer3"],
        {},
        {},
        {"puffer2": {"name": "Puffer", "liter": 1000}},
    )
    assert gelesen == ["/1/3/0/0/12499"], "das Volumen des PufferFlex wird hier nicht gelesen"
    assert (await modul._anlage_pruefen(None, "h", 8080, {}, ["kessel", "puffer"], False))[3] == {}

    async def stumm(self, uri):
        raise modul.ETAApiError("keine Antwort")

    monkeypatch.setattr(ETAApiClient, "async_get_value", stumm)
    einstellwerte = (await modul._anlage_pruefen(None, "h", 8080, {}, komponenten, False))[3]
    assert einstellwerte == {"puffer2": {"name": "Puffer", "liter": None}}
    assert modul._gemeldet(einstellwerte) == "Puffer: ? l"
    assert (
        modul._gemeldet(
            {"puffer": {"name": "Puffer", "liter": 1000}, "puffer2": {"name": "Puffer 2", "liter": 800}}
        )
        == "Puffer: 1000 l, Puffer 2: 800 l"
    )


async def test_aelterer_puffer_mit_gemeldetem_volumen_zeigt_den_wert(monkeypatch):
    """Eigener Schritt mit dem Wert der Anlage; vorbelegt ist 0, also der Wert der Anlage."""
    from eta_heating_ws import config_flow as modul

    bisher = {"host": "192.0.2.10", "port": 8080}
    flow, _ = await options_schritt(monkeypatch, bisher, optionen(components=["puffer", "puffer2"]))

    async def gemeldet(*_):
        return [], {}, {}, {"puffer2": {"name": "Puffer", "liter": 1000}}

    monkeypatch.setattr(modul, "_anlage_pruefen", gemeldet)
    schritt = await flow.async_step_fub_names(
        {"kessel": "Kessel", "sys": "Sys", "pufferflex": "PufferFlex", "pufferflex2": "Puffer"}
    )
    assert schritt["step_id"] == "puffer_einstellwert"
    assert schritt["description_placeholders"] == {"gemeldet": "Puffer: 1000 l"}
    felder = {str(k): k.default() for k in schritt["data_schema"].schema}
    assert felder == {"puffer2_volumen": 0}
    with pytest.raises(vol.Invalid):
        schritt["data_schema"]({"puffer2_volumen": -5})
    fertig = await verbindungen_bestaetigen(
        flow, await flow.async_step_puffer_einstellwert({"puffer2_volumen": 1500})
    )
    assert fertig["type"] == "create_entry"
    assert fertig["data"]["puffer2_volumen"] == 1500


async def test_aelterer_puffer_behaelt_frueher_eingetragene_liter_als_vorgabe(monkeypatch):
    """Was schon eingetragen war, steht im Feld - und 0 stellt auf den Wert der Anlage zurück."""
    from eta_heating_ws import config_flow as modul

    bisher = {"host": "192.0.2.10", "port": 8080, "puffer2_volumen": 800}
    flow, _ = await options_schritt(monkeypatch, bisher, optionen(components=["puffer", "puffer2"]))

    async def gemeldet(*_):
        return [], {}, {}, {"puffer2": {"name": "Puffer", "liter": 1000}}

    monkeypatch.setattr(modul, "_anlage_pruefen", gemeldet)
    schritt = await flow.async_step_fub_names(
        {"kessel": "Kessel", "sys": "Sys", "pufferflex": "PufferFlex", "pufferflex2": "Puffer"}
    )
    felder = {str(k): k.default() for k in schritt["data_schema"].schema}
    assert felder == {"puffer2_volumen": 800}
    fertig = await verbindungen_bestaetigen(
        flow, await flow.async_step_puffer_einstellwert({"puffer2_volumen": 0})
    )
    assert fertig["data"]["puffer2_volumen"] == 0


async def test_beide_puffer_schritte_nacheinander(monkeypatch):
    """Erst der Puffer ohne Volumen, dann der ältere Puffer mit gemeldetem Volumen."""
    from eta_heating_ws import config_flow as modul

    bisher = {"host": "192.0.2.10", "port": 8080}
    flow, _ = await options_schritt(
        monkeypatch, bisher, optionen(components=["puffer", "puffer2", "puffer3"])
    )

    async def beide(*_):
        return ["puffer3"], {}, {}, {"puffer2": {"name": "Puffer", "liter": 1000}}

    monkeypatch.setattr(modul, "_anlage_pruefen", beide)
    schritt = await flow.async_step_fub_names(
        {
            "kessel": "Kessel",
            "sys": "Sys",
            "pufferflex": "PufferFlex",
            "pufferflex2": "Puffer",
            "pufferflex3": "Puffer 2",
        }
    )
    assert schritt["step_id"] == "puffer"
    assert [str(k) for k in schritt["data_schema"].schema] == ["puffer3_volumen"]
    schritt = await flow.async_step_puffer({"puffer3_volumen": 600})
    assert schritt["step_id"] == "puffer_einstellwert"
    assert [str(k) for k in schritt["data_schema"].schema] == ["puffer2_volumen"]
    fertig = await verbindungen_bestaetigen(
        flow, await flow.async_step_puffer_einstellwert({"puffer2_volumen": 0})
    )
    assert fertig["data"]["puffer3_volumen"] == 600
    assert fertig["data"]["puffer2_volumen"] == 0


async def test_erkennung_der_heizkreise_mit_externer_schnittstelle(monkeypatch):
    """Nur mit Schreibzugriff, nur angekreuzte Heizkreise, mit dem Wert der Zeitüberwachung."""
    from eta_heating_ws import config_flow as modul
    from eta_heating_ws.api import ETAApiClient, ETAValue

    async def menue(client, fub_names, **_):
        return {
            "heizkreis_raum_extern": "/1/5/0/0/13046",
            "heizkreis_zeitueberwachung": "/1/5/0/0/13168",
            "heizkreis2_vorlauf": "/1/6/0/11060/0",
        }, []

    async def wert(self, uri):
        return ETAValue(60.0, "0h 1m", "s", False, 0)

    monkeypatch.setattr(modul, "async_discover_uris", menue)
    monkeypatch.setattr(modul, "async_get_clientsession", lambda hass: None)
    monkeypatch.setattr(ETAApiClient, "async_get_value", wert)
    komponenten = ["kessel", "hk1", "hk2"]
    assert await modul._anlage_pruefen(None, "h", 8080, {}, komponenten, True) == (
        [],
        {"hk1": {"uri": "/1/5/0/0/13168", "sekunden": 60}},
        {},
        {},
    )
    assert await modul._anlage_pruefen(None, "h", 8080, {}, komponenten, False) == ([], {}, {}, {})
    assert await modul._anlage_pruefen(None, "h", 8080, {}, ["kessel", "hk2"], True) == ([], {}, {}, {})


async def test_raumfuehler_und_zeitueberwachung_im_dialog(monkeypatch):
    """Die Zeitüberwachung wird nur geschrieben, wenn sie sich ändert - und nicht gespeichert."""
    from eta_heating_ws import config_flow as modul

    bisher = {"host": "192.0.2.10", "port": 8080, "hk1_raumfuehler": "sensor.alt"}
    flow, _ = await options_schritt(
        monkeypatch, bisher, optionen(components=["hk1"], enable_switches=True)
    )

    async def mit_thermostat(*_):
        return [], {"hk1": {"uri": "/1/5/0/0/13168", "sekunden": 60}}, [], {}

    geschrieben = []

    async def schreiben(hass, host, port, uri, sekunden):
        geschrieben.append((host, uri, sekunden))

    monkeypatch.setattr(modul, "_anlage_pruefen", mit_thermostat)
    monkeypatch.setattr(modul, "_zeitueberwachung_schreiben", schreiben)
    schritt = await flow.async_step_fub_names({"kessel": "Kessel", "sys": "Sys", "hk": "HK"})
    assert schritt["step_id"] == "raumfuehler"
    schema = schritt["data_schema"]
    standard = {str(k): k.default() for k in schema.schema if k.default is not vol.UNDEFINED}
    assert standard == {"hk1_zeitueberwachung": 1}
    vorschlag = {str(k): (k.description or {}).get("suggested_value") for k in schema.schema}
    assert vorschlag["hk1_raumfuehler"] == "sensor.alt"
    with pytest.raises(vol.Invalid):
        schema({"hk1_zeitueberwachung": 0})
    with pytest.raises(vol.Invalid):
        schema({"hk1_zeitueberwachung": 61})

    fertig = await flow.async_step_raumfuehler(
        {"hk1_raumfuehler": "sensor.wohnzimmer", "hk1_zeitueberwachung": 10}
    )
    assert fertig["type"] == "create_entry"
    assert fertig["data"]["hk1_raumfuehler"] == "sensor.wohnzimmer"
    assert "hk1_zeitueberwachung" not in fertig["data"]
    assert geschrieben == [("192.0.2.10", "/1/5/0/0/13168", 600)]

    geschrieben.clear()
    geleert = await flow.async_step_raumfuehler({"hk1_zeitueberwachung": 10})
    assert geschrieben == [], "unverändert - nichts zu schreiben"
    assert geleert["data"]["hk1_raumfuehler"] is None, (
        "geleert heißt: kein Thermometer mehr - ausdrücklich, sonst gälte das aus der Ersteinrichtung weiter"
    )


async def test_zeitueberwachung_nicht_geschrieben_zeigt_einen_fehler(monkeypatch):
    from eta_heating_ws import config_flow as modul

    flow, _ = await options_schritt(
        monkeypatch, {"host": "h"}, optionen(components=["hk1"], enable_switches=True)
    )

    async def mit_thermostat(*_):
        return [], {"hk1": {"uri": "/1/5/0/0/13168", "sekunden": 0}}, [], {}

    async def abgelehnt(*_):
        raise modul.ETAApiError("nein")

    monkeypatch.setattr(modul, "_anlage_pruefen", mit_thermostat)
    monkeypatch.setattr(modul, "_zeitueberwachung_schreiben", abgelehnt)
    schritt = await flow.async_step_fub_names({"kessel": "Kessel", "sys": "Sys", "hk": "HK"})
    standard = {str(k): k.default() for k in schritt["data_schema"].schema if k.default is not vol.UNDEFINED}
    assert standard == {"hk1_zeitueberwachung": 10}, "0 an der Anlage: 10 Minuten vorgeschlagen"
    ergebnis = await flow.async_step_raumfuehler({"hk1_zeitueberwachung": 10})
    assert ergebnis["errors"] == {"base": "zeitueberwachung_nicht_geschrieben"}


async def test_weitere_puffer_brenner_und_fernleitung_fragen_ihren_fub_namen(monkeypatch):
    _, ergebnis = await options_schritt(
        monkeypatch, {}, optionen(components=["puffer", "puffer2", "brenner", "fernleitung"])
    )
    felder = {str(k): k.default() for k in ergebnis["data_schema"].schema}
    assert felder["pufferflex2"] == "PufferFlex 2"
    assert felder["brenner"] == "Brenner"
    assert felder["fernleitung"] == "Fernl"


def test_zusatzfunktionen_sind_waehlbar_und_anfangs_an():
    marker = {str(k): k for k in _connection_schema({}).schema}
    assert marker["prognose"].default() is True
    assert marker["verbrauch_zeitraeume"].default() is True
    abgewaehlt = {str(k): k for k in _connection_schema({"prognose": False}).schema}
    assert abgewaehlt["prognose"].default() is False


async def test_zeitplan_je_heizkreis_im_dialog(monkeypatch):
    """Nach dem Raumfühler: je Heizkreis mit beschreibbarem Zeitprogramm ein Zeitplan-Helfer."""
    from eta_heating_ws import config_flow as modul

    bisher = {"host": "192.0.2.10", "port": 8080, "hk1_zeitplan": "schedule.alt"}
    flow, _ = await options_schritt(
        monkeypatch, bisher, optionen(components=["hk1", "hk2"], enable_switches=True)
    )

    from eta_heating_ws.api import ETAApiClient, ETAValue
    from eta_heating_ws.const import WOCHENTAGE

    fenster = {(tag, n): f"/{tag}/{n}" for tag in WOCHENTAGE for n in (1, 2, 3)}

    async def mit_zeitprogramm(*_):
        return [], {}, {"hk1": fenster, "hk2": fenster}, {}

    async def lesen(self, uri):
        text = "05:30 - 22:30 20,0" if uri.endswith("/1") else "00:00 - 00:00 0,0"
        return ETAValue(0.0, text, "°C", False, 1)

    monkeypatch.setattr(modul, "_anlage_pruefen", mit_zeitprogramm)
    monkeypatch.setattr(modul, "async_get_clientsession", lambda hass: None)
    monkeypatch.setattr(ETAApiClient, "async_get_value", lesen)
    schritt = await flow.async_step_fub_names(
        {"kessel": "Kessel", "sys": "Sys", "hk": "HK", "hk2": "HK 2"}
    )
    assert schritt["step_id"] == "zeitplaene"
    assert schritt["description_placeholders"]["programm"] == (
        "**Heizkreis 1**\n- Montag bis Sonntag: 05:30 - 22:30 20,0\n\n"
        "**Heizkreis 2**\n- Montag bis Sonntag: 05:30 - 22:30 20,0"
    )
    vorschlag = {
        str(k): (k.description or {}).get("suggested_value") for k in schritt["data_schema"].schema
    }
    assert vorschlag == {"hk1_zeitplan": "schedule.alt", "hk2_zeitplan": None}

    fertig = await flow.async_step_zeitplaene({"hk2_zeitplan": "schedule.bad"})
    assert fertig["type"] == "create_entry"
    assert fertig["data"]["hk2_zeitplan"] == "schedule.bad"
    assert fertig["data"]["hk1_zeitplan"] is None, (
        "geleert heißt: kein Zeitplan mehr - ausdrücklich, sonst gälte der aus der Ersteinrichtung weiter"
    )


async def test_zeitprogramm_nur_mit_schreibzugriff_im_dialog(monkeypatch):
    from eta_heating_ws import config_flow as modul
    from eta_heating_ws.const import WOCHENTAGE, zeitfenster_schluessel

    gefunden = {
        zeitfenster_schluessel("heizkreis", tag, nummer): f"/1/{nummer}"
        for tag in WOCHENTAGE
        for nummer in (1, 2, 3)
    }

    async def menue(client, fub_names, **_):
        return gefunden, []

    beschreibung = {"writable": True, "zeitfenster": {"mit_wert": True}}

    async def varinfo(self, uri):
        return beschreibung

    monkeypatch.setattr(modul, "async_discover_uris", menue)
    monkeypatch.setattr(modul, "async_get_clientsession", lambda hass: None)
    monkeypatch.setattr(modul.ETAApiClient, "async_get_varinfo", varinfo)
    komponenten = ["kessel", "hk1", "hk2"]
    zeitprogramme = (await modul._anlage_pruefen(None, "h", 8080, {}, komponenten, True))[2]
    assert list(zeitprogramme) == ["hk1"]
    assert zeitprogramme["hk1"][("monday", 2)] == "/1/2"
    assert (await modul._anlage_pruefen(None, "h", 8080, {}, komponenten, False))[2] == {}

    beschreibung = None
    assert list((await modul._anlage_pruefen(None, "h", 8080, {}, komponenten, True))[2]) == [
        "hk1"
    ], "ohne Antwort wird der Zeitplan trotzdem angeboten"
    beschreibung = {"writable": False, "zeitfenster": None}
    assert (await modul._anlage_pruefen(None, "h", 8080, {}, komponenten, True))[2] == {}, (
        "nicht beschreibbar: ein Zeitplan bliebe wirkungslos"
    )

    beschreibung = {"writable": True, "zeitfenster": {"mit_wert": True}}
    gefunden.pop(zeitfenster_schluessel("heizkreis", "sunday", 3))
    assert (await modul._anlage_pruefen(None, "h", 8080, {}, komponenten, True))[2] == {}, (
        "nur mit allen Fenstern der Woche"
    )


async def test_ohne_menuebaum_bleiben_die_bisherigen_angaben(monkeypatch):
    """Antwortet die Anlage beim Speichern nicht, gehen Zeitplan, Raumfühler und Volumen nicht verloren."""
    from eta_heating_ws import config_flow as modul
    from eta_heating_ws.const import puffer_volumen_schluessel

    bisher = {
        "host": "192.0.2.10",
        "port": 8080,
        "enable_switches": True,
        "hk1_zeitplan": "schedule.heizen",
        "hk1_raumfuehler": "sensor.wohnzimmer",
        "hk2_zeitplan": "schedule.weg",
        puffer_volumen_schluessel("puffer"): 800,
    }
    flow, _ = await options_schritt(
        monkeypatch, bisher, optionen(components=["puffer", "hk1"], enable_switches=True)
    )

    async def nicht_lesbar(*_):
        return None

    monkeypatch.setattr(modul, "_anlage_pruefen", nicht_lesbar)
    fertig = await flow.async_step_fub_names(
        {"kessel": "Kessel", "sys": "Sys", "pufferflex": "PufferFlex", "hk": "HK"}
    )

    assert fertig["type"] == "create_entry"
    assert fertig["data"]["hk1_zeitplan"] == "schedule.heizen"
    assert fertig["data"]["hk1_raumfuehler"] == "sensor.wohnzimmer"
    assert fertig["data"][puffer_volumen_schluessel("puffer")] == 800
    assert "hk2_zeitplan" not in fertig["data"], "Heizkreis 2 ist nicht mehr gewählt"


async def test_ohne_menuebaum_bleibt_ein_geleertes_feld_geleert(monkeypatch):
    """Das Thermometer stammt aus der Ersteinrichtung und wurde später entfernt - das bleibt so."""
    from eta_heating_ws import config_flow as modul

    bisher = {"host": "192.0.2.10", "port": 8080, "enable_switches": True, "hk1_raumfuehler": None}
    flow, _ = await options_schritt(
        monkeypatch, bisher, optionen(components=["hk1"], enable_switches=True)
    )

    async def nicht_lesbar(*_):
        return None

    monkeypatch.setattr(modul, "_anlage_pruefen", nicht_lesbar)
    fertig = await flow.async_step_fub_names({"kessel": "Kessel", "sys": "Sys", "hk": "HK"})

    assert fertig["type"] == "create_entry"
    assert fertig["data"]["hk1_raumfuehler"] is None, (
        "fehlte der Eintrag, gälte wieder das Thermometer aus der Ersteinrichtung"
    )


async def _konfigurieren(monkeypatch, daten, gespeichert, pruefung, schreiben=True, eingaben=None):
    """Ein Durchlauf von Konfigurieren für Heizkreis 1 - gibt zurück, was als Optionen gespeichert wird."""
    from eta_heating_ws import config_flow as modul
    from eta_heating_ws.api import ETAApiClient, ETAValue

    flow, schritt = await options_schritt(
        monkeypatch, {**daten, **gespeichert}, optionen(components=["hk1"], enable_switches=schreiben)
    )

    async def lesen(self, uri):
        return ETAValue(0.0, "00:00 - 00:00 0,0", "°C", False, 1)

    monkeypatch.setattr(modul, "_anlage_pruefen", pruefung)
    monkeypatch.setattr(modul, "async_get_clientsession", lambda hass: None)
    monkeypatch.setattr(ETAApiClient, "async_get_value", lesen)
    for _ in range(8):
        if schritt["type"] == "create_entry":
            return schritt["data"]
        name = schritt["step_id"]
        if name == "fub_names":
            schritt = await flow.async_step_fub_names({"kessel": "Kessel", "sys": "Sys", "hk": "HK"})
        elif name == "switch_warning":
            schritt = await flow.async_step_switch_warning({})
        else:
            schritt = await getattr(flow, f"async_step_{name}")(dict((eingaben or {}).get(name, {})))
    raise AssertionError("kein Ende")


_ERSTEINRICHTUNG_HK1 = {
    "host": "192.0.2.10",
    "port": 8080,
    "enable_switches": True,
    "components": ["kessel", "hk1"],
    "hk1_raumfuehler": "sensor.alt",
    "hk1_zeitplan": "schedule.alt",
}


def _hk1_mit_allem():
    from eta_heating_ws.const import WOCHENTAGE

    fenster = {(tag, n): f"/{tag}/{n}" for tag in WOCHENTAGE for n in (1, 2, 3)}

    async def pruefung(hass, host, port, namen, komponenten, schreiben):
        if not schreiben:
            return [], {}, {}, {}
        return [], {"hk1": {"uri": None, "sekunden": None}}, {"hk1": fenster}, {}

    return pruefung


async def test_geleertes_feld_bleibt_geleert_auch_wenn_ein_speichern_den_schritt_nicht_zeigt(monkeypatch):
    """Thermometer und Zeitplan entfernt, dann den Schreibzugriff aus- und wieder eingeschaltet.

    Ohne Schreibzugriff zeigt Konfigurieren die beiden Schritte nicht. Fiele
    das None dabei weg, gälten danach wieder die Werte aus der
    Ersteinrichtung - und Home Assistant schriebe wieder an die Anlage.
    """
    erreichbar = _hk1_mit_allem()

    async def nicht_lesbar(*_):
        return None

    erste = await _konfigurieren(monkeypatch, _ERSTEINRICHTUNG_HK1, {}, erreichbar)
    assert erste["hk1_raumfuehler"] is None and erste["hk1_zeitplan"] is None

    ohne_schreiben = await _konfigurieren(monkeypatch, _ERSTEINRICHTUNG_HK1, erste, erreichbar, schreiben=False)
    assert ohne_schreiben["hk1_raumfuehler"] is None and ohne_schreiben["hk1_zeitplan"] is None

    wieder_ein = await _konfigurieren(monkeypatch, _ERSTEINRICHTUNG_HK1, ohne_schreiben, nicht_lesbar)
    gilt = {**_ERSTEINRICHTUNG_HK1, **wieder_ein}
    assert gilt["hk1_raumfuehler"] is None and gilt["hk1_zeitplan"] is None


async def test_geleertes_feld_bleibt_geleert_wenn_die_anlage_das_zeitprogramm_einmal_nicht_meldet(monkeypatch):
    async def ohne_zeitprogramm(*_):
        return [], {"hk1": {"uri": None, "sekunden": None}}, {}, {}

    erste = await _konfigurieren(monkeypatch, _ERSTEINRICHTUNG_HK1, {}, _hk1_mit_allem())
    assert erste["hk1_zeitplan"] is None

    zweite = await _konfigurieren(monkeypatch, _ERSTEINRICHTUNG_HK1, erste, ohne_zeitprogramm)

    assert {**_ERSTEINRICHTUNG_HK1, **zweite}["hk1_zeitplan"] is None


async def test_ein_neu_gewaehlter_wert_ersetzt_das_none(monkeypatch):
    """Geleert heißt nicht gesperrt: Wer später wieder etwas wählt, bekommt es."""
    erste = await _konfigurieren(monkeypatch, _ERSTEINRICHTUNG_HK1, {}, _hk1_mit_allem())
    assert erste["hk1_raumfuehler"] is None

    zweite = await _konfigurieren(
        monkeypatch,
        _ERSTEINRICHTUNG_HK1,
        erste,
        _hk1_mit_allem(),
        eingaben={"raumfuehler": {"hk1_raumfuehler": "sensor.neu"}},
    )

    assert zweite["hk1_raumfuehler"] == "sensor.neu"
    assert zweite["hk1_zeitplan"] is None
