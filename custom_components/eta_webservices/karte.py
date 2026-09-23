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

BILDPFAD = "/eta_webservices/grafiken"
"""Dort liefert die Integration die Kachelgrafiken aus, siehe URL_GRAFIKEN."""

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


def schalter(entity, top, left, groesse=30):
    """Ein antippbares Symbol, das den Schalter umlegt."""
    return nur_wenn_vorhanden(
        {
            "type": "state-icon",
            "entity": f"switch.eta_heizung_{entity}",
            "tap_action": {"action": "toggle"},
            "style": {
                "top": f"{top}%",
                "left": f"{left}%",
                "--mdc-icon-size": f"{groesse}px",
            },
        }
    )


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


PUFFER_OBEN = 36
PUFFER_UNTEN = 88
PUFFER_MIN = 3
PUFFER_MAX = 9


def puffer_fuehler(anzahl, schrift):
    """Zeigt genau dann N Fühler, wenn die Anlage N Fühler hat.

    Die Integration legt je gefundenem Fühler eine Entität an - wie viele
    das sind, weiß erst die laufende Anlage. Für jede mögliche Anzahl gibt
    es deshalb einen Block, der genau dann greift, wenn Fühler N vorhanden
    und Fühler N+1 nicht vorhanden ist. Home Assistant wertet eine
    fehlende Entität als "unknown".

    Die Fühler sitzen gleichmäßig verteilt zwischen Speicheroberkante und
    -unterkante, denn Fühler 1 misst oben und der letzte unten.
    """
    bedingungen = [
        {
            "condition": "state",
            "entity": f"sensor.eta_heizung_puffer_fuhler_{i}",
            "state_not": "unknown",
        }
        for i in range(1, anzahl + 1)
    ]
    if anzahl < PUFFER_MAX:
        bedingungen.append(
            {
                "condition": "state",
                "entity": f"sensor.eta_heizung_puffer_fuhler_{anzahl + 1}",
                "state": "unknown",
            }
        )

    abstand = (PUFFER_UNTEN - PUFFER_OBEN) / (anzahl - 1)
    return {
        "type": "conditional",
        "conditions": bedingungen,
        "elements": [
            label(
                f"puffer_fuhler_{i}",
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


def modus_tasten(entity, top, groesse=26):
    """Schaltet die Betriebsart direkt auf der Kachel um.

    Vier Symbole nebeneinander, jedes setzt beim Antippen seine
    Betriebsart. "Aus" ist eines davon - einen getrennten Ein/Aus-Schalter
    gibt es am Heizkreis deshalb nicht.
    """
    entitaet = f"select.eta_heizung_{entity}"
    return [
        nur_wenn_vorhanden(
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
                "style": {
                    "top": f"{top}%",
                    "left": f"{links}%",
                    "color": FARBEN["hell"],
                    "--mdc-icon-size": f"{groesse}px",
                },
            }
        )
        for (modus, symbol, titel), links in zip(MODUS_TASTEN, (20, 40, 60, 80))
    ]


def komponente(marker, zustand, bild, elemente):
    """Eine Kachel, die nur erscheint, wenn es die Komponente gibt."""
    return {
        "type": "conditional",
        "conditions": [
            {
                "condition": "state",
                "entity": f"sensor.eta_heizung_komponente_{marker}",
                "state": zustand,
            }
        ],
        "card": {
            "type": "picture-elements",
            "image": f"{BILDPFAD}/{bild}.png",
            "elements": elemente,
        },
    }


def grid(spalten, schrift, kurz):
    """Alle Kacheln nebeneinander, für eine der drei Bildschirmbreiten."""
    kessel = [
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
    kessel.append(schalter("kessel", 92, 86))
    return {
        "type": "grid",
        "columns": spalten,
        "square": False,
        "cards": [
            komponente("kessel", "kessel", "kessel", kessel),
            komponente(
                "pufferspeicher",
                "puffer",
                "puffer",
                [
                    label("puffer_ladezustand", "Ladung: " if kurz else "Ladezustand: ",
                          "hell", 8, 50, schrift + 5),
                    *(
                        puffer_fuehler(anzahl, puffer_schrift(anzahl, schrift))
                        for anzahl in range(PUFFER_MIN, PUFFER_MAX + 1)
                    ),
                ],
            ),
            komponente(
                "fwm",
                "fwm",
                "fwm",
                [
                    label("fwm_warmwassertemperatur", "WW: " if kurz else "Warmwasser: ",
                          "hell", 8, 50, schrift + 5),
                    label("fwm_zirkulationspumpe",
                          "Zirk.: " if kurz else "Zirkulationspumpe: ",
                          "gedaempft", 15, 50, schrift),
                ],
            ),
            komponente(
                "heizkreis_1",
                "hk1",
                "heizkreis",
                [
                    label("heizkreis_vorlauftemperatur", "HK1: " if kurz else "Vorlauf HK1: ",
                          "kessel", 8, 50, schrift),
                    label("heizkreis_anforderung", None, "hell", 15, 50, schrift - 5),
                    betriebsart("heizkreis_1_betriebsart", 23, schrift - 5),
                    *modus_tasten("heizkreis_1_betriebsart", 90),
                ],
            ),
            komponente(
                "heizkreis_2",
                "hk2",
                "heizkreis",
                [
                    label("heizkreis_2_vorlauftemperatur", "HK2: " if kurz else "Vorlauf HK2: ",
                          "kessel", 8, 50, schrift),
                    label("heizkreis_2_anforderung", None, "hell", 15, 50, schrift - 5),
                    betriebsart("heizkreis_2_betriebsart", 23, schrift - 5),
                    *modus_tasten("heizkreis_2_betriebsart", 90),
                ],
            ),
            komponente(
                "heizkreis_3",
                "hk3",
                "heizkreis",
                [
                    label("heizkreis_3_vorlauftemperatur", "HK3: " if kurz else "Vorlauf HK3: ",
                          "kessel", 8, 50, schrift),
                    label("heizkreis_3_anforderung", None, "hell", 15, 50, schrift - 5),
                    betriebsart("heizkreis_3_betriebsart", 23, schrift - 5),
                    *modus_tasten("heizkreis_3_betriebsart", 90),
                ],
            ),
            komponente(
                "heizkreis_4",
                "hk4",
                "heizkreis",
                [
                    label("heizkreis_4_vorlauftemperatur", "HK4: " if kurz else "Vorlauf HK4: ",
                          "kessel", 8, 50, schrift),
                    label("heizkreis_4_anforderung", None, "hell", 15, 50, schrift - 5),
                    betriebsart("heizkreis_4_betriebsart", 23, schrift - 5),
                    *modus_tasten("heizkreis_4_betriebsart", 90),
                ],
            ),
            komponente(
                "pelletlager",
                "lager",
                "lager",
                [
                    label("lager_vorrat", "Vorrat: ", "behaelter", 8, 50, schrift + 5),
                    label("lager_warngrenze", "Ab: " if kurz else "Warnung ab: ",
                          "gedaempft", 15, 50, schrift),
                ],
            ),
            komponente(
                "solar",
                "solar",
                "solar",
                [
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
    "fwm": "komponente_fwm",
    "hk1": "komponente_heizkreis_1",
    "hk2": "komponente_heizkreis_2",
    "hk3": "komponente_heizkreis_3",
    "hk4": "komponente_heizkreis_4",
    "lager": "komponente_pelletlager",
    "solar": "komponente_solar",
}
"""Welche Marker-Entität zu welcher Komponente gehört.

Die Schlüssel sind dieselben, die im Einrichtungsdialog angekreuzt werden.
"twin" fehlt absichtlich: Seine Werte stehen auf der Kessel-Kachel.
"""


def _passt_zur_anlage(kachel, behalten):
    """Sagt, ob eine Kachel zu den gewählten Komponenten gehört."""
    marker = kachel["conditions"][0]["entity"].split("eta_heizung_", 1)[1]
    return marker in behalten


def _ist_fuehlergruppe(element):
    """Erkennt einen der Blöcke, die je nach Fühlerzahl greifen."""
    return element.get("type") == "conditional" and all(
        "puffer_fuhler" in bedingung["entity"] for bedingung in element["conditions"]
    )


def _fuehler_ausduennen(kachel, anzahl):
    """Behält nur den Block für die tatsächliche Zahl der Pufferfühler.

    Danach entfällt auch die Bedingung "Fühler N+1 darf es nicht geben":
    Sie hält nur die Blöcke auseinander, und es bleibt ja nur einer. So
    nennt die Karte am Ende ausschließlich Entitäten, die es auf dieser
    Anlage wirklich gibt.
    """
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


def responsive_karte(komponenten=None, fuehler=None):
    """Die fertige Karte: alle drei Breiten übereinander, eine sichtbar.

    Ohne Angaben entsteht die universelle Karte, die jede Anlage abdeckt -
    die gehört ins Repo, weil sie ohne Nachfragen zu jedem passt.

    Wer seine Anlage kennt, kann sie zuschneiden: "komponenten" nimmt die
    Schlüssel aus MARKER, "fuehler" die tatsächliche Zahl der
    Pufferfühler. Das kürzt die Karte erheblich und lässt Werkzeuge wie
    Spook verstummen, die Entitäten bemängeln, die es auf dieser Anlage
    nicht gibt.
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
    for variante in karte["cards"]:
        gitter = variante["card"]
        gitter["cards"] = [k for k in gitter["cards"] if _passt_zur_anlage(k, behalten)]
        if fuehler:
            for kachel in gitter["cards"]:
                _fuehler_ausduennen(kachel, fuehler)
    return karte
