"""Ermittelt die ETA-Objekt-URIs anhand der Namen im Menübaum.

Die numerischen URIs unterscheiden sich je nach Anlage und Firmware, die
Bezeichnungen unter /user/menu bleiben stabil. Ausnahme sind die Namen der
Funktionsblöcke (FUB), die an der Steuerung geändert werden können. Jeder
Messwert hängt deshalb an einer FUB-*Rolle* ("kessel", "hk", ...), der beim
Einrichten ein tatsächlicher Name zugeordnet wird.
"""

from __future__ import annotations

import logging
import re

from .const import (
    BETRIEBSART_TASTEN,
    COMPONENTS,
    ENTASCHEN_TASTE,
    FUB_ROLE_DEFAULT_NAMES,
    PUFFER_FUEHLER_MAX,
    PUFFER_SPEICHER,
    THERMOSTATE,
    WARMWASSER_SPEICHER,
    WOCHENTAGE,
    ZEITFENSTER_JE_TAG,
    absenkwert_schluessel,
    zeitfenster_schluessel,
)

_LOGGER = logging.getLogger(__name__)

WEITERE_PUFFER = list(PUFFER_SPEICHER)[1:]
"""Der zweite bis achte Puffer - ihre Pfade gleichen denen des ersten."""

WEITERES_WARMWASSER = list(WARMWASSER_SPEICHER)[1:]
"""Das zweite bis achte Warmwasser - ihre Pfade gleichen denen des ersten."""


def _rolle(komponente):
    """Die Rolle, über die der Funktionsblock einer Komponente gefunden wird."""
    return COMPONENTS[komponente]["roles"][0]


DISCOVERY_PATHS = {
    "kessel_temperatur": ("kessel", ["Eingänge", "Kessel"]),
    "ruecklauf_temperatur": ("kessel", ["Eingänge", "Rücklauf"]),
    "kessel_druck": ("kessel", ["Eingänge", "Kesseldruck"]),
    "pellet_tagesbehälter": (
        "kessel",
        ["Kessel", "Pelletsbehälter", "Inhalt Pelletsbehälter"],
    ),
    "kessel_soll": ("kessel", ["Kessel", "Kessel", "Kessel Soll"]),
    "restsauerstoff": ("kessel", ["Eingänge", "Restsauerstoff", "Restsauerstoff"]),
    "pellet_gesamtverbrauch": ("kessel", ["Zählerstände", "Gesamtverbrauch"]),
    "aschebox_verbrauch": (
        "kessel",
        ["Kessel", "Entaschung", "Verbrauch seit Aschebox leeren"],
    ),
    "entaschung_verbrauch": (
        "kessel",
        ["Kessel", "Entaschung", "Verbrauch seit Entaschung"],
    ),
    "aschebox_schwelle": ("kessel", ["Kessel", "Entaschung", "Aschebox leeren nach"]),
    "kessel_zustand": ("kessel", ["Kessel", "Kessel-Zustand detailliert"]),
    "aussentemperatur": ("sys", ["Außentemperatur", "Außentemperaturfühler"]),
    "puffer_ladezustand": ("pufferflex", ["Puffer", "Ladezustand"]),
    "puffer_zustand": ("pufferflex", ["Puffer", "Puffer-Zustand detailliert"]),
    **{
        f"{k}_zustand": (_rolle(k), ["Puffer", "Puffer-Zustand detailliert"])
        for k in WEITERE_PUFFER
    },
    **{f"{k}_ladezustand": (_rolle(k), ["Puffer", "Ladezustand"]) for k in WEITERE_PUFFER},
    "heizkreis_vorlauf": ("hk", ["Eingänge", "Vorlauf"]),
    "heizkreis_anforderung": ("hk", ["Ausgänge", "Heizkreispumpe", "Anforderung"]),
    "heizkreis2_vorlauf": ("hk2", ["Eingänge", "Vorlauf"]),
    "heizkreis2_anforderung": ("hk2", ["Ausgänge", "Heizkreispumpe", "Anforderung"]),
    "heizkreis3_vorlauf": ("hk3", ["Eingänge", "Vorlauf"]),
    "heizkreis3_anforderung": ("hk3", ["Ausgänge", "Heizkreispumpe", "Anforderung"]),
    "heizkreis4_vorlauf": ("hk4", ["Eingänge", "Vorlauf"]),
    "heizkreis4_anforderung": ("hk4", ["Ausgänge", "Heizkreispumpe", "Anforderung"]),
    "heizkreis_raum": ("hk", ["Eingänge", "Raumtemperatur über externe Schnittstellen", "Raum"]),
    "heizkreis2_raum": ("hk2", ["Eingänge", "Raumtemperatur über externe Schnittstellen", "Raum"]),
    "heizkreis3_raum": ("hk3", ["Eingänge", "Raumtemperatur über externe Schnittstellen", "Raum"]),
    "heizkreis4_raum": ("hk4", ["Eingänge", "Raumtemperatur über externe Schnittstellen", "Raum"]),
    "heizkreis_zeitprogramm": ("hk", ["Heizkreis", "Heizzeiten", "Schaltzustand"]),
    "heizkreis2_zeitprogramm": ("hk2", ["Heizkreis", "Heizzeiten", "Schaltzustand"]),
    "heizkreis3_zeitprogramm": ("hk3", ["Heizkreis", "Heizzeiten", "Schaltzustand"]),
    "heizkreis4_zeitprogramm": ("hk4", ["Heizkreis", "Heizzeiten", "Schaltzustand"]),
    "fwm_warmwasser": ("fwm", ["Eingänge", "Warmwasser"]),
    **{f"{k}_warmwasser": (_rolle(k), ["Eingänge", "Warmwasser"]) for k in WEITERES_WARMWASSER},
    "lager_vorrat": ("lager", ["Vorrat"]),
    "lager_warngrenze": ("lager", ["Vorrat", "Vorrat Warngrenze"]),
    "lager_maximum": ("lager", ["Vorrat", "Maximaler Vorrat"]),
    "lager_zustand": ("lager", ["Austragung", "Austragung-Zustand detailliert"]),
    "solar_kollektor": ("solar", ["Eingänge", "Kollektor"]),
    "solar_leistung": ("solar", ["Leistung"]),
    "solar_waermemenge": ("solar", ["Leistung", "Wärmemenge"]),
    "solar_ertrag_heute": ("solar", ["Leistung", "Ertrag heute"]),
    "solar_ertrag_gestern": ("solar", ["Leistung", "Ertrag gestern"]),
    "pvm_heizstab": ("pvm", ["Ausgänge", "Heizstab"]),
    "pvm_temperatur_oben": ("pvm", ["Eingänge", "Temperatur oben"]),
    "pvm_temperatur_mitte": ("pvm", ["Eingänge", "Temperatur mitte"]),
    "pvm_temperatur_unten": ("pvm", ["Eingänge", "Temperatur unten"]),
    "pvm_zustand": ("pvm", ["PV-Heizmodul", "PV Modul -Zustand detailliert"]),
    "pvm_gesamtenergie": ("pvm", ["Zählerstände", "Gesamtenergie Heizstab"]),
    "pvm_ertrag_heute": ("pvm", ["Zählerstände", "Ertrag heute"]),
    "pvm_ertrag_gestern": ("pvm", ["Zählerstände", "Ertrag gestern"]),
    "brenner_anforderung": ("brenner", ["Ausgänge", "Anforderung Brenner"]),
    "brenner_temperatur": ("brenner", ["Brenner", "Brennertemperatur"]),
    "brenner_leistung_soll": ("brenner", ["Ausgänge", "Leistung Soll"]),
    "brenner_volllaststunden": ("brenner", ["Zählerstände", "Volllaststunden"]),
}

