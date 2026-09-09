"""Automatische Ermittlung der ETA-Objekt-URIs anhand stabiler Namen.

Die numerischen URIs (z.B. /264/10891/0/11109/0) unterscheiden sich je nach
Anlagenkonfiguration und Firmware-Version. Die Bezeichnungen im Menübaum
(abrufbar unter /user/menu) bleiben dagegen stabil. Diese Funktion läuft den
Menübaum einmalig ab und ermittelt für jeden bekannten Messwert die aktuell
gültige URI über den Pfad seiner Namen, statt die Zahlen hart zu verdrahten.
"""

import logging
import xmltodict

_LOGGER = logging.getLogger(__name__)

# Für jeden Messwert-Schlüssel: (Name des Funktionsblocks, [Namenspfad zum Objekt])
DISCOVERY_PATHS = {
    "kessel_temperatur": ("Kessel", ["Eingänge", "Kessel"]),
    "ruecklauf_temperatur": ("Kessel", ["Eingänge", "Rücklauf"]),
    "kessel_druck": ("Kessel", ["Eingänge", "Kesseldruck"]),
    "pellet_tagesbehälter": ("Kessel", ["Ausgänge", "Zählerstände", "Inhalt Pelletsbehälter"]),
    "aussentemperatur": ("Sys", ["Außentemperatur", "Außentemperaturfühler"]),
    "puffer_ladezustand": ("PufferFlex", ["Puffer", "Ladezustand"]),
    "puffer_fuehler_1": ("PufferFlex", ["Eingänge", "Fühler 1 (oben)"]),
    "puffer_fuehler_2": ("PufferFlex", ["Eingänge", "Fühler 2"]),
    "puffer_fuehler_3": ("PufferFlex", ["Eingänge", "Fühler 3"]),
    "puffer_fuehler_4": ("PufferFlex", ["Eingänge", "Fühler 4"]),
    "puffer_fuehler_5": ("PufferFlex", ["Eingänge", "Fühler 5"]),
    "heizkreis_vorlauf": ("HK", ["Eingänge", "Vorlauf"]),
    "heizkreis_anforderung": ("HK", ["Ausgänge", "Heizkreispumpe", "Anforderung"]),
    "fwm_warmwasser": ("FWM", ["Eingänge", "Warmwasser"]),
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


async def async_discover_uris(session, host, port):
    """Ruft /user/menu ab und ermittelt die URIs anhand der Namenspfade.

    Gibt ein Dict {schluessel: uri} für alle erfolgreich gefundenen
    Messwerte zurück. Nicht gefundene Schlüssel fehlen im Ergebnis - der
    Aufrufer soll dafür auf die Standard-URI zurückfallen.
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
                return discovered
            xml_text = await response.text()
    except Exception as err:
        _LOGGER.warning(
            "ETA Menü konnte nicht abgerufen werden (%s) - verwende Standard-URIs: %s",
            url,
            err,
        )
        return discovered

    try:
        parsed = xmltodict.parse(xml_text, process_namespaces=False)
        fubs = _as_list(parsed.get("eta", {}).get("menu", {}).get("fub"))
    except Exception as err:
        _LOGGER.warning("ETA Menü konnte nicht geparst werden: %s", err)
        return discovered

    for key, (fub_name, path) in DISCOVERY_PATHS.items():
        target_fub = fub_name.casefold()
        for fub in fubs:
            if fub.get("@name", "").casefold() != target_fub:
                continue
            found = _find_path(fub, path)
            if found is not None:
                uri = found.get("@uri")
                if uri:
                    discovered[key] = uri
                break

    _LOGGER.info(
        "ETA Webservices: %d/%d URIs automatisch über den Anlagenmenübaum erkannt",
        len(discovered),
        len(DISCOVERY_PATHS),
    )
    missing = sorted(set(DISCOVERY_PATHS) - set(discovered))
    if missing:
        _LOGGER.debug(
            "ETA Webservices: Für folgende Messwerte wurde keine passende URI "
            "im Menübaum gefunden, es wird die Standard-URI verwendet: %s",
            ", ".join(missing),
        )

    return discovered
