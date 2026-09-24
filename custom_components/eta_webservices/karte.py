"""Baut die Dashboard-Karte.

Die Karte enthält jede Komponente dreimal - einmal je Bildschirmbreite.
Von Hand wäre das nicht zu pflegen, deshalb entsteht sie hier aus einer
einzigen Beschreibung. Zwei Wege führen hierher:

- die Aktion "Dashboard-Karte erzeugen" in Home Assistant, die eine auf
  die eigene Anlage zugeschnittene Karte liefert (siehe aktionen.py)
- dashboard/karte_bauen.py, das die universelle Karte fürs Repo erzeugt

Das Modul kommt ohne Home Assistant aus, damit das Skript es auch ohne
installiertes Home Assistant laden kann.
"""

import json
import re
from pathlib import Path

VERSION = json.loads(
    (Path(__file__).with_name("manifest.json")).read_text(encoding="utf-8")
)["version"]
"""Die Version der Integration, aus manifest.json."""

BILDPFAD = f"/eta_webservices/grafiken/{VERSION}"
"""Dort liefert die Integration die Kachelgrafiken aus, siehe URL_GRAFIKEN.

Die Version steckt in der Adresse: Die Bilder behalten bei einem Update
ihre Namen, und Browser wie die Home-Assistant-App zeigten sonst noch
lange die alten aus ihrem Zwischenspeicher. Mit jeder Version ist es
eine neue Adresse, also holen sie die neuen Bilder.
"""

FARBEN = {
    "aussen": "#9aa5b1",
    "kessel": "#e8615f",
    "soll": "#e2867f",
    "ruecklauf": "#7b88e0",
    "druck": "#d3a15a",
    "behaelter": "#5fbfa8",
    "aschebox": "#a98fd0",
    "o2": "#d89a6a",
    "hell": "#d5d9de",
    "weiss": "#ffffff",
    "gedaempft": "#9aa5b1",
    "solar": "#e0b63f",
}

KESSEL_ZEILEN = [
    ("aussentemperatur", "Außen: ", "Außen: ", "aussen", 4),
    ("kesseltemperatur", "Kessel: ", "Kessel: ", "kessel", 12),
    ("kessel_solltemperatur", "Soll: ", "Soll: ", "soll", 19),
    ("rucklauftemperatur", "Rücklauf: ", "RL: ", "ruecklauf", 26),
    ("kesseldruck", "Anlagendruck: ", "Anlagendruck: ", "druck", 33),
    ("pellet_inhalt_tagesbehalter", "Tagesbehälter: ", "Tagesbehälter: ", "behaelter", 40),
    ("aschebox_status", "Aschebox: ", "Asche: ", "aschebox", 47),
    ("restsauerstoff", "Restsauerstoff: ", "O₂: ", "o2", 54),
]


def label(entity, prefix, farbe, top, left, schrift, linksbuendig=False):
    """Eine Beschriftungszeile der Kachel."""
    stil = {
        "top": f"{top}%",
        "left": f"{left}%",
        "color": FARBEN[farbe],
        "font-size": f"{schrift}%",
    }
    if linksbuendig:
        stil["transform"] = "translate(0, -50%)"
    element = {
        "type": "state-label",
        "entity": f"sensor.eta_heizung_{entity}",
        "style": stil,
    }
    if prefix:
        element["prefix"] = prefix
    return element


def nur_wenn_vorhanden(element):
    """Blendet ein Element aus, wenn es seine Entität nicht gibt.

    Home Assistant wertet eine fehlende Entität als "unknown".
    """
    return {
        "type": "conditional",
        "conditions": [
            {
                "condition": "state",
                "entity": element["entity"],
                "state_not": "unknown",
            }
        ],
        "elements": [element],
    }


def nur_mit_wert(element):
    """Blendet ein Element aus, wenn es seine Entität nicht gibt oder sie "-" zeigt.

    "-" zeigt ein Sensor, dessen Wert die Anlage nicht führt - etwa die
    Zirkulationspumpe an einer Anlage ohne Zirkulation oder der
    Ladezustand beim älteren Funktionsblock "Puffer". Eine Zeile
    "Zirkulationspumpe: -" sagte dort nur, dass es nichts zu sagen gibt.
    """
    geschuetzt = nur_wenn_vorhanden(element)
    geschuetzt["conditions"].append(
        {"condition": "state", "entity": element["entity"], "state_not": "-"}
    )
    return geschuetzt


def betriebsart(entity, top, schrift):
    """Die Betriebsart als Text; ein Tippen öffnet die Auswahl.

    Am Heizkreis gibt es bewusst kein Ein/Aus-Symbol daneben: "Aus" ist
    einer der vier Einträge dieser Auswahl.
    """
    return nur_wenn_vorhanden(
        {
            "type": "state-label",
            "entity": f"select.eta_heizung_{entity}",
            "prefix": "Modus: ",
            "tap_action": {"action": "more-info"},
            "style": {
                "top": f"{top}%",
                "left": "50%",
                "color": FARBEN["hell"],
                "font-size": f"{schrift}%",
            },
        }
    )


ZEITPROGRAMM_OHNE_WIRKUNG = ["heizen", "absenken", "aus"]
"""In diesen Betriebsarten bestimmt das Zeitprogramm nichts."""


def zeitprogramm(entity, betriebsart_, top, schrift, kurz):
    """Heizzeit oder Absenkzeit - nur, solange das Zeitprogramm gilt.

    Das tut es im Auto-Modus. Gibt es keine Auswahl der Betriebsart, weil
    der Schreibzugriff fehlt, steht die Zeile immer da: Home Assistant
    wertet die fehlende Auswahl als "unknown".
    """
    element = nur_wenn_vorhanden(
        label(entity, "" if kurz else "Zeitprogramm: ", "gedaempft", top, 50, schrift)
    )
    element["conditions"].append(
        {
            "condition": "state",
            "entity": f"select.eta_heizung_{betriebsart_}",
            "state_not": ZEITPROGRAMM_OHNE_WIRKUNG,
        }
    )
    return element