PUMPEN = {
    "fwm_zirkulationspumpe": ("fwm", "zirkulation"),
    **{f"{k}_zirkulationspumpe": (_rolle(k), "zirkulation") for k in WEITERES_WARMWASSER},
    "fernleitung_pumpe": ("fernleitung", "fernpumpe"),
    "puffer_ladepumpe": ("pufferflex", "pufferlade"),
    **{f"{k}_ladepumpe": (_rolle(k), "pufferlade") for k in WEITERE_PUFFER},
}
"""Pumpen, die über ein Stichwort in ihrem Namen gesucht werden.

Je nach Anlage heißt eine Pumpe "Zirkulationspumpe", "Zirkulation" oder
ähnlich. Gesucht wird unter "Ausgänge"; geliefert wird die URI ihrer
"Anforderung", die den Laufzustand meldet.

Das "Pufferladeventil/-pumpe" hat ein Puffer nur, wenn er im
ETA-Assistenten als dezentral geladen eingerichtet ist - sonst sind
seine Ausgänge leer.
"""

NAMENSSUCHE = {
    "solar_kollektor": "Kollektor",
    "solar_leistung": "Leistung",
    "solar_waermemenge": "Wärmemenge",
    "solar_ertrag_heute": "Ertrag heute",
    "solar_ertrag_gestern": "Ertrag gestern",
}
"""Zweiter Versuch über den bloßen Objektnamen, falls der Pfad nicht passt.

Nur für diese Schlüssel, weil ihr Zweig je nach Anlage unterschiedlich
tief im Menü liegt. Für die übrigen bleibt es beim festen Pfad - Namen
wie "Vorlauf" kommen mehrfach vor.
"""

TWIN_SCHLUESSEL = {
    "pellet_tagesbehälter",
    "pellet_gesamtverbrauch",
    "aschebox_verbrauch",
    "entaschung_verbrauch",
    "aschebox_schwelle",
}
"""Pelletwerte, die beim SH TWIN im Funktionsblock "Twin" stehen.

Der Block "Kessel" ist dort der Stückholzteil und führt sie nicht.
Temperaturen, Restsauerstoff und Zustand zeigen beide Blöcke gleich an,
sie kommen weiter aus "Kessel". Gilt nur, wenn die Komponente "twin"
angekreuzt ist - erkennbar daran, dass ihr Funktionsblock-Name im
Formular gespeichert wurde.
"""

AUSWEICHPFADE = {
    f"{k}_warmwasser": [["Eingänge", "Warmwasserspeicher"]] for k in WARMWASSER_SPEICHER
}
"""Weitere Namenspfade, falls der Hauptpfad im Funktionsblock fehlt.

Ein reiner Warmwasserspeicher (Funktionsblock "WW") nennt seinen Fühler
"Warmwasserspeicher", das Frischwassermodul "Warmwasser".
"""

