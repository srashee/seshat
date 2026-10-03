"""Configure one front-door recognition source through Home Assistant UI."""

import aiohttp
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    EntitySelector,
    EntitySelectorConfig,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)
from yarl import URL

from .client import Client
from .const import DEFAULT_ENTITY, DOMAIN


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None):
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()
        errors = {}
        if user_input is not None:
            try:
                url = URL(user_input["url"])
                if (
                    url.scheme not in ("http", "https")
                    or not url.host
                    or url.user
                    or url.query_string
                    or url.fragment
                    or url.path not in ("", "/")
                ):
                    raise ValueError("Use the local add-on base URL")
                if len(user_input["api_key"]) < 32:
                    raise ValueError("Key is too short")
                if not user_input["image_entity"].startswith("image."):
                    raise ValueError("Choose an image entity")
                await Client(async_get_clientsession(self.hass), str(url), user_input["api_key"]).check()
            except (aiohttp.ClientError, TimeoutError):
                errors["base"] = "cannot_connect"
            except ValueError:
                errors["base"] = "invalid_config"
            else:
                return self.async_create_entry(title="Seshat Front Door", data=user_input)
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required("url", default="http://local-seshat:8000"): str,
                    vol.Required("api_key"): TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD)),
                    vol.Required("image_entity", default=DEFAULT_ENTITY): EntitySelector(
                        EntitySelectorConfig(domain="image")
                    ),
                    vol.Required("debounce_ms", default=1000): vol.All(
                        vol.Coerce(int), vol.Range(min=0, max=10000)
                    ),
                }
            ),
            errors=errors,
        )