def thermostat_zeile(entity, top, schrift):
    """Raum- und Solltemperatur des Thermostats; ein Tippen öffnet ihn.

    Den Thermostat gibt es nur bei Heizkreisen mit Raumfühler über die
    externe Schnittstelle und freigegebenem Schreibzugriff - sonst bleibt
    die Zeile leer. Die Tasten − und + stecken im geöffneten Thermostat:
    Eine picture-elements-Karte kann einen Sollwert nur auf einen festen
    Wert setzen, nicht um einen Schritt verändern.

    Kommt kein Raumwert an, fehlt "Raum" - statt eines leeren "Raum: °C".
    Home Assistant wertet ein fehlendes Attribut als "unknown". "Soll"
    steht in jedem Modus außer "Aus": Bei "Dauer" und "ECO" gilt er ja
    weiter, nur ein ausgeschalteter Heizkreis hat keinen.
    """
    entitaet = f"climate.eta_heizung_{entity}"

    def wert(attribut, prefix, links, farbe):
        return {
            "type": "state-label",
            "entity": entitaet,
            "attribute": attribut,
            "prefix": prefix,
            "suffix": " °C",
            "tap_action": {"action": "more-info"},
            "style": {
                "top": f"{top}%",
                "left": f"{links}%",
                "color": FARBEN[farbe],
                "font-size": f"{schrift}%",
            },
        }

    vorhanden = {"condition": "state", "entity": entitaet, "state_not": "unknown"}
    return [
        {
            "type": "conditional",
            "conditions": [
                vorhanden,
                {**vorhanden, "attribute": "current_temperature"},
            ],
            "elements": [wert("current_temperature", "Raum: ", 30, "weiss")],
        },
        {
            "type": "conditional",
            "conditions": [dict(vorhanden), {**vorhanden, "state_not": "off"}],
            "elements": [wert("temperature", "Soll: ", 70, "soll")],
        },
    ]


PUFFER_OBEN = 36
PUFFER_UNTEN = 88
PUFFER_MIN = 2
"""Der ältere Funktionsblock "Puffer" kommt mit zwei Fühlern aus, oben und unten."""
PUFFER_MAX = 9

PUFFER_KACHELN = {
    "puffer": ("puffer", "pufferspeicher"),
    "puffer2": ("puffer_2", "pufferspeicher_2"),
    "puffer3": ("puffer_3", "pufferspeicher_3"),
}
"""Je Puffer: womit seine Entitäts-IDs beginnen und welcher Marker ihn zeigt."""


def puffer_fuehler(anzahl, schrift, praefix="puffer"):
    """Zeigt genau dann N Fühler, wenn die Anlage N Fühler hat.

    Die Integration legt je gefundenem Fühler eine Entität an - wie viele
    das sind, weiß erst die laufende Anlage. Für jede mögliche Anzahl gibt
    es deshalb einen Block, der genau dann greift, wenn Fühler N vorhanden
    und Fühler N+1 nicht vorhanden ist. Home Assistant wertet eine
    fehlende Entität als "unknown".

    Die Fühler sitzen gleichmäßig verteilt zwischen Speicheroberkante und
    -unterkante, denn Fühler 1 misst oben und der letzte unten. praefix
    wählt den Puffer, siehe PUFFER_KACHELN.
    """
    bedingungen = [
        {
            "condition": "state",
            "entity": f"sensor.eta_heizung_{praefix}_fuhler_{i}",
            "state_not": "unknown",
        }
        for i in range(1, anzahl + 1)
    ]
    if anzahl < PUFFER_MAX:
        bedingungen.append(
            {
                "condition": "state",
                "entity": f"sensor.eta_heizung_{praefix}_fuhler_{anzahl + 1}",
                "state": "unknown",
            }
        )

    abstand = (PUFFER_UNTEN - PUFFER_OBEN) / (anzahl - 1)
    return {
        "type": "conditional",
        "conditions": bedingungen,
        "elements": [
            label(
                f"{praefix}_fuhler_{i}",
                None,
                "weiss",
                round(PUFFER_OBEN + abstand * (i - 1), 1),
                50,
                schrift,
            )
            for i in range(1, anzahl + 1)
        ],
    }


def puffer_schrift(anzahl, schrift):
    """Je mehr Fühler, desto weniger Platz je Zeile."""
    if anzahl <= 4:
        return schrift + 10
    if anzahl <= 6:
        return schrift + 5
    return schrift


PUFFER_LAEDT = ["Anfordern", "Laden", "Restwärme", "Abschöpfen"]
"""Puffer-Zustände, bei denen der Rand des Speichers warm pulsiert.

Die Texte von "Puffer-Zustand detailliert" sind bei PufferFlex und beim
älteren Funktionsblock "Puffer" dieselben. Bei allen übrigen - Aus,
Geladen, Frostschutz, Fühlerfehler, Aus Schaltuhr, Extra Warmwasser
laden, Solar Vorrang - bleibt der Rahmen grau.
"""

PUFFER_NAME_OBEN = 23
"""Höhe des Namens: zwischen Ladepumpe und Deckel des Speichers."""


def _marker_entitaet(komponente_):
    return f"sensor.eta_heizung_komponente_{PUFFER_KACHELN[komponente_][1]}"


