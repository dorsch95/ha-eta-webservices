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
    assert reading.value == pytest.approx(55.5)
    assert reading.unit == "°C"
    assert reading.is_text is False


def test_scale_null_fuehrt_nicht_zur_division_durch_null():
    reading = parse(var_xml(value="555", unit="°C", scale="0"))
    assert reading.value == pytest.approx(555.0)


def test_textwert():
    reading = parse(var_xml(str_value="Heizbetrieb"))
    assert reading.value == "Heizbetrieb"
    assert reading.is_text is True


def test_leerer_wert_faellt_auf_text_zurueck():
    reading = parse(var_xml(value="", str_value="Aus"))
    assert reading.value == "Aus"
    assert reading.is_text is True


async def test_einzelwert_lesen(hass):
    client = ETAApiClient(hass, hass.session, "10.0.0.173", 8080)
    reading = await client.async_get_value("/120/10101/0/11109/0")
    assert reading.value == pytest.approx(55.5)


async def test_fehlerhafter_status_wird_zu_api_error(hass):
    class Broken(type(hass.session)):
        def get(self, url, timeout=None):
            from .conftest import FakeResponse

            return FakeResponse("", status=404)

    client = ETAApiClient(hass, Broken(""), "10.0.0.173", 8080)
    with pytest.raises(ETAApiError):
        await client.async_get_value("/1/2/3")


async def test_verbindungstest_meldet_fehler_statt_zu_werfen(hass):
    hass.session.fail_uris = {"/user/menu"}
    client = ETAApiClient(hass, hass.session, "10.0.0.173", 8080)
    assert await client.async_test_connection() is False


async def test_mehrere_werte_parallel_aber_begrenzt(hass):
    client = ETAApiClient(hass, hass.session, "10.0.0.173", 8080)
    uris = {f"s{i}": f"/1/2/{i}" for i in range(20)}
    values = await client.async_get_values(uris)
    assert len(values) == 20
    assert hass.session.peak_parallel <= MAX_PARALLEL_REQUESTS
    assert hass.session.peak_parallel > 1


async def test_einzelner_fehler_kippt_den_zyklus_nicht(hass):
    hass.session.fail_uris = {"/1/2/7"}
    client = ETAApiClient(hass, hass.session, "10.0.0.173", 8080)
    uris = {f"s{i}": f"/1/2/{i}" for i in range(10)}
    values = await client.async_get_values(uris)
    assert "s7" not in values
    assert len(values) == 9