KENNUNGEN = {
    "kessel_temperatur": "0/11109/0",
    "ruecklauf_temperatur": "0/11160/0",
    "kessel_druck": "0/0/12180",
    "pellet_tagesbehälter": "0/0/12011",
    "kessel_soll": "0/0/13953",
    "restsauerstoff": "0/11108/2060",
    "pellet_gesamtverbrauch": "0/0/12016",
    "aschebox_verbrauch": "0/0/12013",
    "entaschung_verbrauch": "0/0/12012",
    "aschebox_schwelle": "0/0/12120",
    "kessel_zustand": "0/0/12000",
    "aussentemperatur": "0/11127/0",
    "puffer_ladezustand": "0/0/12528",
    "puffer_zustand": "0/0/12208",
    **{f"{k}_zustand": "0/0/12208" for k in WEITERE_PUFFER},
    **{f"{k}_ladezustand": "0/0/12528" for k in WEITERE_PUFFER},
    "heizkreis_vorlauf": "0/11060/0",
    "heizkreis_anforderung": "0/11124/2001",
    "heizkreis2_vorlauf": "0/11060/0",
    "heizkreis2_anforderung": "0/11124/2001",
    "heizkreis3_vorlauf": "0/11060/0",
    "heizkreis3_anforderung": "0/11124/2001",
    "heizkreis4_vorlauf": "0/11060/0",
    "heizkreis4_anforderung": "0/11124/2001",
    "heizkreis_zeitprogramm": "12113/0/1109",
    "heizkreis2_zeitprogramm": "12113/0/1109",
    "heizkreis3_zeitprogramm": "12113/0/1109",
    "heizkreis4_zeitprogramm": "12113/0/1109",
    **{f"{k}_warmwasser": "0/11148/0" for k in WARMWASSER_SPEICHER},
    "lager_vorrat": "0/0/12015",
    "lager_warngrenze": "0/0/12042",
    "lager_maximum": "0/0/12790",
    "lager_zustand": "0/0/12423",
    "solar_kollektor": "0/11139/0",
    "solar_leistung": "0/0/12379",
    "solar_waermemenge": "0/0/12349",
    "solar_ertrag_heute": "0/0/12350",
    "solar_ertrag_gestern": "0/0/12769",
    "pvm_heizstab": "0/0/14120",
    "pvm_temperatur_oben": "0/11718/0",
    "pvm_temperatur_mitte": "0/11719/0",
    "pvm_temperatur_unten": "0/11720/0",
    "pvm_zustand": "0/0/15219",
    "pvm_ertrag_heute": "0/0/12350",
    "pvm_ertrag_gestern": "0/0/12769",
    "brenner_anforderung": "0/0/12363",
    "brenner_temperatur": "0/0/12361",
    "brenner_leistung_soll": "0/0/12008",
    "brenner_volllaststunden": "0/0/12153",
}
"""Zweiter Weg zu einem Messwert: die hinteren drei Zahlen seiner URI.

Eine URI hat die Form /Modul/Funktionsblock/Funktion/Ein-Ausgang/Variable.
Die vorderen beiden Zahlen hängen an der einzelnen Anlage, die hinteren
drei bezeichnen das Objekt selbst - in den Menübäumen echter Anlagen
trägt dasselbe Objekt im selben Funktionsblock-Typ dieselben. Findet der
Namenspfad nichts, etwa weil ein Zweig anders liegt oder das Display auf
eine andere Sprache eingestellt ist, wird innerhalb des Funktionsblocks
nach dieser Kennung gesucht - nie außerhalb.

Aufgenommen sind Kennungen, die in einem echten Menübaum mit ihrem
Namen stehen. Heizkreis 2 bis 4 sind derselbe Funktionsblock-Typ wie
Heizkreis 1 und tragen deshalb dieselben, ebenso die weiteren Puffer
und Warmwasser.
Einzige Ausnahme ist das PV-Heizmodul: Von ihm gibt es noch keinen echten Menübaum, seine
Kennungen sind unbelegt. Greift eine davon, steht das in der Diagnose
unter "ueber_kennung_gefunden". Nur Messwerte: Tasten und Schalter
werden weiter ausschließlich über ihren Namen gefunden.
"""

PUFFER_VOLUMEN = ("Effektives Puffervolumen", "0/0/12499")
"""Name und Kennung des effektiven Puffervolumens in Litern.

Die Regelung rechnet es aus dem eingestellten Gesamtvolumen und der Lage
der Fühler; damit rechnen Energieinhalt und Prognose. PufferFlex zeigt es
unter Einstellungen > Leistungsregelung. Der ältere Funktionsblock
"Puffer" kennt es am Display auch, gibt es aber nicht an die Webservices
weiter - dort fragt die Einrichtung nach den Litern. Ob ein Puffer das
Volumen meldet, ist damit zugleich das Merkmal, ob es ein PufferFlex ist.
"""

ALTE_PUFFER_FUEHLER = (
    "Puffer oben",
    "Puffer oben/mitte",
    "Puffer mitte",
    "Puffer mitte/unten",
    "Puffer unten",
)
"""So heißen die Fühler beim älteren Funktionsblock "Puffer", von oben nach unten.

Er kennt kein "Fühler 1 … 9" wie PufferFlex. Gleich benannte Fühler mit
Zusatz ("Puffer oben Solar", "Puffer oben Frischwasser") gehören zur
Solar- bzw. Frischwasserregelung und zählen nicht mit.
"""