def puffer_name(komponente_, schrift):
    """Der Name des Funktionsblocks über dem Speicher, wenn es weitere Puffer gibt.

    Bei einem einzigen Puffer wäre er überflüssig. Der Name kommt aus dem
    Attribut "funktionsblock" des Komponenten-Markers - so, wie der Block
    an der Regelung heißt, etwa "PufferFlex 2" oder "Puffer".

    Ob es weitere gibt, zeigen deren Marker. Bedingungen gelten nur alle
    zugleich, deshalb zwei Elemente: eines, wenn der erste der anderen
    Puffer da ist, eines, wenn nur der zweite da ist. Die zugeschnittene
    Karte ersetzt beide durch das Etikett allein oder lässt sie weg, siehe
    _puffernamen_zuschneiden.
    """
    erster, zweiter = (k for k in PUFFER_KACHELN if k != komponente_)
    eigener = _marker_entitaet(komponente_)
    etikett = label(f"komponente_{PUFFER_KACHELN[komponente_][1]}", None,
                    "weiss", PUFFER_NAME_OBEN, 50, schrift + 5)
    etikett["attribute"] = "funktionsblock"
    vorhanden = {"condition": "state", "entity": eigener, "state_not": "unknown"}
    return [
        {
            "type": "conditional",
            "conditions": [
                vorhanden,
                {"condition": "state", "entity": _marker_entitaet(erster), "state_not": "unknown"},
            ],
            "elements": [etikett],
        },
        {
            "type": "conditional",
            "conditions": [
                vorhanden,
                {"condition": "state", "entity": _marker_entitaet(erster), "state": "unknown"},
                {"condition": "state", "entity": _marker_entitaet(zweiter), "state_not": "unknown"},
            ],
            "elements": [etikett],
        },
    ]


def puffer_kachel(komponente_, schrift, kurz):
    """Die Kachel eines Pufferspeichers.

    Der Rahmen des Speichers pulsiert, solange der Puffer Wärme anfordert
    oder aufnimmt, siehe PUFFER_LAEDT. Oben der Ladezustand - der ältere
    Funktionsblock "Puffer" kennt keinen,
    dann bleibt die Zeile leer. Darunter die Ladepumpe, falls der Puffer
    dezentral geladen wird. Gibt es mehrere Puffer, steht über dem
    Speicher sein Name, siehe puffer_name.
    """
    praefix, marker = PUFFER_KACHELN[komponente_]
    zustand = f"sensor.eta_heizung_{praefix}_zustand"
    return komponente(
        marker,
        komponente_,
        "puffer",
        [
            *bewegt_oder_still(
                "puffer_laden",
                zustand,
                [{"condition": "state", "entity": zustand, "state": PUFFER_LAEDT}],
            ),
            nur_mit_wert(
                label(f"{praefix}_ladezustand", "Ladung: " if kurz else "Ladezustand: ",
                      "hell", 8, 50, schrift + 5)
            ),
            *puffer_name(komponente_, schrift),
            nur_mit_wert(
                label(f"{praefix}_ladepumpe", "Pumpe: " if kurz else "Ladepumpe: ",
                      "gedaempft", 15, 50, schrift)
            ),
            *(
                puffer_fuehler(anzahl, puffer_schrift(anzahl, schrift), praefix)
                for anzahl in range(PUFFER_MIN, PUFFER_MAX + 1)
            ),
        ],
    )


MODUS_TASTEN = [
    ("automatik", "mdi:calendar-clock", "Auto"),
    ("heizen", "mdi:fire", "Dauer"),
    ("absenken", "mdi:leaf", "ECO"),
    ("aus", "mdi:power", "Aus"),
]
"""Die vier Betriebsarten als antippbare Symbole, in der Reihenfolge der Anlage.

Der erste Wert ist die Option der Auswahl-Entität, sie darf sich nicht
ändern - daran hängen auch Blueprints und Automatisierungen. Angezeigt
wird nur das Symbol; welcher Modus gerade gilt, steht als Text darüber.
"""


AKTIV = "var(--state-active-color, #ffc107)"
"""Die Farbe, in der Home Assistant eingeschaltete Symbole zeigt.

Dieselbe wie beim Ein/Aus-Symbol des Kessels, damit beide Kacheln
gleich aussehen - auch mit einem eigenen Theme.
"""


def leuchtendes_symbol(entitaet, symbol, top, left, aktiv_wenn, tap_action, titel, groesse=26):
    """Ein antippbares Symbol, das leuchtet, solange aktiv_wenn gilt.

    Wie bei den Modus-Tasten gibt es das Symbol zweimal, je mit einer
    Bedingung - leuchtend oder hell, nie beide zugleich. aktiv_wenn ist
    eine Bedingung mit "state", das Gegenstück entsteht mit "state_not".
    Fehlt die Entität auf dieser Anlage, erscheint keines von beiden.
    """
    elemente = []
    for aktiv in (True, False):
        stil = {
            "top": f"{top}%",
            "left": f"{left}%",
            "color": AKTIV if aktiv else FARBEN["hell"],
            "--mdc-icon-size": f"{groesse}px",
        }
        if aktiv:
            stil["filter"] = f"drop-shadow(0 0 6px {AKTIV})"
        bedingung = dict(aktiv_wenn)
        if not aktiv:
            bedingung["state_not"] = bedingung.pop("state")
        elemente.append(
            {
                "type": "conditional",
                "conditions": [
                    {"condition": "state", "entity": entitaet, "state_not": "unknown"},
                    bedingung,
                ],
                "elements": [
                    {
                        "type": "icon",
                        "icon": symbol,
                        "title": titel,
                        "entity": entitaet,
                        "tap_action": tap_action,
                        "style": stil,
                    }
                ],
            }
        )
    return elemente


