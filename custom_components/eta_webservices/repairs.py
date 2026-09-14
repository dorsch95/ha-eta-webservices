"""Reparatur-Hinweise für Komponenten ohne Messwerte.

Wenn jemand eine Komponente auswählt, deren Funktionsblock an der Anlage
anders heißt, bleiben deren Werte still leer - das ist der mit Abstand
häufigste Fehlerfall dieser Integration. Home Assistant zeigt dafür einen
Reparatur-Hinweis mit direktem Weg zu den Optionen an, statt dass der
Nutzer erst im Protokoll oder im Diagnose-Export suchen muss.
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
    menu_readable: bool,
) -> list[str]:
    """Meldet Komponenten, für die im Menübaum nichts gefunden wurde.

    War der Menübaum gar nicht lesbar, wird nichts gemeldet: dann liegt es
    an der Verbindung und nicht an den Funktionsblock-Namen, und ein
    Hinweis je Komponente wäre nur Lärm.
    """
    ohne_treffer = []

    for component in components:
        issue_id = _issue_id(entry_id, component)
        gefunden = any(
            key.startswith(vorsilbe)
            for key in discovered_keys
            for vorsilbe in COMPONENTS[component]["discovery_prefixes"]
        )
        if menu_readable and not gefunden:
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
