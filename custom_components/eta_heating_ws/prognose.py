"""Selbstlernende Verbrauchsprognose und Reichweite des Pelletlagers.

Aus den Tageswerten der Anlage - verbrannte Pellets und mittlere
Außentemperatur - lernt das Modell, wie das Haus auf Kälte reagiert:

    Verbrauch am Tag = Grundlast + Faktor × max(0, Heizgrenze − Außentemperatur)

Die Grundlast ist, was auch an warmen Tagen verbrennt (Warmwasser), der
Faktor, wie viel jedes Grad unter der Heizgrenze kostet, die Heizgrenze
die Außentemperatur, ab der das Haus überhaupt heizt. Alle drei werden
bei jeder Berechnung neu aus den eigenen Tagen geschätzt; jüngere Tage
zählen mehr, einzelne Ausreißer (Urlaub, Störung, Besuch) fliegen raus.

Für die kommenden Tage gilt die Wettervorhersage, danach das langjährige
Temperaturmittel, verschoben um das, was der eigene Standort erfahrungs-
gemäß wärmer oder kälter ist. Damit wird der Vorrat Tag für Tag herunter-
gerechnet. Gegengerechnet wird, indem das Modell für jeden der letzten
Tage nur mit den Tagen davor gelernt wird und seine Schätzung mit dem
tatsächlichen Verbrauch verglichen wird.

Ist das Volumen des Pufferspeichers bekannt, wird vorher herausgerechnet,
was der Puffer von einem Tag in den nächsten mitnimmt: Lädt der Kessel
abends voll, sind die Pellets heute verbrannt, die Wärme wird aber erst
morgen gebraucht.

Das Modul kommt ohne Home Assistant aus, damit es sich vollständig
prüfen lässt; die Daten holt prognose_koordinator.py.
"""

from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta
from statistics import median
from typing import Callable, Iterable

MIN_LERNTAGE = 14
"""So viele vollständige Tage braucht das Modell mindestens."""

MIN_HEIZTAGE = 7
"""So viele Tage mit Heizbedarf (höchstens HEIZTAG_BIS °C) müssen dabei sein."""

HEIZTAG_BIS = 12.0
MIN_SPANNE = 5.0
"""Um so viele Grad müssen die Tagesmittel auseinanderliegen.

Nur wer milde und kalte Tage gesehen hat, kann den Faktor schätzen.
"""

MIN_STUNDEN = 20
"""Ein Tag zählt nur, wenn für so viele Stunden Werte vorliegen.

War die Anlage einen halben Tag nicht erreichbar, holt der Zähler das
Verbrannte später auf einen Schlag nach - der Tag wäre verfälscht.
"""

HALBWERTSZEIT = 180
"""Nach so vielen Tagen zählt ein Tag beim Lernen nur noch halb."""

HEIZGRENZEN = [10.0 + 0.25 * i for i in range(41)]
TYPISCHE_HEIZGRENZE = 15.0
GLEICH_GUT = 1.005
"""Passen mehrere Heizgrenzen fast gleich gut, gewinnt die typischste.

Ohne warme Tage lässt sich die Heizgrenze nicht bestimmen - Grundlast
und Heizgrenze gleichen sich dann gegenseitig aus.
"""

HORIZONT = 730
"""Weiter als zwei Jahre wird nicht gerechnet."""

SPANNE_KELVIN = 2.0
"""Für frühestens und spätestens: jenseits der Vorhersage 2 Grad kälter bzw. wärmer."""

STREUUNG_KLIMA = 3.5
"""So weit streuen Tagesmittel üblicherweise um das langjährige Mittel (K).

Solange zu wenige eigene Tage vorliegen; danach aus den eigenen Daten.
"""

STREUUNG_VORHERSAGE = 1.5
"""So weit liegt eine Tagesvorhersage erfahrungsgemäß daneben (K)."""

KLIMA_MONATSMITTEL = [0.9, 1.5, 4.5, 8.9, 12.9, 16.3, 18.3, 18.0, 14.0, 9.5, 5.0, 1.8]
"""Langjährige Monatsmittel der Lufttemperatur in Deutschland (DWD, 1991-2020)."""

