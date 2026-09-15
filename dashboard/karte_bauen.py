"""Erzeugt eta-karte.yaml, die fertige Dashboard-Karte.

Die Karte enthält jede Komponente dreimal - einmal je
Bildschirmbreite. Von Hand wäre das nicht zu pflegen, deshalb wird sie
hier aus einer einzigen Beschreibung erzeugt. Nach Änderungen einfach
dieses Skript ausführen:

    python dashboard/karte_bauen.py
"""

import pathlib

import yaml

BILDPFAD = "/local/community/ha-eta-webservices"

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
    """Die Betriebsart als Text; ein Tippen öffnet die Auswahl."""
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
                    label("puffer_fuhler_1", None, "weiss", 36, 50, schrift + 10),
                    label("puffer_fuhler_2", None, "weiss", 62, 50, schrift + 10),
                    label("puffer_fuhler_3", None, "weiss", 88, 50, schrift + 10),
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
                    schalter("heizkreis_1", 92, 86),
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
                    schalter("heizkreis_2", 92, 86),
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
                    schalter("heizkreis_3", 92, 86),
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
                    schalter("heizkreis_4", 92, 86),
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


def responsive_karte():
    """Die fertige Karte: alle drei Breiten übereinander, eine sichtbar."""
    return {
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


if __name__ == "__main__":
    ziel = pathlib.Path(__file__).with_name("eta-karte.yaml")
    ziel.write_text(
        yaml.safe_dump(responsive_karte(), allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    print(f"{ziel.name} neu erzeugt")
