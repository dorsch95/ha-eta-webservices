"""Den Kessel über seine externe Verriegelung sperren.

Am Kessel lässt sich "Verriegelung durch externen Schaltkontakt"
einrichten. Danach steht im Menübaum einer echten Anlage `Kessel >
Eingänge > Externe Verriegelung` mit zwei Objekten namens "Eingang". Eines
davon beschreibt die Anlage als beschreibbaren Text mit "Nicht invertiert"
(3450) und "Invertiert" (3451) - so antwortet hier auch die Testanlage.
Hängt am Kontakt nichts, läuft der Kessel mit "Invertiert" und sperrt mit
"Nicht invertiert".

Der Schalter "Kessel sperren" stellt diesen Wert um. Es gibt ihn nur mit
Schreibzugriff und wenn diese Art der Sperre gewählt und bestätigt ist: An
einem Eingang mit echtem Kontakt höbe das Umstellen eine Sperre auf.

Die andere Art, über die Ein/Aus-Taste, steht in test_kessel_sperre_taste.
"""

from __future__ import annotations

import pytest

from eta_heating_ws import entitaet_vorgesehen
from eta_heating_ws import switch as switch_platform
from eta_heating_ws.config_flow import _options_schema
from eta_heating_ws.const import (
    CONF_KESSEL_SPERRE,
    KESSEL_SPERRE_ARTEN,
    KESSEL_SPERRE_AUS,
    KESSEL_SPERRE_TASTE,
    KESSEL_SPERRE_VERRIEGELUNG,
    kessel_sperre_art,
)

from .conftest import ohne_objekt
from .test_config_flow import optionen, options_schritt
from .test_sensors import setup_integration

EINGANG = "/264/10891/0/11039/2017"
ZUSTAND_DES_KONTAKTS = "/264/10891/0/11039/2016"
GESPERRT, FREI = "3450", "3451"


async def schalter_von(hass, entry, freigabe=True, schreibzugriff=True):
    """Richtet ein und gibt Koordinator und den Schalter "Kessel sperren" zurück, falls es ihn gibt."""
    entry.data[CONF_KESSEL_SPERRE] = KESSEL_SPERRE_VERRIEGELUNG if freigabe else KESSEL_SPERRE_AUS
    entry.data["enable_switches"] = schreibzugriff
    coordinator, _ = await setup_integration(hass, entry)
    gesammelt: list = []
    await switch_platform.async_setup_entry(hass, entry, gesammelt.extend)
    sperre = next((s for s in gesammelt if s.translation_key == "kessel_sperre"), None)
    if sperre is not None:
        sperre.async_write_ha_state = lambda: None
    return coordinator, sperre


async def test_schalter_entsteht_mit_freigabe_und_schreibzugriff(hass, entry):
    coordinator, sperre = await schalter_von(hass, entry)

    assert coordinator.switch_defs["kessel_sperre"]["uri"] == EINGANG
    assert sperre.entity_id == "switch.eta_heizung_kessel_sperren"
    assert sperre.unique_id == f"eta_switch_{entry.entry_id}_kessel_sperre"
    assert sperre.is_on is False, "Invertiert: Der Kessel läuft"


@pytest.mark.parametrize(
    "freigabe, schreibzugriff", [(False, True), (True, False), (False, False)]
)
async def test_ohne_eigene_freigabe_oder_schreibzugriff_kein_schalter(
    hass, entry, freigabe, schreibzugriff
):
    """Die Freigabe ersetzt den Schreibzugriff nicht - und umgekehrt."""
    coordinator, sperre = await schalter_von(hass, entry, freigabe, schreibzugriff)

    assert sperre is None
    assert "kessel_sperre" not in coordinator.switch_defs
    assert "kessel_sperre" not in coordinator.sensor_defs


async def test_sperren_stellt_den_eingang_auf_nicht_invertiert(hass, entry):
    coordinator, sperre = await schalter_von(hass, entry)
    hass.session.gesetzte_werte.clear()

    await sperre.async_turn_on()

    assert hass.session.gesetzte_werte == [(EINGANG, GESPERRT)]
    assert sperre.is_on is True
    assert coordinator.data["kessel_sperre"].text == "Nicht invertiert"


async def test_freigeben_stellt_den_eingang_zurueck_auf_invertiert(hass, entry):
    _, sperre = await schalter_von(hass, entry)
    await sperre.async_turn_on()
    hass.session.gesetzte_werte.clear()

    await sperre.async_turn_off()

    assert hass.session.gesetzte_werte == [(EINGANG, FREI)]
    assert sperre.is_on is False


async def test_nur_der_einstellwert_wird_geschrieben_nie_der_zustand_des_kontakts(hass, entry):
    """Beide heißen "Eingang" - welcher es ist, sagt allein die Beschreibung der Anlage."""
    coordinator, sperre = await schalter_von(hass, entry)
    await sperre.async_turn_on()
    await sperre.async_turn_off()

    assert coordinator.discovered_uris["kessel_sperre_eingang_1"] == ZUSTAND_DES_KONTAKTS
    assert coordinator.discovered_uris["kessel_sperre_eingang_2"] == EINGANG
    assert all(uri == EINGANG for uri, _ in hass.session.gesetzte_werte)


async def test_kein_schalter_wenn_die_anlage_den_eingang_nicht_beschreibbar_meldet(hass, entry):
    hass.session.sperre_schreibbar = False
    coordinator, sperre = await schalter_von(hass, entry)

    assert sperre is None
    assert "kessel_sperre" not in coordinator.switch_defs


