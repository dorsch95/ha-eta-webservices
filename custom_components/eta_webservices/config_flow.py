import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
import homeassistant.helpers.config_validation as cv

from .const import DOMAIN, DEFAULT_PORT, SCHEMAS


async def _test_connection(hass, host, port):
    session = async_get_clientsession(hass)
    try:
        async with session.get(f"http://{host}:{port}/user/menu", timeout=5) as response:
            return response.status == 200
    except Exception:
        return False


class ETAConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Verwaltet den Setup-Flow für ETA Webservices mit Schemaauswahl."""
    VERSION = 1

    async def async_step_user(self, user_input=None):
        errors = {}

        if user_input is not None:
            host = user_input["host"]
            port = user_input["port"]

            await self.async_set_unique_id(f"{host}:{port}")
            self._abort_if_unique_id_configured()

            if await _test_connection(self.hass, host, port):
                return self.async_create_entry(
                    title=f"ETA Heizung ({user_input['schema']})",
                    data=user_input
                )
            errors["base"] = "cannot_connect"

        # Definition des Eingabeformulars inklusive Dropdown für Schemen
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

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return ETAOptionsFlow(config_entry)


class ETAOptionsFlow(config_entries.OptionsFlow):
    """Erlaubt das nachträgliche Ändern von Host/Port/Schema ohne Neueinrichtung."""

    def __init__(self, config_entry):
        self.config_entry = config_entry

    async def async_step_init(self, user_input=None):
        errors = {}
        current = {**self.config_entry.data, **self.config_entry.options}

        if user_input is not None:
            host = user_input["host"]
            port = user_input["port"]

            if await _test_connection(self.hass, host, port):
                return self.async_create_entry(title="", data=user_input)
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
