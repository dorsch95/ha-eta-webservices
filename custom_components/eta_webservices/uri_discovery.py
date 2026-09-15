"""Ermittelt die ETA-Objekt-URIs anhand der Namen im Menübaum.

Die numerischen URIs unterscheiden sich je nach Anlage und Firmware, die
Bezeichnungen unter /user/menu bleiben stabil. Ausnahme sind die Namen der
Funktionsblöcke (FUB), die an der Steuerung geändert werden können. Jeder
Messwert hängt deshalb an einer FUB-*Rolle* ("kessel", "hk", ...), der beim
Einrichten ein tatsächlicher Name zugeordnet wird.
"""

from __future__ import annotations

import logging
import re

from .const import BETRIEBSART_TASTEN, FUB_ROLE_DEFAULT_NAMES, PUFFER_FUEHLER_MAX

_LOGGER = logging.getLogger(__name__)

DISCOVERY_PATHS = {
    "kessel_temperatur": ("kessel", ["Eingänge", "Kessel"]),
    "ruecklauf_temperatur": ("kessel", ["Eingänge", "Rücklauf"]),
    "kessel_druck": ("kessel", ["Eingänge", "Kesseldruck"]),
    "pellet_tagesbehälter": (
        "kessel",
        ["Kessel", "Pelletsbehälter", "Inhalt Pelletsbehälter"],
    ),
    "kessel_soll": ("kessel", ["Kessel", "Kessel", "Kessel Soll"]),
    "restsauerstoff": ("kessel", ["Eingänge", "Restsauerstoff", "Restsauerstoff"]),
    "pellet_gesamtverbrauch": ("kessel", ["Zählerstände", "Gesamtverbrauch"]),
    "aschebox_verbrauch": (
        "kessel",
        ["Kessel", "Entaschung", "Verbrauch seit Aschebox leeren"],
    ),
    "entaschung_verbrauch": (
        "kessel",
        ["Kessel", "Entaschung", "Verbrauch seit Entaschung"],
    ),
    "aschebox_schwelle": ("kessel", ["Kessel", "Entaschung", "Aschebox leeren nach"]),
    "kessel_zustand": ("kessel", ["Kessel", "Kessel-Zustand detailliert"]),
    "aussentemperatur": ("sys", ["Außentemperatur", "Außentemperaturfühler"]),
    "puffer_ladezustand": ("pufferflex", ["Puffer", "Ladezustand"]),
    "heizkreis_vorlauf": ("hk", ["Eingänge", "Vorlauf"]),
    "heizkreis_anforderung": ("hk", ["Ausgänge", "Heizkreispumpe", "Anforderung"]),
    "heizkreis2_vorlauf": ("hk2", ["Eingänge", "Vorlauf"]),
    "heizkreis2_anforderung": ("hk2", ["Ausgänge", "Heizkreispumpe", "Anforderung"]),
    "heizkreis3_vorlauf": ("hk3", ["Eingänge", "Vorlauf"]),
    "heizkreis3_anforderung": ("hk3", ["Ausgänge", "Heizkreispumpe", "Anforderung"]),
    "heizkreis4_vorlauf": ("hk4", ["Eingänge", "Vorlauf"]),
    "heizkreis4_anforderung": ("hk4", ["Ausgänge", "Heizkreispumpe", "Anforderung"]),
    "fwm_warmwasser": ("fwm", ["Eingänge", "Warmwasser"]),
    "lager_vorrat": ("lager", ["Vorrat"]),
    "lager_warngrenze": ("lager", ["Vorrat", "Vorrat Warngrenze"]),
    "lager_maximum": ("lager", ["Vorrat", "Maximaler Vorrat"]),
    "lager_zustand": ("lager", ["Austragung", "Austragung-Zustand detailliert"]),
    "solar_kollektor": ("solar", ["Eingänge", "Kollektor"]),
    "solar_leistung": ("solar", ["Leistung"]),
    "solar_waermemenge": ("solar", ["Leistung", "Wärmemenge"]),
    "solar_ertrag_heute": ("solar", ["Leistung", "Ertrag heute"]),
    "solar_ertrag_gestern": ("solar", ["Leistung", "Ertrag gestern"]),
}

PUMPEN = {
    "fwm_zirkulationspumpe": ("fwm", "zirkulation"),
}
"""Pumpen, die über ein Stichwort in ihrem Namen gesucht werden.

Je nach Anlage heißt eine Pumpe "Zirkulationspumpe", "Zirkulation" oder
ähnlich. Gesucht wird unter "Ausgänge"; geliefert wird die URI ihrer
"Anforderung", die den Laufzustand meldet.
"""

NAMENSSUCHE = {
    "solar_kollektor": "Kollektor",
    "solar_leistung": "Leistung",
    "solar_waermemenge": "Wärmemenge",
    "solar_ertrag_heute": "Ertrag heute",
    "solar_ertrag_gestern": "Ertrag gestern",
}
"""Zweiter Versuch über den bloßen Objektnamen, falls der Pfad nicht passt.

Nur für diese Schlüssel, weil ihr Zweig je nach Anlage unterschiedlich
tief im Menü liegt. Für die übrigen bleibt es beim festen Pfad - Namen
wie "Vorlauf" kommen mehrfach vor.
"""

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

