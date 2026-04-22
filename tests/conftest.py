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
    "homeassistant.helpers.storage",
    "homeassistant.helpers.update_coordinator",
    "voluptuous",
]

for _mod in _HA_MODULES:
    sys.modules.setdefault(_mod, MagicMock())

# callback is used as a decorator — make it a no-op passthrough so the wrapped
# function remains callable in tests.
sys.modules["homeassistant.core"].callback = lambda f: f


class _CoordinatorEntity:
    def __init__(self, coordinator, *args, **kwargs):
        self.coordinator = coordinator

    @classmethod
    def __class_getitem__(cls, item):
        return cls


sys.modules["homeassistant.helpers.update_coordinator"].CoordinatorEntity = _CoordinatorEntity
sys.modules["homeassistant.components.geo_location"].GeolocationEvent = object
