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


def test_fub_formular_ist_mit_standardnamen_vorbelegt():
    schema = _fub_names_schema(["kessel", "sys", "hk", "hk2"], {})
    defaults = {str(key): key.default() for key in schema.schema}
    assert defaults["kessel"] == "Kessel"
    assert defaults["hk"] == "HK1"
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
