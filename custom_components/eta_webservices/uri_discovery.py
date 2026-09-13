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

import logging
import re

import xmltodict

from .const import FUB_ROLE_DEFAULT_NAMES, PUFFER_FUEHLER_MAX

_LOGGER = logging.getLogger(__name__)

# Für jeden Messwert-Schlüssel: (FUB-Rolle, [Namenspfad zum Objekt])
DISCOVERY_PATHS = {
    "kessel_temperatur": ("kessel", ["Eingänge", "Kessel"]),
    "ruecklauf_temperatur": ("kessel", ["Eingänge", "Rücklauf"]),
    "kessel_druck": ("kessel", ["Eingänge", "Kesseldruck"]),
    "pellet_tagesbehälter": ("kessel", ["Ausgänge", "Zählerstände", "Inhalt Pelletsbehälter"]),
    "kessel_soll": ("kessel", ["Kessel", "Kessel", "Kessel Soll"]),
    "restsauerstoff": ("kessel", ["Eingänge", "Restsauerstoff", "Restsauerstoff"]),
    "aussentemperatur": ("sys", ["Außentemperatur", "Außentemperaturfühler"]),
    "puffer_ladezustand": ("pufferflex", ["Puffer", "Ladezustand"]),
    "heizkreis_vorlauf": ("hk", ["Eingänge", "Vorlauf"]),
    "heizkreis_anforderung": ("hk", ["Ausgänge", "Heizkreispumpe", "Anforderung"]),
    "heizkreis2_vorlauf": ("hk2", ["Eingänge", "Vorlauf"]),
    "heizkreis2_anforderung": ("hk2", ["Ausgänge", "Heizkreispumpe", "Anforderung"]),
    # FWM oder WW: unabhängig vom FUB-Namen interessieren nur Warmwasser
    # und Zirkulation.
    "fwm_warmwasser": ("fwm", ["Eingänge", "Warmwasser"]),
    "fwm_zirkulation": ("fwm", ["Eingänge", "Zirkulation"]),
}

_FUEHLER_NAME_RE = re.compile(r"^F[uü]hler\s*(\d+)", re.IGNORECASE)


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


def _find_fub_for_role(fubs, role, fub_name_overrides):
    """Löst eine FUB-Rolle (z.B. "pufferflex") zum tatsächlichen FUB-Knoten auf.

    Ein vom Nutzer im Setup angegebener Name hat immer Vorrang vor den
    ETA-Standardnamen, da FUBs am Gerät umbenannt werden können.
    """
    override = (fub_name_overrides or {}).get(role)
    candidates = [override] if override else FUB_ROLE_DEFAULT_NAMES.get(role, [])
    for name in candidates:
        fub = _find_fub(fubs, name)
        if fub is not None:
            return fub
    return None


def _discover_puffer_fuehler(fubs, fub_name_overrides):
    """Ermittelt die tatsächlich vorhandenen Pufferfühler (1 bis N).

    PufferFlex kann je nach Anlage zwischen 3 und PUFFER_FUEHLER_MAX Fühler
    haben - Fühler 1 ist immer oben, der zuletzt nummerierte immer unten.
    Da die Anzahl variiert, werden die "Eingänge" von PufferFlex nach allen
    Objekten durchsucht, deren Name mit "Fühler <Zahl>" beginnt.
    """
    fub = _find_fub_for_role(fubs, "pufferflex", fub_name_overrides)
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


async def async_discover_uris(session, host, port, fub_name_overrides=None):
    """Ruft /user/menu ab und ermittelt die URIs anhand der Namenspfade.

    Gibt ein Tupel (discovered, puffer_fuehler_indices) zurück:
    - discovered: Dict {schluessel: uri} für alle erfolgreich gefundenen
      Messwerte (inkl. "puffer_fuehler_<n>" für jeden gefundenen Fühler).
    - puffer_fuehler_indices: sortierte Liste der tatsächlich gefundenen
      Fühler-Nummern (leer, falls nichts gefunden wurde).
    Nicht gefundene Schlüssel fehlen im Ergebnis - der Aufrufer soll dafür
    auf die Standard-URI zurückfallen (sofern vorhanden).
    """
    url = f"http://{host}:{port}/user/menu"
    discovered = {}

    try:
        async with session.get(url, timeout=10) as response:
            if response.status != 200:
                _LOGGER.warning(
                    "ETA Menüabfrage (%s) fehlgeschlagen mit Status %s - "
                    "verwende Standard-URIs",
                    url,
                    response.status,
                )
                return discovered, []
            xml_text = await response.text()
    except Exception as err:
        _LOGGER.warning(
            "ETA Menü konnte nicht abgerufen werden (%s) - verwende Standard-URIs: %s",
            url,
            err,
        )
        return discovered, []

    try:
        parsed = xmltodict.parse(xml_text, process_namespaces=False)
        fubs = _as_list(parsed.get("eta", {}).get("menu", {}).get("fub"))
    except Exception as err:
        _LOGGER.warning("ETA Menü konnte nicht geparst werden: %s", err)
        return discovered, []

    for key, (role, path) in DISCOVERY_PATHS.items():
        fub = _find_fub_for_role(fubs, role, fub_name_overrides)
        if fub is None:
            continue
        found = _find_path(fub, path)
        if found is not None:
            uri = found.get("@uri")
            if uri:
                discovered[key] = uri

    puffer_fuehler = _discover_puffer_fuehler(fubs, fub_name_overrides)
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
