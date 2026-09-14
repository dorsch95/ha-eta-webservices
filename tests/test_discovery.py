"""Tests für die namensbasierte URI-Erkennung."""

from __future__ import annotations

from eta_webservices.api import ETAApiClient
from eta_webservices.const import fub_role_default
from eta_webservices.uri_discovery import async_discover_uris


async def discover(hass, overrides=None):
    client = ETAApiClient(hass, hass.session, "192.0.2.10", 8080)
    return await async_discover_uris(client, overrides or {})


async def test_kernwerte_werden_gefunden(hass):
    uris, _ = await discover(hass)
    assert uris["kessel_temperatur"].startswith("/")
    assert "aussentemperatur" in uris
    assert uris["kessel_temperatur"] != uris["aussentemperatur"]


async def test_pufferfuehler_werden_durchnummeriert(hass):
    _, indices = await discover(hass)
    assert indices
    assert indices == sorted(indices)
    assert indices[0] == 1


async def test_umbenannter_funktionsblock_wird_gefunden(hass, menu_xml):
    hass.session.menu = menu_xml.replace('<fub uri="/264/10891" name="Kessel">', '<fub uri="/264/10891" name="Pelletskessel">')
    uris, _ = await discover(hass, {"kessel": "Pelletskessel"})
    assert "kessel_temperatur" in uris


async def test_falscher_fub_name_liefert_keine_kesselwerte(hass, menu_xml):
    hass.session.menu = menu_xml.replace('<fub uri="/264/10891" name="Kessel">', '<fub uri="/264/10891" name="Pelletskessel">')
    uris, _ = await discover(hass, {"kessel": "Kessel"})
    assert "kessel_temperatur" not in uris


def test_standardnamen_je_rolle():
    assert fub_role_default("kessel", ["kessel"]) == "Kessel"
    assert fub_role_default("hk", ["kessel", "hk", "hk2"]) == "HK1"
    assert fub_role_default("hk", ["kessel", "hk"]) == "HK"
