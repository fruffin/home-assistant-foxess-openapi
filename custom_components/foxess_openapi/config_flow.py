"""Config flow for the FoxESS OpenAPI integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import CONF_HOST, CONF_NAME
from homeassistant.core import callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import (
    FoxESSAuthError,
    FoxESSCannotConnectError,
    FoxESSOpenApi,
    FoxESSDeviceNotFoundError,
)
from .const import (
    CONF_API_KEY,
    CONF_DEVICE_SN,
    CONF_EXTENDED_PV,
    DEFAULT_API_HOST,
    DEFAULT_NAME,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)


STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_API_KEY): str,
        vol.Required(CONF_DEVICE_SN): str,
        vol.Optional(CONF_NAME, default=DEFAULT_NAME): str,
        vol.Optional(CONF_EXTENDED_PV, default=False): bool,
        vol.Optional(CONF_HOST, default=DEFAULT_API_HOST): str,
    }
)


async def _validate_input(hass, user_input: dict[str, Any]) -> dict[str, Any]:
    """Validate the user input allows us to connect."""
    api = FoxESSOpenApi(
        async_get_clientsession(hass),
        user_input[CONF_API_KEY],
        host=user_input[CONF_HOST],
    )

    try:
        return await api.get_device_detail(user_input[CONF_DEVICE_SN])
    except FoxESSAuthError as err:
        raise InvalidAuth from err
    except FoxESSDeviceNotFoundError as err:
        raise InvalidDevice from err
    except FoxESSCannotConnectError as err:
        raise CannotConnect from err


class FoxESSOpenApiConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for FoxESS OpenAPI."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            user_input[CONF_DEVICE_SN] = user_input[CONF_DEVICE_SN].strip()
            user_input[CONF_API_KEY] = user_input[CONF_API_KEY].strip()
            user_input[CONF_HOST] = user_input[CONF_HOST].rstrip("/")

            await self.async_set_unique_id(user_input[CONF_DEVICE_SN])
            self._abort_if_unique_id_configured()

            try:
                device = await _validate_input(self.hass, user_input)
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except InvalidAuth:
                errors["base"] = "invalid_auth"
            except InvalidDevice:
                errors["device_sn"] = "invalid_device"
            except Exception:  # pylint: disable=broad-except
                _LOGGER.exception(
                    "Unexpected exception while configuring FoxESS OpenAPI"
                )
                errors["base"] = "unknown"
            else:
                title = (
                    device.get("stationName")
                    or device.get("plantName")
                    or user_input[CONF_NAME]
                )
                return self.async_create_entry(title=title, data=user_input)

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        """Create the options flow."""
        return FoxESSOpenApiOptionsFlow(config_entry)


class FoxESSOpenApiOptionsFlow(OptionsFlow):
    """Handle FoxESS OpenAPI options."""

    def __init__(self, config_entry: ConfigEntry) -> None:
        """Initialize options flow."""
        self._config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage options."""
        if user_input is not None:
            return self.async_create_entry(
                title="", data={**self._config_entry.options, **user_input}
            )

        options = self._config_entry.options
        data = self._config_entry.data
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_EXTENDED_PV,
                        default=options.get(
                            CONF_EXTENDED_PV, data.get(CONF_EXTENDED_PV, False)
                        ),
                    ): bool,
                }
            ),
        )


class CannotConnect(HomeAssistantError):
    """Error to indicate we cannot connect."""


class InvalidAuth(HomeAssistantError):
    """Error to indicate there is invalid auth."""


class InvalidDevice(HomeAssistantError):
    """Error to indicate the configured device serial number is invalid."""