_FUEHLER_NAME_RE = re.compile(r"^F[uü]hler\s*(\d+)", re.IGNORECASE)

_SCHALTER_NAMEN = (
    "ein/aus taste",
    "ein/aus-taste",
    "e/a taste",
    "ein/aus",
    "on/off button",
    "i/o key",
)
"""Objektnamen, die eindeutig einen Ein/Aus-Schalter bezeichnen.

Bewusst eng gehalten. Ein Name wie "Betriebsart" oder "Kessel" könnte
auch an einem Messwert oder einer mehrstufigen Einstellung hängen - und
dort einen Rohwert hineinzuschreiben wäre in einer Heizungssteuerung
kein Schönheitsfehler. Was die Liste findet, prüft anschließend
/user/varinfo noch einmal nach.
"""

BETRIEBSART_ROLES = {
    "heizkreis_betriebsart": "hk",
    "heizkreis2_betriebsart": "hk2",
    "heizkreis3_betriebsart": "hk3",
    "heizkreis4_betriebsart": "hk4",
}
"""Welcher Funktionsblock zu welcher Betriebsart-Auswahl gehört."""

RAUM_EXTERN = ["Eingänge", "Raumtemperatur über externe Schnittstellen"]
"""Wohin ein Raumfühler über die externe Schnittstelle seinen Wert schreibt.

Das Objekt gibt es nur, wenn der Heizkreis im ETA-Assistenten mit
"Raumfühler ext. Schnittstelle" eingerichtet ist. Darunter liegen "Raum"
(der Wert, mit dem die Anlage regelt) und "Zeitüberwachung" (nach so
vielen Sekunden ohne neuen Wert verwirft sie ihn).
"""


def thermostat_objekte(praefix):
    """Die beschreibbaren Objekte eines Thermostats und wie sie gefunden werden.

    Nur über den Namen, nie über die Kennung - wie bei Tasten und
    Schaltern. Ein Pfad ist eine Liste, ein bloßer Name wird im ganzen
    Funktionsblock gesucht.
    """
    return {
        f"{praefix}_raum_extern": RAUM_EXTERN,
        f"{praefix}_zeitueberwachung": [*RAUM_EXTERN, "Zeitüberwachung"],
        f"{praefix}_raum_soll": "Raum Soll",
    }


HEIZZEITEN = ["Heizkreis", "Heizzeiten"]
"""Darunter liegt das Zeitprogramm eines Heizkreises.

Je Wochentag "Zeitfenster 1" bis "Zeitfenster 3" und der "Wert außerhalb
der Zeitfenster". So an zwei echten Anlagen gesehen.
"""


ABSENKWERT = "Wert außerhalb der Zeitfenster"
"""Die Raumtemperatur eines Tages außerhalb seiner Zeitfenster."""


def _zeitfenster(fub, praefix):
    """Die Zeitfenster eines Heizkreises und je Tag der Wert außerhalb, nur über die Namen.

    Beides wird beschrieben, deshalb nie über Kennungen.
    """
    heizzeiten = _find_path(fub, HEIZZEITEN) if fub is not None else None
    if heizzeiten is None:
        return {}
    return _zeitfenster_unter(heizzeiten, praefix)


def _zeitfenster_unter(programm, praefix):
    """Je Wochentag die drei Zeitfenster und den Wert außerhalb unter einem Zeitprogramm."""
    heizzeiten = programm
    gefunden = {}
    for tag, name in WOCHENTAGE.items():
        for nummer in range(1, ZEITFENSTER_JE_TAG + 1):
            knoten = _find_path(heizzeiten, [name, f"Zeitfenster {nummer}"])
            if knoten is not None and knoten.get("@uri"):
                gefunden[zeitfenster_schluessel(praefix, tag, nummer)] = knoten["@uri"]
        knoten = _find_path(heizzeiten, [name, ABSENKWERT])
        if knoten is not None and knoten.get("@uri"):
            gefunden[absenkwert_schluessel(praefix, tag)] = knoten["@uri"]
    return gefunden


WEITERE_ZEITPROGRAMME = {
    _rolle(k): k for k in [*PUFFER_SPEICHER, *WARMWASSER_SPEICHER]
}
"""In diesen Funktionsblöcken stehen Lade- und Bereitschaftszeiten - Rolle -> Komponente.

An einer echten Anlage gesehen: "Puffer > Erzeuger Kessel/Puffer >
Ladezeiten", "Puffer > Warmwasserbereich > Ladezeiten" und beim
Frischwassermodul "Warmwasser > Bereitschaftszeiten", an der Zweitanlage
"Puffer > Puffer oben > Ladezeiten", an einer Testanlage mit
Warmwasserspeicher (Block "WW") "Warmwasserspeicher > Ladezeiten" und,
wo eine Zirkulation aktiviert ist, "Zirkulation > Zirkulationszeiten".
Gesucht wird deshalb nicht über feste Pfade, sondern nach jedem Knoten,
der je Wochentag Zeitfenster hat.
"""

