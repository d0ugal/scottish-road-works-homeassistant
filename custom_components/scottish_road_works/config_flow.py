"""Config flow for the Scottish Road Works integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .const import (
    CONF_EASTING,
    CONF_LAT,
    CONF_LNG,
    CONF_NORTHING,
    CONF_POSTCODE,
    CONF_RADIUS_KM,
    DEFAULT_RADIUS_KM,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)
_POSTCODES_IO = "https://api.postcodes.io/postcodes/{}"


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            postcode = user_input[CONF_POSTCODE].strip().upper().replace(" ", "")
            radius_km = user_input[CONF_RADIUS_KM]
            try:
                session = async_get_clientsession(self.hass)
                async with session.get(_POSTCODES_IO.format(postcode)) as resp:
                    if resp.status == 404:
                        errors["base"] = "invalid_postcode"
                    else:
                        resp.raise_for_status()
                        data = await resp.json()
                        result = data.get("result") or {}
                        lat = result.get("latitude")
                        lng = result.get("longitude")
                        easting = result.get("eastings")
                        northing = result.get("northings")
                        if not all((lat, lng, easting, northing)):
                            errors["base"] = "invalid_postcode"
                        else:
                            display_postcode = result.get("postcode", postcode)
                            await self.async_set_unique_id(display_postcode)
                            self._abort_if_unique_id_configured()
                            return self.async_create_entry(
                                title=display_postcode,
                                data={
                                    CONF_POSTCODE: display_postcode,
                                    CONF_LAT: float(lat),  # type: ignore[arg-type]
                                    CONF_LNG: float(lng),  # type: ignore[arg-type]
                                    CONF_EASTING: float(easting),  # type: ignore[arg-type]
                                    CONF_NORTHING: float(northing),  # type: ignore[arg-type]
                                    CONF_RADIUS_KM: radius_km,
                                },
                            )
            except Exception:
                _LOGGER.exception("Error looking up postcode")
                errors["base"] = "cannot_connect"

        schema = vol.Schema(
            {
                vol.Required(CONF_POSTCODE): TextSelector(
                    TextSelectorConfig(type=TextSelectorType.TEXT)
                ),
                vol.Optional(CONF_RADIUS_KM, default=DEFAULT_RADIUS_KM): NumberSelector(
                    NumberSelectorConfig(
                        min=0.25,
                        max=10,
                        step=0.25,
                        mode=NumberSelectorMode.BOX,
                        unit_of_measurement="km",
                    )
                ),
            }
        )
        return self.async_show_form(
            step_id="user",
            data_schema=schema,
            errors=errors,
        )