def kessel_knoepfe():
    """Ein/Aus, Entaschen und der Aschebox-Plan unten auf der Kessel-Kachel.

    Ein/Aus leuchtet wie die Modus-Tasten am Heizkreis, solange der Kessel
    an ist. Entaschen fragt vorher nach, denn der Kessel geht dafür in den
    Glutabbrand; es leuchtet, solange er entascht. Das Uhr-Symbol öffnet
    Datum und Uhrzeit zum Leeren der Aschebox und leuchtet, solange ein
    Plan läuft. Entaschen und Plan gibt es nur mit Schreibzugriff und
    einer Entaschentaste an der Anlage.

    Beide hängen am Sensor des Aschebox-Plans statt an ihrer eigenen
    Entität: Ein Knopf meldet "unknown", bis er zum ersten Mal gedrückt
    wurde, und die Uhrzeit ohne Plan ebenfalls - genau das, woran die
    Karte sonst eine fehlende Entität erkennt. Die drei Symbole stehen
    in einer Reihe unter dem Kessel, wie die Modus-Tasten am Heizkreis.
    """
    schalter_ = "switch.eta_heizung_kessel"
    entaschen = "button.eta_heizung_kessel_entaschen"
    zeit = "datetime.eta_heizung_aschebox_leeren_um"
    return [
        *leuchtendes_symbol(
            ASCHEBOX_PLAN, "mdi:delete-clock", 90, 30,
            {"condition": "state", "entity": ASCHEBOX_PLAN, "state": ASCHEBOX_LAEUFT},
            {"action": "more-info", "entity": zeit}, "Aschebox leeren um",
        ),
        *leuchtendes_symbol(
            ASCHEBOX_PLAN, "mdi:delete-sweep", 90, 50,
            {"condition": "state", "entity": KESSEL_ZUSTAND, "state": KESSEL_ENTASCHEN},
            {
                "action": "perform-action",
                "perform_action": "button.press",
                "target": {"entity_id": entaschen},
                "confirmation": {"text": "Kessel jetzt entaschen? Er geht dafür in den Glutabbrand."},
            },
            "Entaschen",
        ),
        *leuchtendes_symbol(
            schalter_, "mdi:power", 90, 70,
            {"condition": "state", "entity": schalter_, "state": "on"},
            {"action": "toggle"}, "Ein/Aus",
        ),
    ]


def aschebox_status(schrift):
    """Oben rechts, solange ein Aschebox-Plan läuft: sein Schritt.

    Antippen bricht den Plan nach einer Rückfrage ab.
    """
    abbrechen = "button.eta_heizung_aschebox_plan_abbrechen"
    return {
        "type": "conditional",
        "conditions": [
            {"condition": "state", "entity": ASCHEBOX_PLAN, "state_not": "unknown"},
            {"condition": "state", "entity": ASCHEBOX_PLAN, "state": ASCHEBOX_LAEUFT},
        ],
        "elements": [
            {
                "type": "state-label",
                "entity": ASCHEBOX_PLAN,
                "suffix": " ✕",
                "tap_action": {
                    "action": "perform-action",
                    "perform_action": "button.press",
                    "target": {"entity_id": abbrechen},
                    "confirmation": {"text": "Aschebox-Plan abbrechen?"},
                },
                "style": {
                    "top": "4%",
                    "left": "94%",
                    "transform": "translate(-100%, -50%)",
                    "color": FARBEN["aschebox"],
                    "font-size": f"{schrift}%",
                },
            }
        ],
    }


def modus_tasten(entity, top, groesse=26):
    """Schaltet die Betriebsart direkt auf der Kachel um.

    Vier Symbole nebeneinander, jedes setzt beim Antippen seine
    Betriebsart. "Aus" ist eines davon - einen getrennten Ein/Aus-Schalter
    gibt es am Heizkreis deshalb nicht.

    Das Symbol der gerade geltenden Betriebsart leuchtet wie das
    eingeschaltete Kessel-Symbol. Dafür gibt es jedes Symbol zweimal, je
    mit einer Bedingung: leuchtend, wenn die Auswahl auf seiner Betriebsart
    steht, sonst hell. Nie beide zugleich - übereinanderliegende Symbole
    bekämen sonst einen grauen Rand.
    """
    entitaet = f"select.eta_heizung_{entity}"
    elemente = []
    for (modus, symbol, titel), links in zip(MODUS_TASTEN, (20, 40, 60, 80)):
        for aktiv in (True, False):
            stil = {
                "top": f"{top}%",
                "left": f"{links}%",
                "color": AKTIV if aktiv else FARBEN["hell"],
                "--mdc-icon-size": f"{groesse}px",
            }
            if aktiv:
                stil["filter"] = f"drop-shadow(0 0 6px {AKTIV})"
            bedingungen = [
                {"condition": "state", "entity": entitaet, "state_not": "unknown"},
                (
                    {"condition": "state", "entity": entitaet, "state": modus}
                    if aktiv
                    else {"condition": "state", "entity": entitaet, "state_not": modus}
                ),
            ]
            elemente.append(
                {
                    "type": "conditional",
                    "conditions": bedingungen,
                    "elements": [
                        {
                            "type": "icon",
                            "icon": symbol,
                            "title": titel,
                            "entity": entitaet,
                            "tap_action": {
                                "action": "perform-action",
                                "perform_action": "select.select_option",
                                "target": {"entity_id": entitaet},
                                "data": {"option": modus},
                            },
                            "style": stil,
                        }
                    ],
                }
            )
    return elemente


KESSEL_FLAMME = [
    "Heizen",
    "Heizen Start",
    "Anheizen",
    "Pellet Betrieb",
    "Heizen, Vorbereitung auf Messung",
    "Heizen, Teillastmessung durchführen",
    "Heizen, Nennlastmessung durchführen",
]
"""Kessel-Zustände, bei denen die Flamme lodert."""

KESSEL_ZUENDUNG = [
    "Zünden",
    "Heizversuch",
]
"""Kessel-Zustände, in denen gezündet wird: Der Zündstab glüht, Funken springen."""

KESSEL_ENTASCHEN = [
    "Entaschen",
]
"""Der Rost dreht sich um seine Längsachse und kippt die Asche ab."""

KESSEL_STOERUNG = [
    "Störung",
    "Störung beim Entaschen",
    "Wartung",
]
"""Ein gelbes Warndreieck mit Ausrufezeichen blinkt im Brennraum."""

KESSEL_GLUT = [
    "Glutabbrand",
    "Glutabbrand wegen Entaschung",
    "Glutabbrand da ausgeschaltet",
    "Glutabbrand weil Aschebox fehlt",
    "Glutabbrand wegen Störung",
    "Glutabbrand wegen Verriegelung",
    "Ausbrand",
]
"""Kessel-Zustände, bei denen nur noch Glut im Brennraum liegt."""