WARMWASSER_MAXIMUM = "Warmwasserspeicher max."
"""Die höchste Temperatur eines Warmwasserspeichers, im selben Block wie seine Ladezeiten."""

WARMWASSER_SOLL = ("Soll Temperatur", "Warmwasserspeicher Soll")
"""So heißt die Solltemperatur im Warmwasserbereich eines Puffers.

Den Warmwasserbereich samt "Ladezeiten" führt ein PufferFlex im Menübaum
auch dann, wenn er gar kein Kombispeicher ist - so an der Anlage des
Nutzers. Ob er eingerichtet ist, verrät seine Solltemperatur: Dort meldet
"Puffer > Warmwasserbereich > Soll Temperatur" keine Einheit, an einer
Testanlage mit Kombispeicher "°C". Im älteren Puffer heißt sie
"Warmwasserspeicher Soll".
"""

ZIRKULATION = "Zirkulation"
"""Der Knoten, unter dem die Zirkulationszeiten stehen - zugleich der Zustand der Zirkulation.

Ein Warmwasserspeicher führt ihn auch ohne Zirkulation, samt
Zirkulationszeiten. An einer Testanlage meldete er dann "xxx" (Block
"WW 2" ohne Zirkulation), mit Zirkulation "Aus" (Block "WW"). Nur dann
gehören die Zirkulationszeiten in die Karte.
"""


def _finde_namen(knoten, name: str):
    """Die URI des ersten Objekts mit diesem Namen irgendwo unterhalb, oder None."""
    for kind in _as_list(knoten.get("object")):
        if kind.get("@name", "").casefold() == name.casefold() and kind.get("@uri"):
            return kind["@uri"]
        gefunden = _finde_namen(kind, name)
        if gefunden:
            return gefunden
    return None


def _ist_zeitprogramm(knoten) -> bool:
    """Hat der Knoten je Wochentag ein "Zeitfenster 1"?"""
    return all(
        _find_path(knoten, [name, "Zeitfenster 1"]) is not None for name in WOCHENTAGE.values()
    )


def _weitere_zeitprogramme(fub, komponente, namen_aus):
    """Die Zeitprogramme eines Funktionsblocks, außer den Heizzeiten eines Heizkreises.

    Schlüssel wie bei den Heizzeiten, als Präfix Komponente und Kennung
    des Programms, etwa puffer_12130_zeitfenster_monday_1. Haben zwei
    Programme dieselbe Kennung, kommt beim zweiten der Rest seiner URI
    dazu, damit sich ihre Fenster nicht vermischen. In namen_aus landet je
    Präfix der Weg im Menübaum, damit die Karte das Programm benennen kann,
    und - falls der Block eine hat - die URI von WARMWASSER_MAXIMUM. Liegt
    ein Programm eines Puffers im Warmwasserbereich, kommt die URI von
    dessen Solltemperatur dazu, siehe WARMWASSER_SOLL; liegt es unter
    einem Knoten "Zirkulation", dessen URI, siehe ZIRKULATION.
    """
    gefunden = {}
    maximum = _finde_namen(fub, WARMWASSER_MAXIMUM) if fub is not None else None

    def soll_im_bereich(bereich):
        if bereich is None or not komponente.startswith("puffer"):
            return None
        namen = {name.casefold() for name in WARMWASSER_SOLL}
        for kind in _as_list(bereich.get("object")):
            if kind.get("@name", "").casefold() in namen and kind.get("@uri"):
                return kind["@uri"]
        return None

    def suchen(knoten, pfad, bereich=None, zirkulation=None):
        for kind in _as_list(knoten.get("object")):
            name = kind.get("@name", "")
            if not _ist_zeitprogramm(kind):
                suchen(
                    kind,
                    [*pfad, name],
                    kind if "warmwasser" in name.casefold() else bereich,
                    kind.get("@uri") if name.casefold() == ZIRKULATION.casefold() else zirkulation,
                )
                continue
            teile = (kind.get("@uri") or "").strip("/").split("/")
            if len(teile) < 3:
                continue
            praefix = f"{komponente}_{teile[2]}"
            if praefix in namen_aus:
                praefix = f"{komponente}_{'_'.join(teile[2:])}"
            if praefix in namen_aus:
                _LOGGER.debug("ETA: Zeitprogramm %s doppelt im Menübaum, übersprungen", kind.get("@uri"))
                continue
            gefunden.update(_zeitfenster_unter(kind, praefix))
            namen_aus[praefix] = {
                "komponente": komponente,
                "pfad": [*pfad, name],
                "maximum_uri": maximum,
                "soll_uri": soll_im_bereich(bereich),
                "zirkulation_uri": zirkulation,
            }

    if fub is not None:
        suchen(fub, [])
    return gefunden


SWITCH_ROLES = {
    "kessel_schalter": "kessel",
    "heizkreis_schalter": "hk",
    "heizkreis2_schalter": "hk2",
    "heizkreis3_schalter": "hk3",
    "heizkreis4_schalter": "hk4",
}


def _as_list(node):
    if node is None:
        return []
    if isinstance(node, list):
        return node
    return [node]


def _find_path(node, names):
    """Sucht rekursiv den 'object'-Knoten entlang des angegebenen Namenspfads."""
    if not names:
        return node
    target = names[0].casefold()
    for child in _as_list(node.get("object")):
        if child.get("@name", "").casefold() == target:
            found = _find_path(child, names[1:])
            if found is not None:
                return found
    return None


