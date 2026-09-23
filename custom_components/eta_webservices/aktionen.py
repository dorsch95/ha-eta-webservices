"""Die Aktion "Dashboard-Karte erzeugen".

Liefert die Karte zugeschnitten auf die eingerichtete Anlage: nur die
angekreuzten Komponenten, genau so viele Pufferfühler wie vorhanden und
die Entitäts-IDs, die es in dieser Installation wirklich gibt - auch wenn
jemand eine umbenannt hat. Kein Python, kein Kopieren aus dem Repo, und
Werkzeuge wie Spook finden keine unbekannten Entitäten.

Aufruf unter Entwicklerwerkzeuge -> Aktionen. Die Antwort ist die fertige
Karte und lässt sich unverändert in eine manuelle Karte einfügen.
"""

from __future__ import annotations

import json
import re

import voluptuous as vol
from homeassistant.core import (
    HomeAssistant,
    ServiceCall,
    ServiceResponse,
    SupportsResponse,
)
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import entity_registry as er

from .const import DOMAIN
from .entitaets_ids import feste_entity_id
from .karte import responsive_karte

AKTION_KARTE = "karte_erzeugen"
CONF_EINTRAG = "config_entry_id"

_ENTITAET = re.compile(
    r"\b(?:sensor|binary_sensor|switch|select)\.eta_heizung_[a-z0-9_]+"
)


def async_aktionen_registrieren(hass: HomeAssistant) -> None:
    """Meldet die Aktionen der Integration bei Home Assistant an."""

    async def karte_erzeugen(call: ServiceCall) -> ServiceResponse:
        eintrag = _eintrag_waehlen(hass, call.data.get(CONF_EINTRAG))
        return karte_fuer_eintrag(hass, eintrag)

    hass.services.async_register(
        DOMAIN,
        AKTION_KARTE,
        karte_erzeugen,
        schema=vol.Schema({vol.Optional(CONF_EINTRAG): cv.string}),
        supports_response=SupportsResponse.ONLY,
    )


def _eintrag_waehlen(hass: HomeAssistant, eintrag_id: str | None):
    """Der gemeinte Eintrag - bei nur einer Anlage muss niemand wählen."""
    geladen = hass.config_entries.async_loaded_entries(DOMAIN)
    if eintrag_id:
        for eintrag in geladen:
            if eintrag.entry_id == eintrag_id:
                return eintrag
        raise ServiceValidationError(
            "Diese ETA-Heizung ist nicht eingerichtet oder gerade nicht geladen."
        )
    if len(geladen) == 1:
        return geladen[0]
    if not geladen:
        raise ServiceValidationError("Es ist keine ETA-Heizung geladen.")
    raise ServiceValidationError(
        "Es sind mehrere ETA-Heizungen eingerichtet - bitte eine auswählen."
    )


def karte_fuer_eintrag(hass: HomeAssistant, eintrag) -> dict:
    """Baut die Karte für diesen Eintrag mit seinen tatsächlichen Entitäten."""
    coordinator = eintrag.runtime_data
    fuehler = sum(
        1 for key in coordinator.sensor_defs if key.startswith("puffer_fuehler_")
    )
    karte = responsive_karte(coordinator.components, fuehler or None)

    registry = er.async_get(hass)
    tatsaechlich: dict[str, str] = {}
    for eintrag_reg in er.async_entries_for_config_entry(registry, eintrag.entry_id):
        vorgabe = feste_entity_id(
            coordinator.deutsche_namen, eintrag_reg.domain, eintrag_reg.translation_key
        )
        if vorgabe:
            tatsaechlich[vorgabe] = eintrag_reg.entity_id

    return karte_anpassen(karte, tatsaechlich)


def karte_anpassen(karte: dict, tatsaechlich: dict[str, str]) -> dict:
    """Setzt die echten IDs ein und lässt weg, was es nicht gibt.

    tatsaechlich ordnet jeder vorgesehenen ID die ID zu, unter der die
    Entität in dieser Installation geführt wird. Elemente, deren Entität
    fehlt - etwa der Kesselschalter ohne freigegebenen Schreibzugriff -,
    entfallen samt ihrer Bedingung.
    """
    text = _ENTITAET.sub(
        lambda treffer: tatsaechlich.get(treffer[0], treffer[0]), json.dumps(karte)
    )
    vorhanden = set(tatsaechlich.values())
    return _ohne_fehlende(json.loads(text), vorhanden)


def _genannt(element) -> set[str]:
    """Die Entitäten, an denen ein Element selbst hängt."""
    if not isinstance(element, dict):
        return set()
    namen = {element.get("entity")}
    for bedingung in element.get("conditions", []) or []:
        if isinstance(bedingung, dict):
            namen.add(bedingung.get("entity"))
    ziel = (element.get("tap_action") or {}).get("target") or {}
    namen.add(ziel.get("entity_id"))
    return {n for n in namen if isinstance(n, str) and _ENTITAET.fullmatch(n)}


def _ohne_fehlende(knoten, vorhanden: set[str]):
    if isinstance(knoten, dict):
        for liste in ("cards", "elements"):
            if isinstance(knoten.get(liste), list):
                knoten[liste] = [
                    _ohne_fehlende(kind, vorhanden)
                    for kind in knoten[liste]
                    if _genannt(kind) <= vorhanden
                ]
        if isinstance(knoten.get("card"), dict):
            knoten["card"] = _ohne_fehlende(knoten["card"], vorhanden)
    return knoten
