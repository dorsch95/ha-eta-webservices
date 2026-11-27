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
    PARTIKEL_NETZTEILE,
    PARTIKEL_WERTE,
    PUFFER_FUEHLER_MAX,
    PUFFER_SPEICHER,
    THERMOSTATE,
    WARMWASSER_SPEICHER,
    WOCHENTAGE,
    ZEITFENSTER_JE_TAG,
    absenkwert_schluessel,
    zeitfenster_schluessel,
)
from .weitere_werte import gesperrt
from .zuordnung import zuordenbar

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
    "kessel_austragung": ("kessel", ["Austragung"]),
    "restsauerstoff": ("kessel", ["Eingänge", "Restsauerstoff", "Restsauerstoff"]),
    "abgas_temperatur": ("kessel", ["Eingänge", "Abgas"]),
    "pellet_gesamtverbrauch": ("kessel", ["Zählerstände", "Gesamtverbrauch"]),
    "kessel_volllaststunden": ("kessel", ["Zählerstände", "Volllaststunden"]),
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
    **{
        f"{k}_warmwasser_unten": (_rolle(k), ["Eingänge", "Warmwasserspeicher unten"])
        for k in WARMWASSER_SPEICHER
    },
    **{
        f"{k}_zustand": (_rolle(k), ["Warmwasser", "Warmwasser-Zustand detailliert"])
        for k in WARMWASSER_SPEICHER
    },
    **{
        f"{k}_durchfluss": (_rolle(k), ["Warmwasser", "Sekundär Durchfluss"])
        for k in WARMWASSER_SPEICHER
    },
    **{
        f"{k}_pufferpumpe_drehzahl": (_rolle(k), ["Warmwasser", "Pufferpumpe"])
        for k in WARMWASSER_SPEICHER
    },
    **{
        f"{k}_warmwasser": (_rolle(k), ["Puffer", "Warmwasserbereich", "Warmwasser"])
        for k in PUFFER_SPEICHER
    },
    **{
        f"{k}_warmwasser_zustand": (_rolle(k), ["Warmwasser-Zustand detailliert"])
        for k in PUFFER_SPEICHER
    },
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
    "partikelabscheider_zustand": (
        "partikelabscheider",
        ["Partikelabscheider", "Part.Abscheider-Zustand detailliert"],
    ),
    "partikelabscheider_leistung_soll": (
        "partikelabscheider",
        ["Ausgänge", "Abscheider Netzteil", "Leistung-Soll"],
    ),
    "partikelabscheider_leistung_max": (
        "partikelabscheider",
        ["Partikelabscheider", "Abscheider Netzteil", "Leistung Max"],
    ),
    **{
        f"partikelabscheider{anhang}_{art}": (
            "partikelabscheider",
            ["Partikelabscheider", f"Abscheider Netzteil{zusatz}", name],
        )
        for anhang, (zusatz, _nummer) in PARTIKEL_NETZTEILE.items()
        for art, _bezeichnung, name, _kennung, _symbol in PARTIKEL_WERTE
    },
    "brennwert_zustand": (
        "brennwert",
        ["Brennwertwärmetauscher", "Brennwertwärmetauscher-Zustand detailliert"],
    ),
    "brenner_anforderung": ("brenner", ["Ausgänge", "Anforderung Brenner"]),
    "brenner_temperatur": ("brenner", ["Brenner", "Brennertemperatur"]),
    "brenner_leistung_soll": ("brenner", ["Ausgänge", "Leistung Soll"]),
    "brenner_volllaststunden": ("brenner", ["Zählerstände", "Volllaststunden"]),
    "fremdwaerme_temperatur": ("fremdwaerme", ["Eingänge", "Fremdwärme"]),
    "fremdwaerme_speicher": ("fremdwaerme", ["Eingänge", "Speichertemperatur"]),
    "fremdwaerme_zustand": ("fremdwaerme", ["Fremdwärme", "Fremdwärme-Zustand detailliert"]),
    "fremdwaerme_ladepumpe": ("fremdwaerme", ["Ausgänge", "Ladepumpe", "Anforderung"]),
}

MERKMALE = ("kessel_austragung",)
"""Suchpfade, hinter denen kein Sensor steht: Sie sagen nur, ob die Anlage das Objekt führt.

kessel_austragung: Ein Hackgutkessel führt seine Austragung im
Funktionsblock des Kessels, gleich auf der ersten Ebene. Ein Pelletkessel
hat dafür den Block Lager, ein Stückholzkessel gar keine. Gelesen wird
das Objekt nicht.
"""