BETRIEBSART_ROLES = {
    "heizkreis_betriebsart": "hk",
    "heizkreis2_betriebsart": "hk2",
    "heizkreis3_betriebsart": "hk3",
    "heizkreis4_betriebsart": "hk4",
}
"""Welcher Funktionsblock zu welcher Betriebsart-Auswahl gehört."""

SWITCH_ROLES = {
    "kessel_schalter": "kessel",
    "heizkreis_schalter": "hk",
    "heizkreis2_schalter": "hk2",
    "heizkreis3_schalter": "hk3",
    "heizkreis4_schalter": "hk4",
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

    Gesucht wird über den Namen, weil der Pfad dorthin je nach Firmware
    abweicht.
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


def _finde_pumpe(fub, stichwort):
    """Sucht unter "Ausgänge" eine Pumpe und liefert ihre Anforderung."""
    if fub is None:
        return None
    ausgaenge = _find_path(fub, ["Ausgänge"])
    if ausgaenge is None:
        return None

    for kind in _as_list(ausgaenge.get("object")):
        if not isinstance(kind, dict):
            continue
        if stichwort not in (kind.get("@name") or "").casefold():
            continue
        anforderung = _find_path(kind, ["Anforderung"])
        if anforderung is not None and anforderung.get("@uri"):
            return anforderung["@uri"]
    return None


def _finde_nach_namen(fub, name):
    """Sucht im ganzen Funktionsblock das erste Objekt mit diesem Namen."""
    if fub is None:
        return None
    ziel = name.casefold()

    def durchsuchen(knoten):
        for kind in _as_list(knoten.get("object")):
            if not isinstance(kind, dict):
                continue
            if kind.get("@name", "").strip().casefold() == ziel and kind.get("@uri"):
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
        if not isinstance(child, dict):
            continue
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
    - discovered: {schluessel: uri} aller gefundenen Messwerte, inklusive
      "puffer_fuehler_<n>" je gefundenem Fühler.
    - puffer_fuehler_indices: sortierte Nummern der gefundenen Fühler.

    Nicht gefundene Schlüssel fehlen im Ergebnis. Ist der Menübaum nicht
    lesbar, wird der ETAApiError durchgereicht.
    """
    discovered = {}

    parsed = await client.async_get_menu()

    fubs = _as_list(parsed.get("eta", {}).get("menu", {}).get("fub"))
    fubs_by_role = _resolve_fubs_by_role(fubs, fub_name_overrides)

    for key, (role, path) in DISCOVERY_PATHS.items():
        fub = fubs_by_role.get(role)
        if fub is None:
            continue
        found = _find_path(fub, path)
        uri = found.get("@uri") if found is not None else None
        if not uri and key in NAMENSSUCHE:
            uri = _finde_nach_namen(fub, NAMENSSUCHE[key])
        if uri:
            discovered[key] = uri

    for key, (role, stichwort) in PUMPEN.items():
        uri = _finde_pumpe(fubs_by_role.get(role), stichwort)
        if uri:
            discovered[key] = uri

    for key, role in SWITCH_ROLES.items():
        fub = fubs_by_role.get(role)
        uri = _finde_schalter(fub)
        if uri:
            discovered[key] = uri

    for key, role in BETRIEBSART_ROLES.items():
        fub = fubs_by_role.get(role)
        if fub is None:
            continue
        for modus, name in BETRIEBSART_TASTEN.items():
            uri = _finde_nach_namen(fub, name)
            if uri:
                discovered[f"{key}_{modus}"] = uri

    puffer_fuehler = _discover_puffer_fuehler(fubs_by_role.get("pufferflex"))
    puffer_fuehler_indices = sorted(puffer_fuehler)
    for index, uri in puffer_fuehler.items():
        discovered[f"puffer_fuehler_{index}"] = uri

    gesucht = set(DISCOVERY_PATHS) | set(PUMPEN)
    messwerte = (gesucht & set(discovered)) | set(puffer_fuehler)
    _LOGGER.info(
        "ETA Webservices: %d von %d Messwerten im Menübaum gefunden "
        "(%d Pufferfühler), dazu %d Schalt- und Betriebsart-Objekte",
        len(messwerte),
        len(gesucht) + len(puffer_fuehler_indices),
        len(puffer_fuehler_indices),
        len(discovered) - len(messwerte),
    )
    missing = sorted(gesucht - set(discovered))
    if missing:
        _LOGGER.debug(
            "ETA Webservices: Für folgende Messwerte wurde keine passende URI "
            "im Menübaum gefunden (evtl. an dieser Anlage nicht vorhanden, oder "
            "der FUB wurde umbenannt): %s",
            ", ".join(missing),
        )

    return discovered, puffer_fuehler_indices
