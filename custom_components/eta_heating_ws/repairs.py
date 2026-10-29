"""Reparatur-Hinweise für Komponenten ohne Messwerte und für Zeitpläne.

Zu einem Zeitplan gibt es zwei: Tage mit zu vielen Blöcken, und die
Rückfrage, bevor ein frisch gewählter Zeitplan das Zeitprogramm der Anlage
zum ersten Mal ändert. Die Rückfrage hat einen Knopf (ZeitplanBestaetigen).

Heißt der Funktionsblock einer ausgewählten Komponente an der Anlage
anders, bleiben ihre Werte leer. Der Hinweis führt direkt zu den
Optionen, wo sich der tatsächliche Name eintragen lässt.
"""

from __future__ import annotations

from typing import Any

from homeassistant.components.repairs import RepairsFlow
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


def _bestaetigung_id(entry_id: str, heizkreis: str) -> str:
    return f"{entry_id}_{heizkreis}_zeitplan_bestaetigen"


def async_zeitplan_bestaetigung_anfragen(
    hass: HomeAssistant,
    entry_id: str,
    heizkreis: str,
    entity_id: str,
    aenderungen: str,
) -> None:
    """Fragt nach, bevor ein frisch gewählter Zeitplan das Zeitprogramm ändert."""
    angaben = {
        "zeitplan": entity_id,
        "heizkreis": COMPONENTS[heizkreis]["name"],
        "aenderungen": aenderungen,
    }
    issue_registry.async_create_issue(
        hass,
        DOMAIN,
        _bestaetigung_id(entry_id, heizkreis),
        is_fixable=True,
        severity=issue_registry.IssueSeverity.WARNING,
        translation_key="zeitplan_bestaetigen",
        translation_placeholders=angaben,
        data={**angaben, "entry_id": entry_id, "komponente": heizkreis},
    )


def async_zeitplan_bestaetigung_erledigt(
    hass: HomeAssistant, entry_id: str, heizkreis: str
) -> None:
    issue_registry.async_delete_issue(hass, DOMAIN, _bestaetigung_id(entry_id, heizkreis))


def async_zeitplan_hinweise_entfernen(hass: HomeAssistant, entry_id: str, heizkreis: str) -> None:
    """Beide Hinweise eines Heizkreises, dessen Zeitplan abgewählt ist."""
    async_zeitplan_bestaetigung_erledigt(hass, entry_id, heizkreis)
    issue_registry.async_delete_issue(hass, DOMAIN, f"{entry_id}_{heizkreis}_zeitplan_zu_voll")


class ZeitplanBestaetigen(RepairsFlow):
    """Zeigt die geplanten Änderungen und überträgt den Zeitplan nach Bestätigung."""

    def __init__(self, daten: dict[str, Any]) -> None:
        self._daten = daten

    async def async_step_init(self, user_input: dict[str, Any] | None = None):
        return await self.async_step_confirm()

    async def async_step_confirm(self, user_input: dict[str, Any] | None = None):
        if user_input is None:
            return self.async_show_form(
                step_id="confirm",
                description_placeholders={
                    name: str(self._daten.get(name, ""))
                    for name in ("zeitplan", "heizkreis", "aenderungen")
                },
            )
        eintrag = self.hass.config_entries.async_get_entry(self._daten.get("entry_id", ""))
        koordinator = getattr(eintrag, "runtime_data", None) if eintrag else None
        abgleich = getattr(koordinator, "zeitplan_abgleiche", {}).get(self._daten.get("komponente"))
        if abgleich is None:
            return self.async_abort(reason="zeitplan_nicht_aktiv")
        await abgleich.bestaetigen()
        return self.async_create_entry(data={})


async def async_create_fix_flow(
    hass: HomeAssistant, issue_id: str, data: dict[str, Any] | None
) -> RepairsFlow:
    """Der Knopf zur Rückfrage eines Zeitplans - der einzige behebbare Hinweis."""
    return ZeitplanBestaetigen(dict(data or {}))