VERGLEICHSTAGE = 14

WASSER_KWH_JE_LITER_KELVIN = 0.001163
"""So viel Wärme nimmt ein Liter Wasser je Grad auf: 4,187 kJ = 1,163 Wh."""

KESSEL_WIRKUNGSGRAD = 0.9
"""Anteil der Pelletenergie, der im Puffer ankommt.

Nur für die Umrechnung der Puffer-Energie in Kilogramm; liegt er
daneben, verschiebt sich die ohnehin kleine Korrektur um wenige Prozent.
"""

PUFFER_BEZUG = 30.0
"""Ab dieser Temperatur zählt Pufferwasser als nutzbare Wärme.

Kälter kommt es von Heizkörpern und Fußbodenheizung ohnehin zurück.
"""


@dataclass
class Tag:
    """Ein vollständiger Tag: verbrannte Pellets und mittlere Außentemperatur."""

    datum: date
    verbrauch: float
    temperatur: float


@dataclass
class Modell:
    grundlast: float
    faktor: float
    heizgrenze: float
    tage: int
    heiztage: int
    streuung: float
    ausreisser: int = 0
    korrektur: float = 1.0
    """Gleicht aus, was die verworfenen Tage im Mittel mehr verbraucht haben.

    Ausreißer fliegen beim Schätzen der Formel raus, damit ein Besuchs-
    wochenende sie nicht verbiegt. Verbrannt wurde an ihnen trotzdem -
    auf lange Sicht zählt das mit.
    """

    def verbrauch(self, temperatur: float) -> float:
        return self.korrektur * (
            self.grundlast + self.faktor * max(0.0, self.heizgrenze - temperatur)
        )

    def erwartung(self, temperatur: float, streuung: float) -> float:
        """Erwarteter Verbrauch, wenn die Temperatur nur ungefähr bekannt ist.

        Um die Heizgrenze herum wird an kalten Tagen geheizt, an warmen
        aber nicht weniger als nichts verbraucht. Mit der mittleren
        Temperatur allein käme im Frühjahr und Herbst zu wenig heraus -
        gerechnet wird deshalb über die Normalverteilung der Tages-
        temperatur.
        """
        if streuung <= 0:
            return self.verbrauch(temperatur)
        abstand = self.heizgrenze - temperatur
        z = abstand / streuung
        dichte = math.exp(-0.5 * z * z) / math.sqrt(2 * math.pi)
        verteilung = 0.5 * (1 + math.erf(z / math.sqrt(2)))
        kelvin = abstand * verteilung + streuung * dichte
        return self.korrektur * (self.grundlast + self.faktor * kelvin)


@dataclass
class Ergebnis:
    """Alles, was die Sensoren anzeigen."""

    status: str
    bereit: bool = False
    modell: Modell | None = None
    lerntage: int = 0
    heiztage: int = 0
    morgen_kg: float | None = None
    morgen_temperatur: float | None = None
    morgen_quelle: str | None = None
    reicht_bis: date | None = None
    reicht_fruehestens: date | None = None
    reicht_spaetestens: date | None = None
    bestellen_bis: date | None = None
    bestellen_fruehestens: date | None = None
    bestellen_spaetestens: date | None = None
    reichweite_tage: int | None = None
    ueber_horizont: bool = False
    treffsicherheit: int | None = None
    verglichene_tage: int = 0
    gestern_prognose: float | None = None
    gestern_tatsaechlich: float | None = None
    klima_abweichung: float = 0.0
    letzte_tage: list[Tag] = field(default_factory=list)


