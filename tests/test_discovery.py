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


SOLAR_ERTRAG = """<object uri="/120/10221/0/0/12379" name="Leistung">
<object uri="/120/10221/0/0/12349" name="Wärmemenge"/>
<object uri="/120/10221/0/0/12350" name="Ertrag heute"/>
<object uri="/120/10221/0/0/12769" name="Ertrag gestern"/>
</object>
"""
"""Der Zweig, den nur eine Solaranlage mit Wärmemengenmessung hat."""


async def test_solarwerte_werden_gefunden(hass):
    uris, _ = await discover(hass)
    assert uris["solar_kollektor"] == "/120/10221/0/11139/0"
    assert uris["solar_leistung"] == "/120/10221/0/0/12379"
    assert uris["solar_waermemenge"] == "/120/10221/0/0/12349"
    assert uris["solar_ertrag_heute"] == "/120/10221/0/0/12350"
    assert uris["solar_ertrag_gestern"] == "/120/10221/0/0/12769"


async def test_ohne_waermemengenmessung_nur_der_kollektor(hass, menu_xml):
    """Ohne Wärmemengenmessung darf nur die Kollektortemperatur entstehen."""
    assert SOLAR_ERTRAG in menu_xml
    hass.session.menu = menu_xml.replace(SOLAR_ERTRAG, "")
    uris, _ = await discover(hass)
    assert uris["solar_kollektor"] == "/120/10221/0/11139/0"
    assert [key for key in uris if key.startswith("solar_")] == ["solar_kollektor"]


async def test_umbenannter_solar_funktionsblock(hass, menu_xml):
    hass.session.menu = menu_xml.replace(
        '<fub uri="/120/10221" name="Solar">', '<fub uri="/120/10221" name="Sonne">'
    )
    uris, _ = await discover(hass, {"solar": "Sonne"})
    assert "solar_kollektor" in uris


async def test_ertragszweig_wird_auch_verschachtelt_gefunden(hass, menu_xml):
    """Liegt der Ertragszweig tiefer im Menü, greift die Suche nach Namen."""
    verschachtelt = (
        '<object uri="/120/10221/0/0/13000" name="Sonstiges">\n'
        + SOLAR_ERTRAG
        + "</object>\n"
    )
    hass.session.menu = menu_xml.replace(SOLAR_ERTRAG, verschachtelt)
    uris, _ = await discover(hass)
    assert uris["solar_waermemenge"] == "/120/10221/0/0/12349"
    assert uris["solar_ertrag_gestern"] == "/120/10221/0/0/12769"