def _find_fub(fubs, fub_name):
    target = fub_name.casefold()
    for fub in fubs:
        if fub.get("@name", "").casefold() == target:
            return fub
    return None


def _resolve_fubs_by_role(fubs, fub_name_overrides):
    """Ordnet jeder FUB-Rolle einmalig den passenden FUB-Knoten zu.

    Ein vom Nutzer im Setup angegebener Name hat immer Vorrang vor den
    ETA-Standardnamen, da FUBs am Gerät umbenannt werden können.

    Das Formular speichert auch unveränderte Vorbelegungen. Ist der
    gespeicherte Name selbst ein Standardname der Rolle, werden deshalb
    danach die übrigen Standardnamen probiert - sonst bliebe etwa "HK 2"
    unentdeckt, nur weil das Formular "HK2" vorbelegt hat. Ein wirklich
    eigener Name gilt dagegen allein.

    Jeder Funktionsblock gehört zu höchstens einer Rolle. Zuerst bekommt
    jede Rolle den Block, dessen Namen sie gespeichert hat; erst danach
    greifen die übrigen Standardnamen, und zwar nur auf Blöcke, die noch
    frei sind. Sonst nähme etwa Puffer 1 mit seinem Standardnamen "Puffer"
    den Block, den Puffer 3 ausdrücklich so genannt hat.
    """
    overrides = fub_name_overrides or {}
    resolved = {}
    vergeben = set()

    for role in FUB_ROLE_DEFAULT_NAMES:
        fub = _find_fub(fubs, overrides[role]) if overrides.get(role) else None
        if fub is not None and id(fub) not in vergeben:
            resolved[role] = fub
            vergeben.add(id(fub))

    for role, default_names in FUB_ROLE_DEFAULT_NAMES.items():
        override = overrides.get(role)
        if role in resolved or (
            override and override.casefold() not in {name.casefold() for name in default_names}
        ):
            continue
        for name in default_names:
            fub = _find_fub(fubs, name)
            if fub is not None and id(fub) not in vergeben:
                resolved[role] = fub
                vergeben.add(id(fub))
                break

    return resolved


FUB_GRUPPEN = (
    ([_rolle(k) for k in PUFFER_SPEICHER], ("pufferflex", "puffer")),
    ([_rolle(k) for k in WARMWASSER_SPEICHER], ("fwm", "ww")),
)
"""Rollen, die ihre Blöcke der Reihe nach bekommen, je mit den Namensanfängen in dieser Folge."""


def _nummer(name: str) -> float:
    """Die Nummer im Namen eines Funktionsblocks, ohne Nummer 0 - "Puffer" vor "Puffer 2"."""
    treffer = re.search(r"\d+(?:\.\d+)?", name)
    return float(treffer.group()) if treffer else 0.0


def fub_namen_vorschlagen(rollen, namen_der_anlage, gespeichert=None):
    """Womit das Formular der Funktionsblock-Namen vorbelegt wird.

    Gespeicherte Namen bleiben. Pufferspeicher und Warmwasser bekommen der
    Reihe nach die noch freien passenden Blöcke der Anlage: zuerst
    PufferFlex, dann die älteren Puffer, beim Warmwasser zuerst FWM, dann
    WW - an einer Testanlage mit PufferFlex, PufferFlex 2, Puffer,
    Puffer 2, WW und WW 2 also genau diese Folge. Jede übrige Rolle bekommt
    den ersten ihrer Standardnamen, den die Anlage kennt, sonst den ersten
    Standardnamen.
    """
    gespeichert = gespeichert or {}
    vorschlag = {rolle: gespeichert[rolle] for rolle in rollen if gespeichert.get(rolle)}
    vergeben = {name.casefold() for name in vorschlag.values()}
    vorhanden = {name.casefold(): name for name in namen_der_anlage}

    for gruppe, anfaenge in FUB_GRUPPEN:
        offen = [rolle for rolle in rollen if rolle in gruppe and rolle not in vorschlag]
        frei = []
        for anfang in anfaenge:
            passend = [
                name
                for name in namen_der_anlage
                if next((a for a in anfaenge if name.casefold().startswith(a)), None) == anfang
                and name.casefold() not in vergeben
            ]
            frei.extend(sorted(passend, key=_nummer))
        for rolle, name in zip(offen, frei):
            vorschlag[rolle] = name
            vergeben.add(name.casefold())

    for rolle in rollen:
        if rolle in vorschlag:
            continue
        standard = FUB_ROLE_DEFAULT_NAMES[rolle]
        vorschlag[rolle] = next(
            (
                vorhanden[name.casefold()]
                for name in standard
                if name.casefold() in vorhanden and name.casefold() not in vergeben
            ),
            standard[0],
        )
        vergeben.add(vorschlag[rolle].casefold())
    return vorschlag


def fub_namen_im_menue(parsed) -> list[str]:
    """Die Namen aller Funktionsblöcke eines gelesenen Menübaums."""
    fubs = _as_list(parsed.get("eta", {}).get("menu", {}).get("fub"))
    return [fub["@name"] for fub in fubs if isinstance(fub, dict) and fub.get("@name")]