PUMPEN = {
    "fwm_zirkulationspumpe": ("fwm", "zirkulation"),
    **{f"{k}_zirkulationspumpe": (_rolle(k), "zirkulation") for k in WEITERES_WARMWASSER},
    "fernleitung_pumpe": ("fernleitung", "fernpumpe"),
    "puffer_ladepumpe": ("pufferflex", "pufferlade"),
    **{f"{k}_ladepumpe": (_rolle(k), "pufferlade") for k in WEITERE_PUFFER},
    **{f"{k}_ladepumpe": (_rolle(k), "ladepumpe") for k in WARMWASSER_SPEICHER},
    **{f"{k}_pufferpumpe": (_rolle(k), "pufferpumpe") for k in WARMWASSER_SPEICHER},
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
    "abgas_temperatur": [["Eingänge", "Abgas Wendekammer"]],
    "ruecklauf_temperatur": [["Kessel", "Rücklauf"]],
    **{f"{k}_warmwasser": [["Eingänge", "Warmwasserspeicher"]] for k in WARMWASSER_SPEICHER},
    **{
        f"{k}_zustand": [["Warmwasserspeicher", "Warmwasser-Zustand detailliert"]]
        for k in WARMWASSER_SPEICHER
    },
    **{
        f"{k}_warmwasser": [["Warmwasser-Zustand detailliert", "Warmwasserspeicher"]]
        for k in PUFFER_SPEICHER
    },
}
"""Weitere Namenspfade, falls der Hauptpfad im Funktionsblock fehlt.

Ein reiner Warmwasserspeicher (Funktionsblock "WW") nennt seinen Fühler
"Warmwasserspeicher", das Frischwassermodul "Warmwasser". Seinen Zustand
führt er unter "Warmwasserspeicher", das Frischwassermodul unter
"Warmwasser".

Das Warmwasser im Kombispeicher steht beim PufferFlex unter "Puffer >
Warmwasserbereich", beim älteren Funktionsblock "Puffer" unter
"Warmwasser-Zustand detailliert" - dieser Knoten ist dort zugleich der
Zustand.

Den Abgasfühler nennt ein Kessel "Abgas Wendekammer", so steht er im
Menübaum einer echten Anlage unter "Eingänge". Der Name "Abgas" ist dort
unbelegt: Unter ihm führt eine ältere Regelung den Wert auf der
Funktionsebene, siehe ANZEIGEWERTE.

Den Rücklauf führt ein Stückholzkessel von 2015 nicht unter "Eingänge",
sondern nur als Anzeigewert unter Kessel > Rücklauf, siehe
WEITERE_ANZEIGEWERTE. Kesseltemperatur, Abgas, Restsauerstoff und
Außentemperatur stehen dort ebenfalls auf der Funktionsebene; sie finden
schon die ANZEIGEWERTE und brauchen keinen eigenen Pfad.
"""

