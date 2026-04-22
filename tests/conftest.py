"""Pytest configuration: stub out homeassistant so pure-Python tests run without it."""

import sys
from unittest.mock import MagicMock

_HA_MODULES = [
    "homeassistant",
    "homeassistant.components",
    "homeassistant.components.geo_location",
    "homeassistant.components.sensor",
    "homeassistant.config_entries",
    "homeassistant.const",
    "homeassistant.core",
    "homeassistant.data_entry_flow",
    "homeassistant.helpers",
    "homeassistant.helpers.aiohttp_client",
    "homeassistant.helpers.device_registry",
    "homeassistant.helpers.entity_platform",
    "homeassistant.helpers.selector",
    "homeassistant.helpers.update_coordinator",
    "voluptuous",
]

for _mod in _HA_MODULES:
    sys.modules.setdefault(_mod, MagicMock())
