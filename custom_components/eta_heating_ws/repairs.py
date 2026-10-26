"""Reparatur-Hinweise für Komponenten ohne Messwerte und für zu volle Zeitpläne.

Heißt der Funktionsblock einer ausgewählten Komponente an der Anlage
anders, bleiben ihre Werte leer. Der Hinweis führt direkt zu den
Optionen, wo sich der tatsächliche Name eintragen lässt.
"""

from __future__ import annotations

from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry

from .const import COMPONENTS, DOMAIN


def _issue_id(entry_id: str, component: str) -> str:
    return f"{entry_id}_{component}_nicht_gefunden"


def async_check_components(
    hass: HomeAssistant,
    entry_id: str,
    components: list[str],
    discovered_keys: set[str],
) -> list[str]:
    """Meldet Komponenten, für die im Menübaum nichts gefunden wurde.

    Wird nur bei lesbarem Menübaum aufgerufen; eine leere Komponente
    liegt dann an den Funktionsblock-Namen.
    """
    ohne_treffer = []

    for component in components:
        issue_id = _issue_id(entry_id, component)
        gefunden = any(
            key.startswith(vorsilbe)
            for key in discovered_keys
            for vorsilbe in COMPONENTS[component]["discovery_prefixes"]
        )
        if not gefunden:
            ohne_treffer.append(component)
            issue_registry.async_create_issue(
                hass,
                DOMAIN,
                issue_id,
                is_fixable=False,
                severity=issue_registry.IssueSeverity.WARNING,
                translation_key="component_not_found",
                translation_placeholders={
                    "component": COMPONENTS[component]["name"],
                    "fub_names": ", ".join(COMPONENTS[component]["roles"]),
                },
            )
        else:
            issue_registry.async_delete_issue(hass, DOMAIN, issue_id)

    return ohne_treffer


def async_zeitplan_pruefen(
    hass: HomeAssistant,
    entry_id: str,
    heizkreis: str,
    entity_id: str,
    zu_volle_tage: list[str],
) -> None:
    """Meldet Tage, an denen der Zeitplan mehr Blöcke hat, als die Anlage Fenster.

    Diese Tage überträgt die Integration nicht. Der Hinweis verschwindet,
    sobald der Zeitplan wieder passt.
    """
    issue_id = f"{entry_id}_{heizkreis}_zeitplan_zu_voll"
    if not zu_volle_tage:
        issue_registry.async_delete_issue(hass, DOMAIN, issue_id)
        return
    issue_registry.async_create_issue(
        hass,
        DOMAIN,
        issue_id,
        is_fixable=False,
        severity=issue_registry.IssueSeverity.WARNING,
        translation_key="zeitplan_zu_voll",
        translation_placeholders={
            "zeitplan": entity_id,
            "heizkreis": COMPONENTS[heizkreis]["name"],
            "tage": ", ".join(zu_volle_tage),
        },
    )
