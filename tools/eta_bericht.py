"""Erstellt einen Bericht über deine ETA-Anlage.

Das Skript liest ausschließlich - es verändert keinen einzigen Wert an
der Heizung. Die einzige Ausnahme ist ein Variablensatz, den die Anlage
ohnehin nur im Arbeitsspeicher hält und der am Ende wieder entfernt
wird; er dient dazu, die Sammelabfrage zu prüfen.

Aufruf im eigenen Netz, ohne Zusatzpakete:

    python3 eta_bericht.py 10.0.0.173

Heraus kommt die Datei eta_bericht.txt. Sie enthält den Menübaum deiner
Anlage, die Beschreibung der schaltbaren Objekte und die der Zeitprogramme,
Warmwasser-Temperaturen und Zirkulation - genau das, was fehlt, um die
Integration an abweichende Anlagen anzupassen. Die IP-Adresse wird darin
geschwärzt.
"""

from __future__ import annotations

import sys
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET

NAMENSRAUM = "{http://www.eta.co.at/rest/v1}"
ET.register_namespace("", NAMENSRAUM.strip("{}"))
"""Ohne diese Zeile schreibt Python beim Einrücken überall ns0: davor."""
SCHALTER_NAMEN = (
    "ein/aus taste",
    "ein/aus-taste",
    "e/a taste",
    "ein/aus",
    "on/off button",
    "i/o key",
)
INTERESSANTE_NAMEN = (
    "zustand",
    "betriebsart",
    "anforderung",
    "taste",
    "freigabe",
    "schalter",
)


class Anlage:
    """Eine ETA-Heizung im Netz; jede Abfrage liest nur."""

    def __init__(self, host: str, port: int = 8080) -> None:
        self.basis = f"http://{host}:{port}"

    def hole(self, pfad: str, methode: str = "GET") -> str | None:
        """Ruft einen Pfad ab; Fehler kommen als Text zurück, statt zu werfen."""
        anfrage = urllib.request.Request(self.basis + pfad, method=methode)
        try:
            with urllib.request.urlopen(anfrage, timeout=15) as antwort:
                return antwort.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as fehler:
            return f"__HTTP {fehler.code}"
        except Exception as fehler:
            return f"__FEHLER {fehler}"


def ist_fehler(text: str | None) -> bool:
    """Erkennt die Fehlertexte, die hole() statt einer Antwort liefert."""
    return text is None or text.startswith("__")


def lesbar(text: str | None) -> str:
    """Bricht eine XML-Antwort zum Lesen auf mehrere Zeilen um."""
    if not text:
        return "keine Antwort"
    if ist_fehler(text):
        return text
    try:
        baum = ET.fromstring(text)
        ET.indent(baum, space="  ")
        return ET.tostring(baum, encoding="unicode")
    except ET.ParseError:
        return text


def objekte(knoten):
    """Läuft rekursiv durch alle object-Elemente unterhalb eines Knotens."""
    for kind in knoten.findall(f"{NAMENSRAUM}object"):
        yield kind
        yield from objekte(kind)


def mit_weg(knoten, weg=()):
    """Wie objekte, dazu der Weg im Menübaum als Liste von Namen."""
    for kind in knoten.findall(f"{NAMENSRAUM}object"):
        eigener = (*weg, (kind.get("name") or "").strip())
        yield eigener, kind
        yield from mit_weg(kind, eigener)


def kind_namens(knoten, name: str):
    """Das direkte Unterobjekt mit diesem Namen, oder None."""
    for kind in knoten.findall(f"{NAMENSRAUM}object"):
        if (kind.get("name") or "").strip().casefold() == name.casefold():
            return kind
    return None


WOCHENTAGE = ("Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag")
"""So heißen die Tage eines Zeitprogramms im Menübaum."""


def ist_zeitprogramm(knoten) -> bool:
    """Hat der Knoten je Wochentag ein "Zeitfenster 1"?"""
    for tag in WOCHENTAGE:
        tag_knoten = kind_namens(knoten, tag)
        if tag_knoten is None or kind_namens(tag_knoten, "Zeitfenster 1") is None:
            return False
    return True


TEMPERATUR_NAMEN = ("soll", "max", "min", "temperatur")
"""Warmwasser-Objekte mit diesen Namensteilen kommen samt Beschreibung in den Bericht."""


def hauptprogramm(host: str, port: int) -> None:
    """Sammelt den Bericht und schreibt ihn auch bei einem Abbruch."""
    zeilen: list[str] = []
    try:
        _sammeln(Anlage(host, port), zeilen)
    except KeyboardInterrupt:
        zeilen.append("\n(abgebrochen)")
    except Exception as fehler:
        zeilen.append(f"\n(Abbruch: {fehler!r})")
    _schreiben(zeilen, host)


