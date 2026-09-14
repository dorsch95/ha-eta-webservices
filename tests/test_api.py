"""Tests für den HTTP-/XML-Zugriff auf die Anlage."""

from __future__ import annotations

import pytest

from eta_webservices.api import ETAApiClient, ETAApiError, _parse_value_node
from eta_webservices.const import MAX_PARALLEL_REQUESTS

from .conftest import var_xml


def parse(xml: str):
    import xmltodict

    return _parse_value_node(xmltodict.parse(xml)["eta"]["value"])


def test_skalierter_zahlenwert():
    reading = parse(var_xml(value="555", unit="°C", scale="10"))
    assert reading.display == pytest.approx(55.5)
    assert reading.unit == "°C"
    assert reading.is_text is False


def test_scale_null_fuehrt_nicht_zur_division_durch_null():
    reading = parse(var_xml(value="555", unit="°C", scale="0"))
    assert reading.display == pytest.approx(555.0)


def test_textwert_zeigt_den_klartext_statt_der_kennzahl():
    """Der Rohwert einer Textvariable ist eine interne Kennzahl.

    Die Anlage kennzeichnet solche Variablen über advTextOffset. Wer das
    übersieht, zeigt dem Nutzer statt "Heizbetrieb" die Zahl 950 an -
    genau das ist in einer früheren Version passiert.
    """
    reading = parse(
        var_xml(value="950", str_value="Heizbetrieb", text_offset="950")
    )
    assert reading.display == "Heizbetrieb"
    assert reading.is_text is True
    assert reading.unit == ""


def test_leerer_wert_faellt_auf_text_zurueck():
    reading = parse(var_xml(value="", str_value="Aus"))
    assert reading.display == "Aus"
    assert reading.is_text is True


def test_zahlenwert_bleibt_zahl_wenn_kein_textoffset_gesetzt_ist():
    reading = parse(
        var_xml(value="724", str_value="72,4", unit="°C", scale="10")
    )
    assert reading.display == pytest.approx(72.4)
    assert reading.is_text is False
    assert reading.unit == "°C"


def test_dezimalstellen_der_anlage_werden_uebernommen():
    reading = parse(
        var_xml(value="148", str_value="1,48", unit="bar", scale="100",
                dec_places="2")
    )
    assert reading.dec_places == 2


async def test_einzelwert_lesen(hass):
    client = ETAApiClient(hass, hass.session, "192.0.2.10", 8080)
    reading = await client.async_get_value("/120/10101/0/11109/0")
    assert reading.display == pytest.approx(55.5)


async def test_fehlerhafter_status_wird_zu_api_error(hass):
    class Broken(type(hass.session)):
        def get(self, url, timeout=None):
            from .conftest import FakeResponse

            return FakeResponse("", status=404)

    client = ETAApiClient(hass, Broken(""), "192.0.2.10", 8080)
    with pytest.raises(ETAApiError):
        await client.async_get_value("/1/2/3")


async def test_verbindungstest_meldet_fehler_statt_zu_werfen(hass):
    hass.session.fail_uris = {"/user/menu"}
    client = ETAApiClient(hass, hass.session, "192.0.2.10", 8080)
    assert await client.async_test_connection() is False


async def test_mehrere_werte_parallel_aber_begrenzt(hass):
    client = ETAApiClient(hass, hass.session, "192.0.2.10", 8080)
    uris = {f"s{i}": f"/1/2/{i}" for i in range(20)}
    values = await client.async_get_values(uris)
    assert len(values) == 20
    assert hass.session.peak_parallel <= MAX_PARALLEL_REQUESTS
    assert hass.session.peak_parallel > 1


async def test_einzelner_fehler_kippt_den_zyklus_nicht(hass):
    hass.session.fail_uris = {"/1/2/7"}
    client = ETAApiClient(hass, hass.session, "192.0.2.10", 8080)
    uris = {f"s{i}": f"/1/2/{i}" for i in range(10)}
    values = await client.async_get_values(uris)
    assert "s7" not in values
    assert len(values) == 9


FEHLER_XML = (
    '<eta version="1.0"><errors uri="/user/errors">'
    '<fub uri="/264/10891" name="Kessel">'
    '<error msg="Wasserdruck zu niedrig 0,00 bar" priority="Error" '
    'time="2026-09-14 12:48:12">Heizungswasser nachfüllen!</error>'
    '<error msg="Abgasfühler unterbrochen" priority="Warning" '
    'time="2026-09-14 12:47:50">Fühler oder Kabel defekt</error>'
    "</fub>"
    '<fub uri="/120/10101" name="HK1"/>'
    "</errors></eta>"
)


async def test_api_version_wird_gelesen(hass):
    client = ETAApiClient(hass, hass.session, "192.0.2.10", 8080)
    assert await client.async_get_api_version() == "1.2"


async def test_fehlende_api_version_ist_kein_fehler(hass):
    hass.session.fail_uris = {"/user/api"}
    client = ETAApiClient(hass, hass.session, "192.0.2.10", 8080)
    assert await client.async_get_api_version() is None


async def test_aktive_fehler_werden_gelesen(hass):
    hass.session.errors_xml = FEHLER_XML
    client = ETAApiClient(hass, hass.session, "192.0.2.10", 8080)
    fehler = await client.async_get_errors()

    assert len(fehler) == 2
    assert fehler[0].fub == "Kessel"
    assert fehler[0].msg == "Wasserdruck zu niedrig 0,00 bar"
    assert fehler[0].priority == "Error"
    assert "nachfüllen" in fehler[0].text
    assert set(fehler[0].as_dict()) == {
        "funktionsblock",
        "meldung",
        "prioritaet",
        "zeit",
        "hinweis",
    }


async def test_funktionsblock_ohne_fehler_liefert_nichts(hass):
    client = ETAApiClient(hass, hass.session, "192.0.2.10", 8080)
    assert await client.async_get_errors() == []


async def test_varinfo_liefert_die_gueltigen_zustaende(hass):
    client = ETAApiClient(hass, hass.session, "192.0.2.10", 8080)
    info = await client.async_get_varinfo("/120/10101/0/11124/2001")

    assert info["valid_values"] == ["Aus", "Heizbetrieb"]
    assert info["writable"] is True
    assert info["type"] == "TEXT"


async def test_varinfo_fehlt_auf_aelteren_anlagen(hass):
    hass.session.varinfo_unterstuetzt = False
    client = ETAApiClient(hass, hass.session, "192.0.2.10", 8080)
    assert await client.async_get_varinfo("/1/2/3/4/5") is None


async def test_variablensatz_liefert_alle_werte_in_einer_anfrage(hass):
    client = ETAApiClient(hass, hass.session, "192.0.2.10", 8080)
    uris = ["/120/10101/0/11109/0", "/120/10101/0/11160/0"]
    await client.async_create_varset("testsatz", uris)

    vorher = hass.session.count
    werte = await client.async_get_varset("testsatz")

    assert set(werte) == set(uris)
    assert hass.session.count - vorher == 1
    assert werte[uris[0]].display == pytest.approx(55.5)


async def test_verschwundener_variablensatz_meldet_sich_deutlich(hass):
    client = ETAApiClient(hass, hass.session, "192.0.2.10", 8080)
    with pytest.raises(ETAApiError):
        await client.async_get_varset("gibtesnicht")