KESSEL_AUS = [
    "Ausgeschaltet",
    "Klappe Öffnen",
    "Pelletsbehälter auffüllen",
    "Füllen gestoppt wegen Zündung",
    "Füllen gestoppt wegen Entaschung",
    "Bereit",
    "Aschebox fehlt",
    "Verriegelt",
    "Lambdasonde kalibrieren",
    "Vorwärmen",
    "Stoker leeren",
    "Füllen",
    "Isoliertür geöffnet",
    "Verzögerungszeit abwarten",
    "Übertemperatur",
    "Vorbereitung",
    "Vorbereiten auf Entaschung",
    "Durchlüften",
    "Umschaltung auf Stückholzbetrieb",
]
"""Kessel-Zustände ohne Feuer.

Die Listen zusammen sind alle Texte, die ein Pelletkessel für
"Kessel-Zustand detailliert" meldet. Ein Text, der in keiner steht - etwa
von einem anderen Kesseltyp -, zeigt die bisherige Kachel mit ruhender
Flamme.
"""


KESSEL_BEWEGT = [
    (KESSEL_FLAMME, "kessel_flamme"),
    (KESSEL_ZUENDUNG, "kessel_zuendung"),
    (KESSEL_ENTASCHEN, "kessel_entaschen"),
    (KESSEL_STOERUNG, "kessel_stoerung"),
    (KESSEL_GLUT, "kessel_glut"),
]
"""Kessel-Zustände mit bewegtem Bild und dessen Name ohne Endung.

Zu jedem gibt es ein Standbild (.png) und die Bewegung (.webp).
"""

KESSEL_ZUSTAND = "sensor.eta_heizung_kessel_zustand"

ASCHEBOX_PLAN = "sensor.eta_heizung_aschebox_plan"
ASCHEBOX_LAEUFT = ["geplant", "glutabbrand", "entaschen", "leeren"]
"""Die Schritte des Aschebox-Plans, in denen einer läuft."""


def kessel_zustandsbilder():
    """Welches Standbild die Kessel-Kachel bei welchem Zustand zeigt.

    Die Bewegung liegt als Auflage darüber, siehe kessel_bewegung.
    """
    bilder = {}
    for zustaende, bild in (*KESSEL_BEWEGT, (KESSEL_AUS, "kessel_aus")):
        for zustand in zustaende:
            bilder[zustand] = f"{BILDPFAD}/{bild}.png"
    return bilder


ANIMATIONEN = "switch.eta_heizung_animationen"
"""Der Schalter, mit dem der Nutzer die Bewegung auf der Karte abschaltet."""


def animationen(zustand):
    """Bedingungen: Der Schalter Animationen steht auf an bzw. aus."""
    return [
        {"condition": "state", "entity": ANIMATIONEN, "state_not": "unknown"},
        {"condition": "state", "entity": ANIMATIONEN, "state": zustand},
    ]


def kessel_bewegung():
    """Die bewegten Kesselbilder über dem Standbild der Kachel.

    Nur bei eingeschalteten Animationen; sonst bleibt das Standbild aus
    state_image stehen, das dasselbe zeigt, nur still.
    """
    return [
        auflage(f"{bild}.webp", KESSEL_ZUSTAND,
                [*animationen("on"),
                 {"condition": "state", "entity": KESSEL_ZUSTAND, "state": zustaende}])
        for zustaende, bild in KESSEL_BEWEGT
    ]


def bewegt_oder_still(bild, entitaet, bedingungen):
    """Das bewegte Bild bei eingeschalteten Animationen, sonst sein Standbild."""
    return [
        auflage(f"{bild}.webp", entitaet, [*animationen("on"), *bedingungen]),
        auflage(f"{bild}.png", entitaet, [*animationen("off"), *bedingungen]),
    ]


def auflage(bild, entitaet, bedingungen):
    """Ein Bild so groß wie die Kachel, das nur unter diesen Bedingungen erscheint.

    Die Auflagen liegen vor den Beschriftungen in der Elementliste, damit
    die Schrift darüber bleibt. Antippen tut nichts - sonst verdeckte das
    Bild die ganze Kachel mit einem Dialog.
    """
    return {
        "type": "conditional",
        "conditions": [
            {"condition": "state", "entity": entitaet, "state_not": "unknown"},
            *bedingungen,
        ],
        "elements": [
            {
                "type": "image",
                "entity": entitaet,
                "image": f"{BILDPFAD}/{bild}",
                "tap_action": {"action": "none"},
                "hold_action": {"action": "none"},
                "style": {"top": "50%", "left": "50%", "width": "100%"},
            }
        ],
    }


LAGER_FUELLSTAND = "sensor.eta_heizung_lager_fullstand"
LAGER_STUFEN = [
    ("lager_100.png", 87.5, None),
    ("lager_75.png", 62.5, 87.5),
    ("lager_50.png", 37.5, 62.5),
    ("lager_25.png", 12.5, 37.5),
    ("lager_leer.png", None, 12.5),
]
"""Welches Lagerbild bei welchem Füllstand in Prozent gilt (über, unter).

Der Füllstand ist ganzzahlig, die Grenzen liegen deshalb auf halben
Prozent - jeder Wert fällt in genau eine Stufe.
"""

LAGER_FOERDERN = "Fördern"
"""Austragung-Zustand, bei dem sich die Förderschnecke dreht."""


def lager_auflagen():
    """Füllstufe, drehende Schnecke und Warnung für die Lager-Kachel."""
    elemente = []
    for bild, ueber, unter in LAGER_STUFEN:
        grenze = {"condition": "numeric_state", "entity": LAGER_FUELLSTAND}
        if ueber is not None:
            grenze["above"] = ueber
        if unter is not None:
            grenze["below"] = unter
        elemente.append(auflage(bild, LAGER_FUELLSTAND, [grenze]))
    austragung = "sensor.eta_heizung_lager_austragung"
    elemente.extend(
        bewegt_oder_still("lager_schnecke", austragung,
                          [{"condition": "state", "entity": austragung, "state": LAGER_FOERDERN}])
    )
    warnung = "binary_sensor.eta_heizung_pelletvorrat_niedrig"
    elemente.append(
        auflage("lager_warnung.png", warnung,
                [{"condition": "state", "entity": warnung, "state": "on"}])
    )
    return elemente


