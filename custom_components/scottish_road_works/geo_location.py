"""Geo location platform for Scottish Road Works."""

from __future__ import annotations

from homeassistant.components.geo_location import GeolocationEvent
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import RoadWork, RoadWorksCoordinator

SOURCE_ACTIVE = "scottish_road_works_active"
SOURCE_UPCOMING = "scottish_road_works_upcoming"


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: RoadWorksCoordinator = hass.data[DOMAIN][entry.entry_id]
    tracked: dict[str, RoadWorksGeoLocation] = {}

    @callback
    def _update_entities() -> None:
        if not coordinator.data:
            return

        all_works = [
            w
            for w in coordinator.data.active + coordinator.data.upcoming
            if w.lat is not None and w.lng is not None
        ]
        current_refs = {w.reference for w in all_works}

        stale = [ref for ref in tracked if ref not in current_refs]
        for ref in stale:
            hass.async_create_task(tracked.pop(ref).async_remove())

        new_entities: list[RoadWorksGeoLocation] = []
        for work in all_works:
            if work.reference not in tracked:
                entity = RoadWorksGeoLocation(coordinator, work.reference, entry.entry_id)
                tracked[work.reference] = entity
                new_entities.append(entity)

        if new_entities:
            async_add_entities(new_entities)

    entry.async_on_unload(coordinator.async_add_listener(_update_entities))
    _update_entities()


class RoadWorksGeoLocation(CoordinatorEntity[RoadWorksCoordinator], GeolocationEvent):
    _attr_should_poll = False

    def __init__(
        self,
        coordinator: RoadWorksCoordinator,
        reference: str,
        entry_id: str,
    ) -> None:
        super().__init__(coordinator)
        self._reference = reference
        self._attr_unique_id = f"{entry_id}_{reference}"

    def _work(self) -> RoadWork | None:
        if not self.coordinator.data:
            return None
        for w in self.coordinator.data.active + self.coordinator.data.upcoming:
            if w.reference == self._reference:
                return w
        return None

    @property
    def source(self) -> str:
        if self.coordinator.data:
            for w in self.coordinator.data.active:
                if w.reference == self._reference:
                    return SOURCE_ACTIVE
        return SOURCE_UPCOMING

    @property
    def name(self) -> str:
        w = self._work()
        if not w:
            return self._reference
        street = w.street_name or self._reference
        return f"{street} ({w.works_type})" if w.works_type else street

    @property
    def latitude(self) -> float | None:
        w = self._work()
        return w.lat if w else None

    @property
    def longitude(self) -> float | None:
        w = self._work()
        return w.lng if w else None

    @property
    def distance(self) -> float | None:
        w = self._work()
        return w.distance_m / 1000.0 if w and w.distance_m is not None else None

    @property
    def extra_state_attributes(self) -> dict:
        w = self._work()
        if not w:
            return {}
        return {
            "reference": w.reference,
            "promoter": w.promoter,
            "type": w.works_type,
            "status": w.status,
            "start_date": w.start_date.isoformat() if w.start_date else None,
            "end_date": w.end_date.isoformat() if w.end_date else None,
            "distance_m": w.distance_m,
        }
