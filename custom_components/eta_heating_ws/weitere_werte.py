"""Weitere Werte: frei aus dem Menübaum gewählte Werte der Anlage, nur gelesen.

Die festen Sensoren der Integration decken ab, was Karten, Prognose und
Blueprints brauchen. Der Menübaum einer Anlage führt weit mehr - an einer
echten Anlage über tausend Objekte, darunter ganze Funktionsblöcke, die
die Integration nicht kennt. Unter Konfigurieren wählt der Nutzer daraus,
was er als Sensor haben will.

Zu jedem gewählten Wert merkt sich die Einrichtung die Adresse, den
Funktionsblock, den Weg im Menübaum und wie die Anlage ihn beim Auswählen
gemeldet hat: als Zahl mit Einheit oder als Text. Daraus entsteht der
Sensor, ohne dass die Integration den Wert kennen muss. Geschrieben wird
nie.

Gelesen werden die weiteren Werte getrennt von den festen, im eigenen
Takt und in Portionen: Je Abfrage kommt eine Portion dran, reihum. Wie
viele Werte eine Abfrage liest und in welchem Abstand die Abfragen
kommen, stellt der Nutzer ein. Mehr gewählte Werte belasten die Anlage
also nicht stärker - jeder einzelne wird nur seltener gelesen, siehe
abfrage_alle. Nach dem Start kommen die Portionen einmal dicht
hintereinander, damit kein Sensor lange ohne Wert bleibt, siehe ANLAUF.

Einzelne Werte kann der Nutzer zusätzlich in die schnelle Abfrage nehmen
("schnell" im Eintrag). Sie bleiben in ihrer Portion - die zählt, ob ein
Wert ausbleibt - und werden dazwischen im schnellen Takt aufgefrischt.
"""

from __future__ import annotations

from typing import Any

from .api import ETAValue

PRAEFIX = "wert"
"""Damit beginnt der Schlüssel jedes gewählten Werts, siehe schluessel."""

JE_ABFRAGE = 25
"""So viele weitere Werte liest eine Abfrage, solange der Nutzer nichts anderes einstellt."""

JE_ABFRAGE_GRENZEN = (20, 100)
"""Zwischen so vielen Werten je Abfrage lässt sich wählen.

Jede Portion ist ein eigener Variablensatz auf der Anlage. Wie viele sie
verträgt, ist an keiner Anlage belegt - mit mindestens 20 Werten je
Abfrage und höchstens HOECHSTENS Werten bleiben es fünf.
"""

INTERVALL_GRENZEN = (10, 600)
"""Zwischen so vielen Sekunden Abstand der Abfragen lässt sich wählen."""

SCHRITT = 5
"""In diesen Schritten gehen beide Schieberegler."""

HOECHSTENS = 100
"""So viele weitere Werte lassen sich höchstens wählen."""

SCHNELL_HOECHSTENS = 10
"""So viele weitere Werte lassen sich höchstens zusätzlich in die schnelle Abfrage nehmen.

Sie läuft alle paar Sekunden, siehe ETADataUpdateCoordinator.schnelle_uris -
jeder Wert darin kostet die Anlage ein Vielfaches eines Werts im normalen Takt.
"""

ANLAUF = 5
"""Sekunden zwischen zwei Abfragen, bis nach dem Start jede Portion einmal gelesen ist."""

TRENNER = " › "
"""Trennt Funktionsblock und Stufen des Menübaums im Namen eines Werts."""

TEXT_LAENGE = 255
"""Länger darf ein Zustand in Home Assistant nicht sein."""


def schluessel(uri: str) -> str:
    """Der Schlüssel eines gewählten Werts: aus /120/10601/0/0/12499 wird wert_120_10601_0_0_12499."""
    return PRAEFIX + uri.replace("/", "_")


def gewaehlt(key: str) -> bool:
    """Gehört dieser Schlüssel zu einem frei gewählten Wert?"""
    return key.startswith(f"{PRAEFIX}_")


def _liste(knoten: Any) -> list:
    if knoten is None:
        return []
    return knoten if isinstance(knoten, list) else [knoten]


