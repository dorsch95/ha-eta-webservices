"""Erstellt einen Bericht über deine ETA-Anlage.

Das Skript liest ausschließlich - es verändert keinen einzigen Wert an
der Heizung. Die einzige Ausnahme ist ein Variablensatz, den die Anlage
ohnehin nur im Arbeitsspeicher hält und der am Ende wieder entfernt
wird; er dient dazu, die Sammelabfrage zu prüfen.

Aufruf im eigenen Netz, ohne Zusatzpakete:

    python3 eta_bericht.py 10.0.0.173

Heraus kommt die Datei eta_bericht.txt. Sie enthält den Menübaum deiner
Anlage und die Beschreibung der schaltbaren Objekte - genau das, was
fehlt, um die Integration an abweichende Anlagen anzupassen. Die
IP-Adresse wird darin geschwärzt.
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
    def __init__(self, host: str, port: int = 8080) -> None:
        self.basis = f"http://{host}:{port}"

    def hole(self, pfad: str, methode: str = "GET") -> str | None:
        anfrage = urllib.request.Request(self.basis + pfad, method=methode)
        try:
            with urllib.request.urlopen(anfrage, timeout=15) as antwort:
                return antwort.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as fehler:
            return f"__HTTP {fehler.code}"
        except Exception as fehler:
            return f"__FEHLER {fehler}"


def ist_fehler(text: str | None) -> bool:
    return text is None or text.startswith("__")


def lesbar(text: str | None) -> str:
    """Bricht eine XML-Antwort auf mehrere Zeilen um.

    Die Anlage antwortet in einer einzigen langen Zeile. Das ist auf
    dem Bildschirm unlesbar, deshalb wird eingerückt - schlägt das
    fehl, bleibt der Originaltext stehen.
    """
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


def hauptprogramm(host: str, port: int) -> None:
    """Sammelt den Bericht und schreibt ihn in jedem Fall.

    Alles, was bis zu einem Abbruch zusammengekommen ist, landet in der
    Datei - eine Anlage, die mittendrin nicht mehr antwortet, soll den
    halben Bericht nicht mitnehmen.
    """
    zeilen: list[str] = []
    try:
        _sammeln(Anlage(host, port), zeilen)
    except KeyboardInterrupt:
        zeilen.append("\n(abgebrochen)")
    except Exception as fehler:
        zeilen.append(f"\n(Abbruch: {fehler!r})")
    _schreiben(zeilen, host)


def _sammeln(anlage: Anlage, zeilen: list[str]) -> None:

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

    sag("\n[5] Aktive Störungen")
    sag(lesbar(anlage.hole("/user/errors")))

    sag("\n[6] Sammelabfrage über einen Variablensatz")
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

    sag("\n[7] Vollständiger Menübaum")
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
