import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
import homeassistant.helpers.config_validation as cv

from .const import DOMAIN, DEFAULT_PORT, SCHEMAS, SCHEMA_FUB_ROLES, fub_role_default


async def _test_connection(hass, host, port):
    session = async_get_clientsession(hass)
    try:
        async with session.get(f"http://{host}:{port}/user/menu", timeout=5) as response:
            return response.status == 200
    except Exception:
        return False


def _fub_names_schema(roles, defaults):
    """Baut das Formular zur Bestätigung/Änderung der FUB-Namen.

    FUB = Funktionsblock. Jeder FUB kann vom Nutzer an der Steuerung
    umbenannt werden - die Felder sind mit den ETA-Standardnamen
    vorbelegt und können bei Bedarf überschrieben werden.
    """
    fields = {}
    for role in roles:
        default_name = defaults.get(role) or fub_role_default(role, roles)
        fields[vol.Required(role, default=default_name)] = cv.string
    return vol.Schema(fields)


class ETAConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Verwaltet den Setup-Flow für ETA Webservices mit Schemaauswahl."""
    VERSION = 1

    def __init__(self):
        self._data = {}

    async def async_step_user(self, user_input=None):
        errors = {}

        if user_input is not None:
            host = user_input["host"]
            port = user_input["port"]

            await self.async_set_unique_id(f"{host}:{port}")
            self._abort_if_unique_id_configured()

            if await _test_connection(self.hass, host, port):
                self._data = user_input
                return await self.async_step_fub_names()
            errors["base"] = "cannot_connect"

        data_schema = vol.Schema({
            vol.Required("host"): cv.string,
            vol.Required("port", default=DEFAULT_PORT): cv.port,
            vol.Required("schema", default="Kessel + Puffer"): vol.In(list(SCHEMAS.keys())),
        })

        return self.async_show_form(
            step_id="user",
            data_schema=data_schema,
            errors=errors
        )

    async def async_step_fub_names(self, user_input=None):
        roles = SCHEMA_FUB_ROLES.get(self._data["schema"], [])

        if user_input is not None:
            fub_names = {role: user_input[role] for role in roles}
            return self.async_create_entry(
                title=f"ETA Heizung ({self._data['schema']})",
                data={**self._data, "fub_names": fub_names},
            )

        return self.async_show_form(
            step_id="fub_names",
            data_schema=_fub_names_schema(roles, {}),
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return ETAOptionsFlow(config_entry)


class ETAOptionsFlow(config_entries.OptionsFlow):
    """Erlaubt das nachträgliche Ändern von Host/Port/Schema/FUB-Namen ohne Neueinrichtung."""

    def __init__(self, config_entry):
        self.config_entry = config_entry
        self._data = {}

    async def async_step_init(self, user_input=None):
        errors = {}
        current = {**self.config_entry.data, **self.config_entry.options}

        if user_input is not None:
            host = user_input["host"]
            port = user_input["port"]

            if await _test_connection(self.hass, host, port):
                self._data = user_input
                return await self.async_step_fub_names()
            errors["base"] = "cannot_connect"

        data_schema = vol.Schema({
            vol.Required("host", default=current.get("host")): cv.string,
            vol.Required("port", default=current.get("port", DEFAULT_PORT)): cv.port,
            vol.Required("schema", default=current.get("schema", "Kessel + Puffer")): vol.In(list(SCHEMAS.keys())),
        })

        return self.async_show_form(
            step_id="init",
            data_schema=data_schema,
            errors=errors
        )

    async def async_step_fub_names(self, user_input=None):
        current = {**self.config_entry.data, **self.config_entry.options}
        current_fub_names = current.get("fub_names", {})
        roles = SCHEMA_FUB_ROLES.get(self._data["schema"], [])

        if user_input is not None:
            fub_names = {role: user_input[role] for role in roles}
            return self.async_create_entry(title="", data={**self._data, "fub_names": fub_names})

        return self.async_show_form(
            step_id="fub_names",
            data_schema=_fub_names_schema(roles, current_fub_names),
        )
