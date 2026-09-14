"""Erzeugt eta-karte.yaml, die fertige Dashboard-Karte.

Die Karte enthält dieselben fünf Komponenten dreimal - einmal je
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
    """Eine Beschriftungszeile der Kachel.

    Jede Entität einer angekreuzten Komponente existiert immer, auch
    wenn der Menübaum den Wert nicht hergibt - dann steht dort "-".
    Deshalb braucht die Zeile keine Bedingung.
    """
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


def komponente(marker, zustand, bild, elemente):
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
                    label("fwm_zirkulation", "Zirk.: " if kurz else "Zirkulation: ",
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
