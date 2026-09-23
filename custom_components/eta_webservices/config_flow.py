"""Config- und Options-Flow für die ETA-Integration."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.config_entries import (
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
    OptionsFlowWithReload,
)
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.selector import (
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)

from .api import ETAApiClient
from .const import (
    COMPONENTS,
    CONF_COMPONENTS,
    CONF_ENABLE_ERRORS,
    CONF_ENABLE_SWITCHES,
    CONF_FUB_NAMES,
    CONF_PELLET_KWH_PER_KG,
    CONF_PELLET_PREIS,
    CONF_SCAN_INTERVAL,
    DEFAULT_ENABLE_ERRORS,
    DEFAULT_ENABLE_SWITCHES,
    DEFAULT_PELLET_KWH_PER_KG,
    DEFAULT_PELLET_PREIS,
    DEFAULT_PORT,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    MAX_PELLET_KWH_PER_KG,
    MAX_PELLET_PREIS,
    MAX_SCAN_INTERVAL,
    MIN_PELLET_KWH_PER_KG,
    MIN_SCAN_INTERVAL,
    components_from_config,
    fub_role_default,
    fub_roles_for_components,
    normalize_components,
)


async def _test_connection(hass: HomeAssistant, host: str, port: int) -> bool:
    """Prüft, ob die Anlage erreichbar ist und Webservices aktiv sind."""
    client = ETAApiClient(hass, async_get_clientsession(hass), host, port)
    return await client.async_test_connection()


_WAEHLBARE_KOMPONENTEN = [
    key for key, info in COMPONENTS.items() if not info.get("required")
]


def _verbindung_felder(current: dict[str, Any]) -> dict:
    """Die Felder, über die die Anlage erreicht wird."""
    return {
        vol.Required(CONF_HOST, default=current.get(CONF_HOST)): cv.string,
        vol.Required(CONF_PORT, default=current.get(CONF_PORT, DEFAULT_PORT)): cv.port,
    }


def _einstellung_felder(current: dict[str, Any]) -> dict:
    """Komponenten, Abfrageintervall, Freigaben und Heizwert.

    Statt einer Liste fertiger Anlagenschemata wird hier angekreuzt, was an
    der Anlage vorhanden ist. Der Kessel steht nicht zur Wahl, den hat jede
    Anlage.
    """
    vorauswahl = [
        key for key in normalize_components(components_from_config(current))
        if key in _WAEHLBARE_KOMPONENTEN
    ]
    return {
        vol.Required(CONF_COMPONENTS, default=vorauswahl): SelectSelector(
            SelectSelectorConfig(
                options=_WAEHLBARE_KOMPONENTEN,
                multiple=True,
                mode=SelectSelectorMode.LIST,
                translation_key="components",
            )
        ),
        vol.Required(
            CONF_SCAN_INTERVAL,
            default=current.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
        ): vol.All(
            cv.positive_int,
            vol.Range(min=MIN_SCAN_INTERVAL, max=MAX_SCAN_INTERVAL),
        ),
        vol.Required(
            CONF_ENABLE_ERRORS,
            default=current.get(CONF_ENABLE_ERRORS, DEFAULT_ENABLE_ERRORS),
        ): cv.boolean,
        vol.Required(
            CONF_ENABLE_SWITCHES,
            default=current.get(CONF_ENABLE_SWITCHES, DEFAULT_ENABLE_SWITCHES),
        ): cv.boolean,
        vol.Required(
            CONF_PELLET_KWH_PER_KG,
            default=current.get(CONF_PELLET_KWH_PER_KG, DEFAULT_PELLET_KWH_PER_KG),
        ): vol.All(
            vol.Coerce(float),
            vol.Range(min=MIN_PELLET_KWH_PER_KG, max=MAX_PELLET_KWH_PER_KG),
        ),
        vol.Required(
            CONF_PELLET_PREIS,
            default=current.get(CONF_PELLET_PREIS, DEFAULT_PELLET_PREIS),
        ): vol.All(vol.Coerce(float), vol.Range(min=0, max=MAX_PELLET_PREIS)),
    }


def _connection_schema(current: dict[str, Any]) -> vol.Schema:
    """Das vollständige Formular beim ersten Einrichten."""
    return vol.Schema({**_verbindung_felder(current), **_einstellung_felder(current)})


def _reconfigure_schema(current: dict[str, Any]) -> vol.Schema:
    """Neu konfigurieren ändert nur, wo die Anlage zu erreichen ist."""
    return vol.Schema(_verbindung_felder(current))


def _options_schema(current: dict[str, Any]) -> vol.Schema:
    """Konfigurieren ändert alles außer der Adresse der Anlage."""
    return vol.Schema(_einstellung_felder(current))


def _fub_names_schema(roles: list[str], defaults: dict[str, str]) -> vol.Schema:
    """Formular zur Bestätigung/Änderung der Funktionsblock-Namen.

    Jeder FUB kann an der Steuerung umbenannt werden - die Felder sind mit
    den ETA-Standardnamen vorbelegt und können überschrieben werden.
    """
    return vol.Schema(
        {
            vol.Required(
                role, default=defaults.get(role) or fub_role_default(role, roles)
            ): cv.string
            for role in roles
        }
    )


class ETAConfigFlow(ConfigFlow, domain=DOMAIN):
    """Einrichtung der Integration in zwei Schritten.

    Ab Unterversion 2 stehen IP-Adresse und Port nur noch in den Daten des
    Eintrags, alle übrigen Einstellungen in seinen Optionen. Vorher konnten
    beide an beiden Stellen stehen - siehe async_migrate_entry.
    """

    VERSION = 1
    MINOR_VERSION = 2

    def __init__(self) -> None:
        self._data: dict[str, Any] = {}

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ändert IP-Adresse und Port, etwa nach einem Wechsel im Heimnetz.

        Alle anderen Einstellungen gehören zu Konfigurieren. Stünden sie an
        beiden Stellen, könnte die eine die andere still überdecken.
        """
        eintrag = self._get_reconfigure_entry()
        errors: dict[str, str] = {}

        if user_input is not None:
            host = user_input[CONF_HOST]
            port = user_input[CONF_PORT]
            neue_id = f"{host}:{port}"
            if (
                neue_id != eintrag.unique_id
                and self.hass.config_entries.async_entry_for_domain_unique_id(
                    DOMAIN, neue_id
                )
            ):
                return self.async_abort(reason="already_configured")

            if await _test_connection(self.hass, host, port):
                return self.async_update_reload_and_abort(
                    eintrag,
                    unique_id=neue_id,
                    data_updates={CONF_HOST: host, CONF_PORT: port},
                )
            errors["base"] = "cannot_connect"

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=_reconfigure_schema(user_input or dict(eintrag.data)),
            errors=errors,
        )

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            host = user_input[CONF_HOST]
            port = user_input[CONF_PORT]

            await self.async_set_unique_id(f"{host}:{port}")
            self._abort_if_unique_id_configured()

            if await _test_connection(self.hass, host, port):
                self._data = {
                    **user_input,
                    CONF_COMPONENTS: normalize_components(
                        user_input.get(CONF_COMPONENTS)
                    ),
                }
                if self._data.get(CONF_ENABLE_SWITCHES):
                    return await self.async_step_switch_warning()
                return await self.async_step_fub_names()
            errors["base"] = "cannot_connect"

        return self.async_show_form(
            step_id="user",
            data_schema=_connection_schema(user_input or {}),
            errors=errors,
        )

    async def async_step_switch_warning(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Lässt den Schreibzugriff ausdrücklich bestätigen.

        Erscheint nur, wenn Schalter eingeschaltet werden.
        """
        if user_input is not None:
            return await self.async_step_fub_names()
        return self.async_show_form(step_id="switch_warning")

    async def async_step_fub_names(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        roles = fub_roles_for_components(self._data[CONF_COMPONENTS])

        if user_input is not None:
            return self.async_create_entry(
                title="ETA Heizung",
                data={
                    **self._data,
                    CONF_FUB_NAMES: {role: user_input[role] for role in roles},
                },
            )

        return self.async_show_form(
            step_id="fub_names",
            data_schema=_fub_names_schema(roles, {}),
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry) -> OptionsFlow:
        return ETAOptionsFlow()


class ETAOptionsFlow(OptionsFlowWithReload):
    """Nachträgliches Ändern von Komponenten, Freigaben und FUB-Namen."""

    def __init__(self) -> None:
        self._data: dict[str, Any] = {}

    @property
    def _current(self) -> dict[str, Any]:
        return {**self.config_entry.data, **self.config_entry.options}

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            self._data = {
                **user_input,
                CONF_COMPONENTS: normalize_components(
                    user_input.get(CONF_COMPONENTS)
                ),
            }
            if self._data.get(CONF_ENABLE_SWITCHES) and not self._current.get(
                CONF_ENABLE_SWITCHES
            ):
                return await self.async_step_switch_warning()
            return await self.async_step_fub_names()

        return self.async_show_form(
            step_id="init",
            data_schema=_options_schema(self._current),
        )

    async def async_step_switch_warning(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Wie im Einrichtungsdialog: Schreibzugriff bestätigen lassen."""
        if user_input is not None:
            return await self.async_step_fub_names()
        return self.async_show_form(step_id="switch_warning")

    async def async_step_fub_names(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        roles = fub_roles_for_components(self._data[CONF_COMPONENTS])

        if user_input is not None:
            return self.async_create_entry(
                title="",
                data={
                    **self._data,
                    CONF_FUB_NAMES: {role: user_input[role] for role in roles},
                },
            )

        return self.async_show_form(
            step_id="fub_names",
            data_schema=_fub_names_schema(
                roles, self._current.get(CONF_FUB_NAMES, {})
            ),
        )
