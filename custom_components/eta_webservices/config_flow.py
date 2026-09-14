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
    CONF_FUB_NAMES,
    CONF_SCAN_INTERVAL,
    DEFAULT_PORT,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    MAX_SCAN_INTERVAL,
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


def _connection_schema(current: dict[str, Any]) -> vol.Schema:
    """Formular für Host, Port, Komponenten und Abfrageintervall.

    Statt einer Liste fertiger Anlagenschemata wird hier angekreuzt, was an
    der Anlage vorhanden ist. Der Kessel steht nicht zur Wahl, den hat jede
    Anlage.
    """
    vorauswahl = [
        key for key in normalize_components(components_from_config(current))
        if key in _WAEHLBARE_KOMPONENTEN
    ]
    return vol.Schema(
        {
            vol.Required(CONF_HOST, default=current.get(CONF_HOST)): cv.string,
            vol.Required(
                CONF_PORT, default=current.get(CONF_PORT, DEFAULT_PORT)
            ): cv.port,
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
        }
    )


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
    """Einrichtung der Integration in zwei Schritten."""

    VERSION = 1

    def __init__(self) -> None:
        self._data: dict[str, Any] = {}

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
                return await self.async_step_fub_names()
            errors["base"] = "cannot_connect"

        return self.async_show_form(
            step_id="user",
            data_schema=_connection_schema(user_input or {}),
            errors=errors,
        )

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
    """Nachträgliches Ändern von Verbindung, Schema und FUB-Namen."""

    def __init__(self) -> None:
        self._data: dict[str, Any] = {}

    @property
    def _current(self) -> dict[str, Any]:
        return {**self.config_entry.data, **self.config_entry.options}

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            if await _test_connection(
                self.hass, user_input[CONF_HOST], user_input[CONF_PORT]
            ):
                self._data = {
                    **user_input,
                    CONF_COMPONENTS: normalize_components(
                        user_input.get(CONF_COMPONENTS)
                    ),
                }
                return await self.async_step_fub_names()
            errors["base"] = "cannot_connect"

        return self.async_show_form(
            step_id="init",
            data_schema=_connection_schema(user_input or self._current),
            errors=errors,
        )

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
