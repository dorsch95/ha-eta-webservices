"""Wer an der Anlage woher seine Wärme bekommt.

Die Karte "ETA Übersicht" zeichnet Leitungen zwischen den Teilen der
Anlage. Dafür muss sie wissen, was woran hängt. Der Menübaum der
Webservices verrät es nicht: Unter jedem Puffer stehen zwar "Erzeuger" und
"Verbraucher", aber nur mit Temperaturen und Einstellungen, ohne den Namen
des angeschlossenen Funktionsblocks.

Deshalb gilt eine Vorgabe, die für die meisten Anlagen stimmt, siehe
vorgabe. Wo sie nicht stimmen kann - bei mehreren Puffern oder mit einer
Fernleitung -, fragt der Einrichtungsdialog je Teil nach der Quelle, siehe
braucht_auswahl.

Puffer und Fernleitung sind beides: Sie bekommen Wärme und geben sie
weiter. Kessel, Solar und PV-Heizmodul erzeugen nur, Heizkreise und
Warmwasser verbrauchen nur.

Der Brenner bekommt keine Verbindung. Sein Funktionsblock fordert ihn nur
an und gibt Leistung und Temperatur vor; Vor- und Rücklauf zu einem
anderen Teil der Anlage hat er im Menübaum nicht.

Das Modul kommt ohne Home Assistant aus.
"""

from __future__ import annotations

from .const import HEIZKREISE, PUFFER_SPEICHER, WARMWASSER_SPEICHER

KESSEL = "kessel"
FERNLEITUNG = "fernleitung"

ERZEUGER = ("solar", "pvm")
"""Erzeuger neben dem Kessel. Bei ihnen steht nicht die Quelle, sondern der Puffer, in den sie laden."""

FELD = "verbindung_"
"""Damit beginnen die Felder des Dialogs, dahinter die Komponente."""


def feld(teil: str) -> str:
    """Der Name des Formularfelds für dieses Teil."""
    return f"{FELD}{teil}"


def _puffer(komponenten) -> list[str]:
    return [k for k in komponenten if k in PUFFER_SPEICHER]


def _verbraucht(teil: str) -> bool:
    return teil in HEIZKREISE or teil in WARMWASSER_SPEICHER


def moegliche_quellen(komponenten, teil: str) -> list[str]:
    """Was für dieses Teil zur Wahl steht.

    Für Puffer, Fernleitung, Heizkreise und Warmwasser: woher die Wärme
    kommt - Kessel, jeder Puffer, die Fernleitung, nur nicht das Teil
    selbst. Für Solar und PV-Heizmodul: in welchen Puffer sie laden.
    """
    if teil in ERZEUGER:
        return _puffer(komponenten)
    return [
        k
        for k in komponenten
        if k != teil and (k == KESSEL or k in PUFFER_SPEICHER or k == FERNLEITUNG)
    ]


def vorgabe(komponenten) -> dict[str, str | None]:
    """Die Verbindungen, wie sie ohne Angabe gelten.

    Der Kessel lädt den ersten Puffer, weitere Puffer hängen
    hintereinander. Die Fernleitung geht vom ersten Puffer ab, Heizkreise
    und Warmwasser hängen am letzten. Solar und PV-Heizmodul laden in den
    ersten Puffer. Ohne Puffer hängt alles am Kessel; die übrigen Erzeuger
    haben dann kein Ziel.
    """
    puffer = _puffer(komponenten)
    erster = puffer[0] if puffer else None
    letzter = puffer[-1] if puffer else KESSEL
    wege: dict[str, str | None] = {
        teil: puffer[nummer - 1] if nummer else KESSEL for nummer, teil in enumerate(puffer)
    }
    if FERNLEITUNG in komponenten:
        wege[FERNLEITUNG] = erster or KESSEL
    wege.update({teil: letzter for teil in komponenten if _verbraucht(teil)})
    wege.update({teil: erster for teil in komponenten if teil in ERZEUGER})
    return wege


def _im_kreis(wege: dict[str, str | None], teil: str) -> bool:
    """Führt der Weg von diesem Teil über seine Quellen zu ihm zurück?"""
    besucht = set()
    aktuell = wege.get(teil)
    while aktuell is not None and aktuell in wege and aktuell not in ERZEUGER:
        if aktuell == teil:
            return True
        if aktuell in besucht:
            return False
        besucht.add(aktuell)
        aktuell = wege[aktuell]
    return False


def im_kreis(komponenten, gewaehlt: dict[str, str]) -> bool:
    """Ergäbe diese Auswahl einen Kreis - etwa Puffer 1 an Puffer 2 und Puffer 2 an Puffer 1?"""
    wege = {**vorgabe(komponenten), **gewaehlt}
    return any(_im_kreis(wege, teil) for teil in wege if teil not in ERZEUGER)


def verbindungen(komponenten, gespeichert: dict[str, str] | None = None) -> dict[str, str | None]:
    """Je Teil seine Quelle, bei Solar und PV-Heizmodul ihr Ziel.

    Gespeichertes gilt, soweit es zur heutigen Auswahl der Komponenten
    passt, sonst die Vorgabe. Entsteht dabei ein Kreis - eine gespeicherte
    Wahl trifft auf die Vorgabe eines anderen Teils -, hängt das Teil am
    Kessel. So findet die Karte immer einen Anfang.
    """
    wege = vorgabe(komponenten)
    for teil, quelle in (gespeichert or {}).items():
        if teil in wege and quelle in moegliche_quellen(komponenten, teil):
            wege[teil] = quelle
    for teil in wege:
        if teil not in ERZEUGER and _im_kreis(wege, teil):
            wege[teil] = KESSEL
    return wege


def braucht_auswahl(komponenten) -> bool:
    """Gibt es etwas zu wählen? Erst mit zwei Puffern oder mit Puffer und Fernleitung.

    Mit einem einzigen Puffer stimmt die Vorgabe so gut wie immer, und der
    Dialog bleibt um einen Schritt kürzer.
    """
    return sum(k in PUFFER_SPEICHER or k == FERNLEITUNG for k in komponenten) >= 2


def felder(komponenten) -> list[str]:
    """Die Teile, bei denen mehr als eine Quelle zur Wahl steht, in der Reihenfolge der Anlage."""
    return [
        teil
        for teil in komponenten
        if teil in vorgabe(komponenten) and len(moegliche_quellen(komponenten, teil)) > 1
    ]
