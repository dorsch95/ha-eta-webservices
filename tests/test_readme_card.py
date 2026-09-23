"""Prüft die Dashboard-Vorlage im README gegen die echte Integration.

Die Karte im README ist Teil des Produkts: Wenn sie Entitäten oder
Elementtypen nennt, die es nicht gibt, bekommt der Nutzer im Dashboard
einen Konfigurationsfehler. Deshalb wird sie hier gegen die tatsächlich
erzeugten Entitäten und gegen die gültigen picture-elements-Typen geprüft.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

from eta_webservices.const import COMPONENTS

WURZEL = Path(__file__).resolve().parents[1]
README = WURZEL / "README.md"
KARTE = WURZEL / "dashboard" / "eta-karte.yaml"

GUELTIGE_ELEMENTTYPEN = {
    "conditional",
    "icon",
    "image",
    "service-button",
    "action-button",
    "state-badge",
    "state-icon",
    "state-label",
}


def yaml_bloecke():
    text = README.read_text(encoding="utf-8")
    return [yaml.safe_load(b) for b in re.findall(r"```yaml\n(.*?)```", text, re.DOTALL)]


@pytest.fixture(scope="module")
def karte():
    return yaml.safe_load(KARTE.read_text(encoding="utf-8"))


def varianten(karte):
    """Die drei Bildschirm-Varianten der Karte."""
    return karte["cards"]


def raster(karte):
    return [variante["card"] for variante in varianten(karte)]


def abgesichert(karte):
    """Entitäten, die in einer eigenen Bedingung stecken und fehlen dürfen."""
    return {
        innen["entity"]
        for element in alle_elemente(karte)
        if element["type"] == "conditional"
        for innen in element["elements"]
    }


def alle_elemente(karte):
    """Alle Elemente der Karte, auch die in Bedingungen verschachtelten.

    Ohne den Abstieg in "conditional" blieben Schalter und Betriebsart
    ungeprüft.
    """

    def absteigen(elemente):
        for element in elemente:
            yield element
            yield from absteigen(element.get("elements", []))

    for gitter in raster(karte):
        for unterkarte in gitter["cards"]:
            yield from absteigen(unterkarte["card"]["elements"])


def test_alle_yaml_bloecke_im_readme_sind_gueltig():
    assert yaml_bloecke()


def test_karte_hat_drei_bildschirm_varianten(karte):
    assert karte["type"] == "vertical-stack"
    abfragen = [v["conditions"][0]["media_query"] for v in varianten(karte)]
    assert len(abfragen) == 3
    for variante in varianten(karte):
        assert variante["conditions"][0]["condition"] == "screen"


def test_varianten_decken_jede_breite_genau_einmal_ab(karte):
    """Ohne Lücke und ohne Überlappung - sonst ist die Karte leer oder doppelt."""
    import re as regex

    grenzen = []
    for variante in varianten(karte):
        abfrage = variante["conditions"][0]["media_query"]
        minimum = regex.search(r"min-width:\s*(\d+)px", abfrage)
        maximum = regex.search(r"max-width:\s*(\d+)px", abfrage)
        grenzen.append(
            (int(minimum.group(1)) if minimum else 0,
             int(maximum.group(1)) if maximum else 10000)
        )
    grenzen.sort()
    assert grenzen[0][0] == 0
    for (_, bis), (ab, _) in zip(grenzen, grenzen[1:]):
        assert ab == bis + 1, f"Lücke oder Überlappung bei {bis}/{ab}"


MIT_KACHEL = [key for key, info in COMPONENTS.items() if info["image"]]
"""Komponenten mit eigener Kachel - "twin" steht auf der Kessel-Kachel."""


def test_je_variante_und_komponente_genau_eine_karte(karte):
    for gitter in raster(karte):
        marker = [u["conditions"][0]["state"] for u in gitter["cards"]]
        assert marker == MIT_KACHEL


def test_karten_verweisen_auf_die_richtige_grafik(karte):
    for gitter in raster(karte):
        for komponente, unterkarte in zip(MIT_KACHEL, gitter["cards"]):
            erwartet = f"{COMPONENTS[komponente]['image']}.png"
            assert unterkarte["card"]["image"].endswith(erwartet)


def test_nur_gueltige_elementtypen(karte):
    for element in alle_elemente(karte):
        assert element["type"] in GUELTIGE_ELEMENTTYPEN


def test_schmale_varianten_haben_weniger_spalten(karte):
    """Je schmaler die Ansicht, desto weniger Spalten - sonst wird geschnitten."""
    import re as regex

    paare = []
    for gitter, variante in zip(raster(karte), varianten(karte)):
        abfrage = variante["conditions"][0]["media_query"]
        minimum = regex.search(r"min-width:\s*(\d+)px", abfrage)
        paare.append((int(minimum.group(1)) if minimum else 0, gitter["columns"]))
    paare.sort()
    spalten = [s for _, s in paare]
    assert spalten == sorted(spalten), f"Spaltenzahl nicht aufsteigend: {paare}"


def test_readme_verweist_auf_die_kartendatei():
    text = README.read_text(encoding="utf-8")
    assert "dashboard/eta-karte.yaml" in text
    assert "Panel" in text


async def test_jede_referenzierte_entitaet_existiert(hass, entry, karte):
    import json

    from homeassistant.util import slugify

    from .conftest import UEBERSETZUNGEN

    from .test_sensors import setup_integration

    from eta_webservices import select as select_platform
    from eta_webservices import switch as switch_platform

    entry.data["components"] = list(COMPONENTS)
    entry.data["enable_switches"] = True
    _, by_name = await setup_integration(hass, entry)
    vorhanden = {f"sensor.{slugify('ETA Heizung ' + name)}" for name in by_name}

    for bereich, platform in (("switch", switch_platform), ("select", select_platform)):
        gesammelt: list = []
        await platform.async_setup_entry(hass, entry, gesammelt.extend)
        namen = json.loads(
            (UEBERSETZUNGEN / "de.json").read_text(encoding="utf-8")
        )["entity"][bereich]
        vorhanden |= {
            f"{bereich}.{slugify('ETA Heizung ' + namen[e.translation_key]['name'])}"
            for e in gesammelt
        }

    referenziert = {
        unterkarte["conditions"][0]["entity"]
        for gitter in raster(karte)
        for unterkarte in gitter["cards"]
    } | {
        element["entity"]
        for element in alle_elemente(karte)
        if "entity" in element and element["type"] != "conditional"
    }

    fehlend = sorted(referenziert - vorhanden - abgesichert(karte))
    assert not fehlend, f"README verweist auf nicht existierende Entitäten: {fehlend}"


def test_nicht_immer_vorhandene_elemente_sind_abgesichert(karte):
    """Wer eine Entität nennt, die fehlen kann, muss sie absichern.

    Schalter, Betriebsart und die Pufferfühler ab dem vierten entstehen
    nicht auf jeder Anlage. Jede Entität, die in einer Bedingung genannt
    wird, muss deshalb durch eine Bedingung derselben Gruppe als
    vorhanden verbürgt sein - "state_not: unknown", denn Home Assistant
    wertet eine fehlende Entität als "unknown".
    """
    for element in alle_elemente(karte):
        if element["type"] != "conditional":
            continue

        verbuergt = {
            bedingung["entity"]
            for bedingung in element["conditions"]
            if bedingung.get("state_not") == "unknown"
        }
        assert verbuergt, element["conditions"]

        for innen in element["elements"]:
            assert innen["entity"] in verbuergt, innen


def test_puffer_zeigt_fuer_jede_fuehleranzahl_genau_eine_gruppe(karte):
    """Bei fünf Fühlern müssen fünf erscheinen, nicht die obersten drei.

    Die Blöcke schließen sich gegenseitig aus: Der Block für N verlangt,
    dass Fühler N vorhanden und Fühler N+1 nicht vorhanden ist. Ohne
    diesen zweiten Teil griffen bei fünf Fühlern auch die Blöcke für drei
    und vier, und die Beschriftungen lägen übereinander.
    """
    from eta_webservices.karte import PUFFER_MAX, PUFFER_MIN

    gruppen = [
        element
        for element in alle_elemente(karte)
        if element["type"] == "conditional"
        and all(
            "puffer_fuhler" in b["entity"] for b in element["conditions"]
        )
    ]
    varianten = PUFFER_MAX - PUFFER_MIN + 1
    assert len(gruppen) == varianten * 3, "je Bildschirmbreite eine Gruppe je Anzahl"

    for anzahl in range(PUFFER_MIN, PUFFER_MAX + 1):
        passend = [g for g in gruppen if len(g["elements"]) == anzahl]
        assert len(passend) == 3, anzahl
        gruppe = passend[0]

        vorhanden = [
            b["entity"] for b in gruppe["conditions"] if b.get("state_not") == "unknown"
        ]
        fehlend = [b["entity"] for b in gruppe["conditions"] if b.get("state") == "unknown"]

        assert len(vorhanden) == anzahl
        assert vorhanden[-1].endswith(f"_{anzahl}")
        if anzahl < PUFFER_MAX:
            assert fehlend == [f"sensor.eta_heizung_puffer_fuhler_{anzahl + 1}"]
        else:
            assert fehlend == []


def test_puffer_fuehler_sitzen_gleichmaessig_im_speicher(karte):
    """Fühler 1 misst oben, der letzte unten - das muss das Bild zeigen."""
    from eta_webservices.karte import PUFFER_MAX, PUFFER_MIN, PUFFER_OBEN, PUFFER_UNTEN

    for element in alle_elemente(karte):
        if element["type"] != "conditional":
            continue
        if not all("puffer_fuhler" in b["entity"] for b in element["conditions"]):
            continue

        hoehen = [float(e["style"]["top"].rstrip("%")) for e in element["elements"]]
        assert hoehen[0] == PUFFER_OBEN
        assert hoehen[-1] == PUFFER_UNTEN
        assert hoehen == sorted(hoehen), "Fühler müssen von oben nach unten laufen"

        if len(hoehen) > 2:
            abstaende = [b - a for a, b in zip(hoehen, hoehen[1:])]
            assert max(abstaende) - min(abstaende) < 0.3, abstaende

    assert PUFFER_MIN < PUFFER_MAX


ABSICHTLICHE_BEISPIELE = {
    "sensor.eta_heizung_boiler_temperature",
}
"""Erwähnungen, die absichtlich keiner echten Entität entsprechen.