def lager_reicht_bis(schrift, kurz):
    """Bis wann der Vorrat reicht - klein ins Dach des Lagers geschrieben.

    Kommt aus der Verbrauchsprognose. Solange sie noch lernt oder der
    Vorrat länger als zwei Jahre reicht, bleibt das Dach leer. Das Datum
    steht deutsch formatiert im Attribut "datum"; der Zustand selbst ist
    ein ISO-Datum, das die Karte ungeformt anzeigen würde.
    """
    element = label(
        "lager_reicht_bis", "bis " if kurz else "Reicht bis ", "hell", 25.5, 50, schrift - 12
    )
    element["attribute"] = "datum"
    return nur_wenn_vorhanden(element)


HEIZKREIS_OHNE_FLUSS = ["Aus", "-", "unavailable"]
"""Anforderungen, bei denen im Heizkreis nichts fließt.

"-" meldet die Integration, wenn die Anlage die Anforderung nicht führt.
"""


def heizkreis_fluss(entitaet):
    """Helle Pulse wandern durch den Heizkreis, solange er angefordert ist.

    Ohne Animationen stehen die Pulse still - der Heizkreis bleibt
    trotzdem sichtbar hervorgehoben.
    """
    entitaet = f"sensor.eta_heizung_{entitaet}"
    return bewegt_oder_still(
        "heizkreis_fluss",
        entitaet,
        [{"condition": "state", "entity": entitaet, "state_not": HEIZKREIS_OHNE_FLUSS}],
    )


LEISTUNG_AB = 0.05
"""Ab dieser Leistung in kW gilt Solar bzw. Heizstab als in Betrieb."""


def aktiv_oder_ruhe(bild, entitaet):
    """Motiv bewegt, solange Leistung anliegt, sonst blass.

    Ohne Animationen leuchtet es still. Meldet die Anlage keine Leistung,
    greift keine der Auflagen und es bleibt beim Grundbild.
    """
    entitaet = f"sensor.eta_heizung_{entitaet}"
    return [
        auflage(f"{bild}_ruhe.png", entitaet,
                [{"condition": "numeric_state", "entity": entitaet, "below": LEISTUNG_AB}]),
        *bewegt_oder_still(f"{bild}_aktiv", entitaet,
                           [{"condition": "numeric_state", "entity": entitaet, "above": LEISTUNG_AB}]),
    ]


BRENNER_ANFORDERUNG = "sensor.eta_heizung_brenner_anforderung"
"""Fordert die Regelung den Brenner an ("Ein"), brennt die Flamme.

Ob er wirklich brennt, meldet der Brenner der Regelung nicht zurück - die
Anforderung ist alles, was sie weiß.
"""

FERNLEITUNG_PUMPE = "sensor.eta_heizung_fernleitung_pumpe"
"""Läuft die Fernpumpe ("Ein"), wandern Pulse durch Vor- und Rücklauf."""


def komponente(marker, zustand, bild, elemente, zustandsbilder=None):
    """Eine Kachel, die nur erscheint, wenn es die Komponente gibt.

    zustandsbilder ist ein Paar (Entität, {Zustand: Bild}). Dann wechselt
    die Kachel ihr Bild mit dem Zustand dieser Entität; bei jedem anderen
    Zustand bleibt es beim Grundbild.
    """
    karte = {
        "type": "picture-elements",
        "image": f"{BILDPFAD}/{bild}.png",
        "elements": elemente,
    }
    if zustandsbilder:
        entitaet, bilder = zustandsbilder
        karte["entity"] = f"sensor.eta_heizung_{entitaet}"
        karte["state_image"] = bilder
    return {
        "type": "conditional",
        "conditions": [
            {
                "condition": "state",
                "entity": f"sensor.eta_heizung_komponente_{marker}",
                "state": zustand,
            }
        ],
        "card": karte,
    }


