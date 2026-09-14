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
