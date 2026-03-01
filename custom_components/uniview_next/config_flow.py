"""Config flow for Uniview Next integration."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_PORT, CONF_USERNAME
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.selector import (
    BooleanSelector,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .const import (
    CONF_SET_NOTIFICATION_HOST,
    CONF_USE_HTTPS,
    DEFAULT_PORT,
    DOMAIN,
)
from .isapi import UnivewDevice, UnivewError

_LOGGER = logging.getLogger(__name__)


class UnivewConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Uniview Next."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            device = UnivewDevice(
                host=user_input[CONF_HOST],
                port=int(user_input[CONF_PORT]),
                username=user_input[CONF_USERNAME],
                password=user_input[CONF_PASSWORD],
                use_https=user_input.get(CONF_USE_HTTPS, False),
            )
            try:
                info = await device.get_device_info()
                _LOGGER.debug("DeviceInfo response: %s", info)

                # info may be empty dict if device returned unexpected format
                serial = info.get("SerialNumber") or user_input[CONF_HOST]
                model = info.get("DeviceModel") or "Uniview Device"

                await self.async_set_unique_id(serial)
                self._abort_if_unique_id_configured()

                return self.async_create_entry(
                    title=f"{model} ({user_input[CONF_HOST]})",
                    data={
                        **user_input,
                        "serial": serial,
                        "model": model,
                        "manufacturer": info.get("Manufacturer", "Uniview"),
                        "firmware": info.get("FirmwareVersion", ""),
                    },
                )
            except UnivewError as err:
                _LOGGER.error(
                    "Cannot connect to Uniview device at %s:%s — %s",
                    user_input[CONF_HOST],
                    user_input[CONF_PORT],
                    err,
                )
                errors["base"] = "cannot_connect"
            except Exception:  # pylint: disable=broad-except
                _LOGGER.exception("Unexpected exception connecting to Uniview")
                errors["base"] = "unknown"
            finally:
                await device.close()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_HOST): TextSelector(
                        TextSelectorConfig(type=TextSelectorType.TEXT)
                    ),
                    vol.Required(CONF_PORT, default=DEFAULT_PORT): NumberSelector(
                        NumberSelectorConfig(min=1, max=65535, mode=NumberSelectorMode.BOX)
                    ),
                    vol.Required(CONF_USERNAME, default="admin"): TextSelector(
                        TextSelectorConfig(type=TextSelectorType.TEXT)
                    ),
                    vol.Required(CONF_PASSWORD): TextSelector(
                        TextSelectorConfig(type=TextSelectorType.PASSWORD)
                    ),
                    vol.Optional(CONF_USE_HTTPS, default=False): BooleanSelector(),
                    vol.Optional(CONF_SET_NOTIFICATION_HOST, default=True): BooleanSelector(),
                }
            ),
            errors=errors,
        )
