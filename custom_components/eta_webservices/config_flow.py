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
    EntitySelector,
    EntitySelectorConfig,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)

from .api import ETAApiClient, ETAApiError
from .prognose_koordinator import einzige_wetter_entitaet
from .uri_discovery import async_discover_uris
from .const import (
    COMPONENTS,
    CONF_COMPONENTS,
    CONF_ENABLE_ERRORS,
    CONF_ENABLE_SWITCHES,
    CONF_FUB_NAMES,
    CONF_PELLET_KWH_PER_KG,
    CONF_PELLET_PREIS,
    CONF_PROGNOSE,
    CONF_SCAN_INTERVAL,
    CONF_WETTER,
    CONF_ZEITRAEUME,
    DEFAULT_ENABLE_ERRORS,
    DEFAULT_ENABLE_SWITCHES,
    DEFAULT_PELLET_KWH_PER_KG,
    DEFAULT_PELLET_PREIS,
    DEFAULT_PORT,
    DEFAULT_PROGNOSE,
    DEFAULT_ZEITRAEUME,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    MAX_PELLET_KWH_PER_KG,
    MAX_PELLET_PREIS,
    MAX_PUFFER_VOLUMEN,
    MAX_SCAN_INTERVAL,
    MIN_PELLET_KWH_PER_KG,
    MIN_SCAN_INTERVAL,
    PUFFER_SPEICHER,
    components_from_config,
    fub_role_default,
    fub_roles_for_components,
    normalize_components,
    puffer_volumen_schluessel,
)


async def _test_connection(hass: HomeAssistant, host: str, port: int) -> bool:
    """Prüft, ob die Anlage erreichbar ist und Webservices aktiv sind."""
    client = ETAApiClient(hass, async_get_clientsession(hass), host, port)
    return await client.async_test_connection()


async def _puffer_ohne_volumen(
    hass: HomeAssistant,
    host: str | None,
    port: int,
    fub_names: dict[str, str],
    komponenten: list[str],
) -> list[str]:
    """Die angekreuzten Puffer, die ihr effektives Volumen nicht melden.

    Das ist der ältere Funktionsblock "Puffer": Er kennt das Volumen am
    Display, gibt es aber nicht an die Webservices weiter. PufferFlex nennt
    es im Menübaum. Gefragt wird nur für Puffer, deren Fühler gefunden
    wurden - einer, den die Erkennung gar nicht findet, hätte mit dem
    Volumen nichts gewonnen. Ist der Menübaum nicht lesbar, wird nicht
    gefragt.
    """
    if not host:
        return []
    client = ETAApiClient(hass, async_get_clientsession(hass), host, port)
    try:
        gefunden, _ = await async_discover_uris(client, fub_names)
    except ETAApiError:
        return []
    return [
        komponente
        for komponente in PUFFER_SPEICHER
        if komponente in komponenten
        and f"{komponente}_volumen" not in gefunden
        and any(key.startswith(f"{komponente}_fuehler_") for key in gefunden)
    ]


def _puffer_schema(komponenten: list[str], current: dict[str, Any]) -> vol.Schema:
    """Je Puffer ohne gemeldetes Volumen ein Feld für seine Liter, 0 = unbekannt."""
    return vol.Schema(
        {
            vol.Required(
                puffer_volumen_schluessel(komponente),
                default=int(current.get(puffer_volumen_schluessel(komponente)) or 0),
            ): vol.All(vol.Coerce(int), vol.Range(min=0, max=MAX_PUFFER_VOLUMEN))
            for komponente in komponenten
        }
    )


_WAEHLBARE_KOMPONENTEN = [
    key for key, info in COMPONENTS.items() if not info.get("required")
]


def _verbindung_felder(current: dict[str, Any]) -> dict:
    """Die Felder, über die die Anlage erreicht wird."""
    return {
        vol.Required(CONF_HOST, default=current.get(CONF_HOST)): cv.string,
        vol.Required(CONF_PORT, default=current.get(CONF_PORT, DEFAULT_PORT)): cv.port,
    }


def wetter_vorschlag(hass: HomeAssistant, current: dict[str, Any]) -> str | None:
    """Die Wetter-Entität, die im Formular vorausgewählt ist.

    Wer schon eine gewählt oder das Feld bewusst geleert hat, bekommt das
    wieder angezeigt. Sonst die einzige Wetter-Entität, falls es genau
    eine gibt - so wie sie die Prognose auch von selbst nehmen würde.
    """
    if CONF_WETTER in current:
        return current[CONF_WETTER] or None
    return einzige_wetter_entitaet(hass)


