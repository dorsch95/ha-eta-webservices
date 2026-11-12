"""Was die Karte "ETA Übersicht" über die Anlage wissen muss.

Die Karte (oberflaeche/eta-uebersicht-karte.js) zeigt die Anlage als
Kacheln, als Anlagenbild mit Leitungen oder kompakt als Liste. Die
Messwerte liest sie aus den Entitäten in Home Assistant. Was sie von dort
nicht erfährt, liefert der Websocket-Befehl hier: welche Teile die Anlage
hat, welche Entität zu welchem Messwert gehört, wer woran hängt und ob
geschaltet werden darf.

Die Entitäten stehen unter ihrem Schlüssel aus const.py, nicht unter ihrer
ID - die kann der Nutzer umbenennen, und bei zwei Anlagen wären die IDs
der zweiten ohnehin andere.
"""

from __future__ import annotations

import voluptuous as vol
from homeassistant.components import websocket_api
from homeassistant.components.frontend import add_extra_js_url
from homeassistant.const import ATTR_RESTORED
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er

from .const import (
    COMPONENTS,
    CONF_VERBINDUNGEN,
    DOMAIN,
    HEIZKREISE,
    KARTE_UEBERSICHT,
    PUFFER_SPEICHER,
    URL_OBERFLAECHE,
    WARMWASSER_SPEICHER,
)
from .karte import VERSION
from .verbindungen import verbindungen

OHNE_KACHEL = ("twin",)
"""Komponenten, die kein eigenes Teil der Anlage sind - der TWIN gehört zum Kessel."""


def karte_adresse() -> str:
    """Die Adresse der Karte, mit der Version als Anhang - wie bei den Kachelgrafiken."""
    return f"{URL_OBERFLAECHE}/{KARTE_UEBERSICHT}?v={VERSION}"


@callback
def async_uebersicht_anmelden(hass: HomeAssistant) -> None:
    """Meldet den Websocket-Befehl an und lässt jedes Dashboard die Karte laden."""
    websocket_api.async_register_command(hass, _ws_uebersicht)
    if "frontend" in hass.config.components:
        add_extra_js_url(hass, karte_adresse())


def art(komponente: str) -> str:
    """Wie die Karte dieses Teil zeichnet: puffer, warmwasser, heizkreis oder der Name der Komponente."""
    if komponente in PUFFER_SPEICHER:
        return "puffer"
    if komponente in WARMWASSER_SPEICHER:
        return "warmwasser"
    if komponente in HEIZKREISE:
        return "heizkreis"
    return komponente


def _nummer(komponente: str) -> int:
    """Der wievielte seiner Art: puffer ist 1, puffer2 ist 2, hk3 ist 3."""
    ziffern = "".join(zeichen for zeichen in komponente if zeichen.isdigit())
    return int(ziffern) if ziffern else 1


def _teil(coordinator, komponente: str, quelle: str | None) -> dict:
    """Ein Teil der Anlage, wie die Karte es braucht.

    block: wie der Funktionsblock an der Anlage heißt. bauart: nur beim
    Warmwasser - das Frischwassermodul bekommt ein anderes Bild als der
    Warmwasserspeicher, weil seine Temperatur ohne Zapfen sinkt und ein
    Speicher mit kalten Farben nach "kein Warmwasser" aussähe. Welches von
    beiden es ist, sagt ETADataUpdateCoordinator.frischwassermodul.
    """
    block = coordinator.funktionsblock(komponente)
    teil = {
        "id": komponente,
        "art": art(komponente),
        "nummer": _nummer(komponente),
        "block": block,
        "von": quelle,
    }
    if komponente in WARMWASSER_SPEICHER:
        teil["bauart"] = "fwm" if coordinator.frischwassermodul(komponente) else "speicher"
    return teil


def _vorhanden(coordinator, komponente: str) -> bool:
    """Führt die Anlage dieses Teil? Ohne einen einzigen Wert im Menübaum bleibt es aus der Karte.

    Der Kessel ist als Komponente nicht abwählbar, aber nicht jede Anlage
    hat einen: An einer Unterstation kommt die Wärme über die Fernleitung.
    Die Außentemperatur allein macht noch keinen Kessel.
    """
    if komponente in coordinator.components_without_data:
        return False
    if komponente == "kessel":
        return any(key.startswith("kessel_") for key in coordinator.discovered_uris)
    return True


def _bereitgestellt(hass: HomeAssistant, entity_id: str) -> bool:
    """Bringt die Einrichtung diese Entität gerade hervor?

    Eine Entität, die nur noch im Register steht, führt Home Assistant als
    "nicht verfügbar" weiter und kennzeichnet ihren Zustand mit restored.
    Das trifft etwa das Warmwasser im Puffer, wenn die Anlage beim ersten
    Start nicht sagen konnte, ob er ein Kombispeicher ist, und es beim
    nächsten verneint. Die Karte zeichnete sonst einen Warmwasserbereich,
    den es nicht gibt.
    """
    stand = hass.states.get(entity_id)
    return stand is not None and not stand.attributes.get(ATTR_RESTORED)


def entitaeten(hass: HomeAssistant, entry_id: str) -> dict[str, str]:
    """Die Entitäten einer Anlage: Schlüssel aus const.py und ihre heutige ID.

    Nur, was es gerade gibt: Deaktivierte fehlen, ebenso solche, die die
    Einrichtung nicht mehr hervorbringt, siehe _bereitgestellt.
    """
    praefixe = (f"eta_static_{entry_id}_", f"eta_switch_{entry_id}_")
    gefunden = {}
    for eintrag in er.async_entries_for_config_entry(er.async_get(hass), entry_id):
        if eintrag.disabled_by is not None or not _bereitgestellt(hass, eintrag.entity_id):
            continue
        for praefix in praefixe:
            if eintrag.unique_id.startswith(praefix):
                gefunden[eintrag.unique_id.removeprefix(praefix)] = eintrag.entity_id
    return gefunden


def anlage(hass: HomeAssistant, eintrag) -> dict:
    """Eine Anlage für die Karte: Teile, Verbindungen, Entitäten, Schreibzugriff.

    Ein Teil, das die Anlage nicht führt, fehlt - und mit ihm die Leitung
    zu allem, was laut Auswahl an ihm hängt.
    """
    coordinator = eintrag.runtime_data
    komponenten = [k for k in coordinator.components if k in COMPONENTS]
    wege = verbindungen(
        komponenten, {**eintrag.data, **eintrag.options}.get(CONF_VERBINDUNGEN)
    )
    gezeigt = [
        komponente
        for komponente in komponenten
        if komponente not in OHNE_KACHEL and _vorhanden(coordinator, komponente)
    ]
    return {
        "eintrag": eintrag.entry_id,
        "titel": eintrag.title,
        "schreiben": bool(coordinator.enable_switches),
        "teile": [
            _teil(
                coordinator,
                komponente,
                wege.get(komponente) if wege.get(komponente) in gezeigt else None,
            )
            for komponente in gezeigt
        ],
        "entitaeten": entitaeten(hass, eintrag.entry_id),
    }


@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/uebersicht"})
@callback
def _ws_uebersicht(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict
) -> None:
    """Alle geladenen Anlagen für die Karte "ETA Übersicht"."""
    connection.send_result(
        msg["id"],
        {
            "anlagen": [
                anlage(hass, eintrag)
                for eintrag in hass.config_entries.async_loaded_entries(DOMAIN)
            ]
        },
    )
