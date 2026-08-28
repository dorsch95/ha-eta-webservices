import voluptuous as vol
import aiohttp
from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
import homeassistant.helpers.config_validation as cv

from .const import DOMAIN, DEFAULT_PORT

class ETAConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Verwaltet den Setup-Flow für ETA Webservices."""
    VERSION = 1

    async def async_step_user(self, user_input=None):
        """Erster Schritt bei der manuellen Einrichtung."""
        errors = {}

        if user_input is not None:
            host = user_input["host"]
            port = user_input["port"]
            
            # Teste die Verbindung, bevor die Integration gespeichert wird
            session = async_get_clientsession(self.hass)
            try:
                async with session.get(f"http://{host}:{port}/user/menu", timeout=5) as response:
                    if response.status == 200:
                        return self.async_create_entry(
                            title=f"ETA Heizung ({host})", 
                            data=user_input
                        )
                    else:
                        errors["base"] = "cannot_connect"
            except Exception:
                errors["base"] = "cannot_connect"

        # Definition des Eingabeformulars
        data_schema = vol.Schema({
            vol.Required("host"): cv.string,
            vol.Required("port", default=DEFAULT_PORT): cv.port,
        })

        return self.async_show_form(
            step_id="user", 
            data_schema=data_schema, 
            errors=errors
        )