def _einstellung_felder(current: dict[str, Any], wetter: str | None = None) -> dict:
    """Komponenten, Abfrageintervall, Freigaben, Zusatzfunktionen, Heizwert, Preis, Wetter.

    Verbrauch je Zeitraum und Prognose sind abwählbar - wer nur die
    Messwerte will, bekommt dann auch nur die.

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
            CONF_ZEITRAEUME,
            default=current.get(CONF_ZEITRAEUME, DEFAULT_ZEITRAEUME),
        ): cv.boolean,
        vol.Required(
            CONF_PROGNOSE,
            default=current.get(CONF_PROGNOSE, DEFAULT_PROGNOSE),
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
        vol.Optional(
            CONF_WETTER, description={"suggested_value": wetter}
        ): EntitySelector(EntitySelectorConfig(domain="weather")),
    }


def _connection_schema(current: dict[str, Any], wetter: str | None = None) -> vol.Schema:
    """Das vollständige Formular beim ersten Einrichten."""
    return vol.Schema(
        {**_verbindung_felder(current), **_einstellung_felder(current, wetter)}
    )


def _reconfigure_schema(current: dict[str, Any]) -> vol.Schema:
    """Neu konfigurieren ändert nur, wo die Anlage zu erreichen ist."""
    return vol.Schema(_verbindung_felder(current))


def _options_schema(current: dict[str, Any], wetter: str | None = None) -> vol.Schema:
    """Konfigurieren ändert alles außer der Adresse der Anlage."""
    return vol.Schema(_einstellung_felder(current, wetter))


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
        self._ohne_volumen: list[str] = []

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

        eingabe = user_input or {}
        return self.async_show_form(
            step_id="user",
            data_schema=_connection_schema(
                eingabe, eingabe.get(CONF_WETTER) or wetter_vorschlag(self.hass, {})
            ),
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
            self._data[CONF_FUB_NAMES] = {role: user_input[role] for role in roles}
            self._ohne_volumen = await _puffer_ohne_volumen(
                self.hass,
                self._data[CONF_HOST],
                self._data[CONF_PORT],
                self._data[CONF_FUB_NAMES],
                self._data[CONF_COMPONENTS],
            )
            if self._ohne_volumen:
                return await self.async_step_puffer()
            return self.async_create_entry(title="ETA Heizung", data=self._data)

        return self.async_show_form(
            step_id="fub_names",
            data_schema=_fub_names_schema(roles, {}),
        )

    async def async_step_puffer(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Fragt nach den Litern der Puffer, die ihr Volumen nicht melden."""
        if user_input is not None:
            return self.async_create_entry(
                title="ETA Heizung", data={**self._data, **user_input}
            )
        return self.async_show_form(
            step_id="puffer", data_schema=_puffer_schema(self._ohne_volumen, {})
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry) -> OptionsFlow:
        return ETAOptionsFlow()


class ETAOptionsFlow(OptionsFlowWithReload):
    """Nachträgliches Ändern von Komponenten, Freigaben und FUB-Namen."""

    def __init__(self) -> None:
        self._data: dict[str, Any] = {}
        self._ohne_volumen: list[str] = []

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
                CONF_WETTER: user_input.get(CONF_WETTER, ""),
            }
            if self._data.get(CONF_ENABLE_SWITCHES) and not self._current.get(
                CONF_ENABLE_SWITCHES
            ):
                return await self.async_step_switch_warning()
            return await self.async_step_fub_names()

        return self.async_show_form(
            step_id="init",
            data_schema=_options_schema(
                self._current, wetter_vorschlag(self.hass, self._current)
            ),
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
            self._data[CONF_FUB_NAMES] = {role: user_input[role] for role in roles}
            self._ohne_volumen = await _puffer_ohne_volumen(
                self.hass,
                self._current.get(CONF_HOST),
                self._current.get(CONF_PORT, DEFAULT_PORT),
                self._data[CONF_FUB_NAMES],
                self._data[CONF_COMPONENTS],
            )
            if self._ohne_volumen:
                return await self.async_step_puffer()
            return self.async_create_entry(title="", data=self._data)

        return self.async_show_form(
            step_id="fub_names",
            data_schema=_fub_names_schema(
                roles, self._current.get(CONF_FUB_NAMES, {})
            ),
        )

    async def async_step_puffer(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Wie im Einrichtungsdialog, vorbelegt mit den bisherigen Litern."""
        if user_input is not None:
            return self.async_create_entry(title="", data={**self._data, **user_input})
        return self.async_show_form(
            step_id="puffer",
            data_schema=_puffer_schema(self._ohne_volumen, self._current),
        )