def _finde_schalter(fub):
    """Sucht im ganzen Funktionsblock nach einem Ein/Aus-Objekt.

    Gesucht wird über den Namen, weil der Pfad dorthin je nach Firmware
    abweicht.
    """
    if fub is None:
        return None

    def durchsuchen(knoten):
        for kind in _as_list(knoten.get("object")):
            if not isinstance(kind, dict):
                continue
            if kind.get("@name", "").strip().casefold() in _SCHALTER_NAMEN:
                if kind.get("@uri"):
                    return kind["@uri"]
            treffer = durchsuchen(kind)
            if treffer:
                return treffer
        return None

    return durchsuchen(fub)


def _finde_pumpe(fub, stichwort):
    """Sucht unter "Ausgänge" eine Pumpe und liefert ihre Anforderung."""
    if fub is None:
        return None
    ausgaenge = _find_path(fub, ["Ausgänge"])
    if ausgaenge is None:
        return None

    for kind in _as_list(ausgaenge.get("object")):
        if not isinstance(kind, dict):
            continue
        if stichwort not in (kind.get("@name") or "").casefold():
            continue
        anforderung = _find_path(kind, ["Anforderung"])
        if anforderung is not None and anforderung.get("@uri"):
            return anforderung["@uri"]
    return None


def _finde_nach_namen(fub, name):
    """Sucht im ganzen Funktionsblock das erste Objekt mit diesem Namen."""
    if fub is None:
        return None
    ziel = name.casefold()

    def durchsuchen(knoten):
        for kind in _as_list(knoten.get("object")):
            if not isinstance(kind, dict):
                continue
            if kind.get("@name", "").strip().casefold() == ziel and kind.get("@uri"):
                return kind["@uri"]
            treffer = durchsuchen(kind)
            if treffer:
                return treffer
        return None

    return durchsuchen(fub)


def _kennung(uri):
    """Die hinteren drei Zahlen einer URI, oder None bei anderer Form."""
    teile = (uri or "").strip("/").split("/")
    return "/".join(teile[2:]) if len(teile) == 5 else None


def _finde_nach_kennung(fub, kennung):
    """Sucht im Funktionsblock das Objekt mit dieser Kennung."""
    if fub is None:
        return None

    def durchsuchen(knoten):
        for kind in _as_list(knoten.get("object")):
            if not isinstance(kind, dict):
                continue
            if _kennung(kind.get("@uri")) == kennung:
                return kind["@uri"]
            treffer = durchsuchen(kind)
            if treffer:
                return treffer
        return None

    return durchsuchen(fub)


def _discover_puffer_fuehler(fub):
    """Ermittelt die tatsächlich vorhandenen Pufferfühler (1 bis N).

    PufferFlex kann je nach Anlage zwischen 3 und PUFFER_FUEHLER_MAX Fühler
    haben - Fühler 1 ist immer oben, der zuletzt nummerierte immer unten.
    Da die Anzahl variiert, werden die "Eingänge" von PufferFlex nach allen
    Objekten durchsucht, deren Name mit "Fühler <Zahl>" beginnt.
    """
    if fub is None:
        return {}
    eingaenge = _find_path(fub, ["Eingänge"])
    if eingaenge is None:
        return {}

    found = {}
    for child in _as_list(eingaenge.get("object")):
        if not isinstance(child, dict):
            continue
        match = _FUEHLER_NAME_RE.match(child.get("@name", ""))
        if not match:
            continue
        index = int(match.group(1))
        if index < 1 or index > PUFFER_FUEHLER_MAX:
            continue
        uri = child.get("@uri")
        if uri and index not in found:
            found[index] = uri
    if found:
        return found

    nach_name = {
        (child.get("@name") or "").strip().casefold(): child.get("@uri")
        for child in _as_list(eingaenge.get("object"))
        if isinstance(child, dict) and child.get("@uri")
    }
    vorhanden = [
        nach_name[name.casefold()]
        for name in ALTE_PUFFER_FUEHLER
        if name.casefold() in nach_name
    ]
    return {index: uri for index, uri in enumerate(vorhanden, start=1)}


