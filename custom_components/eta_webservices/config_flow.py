import voluptuous as vol
import aiohttp
from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
import homeassistant.helpers.config_validation as cv

from .const import DOMAIN, DEFAULT_PORT, SCHEMAS

class ETAConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Verwaltet den Setup-Flow für ETA Webservices mit Schemaauswahl."""
    VERSION = 1

    async def async_step_user(self, user_input=None):
        errors = {}

        if user_input is not None:
            host = user_input["host"]
            port = user_input["port"]
            
            session = async_get_clientsession(self.hass)
            try:
                # Teste ob die Heizung unter der IP erreichbar ist
                async with session.get(f"http://{host}:{port}/user/menu", timeout=5) as response:
                    if response.status == 200:
                        return self.async_create_entry(
                            title=f"ETA Heizung ({user_input['schema']})", 
                            data=user_input
                        )
                    else:
                        errors["base"] = "cannot_connect"
            except Exception:
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