def menue_werte(parsed: Any) -> dict[str, dict[str, Any]]:
    """Alle Objekte des Menübaums mit Adresse, in der Reihenfolge der Anlage.

    Je Adresse der Funktionsblock und der Weg dorthin. Steht eine Adresse
    mehrfach im Menübaum, zählt die erste Stelle. Führt der Menübaum an
    einer Stelle zwei Objekte desselben Namens mit verschiedenen Adressen,
    bekommt das zweite eine Nummer - sonst hießen zwei Sensoren gleich.
    """
    wurzel = parsed.get("eta", {}).get("menu", {}) if isinstance(parsed, dict) else {}
    werte: dict[str, dict[str, Any]] = {}
    vergeben: dict[tuple, int] = {}

    def sammeln(knoten: dict, fub: str, weg: list[str]) -> None:
        for kind in _liste(knoten.get("object")):
            if not isinstance(kind, dict):
                continue
            name = (kind.get("@name") or "").strip()
            pfad = [*weg, name] if name else weg
            uri = kind.get("@uri")
            if uri and name and uri not in werte:
                stelle = (fub, *pfad)
                vergeben[stelle] = vergeben.get(stelle, 0) + 1
                if vergeben[stelle] > 1:
                    pfad = [*weg, f"{name} ({vergeben[stelle]})"]
                werte[uri] = {"fub": fub, "pfad": pfad}
            sammeln(kind, fub, pfad)

    for fub in _liste(wurzel.get("fub") if isinstance(wurzel, dict) else None):
        if isinstance(fub, dict):
            sammeln(fub, (fub.get("@name") or "").strip(), [])
    return werte


def bezeichnung(eintrag: dict[str, Any]) -> str:
    """Der Name eines Werts: Funktionsblock und Weg im Menübaum."""
    return TRENNER.join(teil for teil in [eintrag.get("fub"), *(eintrag.get("pfad") or [])] if teil)


def _als_zahl(text: str) -> float | None:
    try:
        return float(text.strip().replace(",", "."))
    except (AttributeError, ValueError):
        return None


def einordnen(wert: ETAValue | None) -> dict[str, Any] | None:
    """Wie ein gelesener Wert als Sensor erscheint - None, wenn die Anlage nichts Lesbares liefert.

    Eine Zahl ist er, wenn die Anlage eine Einheit nennt oder ihr Text
    dieselbe Zahl zeigt. Alles andere erscheint als Text, so wie die
    Anlage ihn anzeigt - Zustände wie "Ein", aber auch Uhrzeiten und
    Datumsangaben, deren Rohwert niemandem etwas sagt.
    """
    if wert is None:
        return None
    if wert.is_text:
        return {"zahl": False} if wert.text.strip() else None
    if wert.value is None:
        return {"zahl": True, "einheit": wert.unit, "stellen": wert.dec_places} if wert.unit else None
    if wert.unit or _als_zahl(wert.text) is not None or not wert.text.strip():
        return {"zahl": True, "einheit": wert.unit, "stellen": wert.dec_places}
    return {"zahl": False}


def zustand(wert: ETAValue | None, zahl: bool) -> float | str | None:
    """Der Zustand des Sensors zu einem gelesenen Wert.

    Meldet die Anlage zu einem Zahlenwert einmal Text - oder umgekehrt -,
    bleibt der Sensor bei seiner Art: Eine Zahl ohne Messwert ist
    unbekannt, ein Text zeigt, was die Anlage anzeigt.
    """
    if wert is None:
        return None
    if zahl:
        return None if wert.is_text else wert.value
    text = wert.text.strip()
    return text[:TEXT_LAENGE] if text else None


def _begrenzt(wert: Any, grenzen: tuple[int, int], sonst: float) -> int:
    try:
        zahl = float(wert)
    except (TypeError, ValueError):
        zahl = float(sonst)
    return int(min(max(zahl, grenzen[0]), grenzen[1]))


def je_abfrage(eingestellt: Any = None) -> int:
    """Wie viele Werte eine Abfrage liest: das Eingestellte in seinen Grenzen, sonst JE_ABFRAGE."""
    return _begrenzt(eingestellt, JE_ABFRAGE_GRENZEN, JE_ABFRAGE)


def intervall(eingestellt: Any, abfrageintervall: float) -> int:
    """Der Abstand der Abfragen in Sekunden.

    Ohne eigene Einstellung der Abstand, in dem auch die festen Werte
    gelesen werden - in jedem Fall innerhalb von INTERVALL_GRENZEN.
    """
    return _begrenzt(eingestellt, INTERVALL_GRENZEN, abfrageintervall)


def portionen(werte: dict[str, str], groesse: int = JE_ABFRAGE) -> list[dict[str, str]]:
    """Teilt Schlüssel und Adressen in Portionen von höchstens so vielen Werten."""
    paare = list(werte.items())
    return [dict(paare[i : i + groesse]) for i in range(0, len(paare), groesse)]


def abfrage_alle(anzahl: int, abstand: float, groesse: int = JE_ABFRAGE) -> float:
    """Alle wie viele Sekunden ein Wert gelesen wird, wenn so viele gewählt sind."""
    return max(1, -(-anzahl // groesse)) * abstand
