"""Tests für den Einrichtungs-Dialog."""

from __future__ import annotations

import pytest
import voluptuous as vol

from eta_webservices.config_flow import _connection_schema, _fub_names_schema
from eta_webservices.const import (
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
        "components": ["puffer"],
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
    """Nur wenige Anlagen sind ein SH TWIN - die Auswahl beginnt beim Puffer."""
    from eta_webservices.config_flow import _WAEHLBARE_KOMPONENTEN

    assert _WAEHLBARE_KOMPONENTEN[0] == "puffer"
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

    basis = Path(__file__).resolve().parents[1] / "custom_components" / "eta_webservices"
    for datei in ("strings.json", "translations/de.json", "translations/en.json"):
        daten = json.loads((basis / datei).read_text(encoding="utf-8"))
        for bereich in ("config", "options"):
            schritt = daten[bereich]["step"]["switch_warning"]
            assert schritt["title"]
            assert len(schritt["description"]) > 200, datei


def test_warnung_nennt_die_wesentlichen_punkte():
    import json
    from pathlib import Path

    basis = Path(__file__).resolve().parents[1] / "custom_components" / "eta_webservices"
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
    from eta_webservices import config_flow as modul

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
    from eta_webservices.config_flow import _options_schema

    felder = feldnamen(_options_schema({}))
    assert "host" not in felder
    assert "port" not in felder
    assert {"components", "enable_switches", "enable_errors"} <= felder


async def _keiner_ohne_volumen(*_):
    return []


async def options_schritt(monkeypatch, bisher, eingabe):
    """Führt den ersten Schritt von Konfigurieren aus."""
    from eta_webservices import config_flow as modul

    flow = modul.ETAOptionsFlow()
    monkeypatch.setattr(modul.ETAOptionsFlow, "_current", property(lambda self: bisher))
    monkeypatch.setattr(modul, "_puffer_ohne_volumen", _keiner_ohne_volumen)
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
    from eta_webservices import async_migrate_entry

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
    from eta_webservices import async_migrate_entry

    eintrag = FakeEintrag(minor_version=1)
    await async_migrate_entry(FakeHass(eintrag), eintrag)

    assert eintrag.data == {"host": "192.0.2.10", "port": 8080}
    assert eintrag.options == {}


async def test_migration_uebernimmt_keine_fremde_kennung():
    from eta_webservices import async_migrate_entry

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
    from eta_webservices import async_migrate_entry

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

    from eta_webservices.config_flow import wetter_vorschlag

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
    fertig = await flow.async_step_fub_names(
        {"kessel": "Kessel", "sys": "Sys", "pufferflex": "PufferFlex", "pufferflex2": "PufferFlex 2"}
    )
    assert fertig["type"] == "create_entry"
    assert "puffer_volumen" not in fertig["data"]


async def test_alter_puffer_fragt_nach_seinen_litern(monkeypatch):
    """Nur für den Puffer, der sein Volumen nicht meldet; vorbelegt mit dem bisherigen Wert."""
    from eta_webservices import config_flow as modul

    bisher = {"host": "192.0.2.10", "port": 8080, "puffer2_volumen": 650}
    flow, _ = await options_schritt(monkeypatch, bisher, optionen(components=["puffer", "puffer2"]))

    async def nur_puffer2(*_):
        return ["puffer2"]

    monkeypatch.setattr(modul, "_puffer_ohne_volumen", nur_puffer2)
    schritt = await flow.async_step_fub_names(
        {"kessel": "Kessel", "sys": "Sys", "pufferflex": "PufferFlex", "pufferflex2": "Puffer"}
    )
    assert schritt["step_id"] == "puffer"
    felder = {str(k): k.default() for k in schritt["data_schema"].schema}
    assert felder == {"puffer2_volumen": 650}
    with pytest.raises(vol.Invalid):
        schritt["data_schema"]({"puffer2_volumen": -5})
    fertig = await flow.async_step_puffer({"puffer2_volumen": 800})
    assert fertig["type"] == "create_entry"
    assert fertig["data"]["puffer2_volumen"] == 800
    assert fertig["data"]["fub_names"]["pufferflex2"] == "Puffer"


async def test_erkennung_der_puffer_ohne_volumen(monkeypatch):
    """Fühler gefunden, Volumen nicht: der ältere Funktionsblock "Puffer"."""
    from eta_webservices import config_flow as modul

    async def menue(client, fub_names):
        return {
            "puffer_fuehler_1": "/1/2/0/11327/0",
            "puffer_volumen": "/1/2/0/0/12499",
            "puffer2_fuehler_1": "/1/3/0/11153/0",
        }, [1]

    monkeypatch.setattr(modul, "async_discover_uris", menue)
    monkeypatch.setattr(modul, "async_get_clientsession", lambda hass: None)
    komponenten = ["kessel", "puffer", "puffer2", "puffer3"]
    assert await modul._puffer_ohne_volumen(None, "h", 8080, {}, komponenten) == ["puffer2"]
    assert await modul._puffer_ohne_volumen(None, "h", 8080, {}, ["kessel", "puffer"]) == []

    async def kaputt(client, fub_names):
        raise modul.ETAApiError("kein Menübaum")

    monkeypatch.setattr(modul, "async_discover_uris", kaputt)
    assert await modul._puffer_ohne_volumen(None, "h", 8080, {}, komponenten) == []


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
