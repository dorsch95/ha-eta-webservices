"""Automatische Ermittlung der ETA-Objekt-URIs anhand stabiler Namen.

Die numerischen URIs (z.B. /264/10891/0/11109/0) unterscheiden sich je nach
Anlagenkonfiguration und Firmware-Version. Die Bezeichnungen im Menübaum
(abrufbar unter /user/menu) bleiben dagegen stabil - mit einer Ausnahme: die
Namen der Funktionsblöcke (FUB, z.B. "Kessel", "PufferFlex", "HK") können
vom Nutzer an der Steuerung umbenannt werden. Deshalb wird jeder Messwert
nicht direkt einem FUB-Namen zugeordnet, sondern einer FUB-*Rolle*
("kessel", "pufferflex", "hk", ...). Für jede Rolle gibt es ETA-Standard-
namen, die im Setup vom Nutzer überschrieben werden können, falls seine
Anlage abweicht.
"""

from __future__ import annotations

import logging
import re

from .api import ETAApiError
from .const import FUB_ROLE_DEFAULT_NAMES, PUFFER_FUEHLER_MAX

_LOGGER = logging.getLogger(__name__)

DISCOVERY_PATHS = {
    "kessel_temperatur": ("kessel", ["Eingänge", "Kessel"]),
    "ruecklauf_temperatur": ("kessel", ["Eingänge", "Rücklauf"]),
    "kessel_druck": ("kessel", ["Eingänge", "Kesseldruck"]),
    "pellet_tagesbehälter": ("kessel", ["Ausgänge", "Zählerstände", "Inhalt Pelletsbehälter"]),
    "kessel_soll": ("kessel", ["Kessel", "Kessel", "Kessel Soll"]),
    "restsauerstoff": ("kessel", ["Eingänge", "Restsauerstoff", "Restsauerstoff"]),
    "aschebox_verbrauch": ("kessel", ["Ausgänge", "Zählerstände", "Verbrauch seit Aschebox leeren"]),
    "entaschung_verbrauch": ("kessel", ["Ausgänge", "Zählerstände", "Verbrauch seit Entaschung"]),
    "aschebox_schwelle": ("kessel", ["Kessel", "Entaschung", "Aschebox leeren nach"]),
    "kessel_zustand": ("kessel", ["Kessel", "Kessel-Zustand detailliert"]),
    "aussentemperatur": ("sys", ["Außentemperatur", "Außentemperaturfühler"]),
    "puffer_ladezustand": ("pufferflex", ["Puffer", "Ladezustand"]),
    "heizkreis_vorlauf": ("hk", ["Eingänge", "Vorlauf"]),
    "heizkreis_anforderung": ("hk", ["Ausgänge", "Heizkreispumpe", "Anforderung"]),
    "heizkreis2_vorlauf": ("hk2", ["Eingänge", "Vorlauf"]),
    "heizkreis2_anforderung": ("hk2", ["Ausgänge", "Heizkreispumpe", "Anforderung"]),
    "fwm_warmwasser": ("fwm", ["Eingänge", "Warmwasser"]),
    "fwm_zirkulation": ("fwm", ["Eingänge", "Zirkulation"]),
}

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

SWITCH_ROLES = {
    "kessel_schalter": "kessel",
    "heizkreis_schalter": "hk",
    "heizkreis2_schalter": "hk2",
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
    """
    overrides = fub_name_overrides or {}
    resolved = {}

    for role, default_names in FUB_ROLE_DEFAULT_NAMES.items():
        override = overrides.get(role)
        candidates = [override] if override else default_names
        for name in candidates:
            fub = _find_fub(fubs, name)
            if fub is not None:
                resolved[role] = fub
                break

    return resolved


def _finde_schalter(fub):
    """Sucht im ganzen Funktionsblock nach einem Ein/Aus-Objekt.

    Der Pfad dorthin heißt je nach Firmware anders, der Name des Objekts
    selbst ist dagegen eindeutig - deshalb wird hier über den Namen
    gesucht statt über einen festen Pfad.
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


async def async_discover_uris(client, fub_name_overrides=None):
    """Ruft /user/menu ab und ermittelt die URIs anhand der Namenspfade.

    Gibt ein Tupel (discovered, puffer_fuehler_indices) zurück:
    - discovered: Dict {schluessel: uri} für alle erfolgreich gefundenen
      Messwerte (inkl. "puffer_fuehler_<n>" für jeden gefundenen Fühler).
    - puffer_fuehler_indices: sortierte Liste der tatsächlich gefundenen
      Fühler-Nummern (leer, falls nichts gefunden wurde).
    Nicht gefundene Schlüssel fehlen im Ergebnis - der Aufrufer soll dafür
    auf die Standard-URI zurückfallen (sofern vorhanden).
    """
    discovered = {}

    try:
        parsed = await client.async_get_menu()
    except ETAApiError as err:
        _LOGGER.warning(
            "ETA Menü konnte nicht gelesen werden - verwende Standard-URIs: %s", err
        )
        return discovered, []

    fubs = _as_list(parsed.get("eta", {}).get("menu", {}).get("fub"))
    fubs_by_role = _resolve_fubs_by_role(fubs, fub_name_overrides)

    for key, (role, path) in DISCOVERY_PATHS.items():
        fub = fubs_by_role.get(role)
        if fub is None:
            continue
        found = _find_path(fub, path)
        if found is not None:
            uri = found.get("@uri")
            if uri:
                discovered[key] = uri

    for key, role in SWITCH_ROLES.items():
        fub = fubs_by_role.get(role)
        uri = _finde_schalter(fub)
        if uri:
            discovered[key] = uri

    puffer_fuehler = _discover_puffer_fuehler(fubs_by_role.get("pufferflex"))
    puffer_fuehler_indices = sorted(puffer_fuehler)
    for index, uri in puffer_fuehler.items():
        discovered[f"puffer_fuehler_{index}"] = uri

    total_expected = len(DISCOVERY_PATHS) + len(puffer_fuehler_indices)
    _LOGGER.info(
        "ETA Webservices: %d/%d URIs automatisch über den Anlagenmenübaum erkannt "
        "(%d Pufferfühler gefunden)",
        len(discovered),
        total_expected,
        len(puffer_fuehler_indices),
    )
    missing = sorted(set(DISCOVERY_PATHS) - set(discovered))
    if missing:
        _LOGGER.debug(
            "ETA Webservices: Für folgende Messwerte wurde keine passende URI "
            "im Menübaum gefunden (evtl. an dieser Anlage nicht vorhanden, oder "
            "der FUB wurde umbenannt): %s",
            ", ".join(missing),
        )

    return discovered, puffer_fuehler_indices