Hier steht nur das englische Beispiel aus dem Sprachhinweis. Namen, die
auf einen Unterstrich enden, sind im Fließtext als Präfix gemeint
(z.B. "sensor.eta_heizung_puffer_fuhler_") und werden ohnehin übergangen.
"""


def readme_text() -> str:
    return README.read_text(encoding="utf-8")


def test_jede_genannte_entitaet_kann_entstehen():
    """Jede Entitäts-Erwähnung im README muss einer echten Entität entsprechen.

    Betrifft auch den Fließtext, nicht nur die Karte - ein Tippfehler in
    einer Anleitung kostet den Nutzer genauso viel Zeit wie einer im YAML.
    """
    import json
    import re

    from homeassistant.util import slugify

    from .conftest import UEBERSETZUNGEN

    entitaeten = json.loads(
        (UEBERSETZUNGEN / "de.json").read_text(encoding="utf-8")
    )["entity"]
    moeglich = {
        f"{bereich}.{slugify('ETA Heizung ' + eintrag['name'])}"
        for bereich, namen in entitaeten.items()
        for eintrag in namen.values()
    }
    genannt = set(
        re.findall(
            r"\b(?:binary_sensor|sensor|switch|select)\.eta_heizung_[a-z0-9_]+",
            readme_text() + KARTE.read_text(encoding="utf-8"),
        )
    )

    genannt = {name for name in genannt if not name.endswith("_")}
    unbekannt = sorted(
        genannt - (moeglich - nur_intern(entitaeten)) - ABSICHTLICHE_BEISPIELE
    )
    assert not unbekannt, f"README nennt Entitäten, die nicht entstehen: {unbekannt}"


def test_jede_komponente_ist_beschrieben():
    text = readme_text()
    for key, info in COMPONENTS.items():
        assert info["name"] in text or key in text, key


def test_genannte_grenzwerte_stimmen_mit_dem_code_ueberein():
    """Zahlen im Fließtext veralten still - hier fallen sie auf."""
    import json
    from pathlib import Path

    from eta_webservices.const import (
        DEFAULT_PELLET_KWH_PER_KG,
        DEFAULT_SCAN_INTERVAL,
        MAX_SCAN_INTERVAL,
        MIN_SCAN_INTERVAL,
        PUFFER_FUEHLER_MAX,
    )

    text = readme_text()
    hacs = json.loads(
        (Path(__file__).resolve().parents[1] / "hacs.json").read_text(encoding="utf-8")
    )

    erwartet = {
        f"{DEFAULT_SCAN_INTERVAL} Sekunden": "Standard-Abfrageintervall",
        f"{MIN_SCAN_INTERVAL} bis {MAX_SCAN_INTERVAL}": "Intervallgrenzen",
        str(DEFAULT_PELLET_KWH_PER_KG).replace(".", ","): "Standard-Heizwert",
        f"3 bis {PUFFER_FUEHLER_MAX}": "Pufferfühler-Spanne",
        hacs["homeassistant"].rsplit(".", 1)[0]: "Mindestversion von Home Assistant",
    }
    for wert, label in erwartet.items():
        assert wert in text, f"{label}: '{wert}' fehlt im README"


def test_genannte_bilder_werden_ausgeliefert():
    """Jede Grafik, auf die Karte oder README zeigen, liegt der Integration bei."""
    import re

    from eta_webservices import GRAFIKEN
    from eta_webservices.const import URL_GRAFIKEN

    text = readme_text() + KARTE.read_text(encoding="utf-8")
    bilder = set(re.findall(rf"{re.escape(URL_GRAFIKEN)}/([a-z0-9_]+\.png)", text))
    assert bilder, "keine Bildverweise gefunden"
    for bild in bilder:
        assert (GRAFIKEN / bild).is_file(), bild
    assert "/local/community/" not in KARTE.read_text(encoding="utf-8")


def test_jede_komponente_hat_ihre_kachel():
    """Je Komponente eine Kachel im Format 255x501, so wie die Karte sie setzt."""
    import struct

    from eta_webservices import GRAFIKEN

    for key in MIT_KACHEL:
        info = COMPONENTS[key]
        daten = (GRAFIKEN / f"{info['image']}.png").read_bytes()
        assert daten.startswith(b"\x89PNG\r\n\x1a\n"), info["image"]
        assert struct.unpack(">II", daten[16:24]) == (255, 501), info["image"]


def test_karte_kennt_die_bildadresse():
    from eta_webservices.const import URL_GRAFIKEN
    from eta_webservices.karte import BILDPFAD

    assert BILDPFAD == URL_GRAFIKEN


def test_kartendatei_ist_aktuell():
    """Die Karte muss zu ihrem Erzeugungsskript passen.

    Sonst laufen eine von Hand geänderte Karte und das Skript auseinander,
    und der nächste Lauf des Skripts wirft die Änderung weg.
    """
    import subprocess
    import sys

    vorher = KARTE.read_text(encoding="utf-8")
    subprocess.run(
        [sys.executable, str(WURZEL / "dashboard" / "karte_bauen.py")],
        check=True,
        capture_output=True,
    )
    nachher = KARTE.read_text(encoding="utf-8")
    assert vorher == nachher, (
        "eta-karte.yaml weicht von karte_bauen.py ab - "
        "Skript ausführen oder Änderung dort nachziehen"
    )


def test_fub_standardnamen_stehen_in_der_tabelle():
    from eta_webservices.const import FUB_ROLE_DEFAULT_NAMES

    text = readme_text()
    for rolle, namen in FUB_ROLE_DEFAULT_NAMES.items():
        assert any(f"`{name}`" in text for name in namen), rolle


def nur_intern(entitaeten: dict) -> set[str]:
    """Entitäten, die zwar einen Namen haben, aber nie entstehen.

    Die Ein/Aus-Tasten der Heizkreise werden gesucht und geprüft, weil die
    Betriebsart-Auswahl sie zum Schalten auf "Aus" braucht. Eine eigene
    Entität ergeben sie nicht - deshalb darf das README sie auch nicht
    nennen.
    """
    from homeassistant.util import slugify

    from eta_webservices.const import SWITCHES

    return {
        f"switch.{slugify('ETA Heizung ' + entitaeten['switch'][info['translation_key']]['name'])}"
        for info in SWITCHES.values()
        if info.get("nur_fuer_auswahl")
    }


def entitaetstabelle() -> list[str]:
    """Die Zeilen, die die Entitätsübersicht im README enthalten muss."""
    import json

    from homeassistant.util import slugify

    from eta_webservices.const import SELECTS, SENSORS, SWITCHES

    from .conftest import UEBERSETZUNGEN

    namen = json.loads(
        (UEBERSETZUNGEN / "de.json").read_text(encoding="utf-8")
    )["entity"]

    def zeile(bereich, key, einheit):
        name = namen[bereich][key]["name"]
        eid = f"{bereich}.{slugify('ETA Heizung ' + name)}"
        return f"| `{eid}` | {name} | {einheit} |"

    zeilen = [
        zeile(
            "sensor",
            info["translation_key"],
            info.get("default_unit") or ("Text" if info.get("is_string") else "–"),
        )
        for info in SENSORS.values()
    ]
    zeilen += [
        zeile("switch", i["translation_key"], "Schalter")
        for i in SWITCHES.values()
        if not i.get("nur_fuer_auswahl")
    ]
    zeilen += [zeile("select", i["translation_key"], "Auswahl") for i in SELECTS.values()]
    return zeilen


def test_entitaetsuebersicht_ist_vollstaendig():
    """Jede Entität muss in der Übersicht des README stehen.

    Sonst beschreibt die Anleitung eine Integration, die es so nicht
    mehr gibt.
    """
    text = readme_text()
    fehlend = [zeile for zeile in entitaetstabelle() if zeile not in text]
    assert not fehlend, f"Nicht in der README-Übersicht: {fehlend}"


def test_name_ist_ueberall_derselbe():
    """manifest.json, hacs.json und README müssen denselben Namen nennen.

    Der Name steht an drei Stellen und wird an einer vierten - im README -
    dem Nutzer als Suchbegriff und als Menüpfad genannt. Läuft das
    auseinander, sucht er in HACS nach etwas, das dort anders heißt.
    """
    import json
    from pathlib import Path

    wurzel = Path(__file__).resolve().parents[1]
    manifest = json.loads(
        (wurzel / "custom_components" / "eta_webservices" / "manifest.json").read_text(
            encoding="utf-8"
        )
    )
    hacs = json.loads((wurzel / "hacs.json").read_text(encoding="utf-8"))

    name = manifest["name"]
    assert hacs["name"] == name, "hacs.json nennt einen anderen Namen"

    text = readme_text()
    assert text.splitlines()[0].startswith(f"# {name}"), "README-Titel weicht ab"
    assert f"nach **{name}** suchen" in text, "README nennt einen anderen Suchbegriff"


def test_domain_und_geraetename_sind_unveraendert():
    """Beide stecken in bestehenden Installationen und dürfen nicht wandern.

    Die Domain steht in jedem Config Entry und in jeder unique_id, der
    Gerätename bestimmt die Entity-IDs (sensor.eta_heizung_...). Eine
    Umbenennung hier nimmt allen Nutzern ihre Historie, ihre Dashboards
    und ihre Automatisierungen.
    """
    import json
    from pathlib import Path

    from eta_webservices.const import DOMAIN

    wurzel = Path(__file__).resolve().parents[1]
    manifest = json.loads(
        (wurzel / "custom_components" / "eta_webservices" / "manifest.json").read_text(
            encoding="utf-8"
        )
    )

    assert DOMAIN == "eta_webservices"
    assert manifest["domain"] == "eta_webservices"

    koordinator = (
        wurzel / "custom_components" / "eta_webservices" / "coordinator.py"
    ).read_text(encoding="utf-8")
    assert 'name="ETA Heizung",' in koordinator


def zugeschnitten(komponenten, fuehler):
    """Erzeugt eine auf eine konkrete Anlage zugeschnittene Karte."""
    from eta_webservices.karte import responsive_karte

    return responsive_karte(komponenten, fuehler)


def genannte_entitaeten(karte) -> set[str]:
    """Alle Entitäten, die eine Karte überhaupt erwähnt - auch in Bedingungen."""
    import re

    import yaml

    text = yaml.safe_dump(karte, allow_unicode=True, sort_keys=False)
    return set(
        re.findall(r"\b(?:sensor|select|switch|binary_sensor)\.eta_heizung_[a-z0-9_]+", text)
    )


def test_zuschnitt_laesst_fremde_komponenten_weg():
    """Wer keinen zweiten Heizkreis hat, soll ihn auch nicht im YAML stehen haben.

    Werkzeuge wie Spook lesen die Karte nach Entitäten ab und werten die
    Bedingungen nicht aus. Sie melden deshalb jede Entität, die es auf
    dieser Anlage nicht gibt - auch wenn sie sauber abgesichert ist.
    """
    karte = zugeschnitten(["kessel", "puffer", "fwm", "hk1", "lager", "solar"], 5)
    genannt = genannte_entitaeten(karte)

    assert not [e for e in genannt if "heizkreis_2" in e or "heizkreis_3" in e]
    assert "sensor.eta_heizung_heizkreis_vorlauftemperatur" in genannt
    assert "sensor.eta_heizung_solar_kollektortemperatur" in genannt


def test_zuschnitt_nennt_nur_die_vorhandenen_pufferfuehler():
    """Auch die Bedingung "Fühler N+1 fehlt" muss verschwinden.

    Sie hält nur die Blöcke für verschiedene Fühlerzahlen auseinander.
    Bleibt nur einer übrig, nennt sie sonst eine Entität, die es auf
    dieser Anlage gerade nicht gibt.
    """
    genannt = genannte_entitaeten(zugeschnitten(["kessel", "puffer"], 5))
    fuehler = sorted(int(e.rsplit("_", 1)[1]) for e in genannt if "puffer_fuhler" in e)

    assert fuehler == [1, 2, 3, 4, 5]


def test_zuschnitt_behaelt_alle_drei_bildschirmbreiten():
    karte = zugeschnitten(["kessel", "puffer"], 3)
    assert len(karte["cards"]) == 3
    for variante in karte["cards"]:
        assert variante["conditions"][0]["condition"] == "screen"
        assert len(variante["card"]["cards"]) == 2


def test_ohne_angaben_entsteht_die_universelle_karte():
    """Die Karte im Repo muss zu jeder Anlage passen, ohne Nachfragen."""
    from eta_webservices.karte import responsive_karte

    import yaml

    erzeugt = yaml.safe_dump(responsive_karte(), allow_unicode=True, sort_keys=False)
    assert erzeugt == KARTE.read_text(encoding="utf-8")


def test_twin_bringt_keine_eigene_kachel():
    """Die Pelletwerte des SH TWIN stehen auf der Kessel-Kachel."""
    mit_twin = zugeschnitten(["kessel", "twin", "puffer"], 5)
    ohne_twin = zugeschnitten(["kessel", "puffer"], 5)
    assert mit_twin == ohne_twin


def test_geltende_betriebsart_leuchtet(karte):
    """Je Betriebsart genau ein leuchtendes und ein helles Symbol.

    Die beiden schließen sich aus: leuchtend nur bei genau dieser
    Betriebsart, hell bei jeder anderen.
    """
    from eta_webservices.karte import AKTIV, MODUS_TASTEN

    gruppen = [
        element
        for element in alle_elemente(karte)
        if element["type"] == "conditional"
        and element["elements"][0].get("tap_action", {}).get("perform_action")
        == "select.select_option"
    ]
    for modus, _, _ in MODUS_TASTEN:
        je_modus = [
            g for g in gruppen if g["elements"][0]["tap_action"]["data"]["option"] == modus
        ]
        leuchtend = [g for g in je_modus if any(b.get("state") == modus for b in g["conditions"])]
        hell = [g for g in je_modus if any(b.get("state_not") == modus for b in g["conditions"])]
        assert leuchtend and hell and len(leuchtend) == len(hell), modus
        for gruppe in leuchtend:
            assert gruppe["elements"][0]["style"]["color"] == AKTIV
        for gruppe in hell:
            assert gruppe["elements"][0]["style"]["color"] != AKTIV


ALLE_KESSEL_ZUSTAENDE = [
    "Ausgeschaltet", "Klappe Öffnen", "Pelletsbehälter auffüllen",
    "Füllen gestoppt wegen Zündung", "Heizversuch", "Zünden", "Heizen",
    "Glutabbrand", "Glutabbrand wegen Entaschung", "Glutabbrand da ausgeschaltet",
    "Glutabbrand weil Aschebox fehlt", "Füllen gestoppt wegen Entaschung", "Bereit",
    "Aschebox fehlt", "Entaschen", "Störung beim Entaschen", "Störung",
    "Glutabbrand wegen Störung", "Glutabbrand wegen Verriegelung", "Verriegelt",
    "Lambdasonde kalibrieren", "Heizen Start", "Vorwärmen", "Stoker leeren", "Füllen",
    "Isoliertür geöffnet", "Anheizen", "Verzögerungszeit abwarten", "Übertemperatur",
    "Pellet Betrieb", "Vorbereitung", "Heizen, Vorbereitung auf Messung",
    "Heizen, Teillastmessung durchführen", "Heizen, Nennlastmessung durchführen",
    "Vorbereiten auf Entaschung", "Durchlüften", "Wartung", "Ausbrand",
    "Umschaltung auf Stückholzbetrieb",
]
"""Alle Texte, die ein Pelletkessel für "Kessel-Zustand detailliert" meldet (varinfo)."""


def test_jeder_kessel_zustand_hat_genau_ein_bild():
    from eta_webservices.karte import KESSEL_AUS, KESSEL_FLAMME, KESSEL_GLUT

    listen = KESSEL_FLAMME + KESSEL_GLUT + KESSEL_AUS
    assert len(listen) == len(set(listen)), "Zustand doppelt zugeordnet"
    assert set(listen) == set(ALLE_KESSEL_ZUSTAENDE)


def test_kessel_zustandsbilder_gibt_es_und_sie_bewegen_sich():
    from PIL import Image

    from eta_webservices import GRAFIKEN
    from eta_webservices.karte import kessel_zustandsbilder

    dateien = {pfad.rsplit("/", 1)[1] for pfad in kessel_zustandsbilder().values()}
    assert dateien == {"kessel_flamme.webp", "kessel_glut.webp", "kessel_aus.png"}
    for datei in dateien:
        with Image.open(GRAFIKEN / datei) as bild:
            assert bild.size == (255, 501), datei
            if datei.endswith(".webp"):
                assert bild.n_frames > 1, datei


def test_kessel_kachel_wechselt_mit_dem_zustand(karte):
    for gitter in raster(karte):
        kessel = gitter["cards"][0]["card"]
        assert kessel["entity"] == "sensor.eta_heizung_kessel_zustand"
        assert kessel["image"].endswith("/kessel.png")
        assert kessel["state_image"]["Heizen"].endswith("/kessel_flamme.webp")
        assert kessel["state_image"]["Glutabbrand"].endswith("/kessel_glut.webp")
        assert kessel["state_image"]["Bereit"].endswith("/kessel_aus.png")