KENNUNGEN = {
    "kessel_temperatur": "0/11109/0",
    "ruecklauf_temperatur": "0/11160/0",
    "kessel_druck": "0/0/12180",
    "pellet_tagesbehälter": "0/0/12011",
    "kessel_soll": "0/0/13953",
    "restsauerstoff": "0/11108/2060",
    "abgas_temperatur": "0/11693/0",
    "pellet_gesamtverbrauch": "0/0/12016",
    "kessel_volllaststunden": "0/0/12153",
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
    **{f"{k}_warmwasser_unten": "0/11130/0" for k in WARMWASSER_SPEICHER},
    "lager_vorrat": "0/0/12015",
    "lager_warngrenze": "0/0/12042",
    "lager_maximum": "0/0/12790",
    "lager_zustand": "0/0/12423",
    "solar_kollektor": "0/11139/0",
    "solar_leistung": "0/0/12379",
    "solar_waermemenge": "0/0/12349",
    "solar_ertrag_heute": "0/0/12350",
    "solar_ertrag_gestern": "0/0/12769",
    "partikelabscheider_zustand": "0/0/12733",
    "partikelabscheider_leistung_soll": "0/11318/2328",
    "partikelabscheider_leistung_max": "14912/0/15424",
    **{
        f"partikelabscheider{anhang}_{art}": f"{nummer}/0/{kennung}"
        for anhang, (_zusatz, nummer) in PARTIKEL_NETZTEILE.items()
        for art, _bezeichnung, _name, kennung, _symbol in PARTIKEL_WERTE
    },
    "brennwert_zustand": "0/0/12731",
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
    "fremdwaerme_temperatur": "0/11112/0",
    "fremdwaerme_speicher": "0/11089/0",
    "fremdwaerme_zustand": "0/0/12386",
    "fremdwaerme_ladepumpe": "0/11088/2001",
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

ANZEIGEWERTE = {
    "kessel_temperatur": "0/0/12161",
    "ruecklauf_temperatur": "0/0/12999",
    "restsauerstoff": "0/0/12164",
    "abgas_temperatur": "0/0/12162",
    "aussentemperatur": "0/0/12197",
    **{f"{d['praefix']}_vorlauf": "0/0/12241" for d in THERMOSTATE.values()},
    **{f"{d['praefix']}_raum": "0/0/12634" for d in THERMOSTATE.values()},
    **{f"{k}_warmwasser": "0/0/12271" for k in WARMWASSER_SPEICHER},
    **{f"{k}_zustand": "0/0/12129" for k in WARMWASSER_SPEICHER},
    **{f"{k}_zustand": "0/0/12207" for k in PUFFER_SPEICHER},
    "lager_zustand": "0/0/12058",
    "fremdwaerme_temperatur": "0/0/12383",
    "fremdwaerme_speicher": "0/0/12491",
}
"""Dritter Weg zu einem Messwert: sein Anzeigewert auf der Funktionsebene.

Ältere Regelungen führen in ihren Funktionsblöcken keinen Zweig
"Eingänge" oder "Ausgänge". Belegt ist das am Menübaum einer Anlage mit
Software 3.42.0 von 2017 und Webservices 1.1: Die Kesseltemperatur steht
dort nur unter Kessel > Kessel > Kessel, der Vorlauf unter Heizkreis >
Vorlauf, das Warmwasser unter Warmwasserspeicher > Warmwasserspeicher.
Namenspfad und KENNUNGEN zeigen auf die Ein- und Ausgänge und finden an
so einer Anlage nichts.

Hier steht je Messwert die Kennung dieses Anzeigewerts, wie sie in jenem
Menübaum steht. Wo neuere Menübäume dasselbe Objekt führen, trägt es
dieselbe Kennung: "Kessel" 12161, "Außentemperatur" 12197, "Raum" 12634,
"Warmwasserspeicher" 12271 und der Zustand des Warmwasserspeichers 12129.
Den Zustand von Puffer, Warmwasserspeicher und Austragung meldet an der
älteren Anlage der Knoten der Funktion selbst.

Die Fremdwärme führt ihre beiden Temperaturen an jener Anlage nur unter
"Ladepumpe": "Fremdwärme" 12383 und "Speichertemperatur" 12491. Dieselben
Objekte stehen mit denselben Kennungen auch im Menübaum zweier neuerer
Anlagen, dort neben den Fühlern unter "Eingänge". Zustand und Ladepumpe
findet schon KENNUNGEN.

Gesucht wird erst, wenn Namenspfad und KENNUNGEN nichts gefunden haben,
und wie dort nur im eigenen Funktionsblock. Ein Treffer steht in der
Diagnose ebenfalls unter "ueber_kennung_gefunden".
"""

WEITERE_ANZEIGEWERTE = {
    "ruecklauf_temperatur": ("0/0/12220",),
}
"""Anzeigewerte, die ein Messwert neben dem aus ANZEIGEWERTE haben kann.

Den Rücklauf führt die Regelung von 2017 als "Rücklaufmischer" 12999.
Ein Stückholzkessel von 2015 (Menübaum aus Issue 11) hat stattdessen
Kessel > Rücklauf mit der Kennung 12220, gelesen mit 69,1 °C bei 81,9 °C
Kesseltemperatur. Denselben Eintrag führt der Kessel-Block einer neueren
Anlage, dort neben dem Fühler unter "Eingänge".

Die Kennung 12220 heißt auch in Heizkreis, Puffer und Brennwert-
Wärmetauscher "Rücklauf". Gesucht wird deshalb wie bei allen Kennungen
nur im Funktionsblock des Messwerts, hier dem Kessel, und erst nach
ANZEIGEWERTE.
"""

FLEXIBLE_PFAD_MUSTER: dict[str, dict[str, tuple]] = {
    "kessel_temperatur": {
        "pfade": (
            ("Eingänge", "Kessel"),
            ("Inputs", "Boiler"),
            ("Kessel", "Kessel"),
        ),
        "namen": ("Kesseltemperatur", "Boiler temperature"),
        "ausschluss": (
            "soll",
            "setpoint",
            "min",
            "max",
            "pumpe",
            "pump",
            "zustand",
            "state",
            "status",
            "druck",
            "pressure",
            "abschalten",
            "gebläse",
            "anforderung",
            "leistung",
        ),
    },
    "ruecklauf_temperatur": {
        "pfade": (
            ("Eingänge", "Rücklauf"),
            ("Inputs", "Return"),
            ("Rücklauf", "Ist Temperatur"),
            ("Return", "Actual temperature"),
            ("Rücklaufmischer", "Ist Temperatur"),
            ("Return mixer", "Actual temperature"),
        ),
        "namen": ("Rücklauf", "Return", "Rücklauftemperatur", "Return temperature"),
        "ausschluss": (
            "soll",
            "setpoint",
            "min",
            "max",
            "pumpe",
            "pump",
            "zustand",
            "state",
            "status",
            "position",
            "solar",
        ),
    },
    "abgas_temperatur": {
        "pfade": (
            ("Eingänge", "Abgas Wendekammer"),
            ("Eingänge", "Abgas"),
            ("Inputs", "Flue gas"),
            ("Kessel", "Abgas"),
        ),
        "namen": (
            "Abgas Wendekammer",
            "Abgas",
            "Abgastemperatur",
            "Flue gas",
            "Flue gas temperature",
        ),
        "ausschluss": (
            "soll",
            "setpoint",
            "min",
            "max",
            "gebläse",
            "fan",
            "zustand",
            "state",
            "status",
            "emissionsmessung",
        ),
    },
    "restsauerstoff": {
        "pfade": (
            ("Eingänge", "Restsauerstoff", "Restsauerstoff"),
            ("Inputs", "Residual oxygen", "Residual oxygen"),
            ("Kessel", "Restsauerstoff"),
        ),
        "namen": ("Restsauerstoff", "Residual oxygen", "O2"),
        "ausschluss": (
            "soll",
            "setpoint",
            "anforderung",
            "demand",
            "zustand",
            "state",
            "status",
            "sensor typ",
            "type",
        ),
    },
    "kessel_druck": {
        "pfade": (
            ("Eingänge", "Kesseldruck"),
            ("Inputs", "Boiler pressure"),
            ("Kessel", "Kesseldruck"),
        ),
        "namen": ("Kesseldruck", "Boiler pressure"),
        "ausschluss": ("mindest", "min", "max", "notbetrieb", "emergency"),
    },
    "kessel_soll": {
        "pfade": (
            ("Kessel", "Kessel Soll"),
            ("Boiler", "Boiler setpoint"),
            ("Boiler", "Boiler target"),
        ),
        "namen": ("Kessel Soll", "Boiler setpoint", "Boiler target"),
        "ausschluss": ("angefordert", "requested", "min", "max"),
    },
    "kessel_zustand": {
        "pfade": (
            ("Kessel", "Kessel-Zustand detailliert"),
            ("Boiler", "Boiler state detailed"),
            ("Boiler", "Boiler-State detailed"),
        ),
        "namen": (
            "Kessel-Zustand detailliert",
            "Kessel Zustand",
            "Boiler state detailed",
            "Boiler-State detailed",
        ),
        "ausschluss": ("soll", "min", "max"),
    },
    "aussentemperatur": {
        "pfade": (
            ("Außentemperatur", "Außentemperaturfühler"),
            ("Eingänge", "Außentemperatur"),
            ("System", "Außentemperatur"),
            ("Inputs", "Outside temperature"),
            ("Outside temperature", "Outside temperature sensor"),
        ),
        "namen": (
            "Außentemperaturfühler",
            "Außentemperatur",
            "Outside temperature",
            "Outside temp",
        ),
        "ausschluss": (
            "schnittstellen",
            "interface",
            "verzögert",
            "delayed",
            "heizgrenze",
            "min",
            "max",
            "solar",
            "zustand",
            "state",
            "kalibrier",
            "offset",
            "fixwert",
            "typ",
        ),
    },
    **{
        f"{k}_ladezustand": {
            "pfade": (
                ("Puffer", "Ladezustand"),
                ("Buffer", "Charge state"),
                ("Buffer", "State of charge"),
            ),
            "namen": ("Ladezustand", "Charge state", "State of charge"),
            "ausschluss": ("soll", "min", "max", "solar"),
        }
        for k in PUFFER_SPEICHER
    },
    **{
        f"{k}_zustand": {
            "pfade": (
                ("Puffer", "Puffer-Zustand detailliert"),
                ("Buffer", "Buffer state detailed"),
            ),
            "namen": ("Puffer-Zustand detailliert", "Buffer state detailed"),
            "ausschluss": ("soll", "min", "max", "solar"),
        }
        for k in PUFFER_SPEICHER
    },
    **{
        f"{d['praefix']}_vorlauf": {
            "pfade": (
                ("Eingänge", "Vorlauf"),
                ("Inputs", "Flow"),
                ("Heizkreis", "Vorlauf"),
                ("Heating circuit", "Flow"),
            ),
            "namen": ("Vorlauf", "Vorlauftemperatur", "Flow", "Flow temperature"),
            "ausschluss": (
                "soll",
                "min",
                "max",
                "kurve",
                "curve",
                "-10",
                "+10",
                "absenk",
                "primär",
                "primary",
                "solar",
            ),
        }
        for d in THERMOSTATE.values()
    },
    **{
        f"{k}_warmwasser": {
            "pfade": (
                ("Eingänge", "Warmwasser"),
                ("Eingänge", "Warmwasserspeicher"),
                ("Inputs", "Hot water"),
                ("Inputs", "Domestic hot water"),
            ),
            "namen": ("Warmwasser", "Warmwasserspeicher", "Hot water", "Domestic hot water"),
            "ausschluss": (
                "unten",
                "bottom",
                "soll",
                "setpoint",
                "max",
                "min",
                "zustand",
                "state",
                "pumpe",
                "pump",
                "zirkulation",
                "circulation",
                "ladezeiten",
                "bereich",
            ),
        }
        for k in WARMWASSER_SPEICHER
    },
    "lager_vorrat": {
        "pfade": (("Vorrat",), ("Stock",)),
        "namen": ("Vorrat", "Stock"),
        "ausschluss": ("warngrenze", "warning", "maximal", "max", "min"),
    },
    "lager_zustand": {
        "pfade": (("Austragung", "Austragung-Zustand detailliert"),),
        "namen": ("Austragung-Zustand detailliert", "Discharge state detailed"),
        "ausschluss": ("laufzeit", "runtime"),
    },
    "solar_kollektor": {
        "pfade": (("Eingänge", "Kollektor"), ("Inputs", "Collector")),
        "namen": ("Kollektor", "Collector"),
        "ausschluss": ("min", "max", "pumpe", "pump", "differenz"),
    },
    "solar_leistung": {
        "pfade": (("Leistung",), ("Output",)),
        "namen": ("Leistung", "Output"),
        "ausschluss": ("wärmemenge", "ertrag", "yield"),
    },
    "solar_waermemenge": {
        "namen": ("Wärmemenge", "Heat amount", "Heat energy"),
        "ausschluss": (),
    },
    "solar_ertrag_heute": {
        "namen": ("Ertrag heute", "Yield today"),
        "ausschluss": (),
    },
    "solar_ertrag_gestern": {
        "namen": ("Ertrag gestern", "Yield yesterday"),
        "ausschluss": (),
    },
}
"""Woran ein fehlender Messwert im Menübaum zu erkennen sein könnte - nur als Vorschlag.

Je Messwert die Enden möglicher Wege ("pfade"), mögliche Namen des
Objekts ("namen") und Wörter, die einen Weg ausschließen ("ausschluss"),
etwa "soll" oder "pumpe". Anders als DISCOVERY_PATHS, KENNUNGEN und
ANZEIGEWERTE ist das eine Vermutung: Die deutschen Namen stammen aus
Menübäumen echter Anlagen, stehen dort aber an anderer Stelle; die
englischen sind an keinem Menübaum belegt.

Deshalb übernimmt die Erkennung einen solchen Treffer nie von selbst.
Er erscheint beim Zuordnen von Hand als Vorschlag, und auch das nur,
wenn seine Einheit zum Messwert passt, siehe vorschlaege_fuer_zuordnung
und config_flow.py. An dreizehn bekannten Menübäumen findet die Suche
nichts, was die übrigen Stufen nicht schon gefunden hätten.
"""

PUFFER_VOLUMEN = ("Gesamtvolumen", "0/0/13520")
"""Name und Kennung des Gesamtvolumens eines Puffers in Litern.

Der PufferFlex führt es unter Einstellungen. Eine Anlage meldet es über
die Webservices als beschreibbar, von 50 bis 500000 l, ab Werk 1000 l.
Mit ihm rechnet die Prognose, und das Zahlenfeld "Puffervolumen" stellt
es, siehe const.ZAHLEN.

Der ältere Funktionsblock "Puffer" führt kein Gesamtvolumen. Dort trägt
der Nutzer die Liter ein, bei der Einrichtung oder im Zahlenfeld.

Das "Effektive Puffervolumen" liest die Integration nicht. Beim
PufferFlex steht es im Menübaum bei der Leistungsregelung, folgt dem
Gesamtvolumen und ist nicht beschreibbar. Der ältere Puffer führt es nur
mit mehr als seinen zwei Fühlern ab Werk, dort als Einstellwert. Die
Menübäume dazu stehen in tests/fixtures/fub_puffer_2_fuehler.xml und
fub_puffer_5_fuehler.xml.
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

ALTE_PUFFER_FUNKTION = ["Puffer"]
"""Wo die Fühler des älteren Puffers stehen, wenn der Zweig "Eingänge" fehlt.

Siehe ANZEIGEWERTE: An einer älteren Regelung hängen "Puffer oben" und
"Puffer unten" nur als Anzeigewerte unter Puffer > Puffer.
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


def _vergleichsname(name) -> str:
    """Ein Name so, wie er verglichen wird: ohne Leerzeichen am Rand, ohne Groß und Klein.

    Manche Anlagen melden Namen mit einem Leerzeichen am Ende, etwa "Sys "
    oder "Puffer ". Am Display und im Formular ist das nicht zu sehen.
    """
    return (name or "").strip().casefold()


def _find_path(node, names):
    """Sucht rekursiv den 'object'-Knoten entlang des angegebenen Namenspfads."""
    if not names:
        return node
    target = _vergleichsname(names[0])
    for child in _as_list(node.get("object")):
        if _vergleichsname(child.get("@name")) == target:
            found = _find_path(child, names[1:])
            if found is not None:
                return found
    return None


def _find_fub(fubs, fub_name):
    target = _vergleichsname(fub_name)
    for fub in fubs:
        if _vergleichsname(fub.get("@name")) == target:
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
            override
            and _vergleichsname(override) not in {name.casefold() for name in default_names}
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
    vergeben = {_vergleichsname(name) for name in vorschlag.values()}
    vorhanden = {_vergleichsname(name): name for name in namen_der_anlage}

    for gruppe, anfaenge in FUB_GRUPPEN:
        offen = [rolle for rolle in rollen if rolle in gruppe and rolle not in vorschlag]
        frei = []
        for anfang in anfaenge:
            passend = [
                name
                for name in namen_der_anlage
                if next((a for a in anfaenge if name.casefold().startswith(a)), None) == anfang
                and _vergleichsname(name) not in vergeben
            ]
            frei.extend(sorted(passend, key=_nummer))
        for rolle, name in zip(offen, frei):
            vorschlag[rolle] = name
            vergeben.add(_vergleichsname(name))

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
        vergeben.add(_vergleichsname(vorschlag[rolle]))
    return vorschlag


def fub_namen_im_menue(parsed) -> list[str]:
    """Die Namen aller Funktionsblöcke eines gelesenen Menübaums."""
    fubs = _as_list(parsed.get("eta", {}).get("menu", {}).get("fub"))
    return [fub["@name"] for fub in fubs if isinstance(fub, dict) and fub.get("@name")]


def fub_namen_abgleich(rollen, namen_der_anlage):
    """Der Vorschlag für die Funktionsblock-Namen und die Rollen, deren Block die Anlage nicht meldet.

    Meldet die Anlage zu jeder Rolle einen Block unter dem vorgeschlagenen
    Namen, gibt es nichts zu bestätigen: Die Ersteinrichtung überspringt
    dann den Schritt der Funktionsblock-Namen. Fehlt einer - weil der
    Block an der Steuerung umbenannt ist oder die Anlage nicht antwortet -,
    zeigt sie ihn.
    """
    vorschlag = fub_namen_vorschlagen(rollen, namen_der_anlage)
    vorhanden = {_vergleichsname(name) for name in namen_der_anlage}
    fehlende = [rolle for rolle in rollen if _vergleichsname(vorschlag[rolle]) not in vorhanden]
    return vorschlag, fehlende


def _block_eintraege(fub) -> list[tuple[tuple[str, ...], str]]:
    """Alle benannten Objekte eines Funktionsblocks: der Weg dorthin und die Adresse.

    In der Reihenfolge der Anlage. Steht eine Adresse mehrfach im Block,
    zählt die erste Stelle.
    """
    eintraege: list[tuple[tuple[str, ...], str]] = []
    gesehen: set[str] = set()

    def sammeln(knoten, weg: tuple[str, ...]) -> None:
        for kind in _as_list(knoten.get("object")):
            if not isinstance(kind, dict):
                continue
            name = (kind.get("@name") or "").strip()
            uri = (kind.get("@uri") or "").strip()
            pfad = (*weg, name) if name else weg
            if name and uri and uri not in gesehen:
                gesehen.add(uri)
                eintraege.append((pfad, uri))
            sammeln(kind, pfad)

    if isinstance(fub, dict):
        sammeln(fub, ())
    return eintraege


def _ausgeschlossen(pfad: tuple[str, ...], ausschluss: tuple[str, ...]) -> bool:
    """Ob im Weg eines der Wörter steht, die einen Vorschlag ausschließen."""
    gesamt = " ".join(pfad).casefold()
    return any(wort.casefold() in gesamt for wort in ausschluss)


def _vermutung(eintraege: list[tuple[tuple[str, ...], str]], key: str) -> str | None:
    """Die Adresse, die nach FLEXIBLE_PFAD_MUSTER zu einem Messwert passen könnte.

    Zuerst die Wege, die auf eines der Muster enden, dann die bloßen
    Namen. Ein Weg mit einem Ausschlusswort zählt nicht.
    """
    muster = FLEXIBLE_PFAD_MUSTER.get(key)
    if not muster:
        return None
    ausschluss = muster.get("ausschluss", ())
    for ende in muster.get("pfade", ()):
        ziel = tuple(_vergleichsname(teil) for teil in ende)
        for pfad, uri in eintraege:
            if tuple(_vergleichsname(teil) for teil in pfad[-len(ziel) :]) == ziel and not (
                _ausgeschlossen(pfad, ausschluss)
            ):
                return uri
    namen = {_vergleichsname(name) for name in muster.get("namen", ())}
    for pfad, uri in eintraege:
        if _vergleichsname(pfad[-1]) in namen and not _ausgeschlossen(pfad, ausschluss):
            return uri
    return None


_ZEITPLAN_NAMEN = {_vergleichsname(tag) for tag in WOCHENTAGE.values()} | {"absenktemperatur"}


def _im_zeitprogramm(pfad: tuple[str, ...]) -> bool:
    """Ob ein Weg durch ein Zeitprogramm führt: über einen Wochentag oder ein Zeitfenster.

    Solche Einträge sind Schaltzeiten, kein Messwert. Ein Zeitprogramm
    hat an jedem Wochentag drei Fenster - sie füllten die Auswahl beim
    Zuordnen, ohne dass je eines passte.
    """
    return any(
        _vergleichsname(teil) in _ZEITPLAN_NAMEN or _vergleichsname(teil).startswith("zeitfenster ")
        for teil in pfad
    )


def _block_des_messwerts(key, fubs_by_role, twin):
    """Der Funktionsblock, in dem die Erkennung einen Messwert sucht - None, wenn es ihn nicht gibt."""
    eintrag = DISCOVERY_PATHS.get(key) or PUMPEN.get(key)
    if eintrag is None:
        return None
    if twin is not None and key in TWIN_SCHLUESSEL:
        return twin
    return fubs_by_role.get(eintrag[0])


def _bloecke(parsed, fub_name_overrides):
    """Die Funktionsblöcke eines gelesenen Menübaums je Rolle und der Block "Twin", wenn er gewählt ist."""
    wurzel = parsed.get("eta", {}).get("menu", {}) if isinstance(parsed, dict) else {}
    fubs = _as_list(wurzel.get("fub") if isinstance(wurzel, dict) else None)
    fubs_by_role = _resolve_fubs_by_role(fubs, fub_name_overrides)
    twin = fubs_by_role.get("twin") if "twin" in (fub_name_overrides or {}) else None
    return fubs_by_role, twin


def kandidaten_fuer_zuordnung(
    parsed, schluessel, fub_name_overrides=None
) -> dict[str, dict[str, str]]:
    """Je Messwert die Einträge seines Funktionsblocks, die sich ihm von Hand zuordnen lassen.

    Je Adresse der Weg im Block, etwa "Kessel › Rücklauf". Zur Wahl steht
    nur der eigene Funktionsblock des Messwerts, ohne die Einträge seiner
    Zeitprogramme. Ob ein Eintrag nach Art und Einheit passt, zeigt erst
    sein gelesener Wert, siehe zuordnung.passt. Für Messwerte, die sich
    nicht zuordnen lassen (zuordnung.zuordenbar), und für gesperrte
    Funktionsblöcke (weitere_werte.gesperrt) gibt es nichts.

    Führt der Block an einer Stelle zwei Objekte desselben Namens mit
    verschiedenen Adressen, bekommt das zweite eine Nummer - wie bei den
    weiteren Werten, siehe weitere_werte.menue_werte.
    """
    fubs_by_role, twin = _bloecke(parsed, fub_name_overrides)
    ergebnis: dict[str, dict[str, str]] = {}
    for key in schluessel:
        fub = _block_des_messwerts(key, fubs_by_role, twin)
        if fub is None or not zuordenbar(key) or gesperrt(fub):
            continue
        eintraege: dict[str, str] = {}
        vergeben: dict[tuple[str, ...], int] = {}
        for pfad, uri in _block_eintraege(fub):
            vergeben[pfad] = vergeben.get(pfad, 0) + 1
            if not _im_zeitprogramm(pfad):
                weg = " › ".join(pfad)
                eintraege[uri] = weg if vergeben[pfad] == 1 else f"{weg} ({vergeben[pfad]})"
        ergebnis[key] = eintraege
    return ergebnis


def vorschlaege_fuer_zuordnung(parsed, schluessel, fub_name_overrides=None) -> dict[str, str]:
    """Je Messwert die Adresse, die FLEXIBLE_PFAD_MUSTER für ihn vermutet.

    Nur ein Vorschlag für die Zuordnung von Hand, nie von selbst
    übernommen - siehe FLEXIBLE_PFAD_MUSTER. Messwerte ohne Vermutung
    fehlen.
    """
    fubs_by_role, twin = _bloecke(parsed, fub_name_overrides)
    vorschlaege: dict[str, str] = {}
    for key in schluessel:
        fub = _block_des_messwerts(key, fubs_by_role, twin)
        if fub is None or not zuordenbar(key) or gesperrt(fub):
            continue
        uri = _vermutung(
            [(pfad, uri) for pfad, uri in _block_eintraege(fub) if not _im_zeitprogramm(pfad)],
            key,
        )
        if uri:
            vorschlaege[key] = uri
    return vorschlaege


def _zugeordnet(key, fub, zuordnungen) -> str | None:
    """Die von Hand zugeordnete Adresse eines Messwerts, wenn sie gilt.

    Sie gilt nur für einen Messwert, der sich zuordnen lässt, und nur,
    solange die Adresse im eigenen Funktionsblock des Messwerts steht -
    nie außerhalb und nie in einem gesperrten Block.
    """
    uri = (zuordnungen or {}).get(key)
    if not isinstance(uri, str) or not zuordenbar(key) or gesperrt(fub):
        return None
    return uri if any(uri == adresse for _, adresse in _block_eintraege(fub)) else None


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


def _alte_puffer_fuehler(knoten):
    """Die Fühler des älteren Puffers direkt unter diesem Knoten, von oben nach unten."""
    if knoten is None:
        return {}
    nach_name = {
        _vergleichsname(child.get("@name")): child.get("@uri")
        for child in _as_list(knoten.get("object"))
        if isinstance(child, dict) and child.get("@uri")
    }
    vorhanden = [
        nach_name[name.casefold()]
        for name in ALTE_PUFFER_FUEHLER
        if name.casefold() in nach_name
    ]
    return {index: uri for index, uri in enumerate(vorhanden, start=1)}


def _discover_puffer_fuehler(fub):
    """Ermittelt die tatsächlich vorhandenen Pufferfühler (1 bis N).

    PufferFlex kann je nach Anlage zwischen 3 und PUFFER_FUEHLER_MAX Fühler
    haben - Fühler 1 ist immer oben, der zuletzt nummerierte immer unten.
    Da die Anzahl variiert, werden die "Eingänge" von PufferFlex nach allen
    Objekten durchsucht, deren Name mit "Fühler <Zahl>" beginnt.

    Der ältere Funktionsblock "Puffer" nennt seine Fühler anders, siehe
    ALTE_PUFFER_FUEHLER. Fehlt ihm der Zweig "Eingänge", stehen sie unter
    ALTE_PUFFER_FUNKTION.
    """
    if fub is None:
        return {}
    eingaenge = _find_path(fub, ["Eingänge"])
    if eingaenge is None:
        return _alte_puffer_fuehler(_find_path(fub, ALTE_PUFFER_FUNKTION))

    found = _nummerierte_fuehler(eingaenge)
    if found:
        return found
    return _alte_puffer_fuehler(eingaenge) or _alte_puffer_fuehler(
        _find_path(fub, ALTE_PUFFER_FUNKTION)
    )


def _nummerierte_fuehler(eingaenge):
    """Die Fühler eines PufferFlex unter "Eingänge": je Nummer der erste "Fühler <Zahl>"."""
    found = {}
    if eingaenge is None:
        return found
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
    return found


async def async_discover_uris(
    client,
    fub_name_overrides=None,
    ueber_kennung=None,
    fub_namen=None,
    zeitprogramme=None,
    zuordnungen=None,
    von_hand=None,
    menue=None,
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

    zuordnungen sind die Adressen, die der Nutzer fehlenden Messwerten von
    Hand zugeordnet hat, je Schlüssel. Eine gültige Zuordnung geht der
    Suche vor, siehe _zugeordnet; in von_hand, falls übergeben, landen die
    Schlüssel, bei denen sie gegriffen hat. Ist der Menübaum schon gelesen,
    kommt er als menue mit und wird nicht noch einmal geholt.
    """
    discovered = {}

    parsed = menue if menue is not None else await client.async_get_menu()

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
        uri = _zugeordnet(key, fub, zuordnungen)
        if uri:
            discovered[key] = uri
            if von_hand is not None:
                von_hand.add(key)
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
        for kennungen in (KENNUNGEN, ANZEIGEWERTE):
            if uri or key not in kennungen:
                continue
            uri = _finde_nach_kennung(fub, kennungen[key])
            if uri and ueber_kennung is not None:
                ueber_kennung.add(key)
        for kennung in WEITERE_ANZEIGEWERTE.get(key, ()):
            if uri:
                break
            uri = _finde_nach_kennung(fub, kennung)
            if uri and ueber_kennung is not None:
                ueber_kennung.add(key)
        if uri:
            discovered[key] = uri

    for key, (role, stichwort) in PUMPEN.items():
        fub = fubs_by_role.get(role)
        uri = _zugeordnet(key, fub, zuordnungen) if fub is not None else None
        if uri and von_hand is not None:
            von_hand.add(key)
        uri = uri or _finde_pumpe(fub, stichwort)
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
