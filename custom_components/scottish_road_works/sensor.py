"""Sensor platform for the Scottish Road Works integration."""

from __future__ import annotations

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_POSTCODE, DOMAIN
from .coordinator import RoadWorksCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: RoadWorksCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        [
            RoadWorksSensor(coordinator, entry, "active", "Active Road Works"),
            RoadWorksSensor(coordinator, entry, "upcoming", "Upcoming Road Works"),
        ]
    )


class RoadWorksSensor(CoordinatorEntity[RoadWorksCoordinator], SensorEntity):
    _attr_has_entity_name = True
    _attr_native_unit_of_measurement = "works"

    def __init__(
        self,
        coordinator: RoadWorksCoordinator,
        entry: ConfigEntry,
        kind: str,
        name: str,
    ) -> None:
        super().__init__(coordinator)
        self._kind = kind
        self._attr_name = name
        self._attr_unique_id = f"{entry.entry_id}_{kind}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=f"Scottish Road Works ({entry.data[CONF_POSTCODE]})",
        )

    @property
    def native_value(self) -> int | None:
        if not self.coordinator.data:
            return None
        return len(getattr(self.coordinator.data, self._kind))

    @property
    def extra_state_attributes(self) -> dict:
        if not self.coordinator.data:
            return {}
        works = getattr(self.coordinator.data, self._kind)
        return {
            "search_radius_m": self.coordinator._radius_m,
            "works": [
                {
                    "reference": w.reference,
                    "street": w.street_name,
                    "promoter": w.promoter,
                    "type": w.works_type,
                    "start_date": w.start_date.isoformat() if w.start_date else None,
                    "end_date": w.end_date.isoformat() if w.end_date else None,
                    "status": w.status,
                    "distance_m": w.distance_m,
                }
                for w in works[:20]
            ],
        }