def tage_aus_stunden(
    verbrauch: Iterable[tuple[float, float]],
    temperatur: Iterable[tuple[float, float]],
    lokales_datum: Callable[[float], date],
    heute: date,
) -> list[Tag]:
    """Fasst Stundenwerte zu vollständigen Tagen zusammen.

    verbrauch sind Paare (Zeitstempel, verbrannte kg in dieser Stunde),
    temperatur Paare (Zeitstempel, Stundenmittel). Der laufende Tag und
    Tage mit Lücken fallen weg.
    """
    kg: dict[date, list[float]] = defaultdict(list)
    grad: dict[date, list[float]] = defaultdict(list)
    for zeit, wert in verbrauch:
        if wert is not None:
            kg[lokales_datum(zeit)].append(float(wert))
    for zeit, wert in temperatur:
        if wert is not None:
            grad[lokales_datum(zeit)].append(float(wert))
    tage = []
    for datum in sorted(set(kg) & set(grad)):
        if datum >= heute:
            continue
        if len(kg[datum]) < MIN_STUNDEN or len(grad[datum]) < MIN_STUNDEN:
            continue
        summe = sum(kg[datum])
        if summe < 0:
            continue
        tage.append(Tag(datum, summe, sum(grad[datum]) / len(grad[datum])))
    return tage


def _gewichte(tage: list[Tag], heute: date) -> list[float]:
    return [0.5 ** (max(0, (heute - t.datum).days) / HALBWERTSZEIT) for t in tage]


def _anpassen(tage: list[Tag], gewichte: list[float], heizgrenze: float):
    """Gewichtete Ausgleichsgerade für eine feste Heizgrenze, nie negativ."""
    s = sx = sy = sxx = sxy = 0.0
    for t, w in zip(tage, gewichte):
        x = max(0.0, heizgrenze - t.temperatur)
        s += w
        sx += w * x
        sy += w * t.verbrauch
        sxx += w * x * x
        sxy += w * x * t.verbrauch
    det = s * sxx - sx * sx
    if s <= 0:
        return 0.0, 0.0, math.inf
    if det <= 1e-9 * max(1.0, s * sxx):
        faktor, grundlast = 0.0, sy / s
    else:
        faktor = (s * sxy - sx * sy) / det
        grundlast = (sy - faktor * sx) / s
        if faktor < 0:
            faktor, grundlast = 0.0, sy / s
        elif grundlast < 0:
            grundlast = 0.0
            faktor = sxy / sxx if sxx > 0 else 0.0
    fehler = 0.0
    for t, w in zip(tage, gewichte):
        r = t.verbrauch - grundlast - faktor * max(0.0, heizgrenze - t.temperatur)
        fehler += w * r * r
    return grundlast, faktor, fehler


def _bestes(tage: list[Tag], gewichte: list[float]):
    kandidaten = [(g, *_anpassen(tage, gewichte, g)) for g in HEIZGRENZEN]
    bester = min(k[3] for k in kandidaten)
    gut = [k for k in kandidaten if k[3] <= bester * GLEICH_GUT + 1e-9]
    return min(gut, key=lambda k: abs(k[0] - TYPISCHE_HEIZGRENZE))