def grid(spalten, schrift, kurz):
    """Alle Kacheln nebeneinander, für eine der drei Bildschirmbreiten."""
    kessel = kessel_bewegung() + [
        label(
            entity,
            kurz_text if kurz else lang_text,
            farbe,
            top,
            6,
            schrift,
            linksbuendig=True,
        )
        for entity, lang_text, kurz_text, farbe, top in KESSEL_ZEILEN
    ]
    kessel.extend(kessel_knoepfe())
    kessel.append(aschebox_status(schrift - 10))
    return {
        "type": "grid",
        "columns": spalten,
        "square": False,
        "cards": [
            komponente("kessel", "kessel", "kessel", kessel,
                       ("kessel_zustand", kessel_zustandsbilder())),
            *(puffer_kachel(k, schrift, kurz) for k in PUFFER_KACHELN),
            komponente(
                "fwm",
                "fwm",
                "fwm",
                [
                    label("fwm_warmwassertemperatur", "WW: " if kurz else "Warmwasser: ",
                          "hell", 8, 50, schrift + 5),
                    nur_mit_wert(
                        label("fwm_zirkulationspumpe",
                              "Zirk.: " if kurz else "Zirkulationspumpe: ",
                              "gedaempft", 15, 50, schrift)
                    ),
                ],
            ),
            komponente(
                "heizkreis_1",
                "hk1",
                "heizkreis",
                [
                    *heizkreis_fluss("heizkreis_anforderung"),
                    label("heizkreis_vorlauftemperatur", "HK1: " if kurz else "Vorlauf HK1: ",
                          "kessel", 8, 50, schrift),
                    label("heizkreis_anforderung", "Anforderung: ", "hell", 15, 50, schrift - 5),
                    betriebsart("heizkreis_1_betriebsart", 23, schrift - 5),
                    zeitprogramm("heizkreis_zeitprogramm", "heizkreis_1_betriebsart", 31,
                                 schrift - 5, kurz),
                    *thermostat_zeile("heizkreis_1_thermostat", 39, schrift - 5),
                    *modus_tasten("heizkreis_1_betriebsart", 90),
                ],
            ),
            komponente(
                "heizkreis_2",
                "hk2",
                "heizkreis",
                [
                    *heizkreis_fluss("heizkreis_2_anforderung"),
                    label("heizkreis_2_vorlauftemperatur", "HK2: " if kurz else "Vorlauf HK2: ",
                          "kessel", 8, 50, schrift),
                    label("heizkreis_2_anforderung", "Anforderung: ", "hell", 15, 50, schrift - 5),
                    betriebsart("heizkreis_2_betriebsart", 23, schrift - 5),
                    zeitprogramm("heizkreis_2_zeitprogramm", "heizkreis_2_betriebsart", 31,
                                 schrift - 5, kurz),
                    *thermostat_zeile("heizkreis_2_thermostat", 39, schrift - 5),
                    *modus_tasten("heizkreis_2_betriebsart", 90),
                ],
            ),
            komponente(
                "heizkreis_3",
                "hk3",
                "heizkreis",
                [
                    *heizkreis_fluss("heizkreis_3_anforderung"),
                    label("heizkreis_3_vorlauftemperatur", "HK3: " if kurz else "Vorlauf HK3: ",
                          "kessel", 8, 50, schrift),
                    label("heizkreis_3_anforderung", "Anforderung: ", "hell", 15, 50, schrift - 5),
                    betriebsart("heizkreis_3_betriebsart", 23, schrift - 5),
                    zeitprogramm("heizkreis_3_zeitprogramm", "heizkreis_3_betriebsart", 31,
                                 schrift - 5, kurz),
                    *thermostat_zeile("heizkreis_3_thermostat", 39, schrift - 5),
                    *modus_tasten("heizkreis_3_betriebsart", 90),
                ],
            ),
            komponente(
                "heizkreis_4",
                "hk4",
                "heizkreis",
                [
                    *heizkreis_fluss("heizkreis_4_anforderung"),
                    label("heizkreis_4_vorlauftemperatur", "HK4: " if kurz else "Vorlauf HK4: ",
                          "kessel", 8, 50, schrift),
                    label("heizkreis_4_anforderung", "Anforderung: ", "hell", 15, 50, schrift - 5),
                    betriebsart("heizkreis_4_betriebsart", 23, schrift - 5),
                    zeitprogramm("heizkreis_4_zeitprogramm", "heizkreis_4_betriebsart", 31,
                                 schrift - 5, kurz),
                    *thermostat_zeile("heizkreis_4_thermostat", 39, schrift - 5),
                    *modus_tasten("heizkreis_4_betriebsart", 90),
                ],
            ),
            komponente(
                "pelletlager",
                "lager",
                "lager",
                [
                    *lager_auflagen(),
                    label("lager_vorrat", "Vorrat: ", "behaelter", 8, 50, schrift + 5),
                    label("lager_warngrenze", "Ab: " if kurz else "Warnung ab: ",
                          "gedaempft", 15, 50, schrift),
                    lager_reicht_bis(schrift, kurz),
                ],
            ),
            komponente(
                "solar",
                "solar",
                "solar",
                [
                    *aktiv_oder_ruhe("solar", "solar_leistung"),
                    label(
                                "solar_kollektortemperatur",
                                "Koll.: " if kurz else "Kollektor: ",
                                "kessel",
                                8,
                                50,
                                schrift,
                            ),
                    label(
                                "solar_leistung",
                                "Leistung: ",
                                "solar",
                                15,
                                50,
                                schrift - 5,
                            ),
                    label(
                                "solar_ertrag_heute",
                                "Heute: ",
                                "hell",
                                22,
                                50,
                                schrift - 5,
                            ),
                ],
            ),
            komponente(
                "pv_heizmodul",
                "pvm",
                "pvm",
                [
                    *aktiv_oder_ruhe("pvm", "pv_heizmodul_heizstab"),
                    label("pv_heizmodul_heizstab", "Stab: " if kurz else "Heizstab: ",
                          "solar", 8, 50, schrift),
                    label("pv_heizmodul_temperatur_oben", "Oben: ",
                          "kessel", 15, 50, schrift - 5),
                    label("pv_heizmodul_ertrag_heute", "Heute: ",
                          "hell", 22, 50, schrift - 5),
                ],
            ),
            komponente(
                "brenner",
                "brenner",
                "brenner",
                [
                    *bewegt_oder_still(
                        "brenner_aktiv",
                        BRENNER_ANFORDERUNG,
                        [{"condition": "state", "entity": BRENNER_ANFORDERUNG, "state": "Ein"}],
                    ),
                    label("brenner_anforderung", "Anf.: " if kurz else "Anforderung: ",
                          "hell", 8, 50, schrift),
                    label("brenner_temperatur", "Temp.: " if kurz else "Temperatur: ",
                          "kessel", 15, 50, schrift - 5),
                ],
            ),
            komponente(
                "fernleitung",
                "fernleitung",
                "fernleitung",
                [
                    *bewegt_oder_still(
                        "fernleitung_fluss",
                        FERNLEITUNG_PUMPE,
                        [{"condition": "state", "entity": FERNLEITUNG_PUMPE, "state": "Ein"}],
                    ),
                    label("fernleitung_pumpe", "Fernl.: " if kurz else "Fernleitung: ",
                          "hell", 8, 50, schrift),
                ],
            ),
        ],
    }


VARIANTEN = [
    ("(max-width: 767px)", 2, 90, True),
    ("(min-width: 768px) and (max-width: 1039px)", 3, 95, False),
    ("(min-width: 1040px)", 4, 100, False),
]
"""Drei Stufen entlang der Breakpoints von Home Assistant.

Je schmaler die Ansicht, desto weniger Spalten - sonst wird jede Kachel
so schmal, dass die Beschriftungen abgeschnitten werden. Auf dem Handy
sind zusätzlich die Beschriftungen gekürzt.
"""


