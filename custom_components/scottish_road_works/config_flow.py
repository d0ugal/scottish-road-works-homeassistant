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
)

from .const import (
    CONF_EASTING,
    CONF_LAT,
    CONF_LNG,
    CONF_NORTHING,
    CONF_RADIUS_KM,
    DEFAULT_RADIUS_KM,
    DOMAIN,
    MAX_RADIUS_KM,
)

_LOGGER = logging.getLogger(__name__)
_POSTCODES_IO_REVERSE = "https://api.postcodes.io/postcodes?lon={lon}&lat={lat}&limit=1"


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            lat = self.hass.config.latitude
            lon = self.hass.config.longitude
            radius_km = user_input[CONF_RADIUS_KM]
            try:
                session = async_get_clientsession(self.hass)
                url = _POSTCODES_IO_REVERSE.format(lon=lon, lat=lat)
                async with session.get(url) as resp:
                    resp.raise_for_status()
                    data = await resp.json()
                    results = data.get("result") or []
                    if not results:
                        errors["base"] = "location_not_found"
                    else:
                        result = results[0]
                        easting = result.get("eastings")
                        northing = result.get("northings")
                        if not all((easting, northing)):
                            errors["base"] = "location_not_found"
                        else:
                            await self.async_set_unique_id("home")
                            self._abort_if_unique_id_configured()
                            return self.async_create_entry(
                                title="Home",
                                data={
                                    CONF_LAT: float(lat),
                                    CONF_LNG: float(lon),
                                    CONF_EASTING: float(easting),
                                    CONF_NORTHING: float(northing),
                                    CONF_RADIUS_KM: radius_km,
                                },
                            )
            except Exception:
                _LOGGER.exception("Error looking up home coordinates")
                errors["base"] = "cannot_connect"

        schema = vol.Schema(
            {
                vol.Optional(CONF_RADIUS_KM, default=DEFAULT_RADIUS_KM): NumberSelector(
                    NumberSelectorConfig(
                        min=0.25,
                        max=MAX_RADIUS_KM,
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