def lernen(tage: list[Tag], heute: date) -> Modell | None:
    """Schätzt Grundlast, Faktor und Heizgrenze aus den Tagen.

    Zweimal: Nach dem ersten Durchgang werden Tage verworfen, die weit
    aus der Reihe fallen - höchstens jeder zehnte -, dann wird neu
    gerechnet.
    """
    if not tage:
        return None
    gewichte = _gewichte(tage, heute)
    heizgrenze, grundlast, faktor, _ = _bestes(tage, gewichte)
    reste = [
        t.verbrauch - grundlast - faktor * max(0.0, heizgrenze - t.temperatur)
        for t in tage
    ]
    mitte = median(reste)
    mad = median(abs(r - mitte) for r in reste)
    schwelle = max(4.0 * 1.4826 * mad, 0.25 * (sum(t.verbrauch for t in tage) / len(tage)) + 1.0)
    auffaellig = sorted(
        (i for i, r in enumerate(reste) if abs(r - mitte) > schwelle),
        key=lambda i: -abs(reste[i] - mitte),
    )[: len(tage) // 10]
    verworfen = set(auffaellig)
    behalten = [i for i in range(len(tage)) if i not in verworfen]
    tage_b = [tage[i] for i in behalten]
    gewichte_b = [gewichte[i] for i in behalten]
    if auffaellig:
        heizgrenze, grundlast, faktor, _ = _bestes(tage_b, gewichte_b)
    geschaetzt = sum(
        w * (grundlast + faktor * max(0.0, heizgrenze - t.temperatur))
        for t, w in zip(tage, gewichte)
    )
    tatsaechlich = sum(w * t.verbrauch for t, w in zip(tage, gewichte))
    korrektur = tatsaechlich / geschaetzt if geschaetzt > 0 else 1.0
    korrektur = max(0.85, min(1.2, korrektur))
    summe_w = sum(gewichte_b)
    streuung = math.sqrt(
        sum(
            w * (t.verbrauch - grundlast - faktor * max(0.0, heizgrenze - t.temperatur)) ** 2
            for t, w in zip(tage_b, gewichte_b)
        )
        / summe_w
    ) if summe_w else 0.0
    return Modell(
        grundlast=grundlast,
        faktor=faktor,
        heizgrenze=heizgrenze,
        tage=len(tage_b),
        heiztage=sum(1 for t in tage_b if t.temperatur <= HEIZTAG_BIS),
        streuung=streuung,
        ausreisser=len(auffaellig),
        korrektur=korrektur,
    )


def lernstand(tage: list[Tag]) -> tuple[bool, str]:
    """Ob genug gelernt ist, und wenn nicht, woran es fehlt."""
    if len(tage) < MIN_LERNTAGE:
        return False, f"lernt noch ({len(tage)} von {MIN_LERNTAGE} Tagen)"
    heiztage = sum(1 for t in tage if t.temperatur <= HEIZTAG_BIS)
    if heiztage < MIN_HEIZTAGE:
        return False, f"lernt noch ({heiztage} von {MIN_HEIZTAGE} Heiztagen)"
    temperaturen = [t.temperatur for t in tage]
    if max(temperaturen) - min(temperaturen) < MIN_SPANNE:
        return False, "lernt noch (braucht mildere und kältere Tage)"
    return True, "bereit"


def klima(datum: date) -> float:
    """Langjähriges Tagesmittel, zwischen den Monatsmitten linear verbunden."""
    mitte = date(datum.year, datum.month, 15)
    if datum >= mitte:
        von_monat, bis_monat = datum.month, datum.month % 12 + 1
        von = mitte
        bis = date(datum.year + (1 if datum.month == 12 else 0), bis_monat, 15)
    else:
        bis_monat, von_monat = datum.month, (datum.month - 2) % 12 + 1
        bis = mitte
        von = date(datum.year - (1 if datum.month == 1 else 0), von_monat, 15)
    anteil = (datum - von).days / (bis - von).days
    a, b = KLIMA_MONATSMITTEL[von_monat - 1], KLIMA_MONATSMITTEL[bis_monat - 1]
    return a + (b - a) * anteil


STANDORT_STREUUNG = 1.5
"""So weit weichen Standorte in DACH üblicherweise vom Landesmittel ab (K)."""

MONATS_STREUUNG = 1.5
"""So weit weicht ein einzelner Monat üblicherweise vom langjährigen Mittel ab (K)."""


def klima_abweichung(tage: list[Tag]) -> float:
    """Wie viel wärmer (+) oder kälter (−) der eigene Standort ist.

    Was die eigenen Tage vom langjährigen Mittel abweichen, ist zum Teil
    der Standort und zum Teil Zufall - ein milder Herbst sagt nichts über
    den Winter. Übernommen wird deshalb nur der Anteil, der dem Standort
    zuzutrauen ist: nach einem Monat wenig, nach einem Jahr fast alles.
    Ein Monat zählt dabei wie eine unabhängige Beobachtung, weil Wetter-
    lagen wochenlang anhalten.
    """
    juengste = tage[-365:]
    if not juengste:
        return 0.0
    roh = sum(t.temperatur - klima(t.datum) for t in juengste) / len(juengste)
    zufall = MONATS_STREUUNG**2 / (len(juengste) / 30)
    anteil = STANDORT_STREUUNG**2 / (STANDORT_STREUUNG**2 + zufall)
    return max(-6.0, min(6.0, roh * anteil))


def klima_streuung(tage: list[Tag], abweichung: float) -> float:
    """Wie weit die eigenen Tagesmittel um Klima plus Standort streuen."""
    juengste = tage[-365:]
    if len(juengste) < 30:
        return STREUUNG_KLIMA
    quadrate = sum((t.temperatur - klima(t.datum) - abweichung) ** 2 for t in juengste)
    return max(2.0, min(6.0, math.sqrt(quadrate / len(juengste))))


def temperaturreihe(
    heute: date,
    vorhersage: dict[date, float],
    abweichung: float,
    verschiebung: float = 0.0,
    streuung: float = STREUUNG_KLIMA,
):
    """Tagesmittel ab heute: erst die Vorhersage, danach Klima plus Standort.

    Liefert je Tag Datum, Temperatur, Quelle und wie unsicher sie ist.
    verschiebung wirkt nur jenseits der Vorhersage - für frühestens und
    spätestens.
    """
    for tag in range(HORIZONT):
        datum = heute + timedelta(days=tag)
        if datum in vorhersage:
            yield datum, vorhersage[datum], "Wettervorhersage", STREUUNG_VORHERSAGE
        else:
            yield datum, klima(datum) + abweichung + verschiebung, "Klimamittel", streuung


def herunterrechnen(
    modell: Modell,
    vorrat: float,
    grenze: float | None,
    heute_schon: float,
    heute: date,
    vorhersage: dict[date, float],
    abweichung: float,
    verschiebung: float = 0.0,
    streuung: float = STREUUNG_KLIMA,
) -> tuple[date | None, date | None]:
    """Rechnet den Vorrat Tag für Tag herunter.

    Liefert den Tag, an dem die Warngrenze erreicht wird, und den Tag, an
    dem das Lager leer ist - jeweils None, wenn es länger als HORIZONT
    reicht. Vom heutigen Tag zählt nur, was noch nicht verbrannt ist.
    """
    rest = vorrat
    bestellen = heute if grenze is not None and rest <= grenze else None
    if rest <= 0:
        return heute, heute
    for datum, temperatur, _, unsicher in temperaturreihe(
        heute, vorhersage, abweichung, verschiebung, streuung
    ):
        bedarf = modell.erwartung(temperatur, unsicher)
        if datum == heute:
            bedarf = max(0.0, bedarf - heute_schon)
        rest -= bedarf
        if bestellen is None and grenze is not None and rest <= grenze:
            bestellen = datum
        if rest <= 0:
            return bestellen, datum
    return bestellen, None


def gegenrechnen(tage: list[Tag], anzahl: int = VERGLEICHSTAGE):
    """Prüft das Modell an den letzten Tagen, ohne dass es sie vorher kennt.

    Für jeden dieser Tage wird nur mit den Tagen davor gelernt und der
    Verbrauch aus der tatsächlichen Außentemperatur geschätzt. Liefert
    Treffsicherheit in Prozent (100 = auf das Kilogramm genau), die Zahl
    der verglichenen Tage und Schätzung und Wirklichkeit des letzten.
    """
    paare = []
    for i in range(max(0, len(tage) - anzahl), len(tage)):
        vorher = tage[:i]
        if not lernstand(vorher)[0]:
            continue
        modell = lernen(vorher, tage[i].datum)
        if modell is None:
            continue
        paare.append((modell.verbrauch(tage[i].temperatur), tage[i].verbrauch))
    if not paare:
        return None, 0, None, None
    ist = sum(p[1] for p in paare)
    fehler = sum(abs(p[0] - p[1]) for p in paare)
    treffsicherheit = None
    if ist >= 5:
        treffsicherheit = max(0, min(100, round(100 * (1 - fehler / ist))))
    return treffsicherheit, len(paare), paare[-1][0], paare[-1][1]


def berechnen(
    tage: list[Tag],
    heute: date,
    vorhersage: dict[date, float],
    vorrat: float | None,
    grenze: float | None,
    heute_schon: float,
    gegenrechnung=None,
) -> Ergebnis:
    """Alles in einem Durchgang - so, wie der Koordinator es braucht.

    gegenrechnung kann ein schon berechnetes Ergebnis von gegenrechnen
    sein; es ändert sich nur, wenn ein neuer vollständiger Tag dazukommt.
    """
    bereit, status = lernstand(tage)
    ergebnis = Ergebnis(
        status=status,
        bereit=bereit,
        lerntage=len(tage),
        heiztage=sum(1 for t in tage if t.temperatur <= HEIZTAG_BIS),
        letzte_tage=tage[-VERGLEICHSTAGE:],
    )
    if not bereit:
        return ergebnis
    modell = lernen(tage, heute)
    ergebnis.modell = modell
    abweichung = klima_abweichung(tage)
    streuung = klima_streuung(tage, abweichung)
    ergebnis.klima_abweichung = abweichung

    morgen = heute + timedelta(days=1)
    for datum, temperatur, quelle, unsicher in temperaturreihe(
        heute, vorhersage, abweichung, streuung=streuung
    ):
        if datum == morgen:
            ergebnis.morgen_temperatur = temperatur
            ergebnis.morgen_quelle = quelle
            ergebnis.morgen_kg = modell.erwartung(temperatur, unsicher)
            break

    if gegenrechnung is None:
        gegenrechnung = gegenrechnen(tage)
    (
        ergebnis.treffsicherheit,
        ergebnis.verglichene_tage,
        ergebnis.gestern_prognose,
        ergebnis.gestern_tatsaechlich,
    ) = gegenrechnung

    if vorrat is None:
        return ergebnis
    def rechnen(verschiebung):
        return herunterrechnen(
            modell, vorrat, grenze, heute_schon, heute, vorhersage, abweichung,
            verschiebung, streuung,
        )

    ergebnis.bestellen_bis, ergebnis.reicht_bis = rechnen(0.0)
    ergebnis.bestellen_fruehestens, ergebnis.reicht_fruehestens = rechnen(-SPANNE_KELVIN)
    ergebnis.bestellen_spaetestens, ergebnis.reicht_spaetestens = rechnen(SPANNE_KELVIN)
    if ergebnis.reicht_bis is not None:
        ergebnis.reichweite_tage = (ergebnis.reicht_bis - heute).days
    else:
        ergebnis.ueber_horizont = True
    return ergebnis


def tagesmittel_aus_vorhersage(
    eintraege: list[dict],
    art: str,
    lokales_datum: Callable[[str], date | None],
    fahrenheit: bool = False,
) -> dict[date, float]:
    """Macht aus einer Wettervorhersage ein Tagesmittel je Datum.

    Tagesvorhersagen nennen meist Höchst- und Tiefstwert, dann gilt deren
    Mitte; fehlt der Tiefstwert, liegt das Mittel erfahrungsgemäß rund
    vier Grad unter dem Höchstwert. Stunden- und Halbtagesvorhersagen
    werden gemittelt, sofern der Tag genug Einträge hat.
    """
    werte: dict[date, list[float]] = defaultdict(list)
    for eintrag in eintraege:
        datum = lokales_datum(eintrag.get("datetime"))
        hoch = eintrag.get("temperature")
        tief = eintrag.get("templow")
        if datum is None or hoch is None:
            continue
        try:
            hoch = float(hoch)
            tief = float(tief) if tief is not None else None
        except (TypeError, ValueError):
            continue
        if fahrenheit:
            hoch = (hoch - 32) * 5 / 9
            tief = (tief - 32) * 5 / 9 if tief is not None else None
        if art == "daily":
            werte[datum].append((hoch + tief) / 2 if tief is not None else hoch - 4.0)
        else:
            werte[datum].append(hoch)
            if tief is not None:
                werte[datum].append(tief)
    noetig = {"daily": 1, "twice_daily": 2, "hourly": 12}.get(art, 1)
    return {
        datum: sum(liste) / len(liste)
        for datum, liste in werte.items()
        if len(liste) >= noetig
    }


def puffer_temperaturen(daten, schluessel) -> list[float]:
    """Die aktuellen Temperaturen aller Pufferfühler - leer, wenn einer fehlt.

    Mit einem fehlenden Fühler wäre das Mittel schief, weil jeder für
    einen gleich großen Teil des Speichers steht.
    """
    werte = []
    for key in schluessel:
        wert = (daten or {}).get(key)
        try:
            werte.append(float(wert.value))
        except (AttributeError, TypeError, ValueError):
            return []
    return werte


def puffer_energieinhalt(temperaturen: list[float], volumen: float) -> float | None:
    """Nutzbare Wärme im Puffer in kWh: alles über PUFFER_BEZUG."""
    if not temperaturen or not volumen:
        return None
    ueber = sum(max(0.0, t - PUFFER_BEZUG) for t in temperaturen) / len(temperaturen)
    return ueber * volumen * WASSER_KWH_JE_LITER_KELVIN


def puffer_tagesenden(
    fuehler: list[list[tuple[float, float]]],
    lokale_stunde: Callable[[float], tuple[date, int]],
) -> dict[date, float]:
    """Mittlere Puffertemperatur in der letzten Stunde jedes Tages.

    fuehler enthält je Pufferfühler die Stundenmittel als Paare
    (Zeitstempel, °C). Eine Stunde zählt nur, wenn alle Fühler einen
    Wert haben.
    """
    je_stunde: dict[float, list[float]] = defaultdict(list)
    for reihe in fuehler:
        for zeit, wert in reihe:
            if wert is not None:
                je_stunde[zeit].append(float(wert))
    enden = {}
    for zeit, werte in je_stunde.items():
        if len(werte) != len(fuehler):
            continue
        datum, stunde = lokale_stunde(zeit)
        if stunde == 23:
            enden[datum] = sum(werte) / len(werte)
    return enden


def puffer_energie_enden(
    puffer: list[tuple[dict[date, float], float]],
) -> dict[date, float]:
    """Wärme in allen Puffern zusammen am Ende jedes Tages (kWh).

    puffer enthält je Speicher seine Tagesend-Temperaturen und kWh je
    Grad. Gezählt werden nur Tage, für die jeder Speicher einen Wert hat -
    sonst sähe ein fehlender Tag wie ein leergelaufener Puffer aus.
    """
    if not puffer:
        return {}
    gemeinsam = set.intersection(*(set(enden) for enden, _ in puffer))
    return {
        datum: sum(enden[datum] * kwh_je_kelvin for enden, kwh_je_kelvin in puffer)
        for datum in gemeinsam
    }


def puffer_ausgleichen(
    tage: list[Tag], enden: dict[date, float], kwh_je_kelvin: float, kwh_je_kg: float
) -> tuple[list[Tag], int]:
    """Rechnet heraus, was der Puffer über Mitternacht mitgenommen hat.

    Ist er am Tagesende wärmer als am Vorabend, steckt ein Teil der heute
    verbrannten Pellets noch im Puffer - der gehört zum Verbrauch von
    morgen. Ist er kälter, hat das Haus von gestern gezehrt. Liefert die
    ausgeglichenen Tage und wie viele davon ausgeglichen wurden; Tage
    ohne beide Tagesenden bleiben wie sie sind.
    """
    ergebnis, ausgeglichen = [], 0
    for tag in tage:
        heute = enden.get(tag.datum)
        vorher = enden.get(tag.datum - timedelta(days=1))
        if heute is None or vorher is None or kwh_je_kg <= 0:
            ergebnis.append(tag)
            continue
        verschoben = (heute - vorher) * kwh_je_kelvin / kwh_je_kg
        ergebnis.append(Tag(tag.datum, max(0.0, tag.verbrauch - verschoben), tag.temperatur))
        ausgeglichen += 1
    return ergebnis, ausgeglichen