async def test_kein_schalter_wenn_beide_eingaenge_gleich_beschrieben_sind(hass, entry):
    """Dann ist nicht zu entscheiden, welcher der Einstellwert ist - geraten wird nicht."""
    hass.session.sperre_doppelt = True
    _, sperre = await schalter_von(hass, entry)

    assert sperre is None


async def test_kein_schalter_ohne_eingerichtete_verriegelung(hass, entry, menu_xml):
    """Ohne den Zweig im Menübaum gibt es nichts umzustellen."""
    hass.session.menu = ohne_objekt(menu_xml, "/264/10891/0/11039/0")
    coordinator, sperre = await schalter_von(hass, entry)

    assert sperre is None
    assert not any(key.startswith("kessel_sperre") for key in coordinator.discovered_uris)


async def test_kein_schalter_ohne_varinfo(hass, entry):
    """Ältere Anlagen beschreiben ihre Werte nicht - dann lieber kein Schalter."""
    hass.session.varinfo_unterstuetzt = False
    _, sperre = await schalter_von(hass, entry)

    assert sperre is None


async def test_ablehnung_der_anlage_wird_gemeldet(hass, entry):
    from homeassistant.exceptions import HomeAssistantError

    _, sperre = await schalter_von(hass, entry)
    hass.session.fail_uris.add("11039/2017")

    with pytest.raises(HomeAssistantError):
        await sperre.async_turn_on()

    assert sperre._erwartet is None, "kein vorweggenommener Zustand"


def test_schalter_bleibt_nur_mit_freigabe_schreibzugriff_und_kessel():
    """Danach räumt die Integration auf, wenn die Freigabe wieder abgewählt wird."""
    def vorgesehen(schreibzugriff, freigabe):
        return entitaet_vorgesehen(
            "kessel_sperre", ["kessel"], schreibzugriff, True, kessel_sperre=freigabe
        )

    assert vorgesehen(True, True) is True
    assert vorgesehen(True, False) is False
    assert vorgesehen(False, True) is False
    assert vorgesehen(False, False) is False
    assert entitaet_vorgesehen("kessel_schalter", ["kessel"], True, True) is True, (
        "der Ein/Aus-Schalter braucht die Freigabe nicht"
    )


def test_formular_legt_den_schalter_ab_werk_nicht_an():
    feld = next(k for k in _options_schema({}).schema if k == CONF_KESSEL_SPERRE)
    assert feld.default() == KESSEL_SPERRE_AUS


def test_formular_bietet_beide_arten_zur_wahl():
    schema = _options_schema({})
    feld = next(k for k in schema.schema if k == CONF_KESSEL_SPERRE)
    assert schema.schema[feld].config["options"] == KESSEL_SPERRE_ARTEN
    assert KESSEL_SPERRE_ARTEN == [KESSEL_SPERRE_AUS, KESSEL_SPERRE_TASTE, KESSEL_SPERRE_VERRIEGELUNG]


@pytest.mark.parametrize("gespeichert", [None, True, False, "irgendwas", ""])
def test_unbekannte_einstellung_legt_keinen_schalter_an(gespeichert):
    assert kessel_sperre_art({CONF_KESSEL_SPERRE: gespeichert}) == KESSEL_SPERRE_AUS
    assert kessel_sperre_art({}) == KESSEL_SPERRE_AUS


@pytest.mark.parametrize("vorher", [KESSEL_SPERRE_AUS, KESSEL_SPERRE_TASTE])
async def test_neu_gewaehlt_folgt_der_warnschritt(monkeypatch, vorher):
    """Erst nach der Bestätigung geht es weiter zu den Funktionsblock-Namen."""
    bisher = {**optionen(), "enable_switches": True, CONF_KESSEL_SPERRE: vorher}
    flow, ergebnis = await options_schritt(
        monkeypatch,
        bisher,
        {**optionen(), "enable_switches": True, CONF_KESSEL_SPERRE: KESSEL_SPERRE_VERRIEGELUNG},
    )

    assert ergebnis["step_id"] == "sperre_warnung"
    weiter = await flow.async_step_sperre_warnung({})
    assert weiter["step_id"] == "fub_names"


async def test_schon_gewaehlt_folgt_keine_warnung(monkeypatch):
    bisher = {**optionen(), "enable_switches": True, CONF_KESSEL_SPERRE: KESSEL_SPERRE_VERRIEGELUNG}
    _, ergebnis = await options_schritt(
        monkeypatch,
        bisher,
        {**optionen(), "enable_switches": True, CONF_KESSEL_SPERRE: KESSEL_SPERRE_VERRIEGELUNG},
    )

    assert ergebnis["step_id"] == "fub_names"


async def test_beide_warnungen_nacheinander_wenn_beides_neu_ist(monkeypatch):
    """Erst der Schreibzugriff, dann die Kesselsperre."""
    bisher = {**optionen(), "enable_switches": False, CONF_KESSEL_SPERRE: KESSEL_SPERRE_AUS}
    flow, ergebnis = await options_schritt(
        monkeypatch,
        bisher,
        {**optionen(), "enable_switches": True, CONF_KESSEL_SPERRE: KESSEL_SPERRE_VERRIEGELUNG},
    )

    assert ergebnis["step_id"] == "switch_warning"
    ergebnis = await flow.async_step_switch_warning({})
    assert ergebnis["step_id"] == "sperre_warnung"
