"""Ob Warmwasser lädt, ob das Frischwassermodul arbeitet und das Warmwasser im Kombispeicher.

Belegt an zwei Menübäumen: der Testanlage mit Warmwasserspeichern "WW" und
"WW 2" und vier Kombispeichern (zwei PufferFlex, zwei ältere "Puffer") und
der Anlage des Nutzers mit Frischwassermodul und PufferFlex ohne
Kombispeicher.
"""

from __future__ import annotations

from eta_heating_ws.uebersicht import _ws_uebersicht

from . import test_mehrere_speicher as testanlage
from . import test_puffer_ohne_kombi as nutzeranlage
from .test_zeitprogramm_karte import Verbindung


def uris(coordinator, *schluessel):
    return {key: coordinator.sensor_defs.get(key, {}).get("uri") for key in schluessel}


async def test_warmwasserspeicher_meldet_zustand_und_ladepumpe(hass, entry):
    """Laden und Zirkulation sind zweierlei: Der Speicher hat für beides einen eigenen Wert."""
    coordinator = await testanlage.aufbauen(hass, entry)

    assert uris(coordinator, "fwm_zustand", "fwm_ladepumpe", "fwm_zirkulationspumpe") == {
        "fwm_zustand": "/120/10111/0/0/12129",
        "fwm_ladepumpe": "/120/10111/0/11131/2001",
        "fwm_zirkulationspumpe": "/120/10111/0/11137/2001",
    }
    assert uris(coordinator, "fwm2_zustand", "fwm2_ladepumpe") == {
        "fwm2_zustand": "/120/10112/0/0/12129",
        "fwm2_ladepumpe": "/120/10112/0/11131/2001",
    }
    assert "fwm_pufferpumpe" not in coordinator.sensor_defs, "die hat nur das Frischwassermodul"


async def test_frischwassermodul_meldet_zustand_und_pufferpumpe(hass, entry):
    """Die Pufferpumpe läuft, solange das Modul Wasser erwärmt - daran sieht die Karte das Zapfen."""
    coordinator = await nutzeranlage.aufbauen(hass, entry)

    assert uris(coordinator, "fwm_zustand", "fwm_pufferpumpe") == {
        "fwm_zustand": "/79/10531/0/0/12195",
        "fwm_pufferpumpe": "/79/10531/0/11280/2001",
    }
    assert "fwm_ladepumpe" not in coordinator.sensor_defs, "die hat nur der Warmwasserspeicher"


async def test_kombispeicher_meldet_sein_warmwasser(hass, entry):
    """PufferFlex unter "Warmwasserbereich", der ältere Puffer unter seinem Warmwasser-Zustand."""
    coordinator = await testanlage.aufbauen(hass, entry)

    assert uris(coordinator, "puffer_warmwasser", "puffer_warmwasser_zustand") == {
        "puffer_warmwasser": "/120/10601/0/0/13434",
        "puffer_warmwasser_zustand": None,
    }, "der PufferFlex führt keinen eigenen Warmwasser-Zustand"
    assert coordinator.funktionsblock("puffer3") == "Puffer"
    assert uris(coordinator, "puffer3_warmwasser", "puffer3_warmwasser_zustand") == {
        "puffer3_warmwasser": "/120/10251/0/0/12271",
        "puffer3_warmwasser_zustand": "/120/10251/0/0/12129",
    }


async def test_ohne_kombispeicher_kein_warmwasser_im_puffer(hass, entry):
    """Der Menübaum führt den Warmwasserbereich trotzdem - seine Solltemperatur hat dann keine Einheit."""
    coordinator = await nutzeranlage.aufbauen(hass, entry)

    assert "puffer_warmwasser" not in coordinator.sensor_defs
    assert "puffer_warmwasser" not in coordinator.discovered_uris


async def test_mit_kombispeicher_an_derselben_anlage(hass, entry):
    coordinator = await nutzeranlage.aufbauen(hass, entry, kombi=True)

    assert coordinator.sensor_defs["puffer_warmwasser"]["uri"] == "/120/10601/0/0/13434"


async def test_ohne_antwort_bleibt_das_warmwasser(hass, entry, monkeypatch):
    """Antwortet die Anlage auf die Frage nach der Einheit nicht, zählt der Menübaum."""
    from eta_heating_ws.coordinator import ETADataUpdateCoordinator

    async def stumm(self, uris):
        return [None for _ in uris]

    monkeypatch.setattr(ETADataUpdateCoordinator, "_varinfos", stumm)
    coordinator = await nutzeranlage.aufbauen(hass, entry)

    assert "puffer_warmwasser" in coordinator.sensor_defs


async def test_karte_bekommt_die_neuen_werte(hass, entry):
    """Die Karte fragt nach dem Schlüssel - die neuen Sensoren kommen ohne Zutun mit."""
    await testanlage.aufbauen(hass, entry)
    for key in ("fwm_zustand", "fwm_ladepumpe", "puffer_warmwasser"):
        hass.entity_registry.anlegen(f"sensor.{key}", f"eta_static_testeintrag_{key}", "testeintrag")
    verbindung = Verbindung()

    _ws_uebersicht(hass, verbindung, {"id": 1, "type": "eta_heating_ws/uebersicht"})

    [(_, ergebnis)] = verbindung.ergebnisse
    [anlage] = ergebnis["anlagen"]
    assert {"fwm_zustand", "fwm_ladepumpe", "puffer_warmwasser"} <= set(anlage["entitaeten"])
    bauarten = {teil["id"]: teil.get("bauart") for teil in anlage["teile"] if teil["art"] == "warmwasser"}
    assert bauarten == {"fwm": "speicher", "fwm2": "speicher"}, "WW und WW 2 sind Warmwasserspeicher"