def _sammeln(anlage: Anlage, zeilen: list[str]) -> None:
    """Fragt die Anlage Abschnitt für Abschnitt ab und protokolliert mit."""

    def sag(text: str = "") -> None:
        zeilen.append(text)
        try:
            print(text)
        except (BrokenPipeError, OSError):
            pass

    sag("ETA-Bericht")
    sag("=" * 60)

    version = anlage.hole("/user/api")
    sag(f"\n[1] Webservice-Version\n{lesbar(version)}")

    menu = anlage.hole("/user/menu")
    if ist_fehler(menu):
        sag(f"\nMenübaum nicht lesbar: {menu}")
        sag("Sind die Webservices aktiviert und der LAN-Zugriff beantragt?")
        return

    wurzel = ET.fromstring(menu)
    fubs = list(wurzel.iter(f"{NAMENSRAUM}fub"))
    sag(f"\n[2] Funktionsblöcke ({len(fubs)})")
    for fub in fubs:
        anzahl = len(list(objekte(fub)))
        sag(f"    {fub.get('name'):20s} {fub.get('uri'):18s} {anzahl} Objekte")

    sag("\n[3] Schaltbar aussehende Objekte")
    kandidaten: list[tuple[str, str, str]] = []
    for fub in fubs:
        for obj in objekte(fub):
            name = (obj.get("name") or "").strip()
            klein = name.casefold()
            if klein in SCHALTER_NAMEN or any(w in klein for w in INTERESSANTE_NAMEN):
                kandidaten.append((fub.get("name") or "", name, obj.get("uri") or ""))
    if not kandidaten:
        sag("    keine gefunden")
    for fub_name, name, uri in kandidaten:
        sag(f"    {fub_name:12s} {name:34s} {uri}")

    sag("\n[4] Beschreibung dieser Objekte (varinfo)")
    for fub_name, name, uri in kandidaten:
        info = anlage.hole(f"/user/varinfo{uri}")
        sag(f"\n--- {fub_name} > {name} ({uri})")
        sag(lesbar(info))

    sag("\n[5] Zeitprogramme, Warmwasser und Zirkulation (varinfo und Wert)")
    gezeigt: set[str] = set()

    def zeigen(titel: str, knoten) -> None:
        uri = knoten.get("uri") if knoten is not None else None
        if not uri or uri in gezeigt:
            return
        gezeigt.add(uri)
        sag(f"\n--- {titel} ({uri})")
        sag(lesbar(anlage.hole(f"/user/varinfo{uri}")))
        sag(lesbar(anlage.hole(f"/user/var{uri}")))

    for fub in fubs:
        fub_name = (fub.get("name") or "").strip()
        for weg, obj in mit_weg(fub):
            text = " > ".join((fub_name, *weg))
            klein = text.casefold()
            if ist_zeitprogramm(obj):
                montag = kind_namens(obj, "Montag")
                zeigen(f"{text} > Montag > Zeitfenster 1", kind_namens(montag, "Zeitfenster 1"))
                zeigen(
                    f"{text} > Montag > Wert außerhalb der Zeitfenster",
                    kind_namens(montag, "Wert außerhalb der Zeitfenster"),
                )
                zeigen(f"{text} > Temperatur", kind_namens(obj, "Temperatur"))
            elif any(tag.casefold() in klein for tag in WOCHENTAGE):
                continue
            elif "zirkulation" in klein:
                zeigen(text, obj)
            elif ("warmwasser" in klein or fub_name.casefold() in ("ww", "fwm")) and any(
                teil in weg[-1].casefold() for teil in TEMPERATUR_NAMEN
            ):
                zeigen(text, obj)
    if not gezeigt:
        sag("    keine gefunden")

    sag("\n[6] Aktive Störungen")
    sag(lesbar(anlage.hole("/user/errors")))

    sag("\n[7] Sammelabfrage über einen Variablensatz")
    name = "etabericht"
    anlage.hole(f"/user/vars/{name}", "DELETE")
    erstellt = anlage.hole(f"/user/vars/{name}", "PUT")
    if ist_fehler(erstellt):
        sag(f"    Variablensätze nicht unterstützt: {erstellt}")
    else:
        erste = next(
            (obj.get("uri") for fub in fubs for obj in objekte(fub) if obj.get("uri")),
            None,
        )
        if erste:
            anlage.hole(f"/user/vars/{name}{erste}", "PUT")
            sag(f"    Testvariable {erste}")
            sag(lesbar(anlage.hole(f"/user/vars/{name}")))
        anlage.hole(f"/user/vars/{name}", "DELETE")
        sag("    Variablensatz wieder entfernt")

    sag("\n[8] Vollständiger Menübaum")
    sag(lesbar(menu))


def _schreiben(zeilen: list[str], host: str) -> None:
    inhalt = "\n".join(zeilen).replace(host, "<IP-ADRESSE>")
    with open("eta_bericht.txt", "w", encoding="utf-8") as datei:
        datei.write(inhalt + "\n")
    print("\nGeschrieben nach eta_bericht.txt (IP-Adresse geschwärzt)")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit("Aufruf: python3 eta_bericht.py <IP-Adresse> [Port]")
    hauptprogramm(sys.argv[1], int(sys.argv[2]) if len(sys.argv) > 2 else 8080)
