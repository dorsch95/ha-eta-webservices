"""Erzeugt eta-karte.yaml, die universelle Dashboard-Karte fürs Repo.

Die eigentliche Karte baut custom_components/eta_webservices/karte.py.
Nach Änderungen dort einfach dieses Skript ausführen:

    python dashboard/karte_bauen.py

Eine auf die eigene Anlage zugeschnittene Karte liefert bequemer die
Aktion "Dashboard-Karte erzeugen" in Home Assistant. Hier geht es auch:

    python dashboard/karte_bauen.py --komponenten kessel,puffer,hk1 --fuehler 5
"""

import argparse
import importlib.util
import pathlib

import yaml

KARTE_PY = (
    pathlib.Path(__file__).resolve().parent.parent
    / "custom_components"
    / "eta_webservices"
    / "karte.py"
)


def _karte_laden():
    """Lädt karte.py direkt aus der Datei, ohne Home Assistant zu brauchen."""
    spec = importlib.util.spec_from_file_location("eta_karte", KARTE_PY)
    modul = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modul)
    return modul


karte = _karte_laden()


def _argumente():
    """Liest Komponenten und Fühlerzahl von der Kommandozeile."""
    p = argparse.ArgumentParser(
        description="Erzeugt die Dashboard-Karte für die ETA-Integration.",
        epilog="Ohne Angaben entsteht die universelle Karte für jede Anlage.",
    )
    p.add_argument(
        "--komponenten",
        help="Kommaliste der vorhandenen Komponenten, z.B. "
        "kessel,puffer,fwm,hk1,lager,solar",
    )
    p.add_argument(
        "--fuehler",
        type=int,
        help=f"Zahl der Pufferfühler ({karte.PUFFER_MIN} bis {karte.PUFFER_MAX})",
    )
    p.add_argument("--ziel", help="Zieldatei, sonst dashboard/eta-karte.yaml")
    return p.parse_args()


if __name__ == "__main__":
    args = _argumente()
    komponenten = args.komponenten.split(",") if args.komponenten else None
    if komponenten:
        unbekannt = [k for k in komponenten if k not in karte.MARKER]
        if unbekannt:
            raise SystemExit(
                f"Unbekannte Komponente: {', '.join(unbekannt)}\n"
                f"Möglich sind: {', '.join(karte.MARKER)}"
            )
    if args.fuehler and not karte.PUFFER_MIN <= args.fuehler <= karte.PUFFER_MAX:
        raise SystemExit(
            f"Pufferfühler müssen zwischen {karte.PUFFER_MIN} und {karte.PUFFER_MAX} liegen"
        )

    ziel = (
        pathlib.Path(args.ziel)
        if args.ziel
        else pathlib.Path(__file__).with_name("eta-karte.yaml")
    )
    inhalt = yaml.safe_dump(
        karte.responsive_karte(komponenten, args.fuehler),
        allow_unicode=True,
        sort_keys=False,
    )
    ziel.write_text(inhalt, encoding="utf-8")
    print(f"{ziel.name} neu erzeugt: {len(inhalt.splitlines())} Zeilen")