async def async_discover_uris(
    client, fub_name_overrides=None, ueber_kennung=None, fub_namen=None, zeitprogramme=None
):
    """Ruft /user/menu ab und ermittelt die URIs anhand der Namenspfade.

    Gibt ein Tupel (discovered, puffer_fuehler_indices) zurück:
    - discovered: {schluessel: uri} aller gefundenen Messwerte, inklusive
      "puffer_fuehler_<n>" je gefundenem Fühler.
    - puffer_fuehler_indices: sortierte Nummern der gefundenen Fühler.

    Nicht gefundene Schlüssel fehlen im Ergebnis. Ist der Menübaum nicht
    lesbar, wird der ETAApiError durchgereicht. In ueber_kennung, falls
    übergeben, landen die Schlüssel, die erst über KENNUNGEN gefunden
    wurden - ein Hinweis, dass der Namenspfad an dieser Anlage nicht passt.
    In fub_namen, falls übergeben, landet je Rolle der Name des
    Funktionsblocks, wie er im Menübaum steht - etwa "Puffer" statt des
    vorbelegten "PufferFlex", wenn die Erkennung auf den älteren Block
    ausgewichen ist. In zeitprogramme, falls übergeben, landen die Lade-
    und Bereitschaftszeiten, siehe WEITERE_ZEITPROGRAMME.
    """
    discovered = {}

    parsed = await client.async_get_menu()

    fubs = _as_list(parsed.get("eta", {}).get("menu", {}).get("fub"))
    fubs_by_role = _resolve_fubs_by_role(fubs, fub_name_overrides)
    if fub_namen is not None:
        fub_namen.update(
            {rolle: fub["@name"] for rolle, fub in fubs_by_role.items() if fub.get("@name")}
        )
    twin = fubs_by_role.get("twin") if "twin" in (fub_name_overrides or {}) else None

    for key, (role, path) in DISCOVERY_PATHS.items():
        fub = fubs_by_role.get(role)
        if twin is not None and key in TWIN_SCHLUESSEL:
            fub = twin
        if fub is None:
            continue
        found = _find_path(fub, path)
        uri = found.get("@uri") if found is not None else None
        for ausweichpfad in AUSWEICHPFADE.get(key, []):
            if uri:
                break
            found = _find_path(fub, ausweichpfad)
            uri = found.get("@uri") if found is not None else None
        if not uri and key in NAMENSSUCHE:
            uri = _finde_nach_namen(fub, NAMENSSUCHE[key])
        if not uri and key in KENNUNGEN:
            uri = _finde_nach_kennung(fub, KENNUNGEN[key])
            if uri and ueber_kennung is not None:
                ueber_kennung.add(key)
        if uri:
            discovered[key] = uri

    for key, (role, stichwort) in PUMPEN.items():
        uri = _finde_pumpe(fubs_by_role.get(role), stichwort)
        if uri:
            discovered[key] = uri

    for definition in THERMOSTATE.values():
        fub = fubs_by_role.get(definition["role"])
        if fub is None or _find_path(fub, RAUM_EXTERN) is None:
            continue
        for key, weg in thermostat_objekte(definition["praefix"]).items():
            if isinstance(weg, list):
                gefunden = _find_path(fub, weg)
                uri = gefunden.get("@uri") if gefunden is not None else None
            else:
                uri = _finde_nach_namen(fub, weg)
            if uri:
                discovered[key] = uri

    for definition in THERMOSTATE.values():
        discovered.update(
            _zeitfenster(fubs_by_role.get(definition["role"]), definition["praefix"])
        )
    namen = zeitprogramme if zeitprogramme is not None else {}
    for rolle, komponente in WEITERE_ZEITPROGRAMME.items():
        discovered.update(_weitere_zeitprogramme(fubs_by_role.get(rolle), komponente, namen))

    for key, role in SWITCH_ROLES.items():
        fub = fubs_by_role.get(role)
        uri = _finde_schalter(fub)
        if uri:
            discovered[key] = uri

    entaschen = _finde_nach_namen(fubs_by_role.get("kessel"), ENTASCHEN_TASTE)
    if entaschen:
        discovered["kessel_entaschen"] = entaschen

    for key, role in BETRIEBSART_ROLES.items():
        fub = fubs_by_role.get(role)
        if fub is None:
            continue
        for modus, name in BETRIEBSART_TASTEN.items():
            uri = _finde_nach_namen(fub, name)
            if uri:
                discovered[f"{key}_{modus}"] = uri

    puffer_fuehler_indices = []
    alle_fuehler = set()
    for komponente in PUFFER_SPEICHER:
        puffer = fubs_by_role.get(COMPONENTS[komponente]["roles"][0])
        fuehler = _discover_puffer_fuehler(puffer)
        for index, uri in fuehler.items():
            discovered[f"{komponente}_fuehler_{index}"] = uri
            alle_fuehler.add(f"{komponente}_fuehler_{index}")
        if komponente == "puffer":
            puffer_fuehler_indices = sorted(fuehler)
        volumen = _finde_nach_namen(puffer, PUFFER_VOLUMEN[0]) or _finde_nach_kennung(
            puffer, PUFFER_VOLUMEN[1]
        )
        if volumen:
            discovered[f"{komponente}_volumen"] = volumen

    gesucht = set(DISCOVERY_PATHS) | set(PUMPEN) | {f"{k}_volumen" for k in PUFFER_SPEICHER}
    messwerte = (gesucht & set(discovered)) | alle_fuehler
    zeitprogramm = {key for key in discovered if "_zeitfenster_" in key or "_absenkwert_" in key}
    zeitfenster = {key for key in zeitprogramm if "_zeitfenster_" in key}
    _LOGGER.info(
        "ETA Webservices: %d von %d Messwerten im Menübaum gefunden "
        "(%d Pufferfühler), dazu %d Schalt- und Betriebsart-Objekte und %d Zeitfenster",
        len(messwerte),
        len(gesucht) + len(alle_fuehler),
        len(alle_fuehler),
        len(discovered) - len(messwerte) - len(zeitprogramm),
        len(zeitfenster),
    )
    missing = sorted(gesucht - set(discovered))
    if missing:
        _LOGGER.debug(
            "ETA Webservices: Für folgende Messwerte wurde keine passende URI "
            "im Menübaum gefunden (evtl. an dieser Anlage nicht vorhanden, oder "
            "der FUB wurde umbenannt): %s",
            ", ".join(missing),
        )

    return discovered, puffer_fuehler_indices