MARKER = {
    "kessel": "komponente_kessel",
    "puffer": "komponente_pufferspeicher",
    "puffer2": "komponente_pufferspeicher_2",
    "puffer3": "komponente_pufferspeicher_3",
    "fwm": "komponente_fwm",
    "hk1": "komponente_heizkreis_1",
    "hk2": "komponente_heizkreis_2",
    "hk3": "komponente_heizkreis_3",
    "hk4": "komponente_heizkreis_4",
    "lager": "komponente_pelletlager",
    "solar": "komponente_solar",
    "pvm": "komponente_pv_heizmodul",
    "brenner": "komponente_brenner",
    "fernleitung": "komponente_fernleitung",
}
"""Welche Marker-Entität zu welcher Komponente gehört.

Die Schlüssel sind dieselben, die im Einrichtungsdialog angekreuzt werden.
"twin" fehlt absichtlich: Seine Werte stehen auf der Kessel-Kachel.
"""


def _passt_zur_anlage(kachel, behalten):
    """Sagt, ob eine Kachel zu den gewählten Komponenten gehört."""
    marker = kachel["conditions"][0]["entity"].split("eta_heizung_", 1)[1]
    return marker in behalten


_FUEHLER_ENTITAET = re.compile(r"sensor\.eta_heizung_puffer(_\d)?_fuhler_\d+")


def _ist_fuehlergruppe(element):
    """Erkennt einen der Blöcke, die je nach Fühlerzahl greifen."""
    return element.get("type") == "conditional" and all(
        _FUEHLER_ENTITAET.fullmatch(bedingung["entity"])
        for bedingung in element["conditions"]
    )


def _fuehler_ausduennen(kachel, anzahl):
    """Behält nur den Block für die tatsächliche Zahl der Pufferfühler.

    Danach entfällt auch die Bedingung "Fühler N+1 darf es nicht geben":
    Sie hält nur die Blöcke auseinander, und es bleibt ja nur einer. So
    nennt die Karte am Ende ausschließlich Entitäten, die es auf dieser
    Anlage wirklich gibt. Ohne bekannte Anzahl bleiben alle Blöcke.
    """
    if not anzahl:
        return
    behalten = []
    for element in kachel["card"]["elements"]:
        if not _ist_fuehlergruppe(element):
            behalten.append(element)
            continue
        if len(element["elements"]) != anzahl:
            continue
        element["conditions"] = [
            bedingung
            for bedingung in element["conditions"]
            if bedingung.get("state_not") == "unknown"
        ]
        behalten.append(element)
    kachel["card"]["elements"] = behalten


def _ist_puffername(element):
    """Erkennt die Elemente, die den Namen eines Puffers zeigen."""
    return element.get("type") == "conditional" and any(
        kind.get("attribute") == "funktionsblock" for kind in element.get("elements", [])
    )


def _puffernamen_zuschneiden(kachel, mehrere):
    """Zeigt den Namen fest, wenn es mehrere Puffer gibt, sonst gar nicht.

    Die Bedingungen der universellen Karte fragen Marker ab, die es auf
    dieser Anlage womöglich nicht gibt - die zugeschnittene Karte soll
    nur vorhandene Entitäten nennen.
    """
    behalten, gesetzt = [], False
    for element in kachel["card"]["elements"]:
        if not _ist_puffername(element):
            behalten.append(element)
        elif mehrere and not gesetzt:
            behalten.extend(element["elements"])
            gesetzt = True
    kachel["card"]["elements"] = behalten


def responsive_karte(komponenten=None, fuehler=None):
    """Die fertige Karte: alle drei Breiten übereinander, eine sichtbar.

    Ohne Angaben entsteht die universelle Karte, die jede Anlage abdeckt -
    die gehört ins Repo, weil sie ohne Nachfragen zu jedem passt.

    Wer seine Anlage kennt, kann sie zuschneiden: "komponenten" nimmt die
    Schlüssel aus MARKER, "fuehler" die tatsächliche Zahl der
    Pufferfühler - als Zahl für den ersten Puffer oder je Puffer, etwa
    {"puffer": 9, "puffer2": 3}. Das kürzt die Karte erheblich und lässt
    Werkzeuge wie Spook verstummen, die Entitäten bemängeln, die es auf
    dieser Anlage nicht gibt.
    """
    karte = {
        "type": "vertical-stack",
        "cards": [
            {
                "type": "conditional",
                "conditions": [{"condition": "screen", "media_query": abfrage}],
                "card": grid(spalten=spalten, schrift=schrift, kurz=kurz),
            }
            for abfrage, spalten, schrift, kurz in VARIANTEN
        ],
    }
    if komponenten is None and fuehler is None:
        return karte

    behalten = (
        {MARKER[k] for k in komponenten if k in MARKER}
        if komponenten
        else set(MARKER.values())
    )
    if not isinstance(fuehler, dict):
        fuehler = {"puffer": fuehler}
    je_marker = {
        f"sensor.eta_heizung_komponente_{marker}": fuehler.get(k)
        for k, (_, marker) in PUFFER_KACHELN.items()
    }
    puffer_marker = {_marker_entitaet(k) for k in PUFFER_KACHELN}
    mehrere = komponenten is not None and sum(k in PUFFER_KACHELN for k in komponenten) > 1
    for variante in karte["cards"]:
        gitter = variante["card"]
        gitter["cards"] = [k for k in gitter["cards"] if _passt_zur_anlage(k, behalten)]
        for kachel in gitter["cards"]:
            _fuehler_ausduennen(kachel, je_marker.get(kachel["conditions"][0]["entity"]))
            if komponenten is not None and kachel["conditions"][0]["entity"] in puffer_marker:
                _puffernamen_zuschneiden(kachel, mehrere)
    return karte
