"""Tests für den Einrichtungs-Dialog."""

from __future__ import annotations

import pytest
import voluptuous as vol

from eta_webservices.config_flow import _connection_schema, _fub_names_schema
from eta_webservices.const import (
    DEFAULT_SCAN_INTERVAL,
    MAX_SCAN_INTERVAL,
    MIN_SCAN_INTERVAL,
    SCHEMA_FUB_ROLES,
    SCHEMAS,
)


def gueltige_eingabe(**overrides):
    daten = {
        "host": "10.0.0.173",
        "port": 8080,
        "schema": next(iter(SCHEMAS)),
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


def test_verbindungsformular_lehnt_unbekanntes_schema_ab():
    with pytest.raises(vol.Invalid):
        _connection_schema({})(gueltige_eingabe(schema="Gibt es nicht"))


def test_verbindungsformular_uebernimmt_bisherige_werte():
    schema = _connection_schema({"host": "192.168.1.5", "port": 8081})
    markers = {str(key): key for key in schema.schema}
    assert markers["host"].default() == "192.168.1.5"
    assert markers["port"].default() == 8081


@pytest.mark.parametrize("anlagenschema", list(SCHEMAS))
def test_jedes_anlagenschema_hat_fub_rollen(anlagenschema):
    assert SCHEMA_FUB_ROLES.get(anlagenschema)


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
