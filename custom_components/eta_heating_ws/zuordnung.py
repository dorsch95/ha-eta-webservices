"""Fehlende Werte von Hand zuordnen.

Die Erkennung findet die festen Messwerte über Namen und Kennungen, die
an Menübäumen echter Anlagen belegt sind, siehe uri_discovery.py. An
einer Anlage, deren Menübaum anders aufgebaut ist, bleibt ein Wert
unentdeckt, obwohl die Heizung ihn führt - so der Rücklauf eines
Stückholzkessels von 2015 (Issue 11), solange sein Menübaum nicht
bekannt war.

Für diesen Fall ordnet der Nutzer den Wert selbst zu: Er wählt den
fehlenden Messwert und dazu einen Eintrag aus dem Menübaum seiner
Heizung. Drei Regeln halten das ungefährlich:

- Zur Wahl stehen nur gelesene Messwerte. Was die Integration auch
  beschreibt - Vorrat und Fassungsvermögen des Pelletlagers über ihre
  Zahlenfelder -, lässt sich nicht zuordnen: Ein falscher Eintrag wäre
  dort ein Schreibzugriff an die falsche Stelle. Schalter, Tasten und
  Zeitfenster sind keine Messwerte und stehen deshalb nie zur Wahl.
- Ein Eintrag muss im Funktionsblock des Messwerts stehen und nach Art
  und Einheit zu ihm passen: eine Temperatur zu einer Temperatur, ein
  Text zu einem Zustand. Dazu liest die Einrichtung die Einträge des
  Blocks einmal, siehe passt.
- Der Partikelabscheider bleibt außen vor. Aus seinem Funktionsblock
  gibt es nur Hochspannung, Strom und Leistung.

Dazu kommt eine vierte für das, was die Integration von selbst
schaltet: Der Aschebox-Plan schaltet den Kessel aus und wieder ein und
drückt die Entaschentaste, je nachdem, was Kessel-Zustand und Verbrauch
seit dem Leeren melden. Stammt einer der beiden aus einer Zuordnung von
Hand, gibt es den Plan nicht, siehe STEUERND - geschaltet wird nur nach
Werten, die die Erkennung selbst gefunden hat.

Gespeichert wird je Messwert die Adresse (CONF_ZUORDNUNGEN). Eine
Zuordnung geht der Suche vor, siehe uri_discovery.async_discover_uris.
Beim Laden prüft die Integration jede noch einmal nach Art und Einheit,
siehe coordinator.ETADataUpdateCoordinator.async_discover.
"""

from __future__ import annotations

from typing import Any

from .api import ETAValue
from .const import SENSORS, ZAHLEN, normalize_components
from .weitere_werte import TEXT_LAENGE, einordnen

BESCHRIEBEN = frozenset(definition["quelle"] for definition in ZAHLEN.values())
"""Messwerte, an deren Adresse die Integration auch schreibt, siehe const.ZAHLEN."""

OHNE_ZUORDNUNG = frozenset({"partikelabscheider"})
"""Komponenten, deren Messwerte sich nie von Hand zuordnen lassen."""

STEUERND = frozenset({"kessel_zustand", "aschebox_verbrauch"})
"""Messwerte, nach denen die Integration von selbst schaltet, siehe aschebox.py.

Sie lassen sich zuordnen, damit ihr Sensor einen Wert hat. Den
Aschebox-Plan gibt es dann aber nicht.
"""


def zuordenbar(key: str) -> bool:
    """Ob sich ein Messwert von Hand zuordnen lässt, siehe oben."""
    info = SENSORS.get(key)
    return (
        info is not None
        and key not in BESCHRIEBEN
        and info["component"] not in OHNE_ZUORDNUNG
    )


def gueltige(zuordnungen: Any) -> dict[str, str]:
    """Die gespeicherten Zuordnungen, soweit sie sich zuordnen lassen: je Messwert eine Adresse."""
    if not isinstance(zuordnungen, dict):
        return {}
    return {
        key: uri
        for key, uri in zuordnungen.items()
        if isinstance(uri, str) and uri and zuordenbar(key)
    }


def fehlende(komponenten, gefunden, zuordnungen=None) -> list[str]:
    """Die Messwerte der gewählten Komponenten, die zum Zuordnen anstehen.

    Das sind die, die die Erkennung nicht gefunden hat, und die schon von
    Hand zugeordneten - sonst ließe sich eine Zuordnung nicht mehr ändern
    oder aufheben. In der Reihenfolge von const.SENSORS.
    """
    aktiv = set(normalize_components(komponenten))
    zugeordnet = gueltige(zuordnungen)
    return [
        key
        for key, info in SENSORS.items()
        if info["component"] in aktiv
        and zuordenbar(key)
        and (key not in gefunden or key in zugeordnet)
    ]


def gleiche_einheit(eine: str | None, andere: str | None) -> bool:
    """Ob zwei Einheiten dieselbe sind - die Anlage schreibt Liter klein, Home Assistant groß."""
    return (eine or "").strip().casefold() == (andere or "").strip().casefold()


def passt(key: str, wert: ETAValue | None) -> bool:
    """Ob ein gelesener Eintrag nach Art und Einheit zu einem Messwert passt.

    Ein Zustand nimmt nur einen Text, eine Zahl nur eine Zahl mit der
    Einheit des Messwerts. Wo die Integration die Einheit selbst von der
    Anlage nimmt (einheit_der_anlage), passt jede Zahl. Liefert die Anlage
    zu einem Eintrag nichts Lesbares, passt er nie.
    """
    info = SENSORS[key]
    art = einordnen(wert)
    if art is None:
        return False
    if info.get("is_string"):
        return not art["zahl"]
    if not art["zahl"]:
        return False
    einheit = info.get("default_unit")
    if info.get("einheit_der_anlage") or not einheit:
        return True
    return gleiche_einheit(art.get("einheit"), einheit)


def anzeige(wert: ETAValue | None) -> str:
    """Was die Anlage zu einem Eintrag gerade anzeigt, etwa "69,1 °C" - leer ohne lesbaren Wert."""
    if wert is None:
        return ""
    text = (wert.text or "").strip()[:TEXT_LAENGE]
    if wert.is_text or not wert.unit:
        return text
    return f"{text} {wert.unit}".strip()
