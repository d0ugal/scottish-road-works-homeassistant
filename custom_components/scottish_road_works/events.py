"""Fire HA events when new road works appear near home."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.storage import Store

from .const import DOMAIN
from .coordinator import RoadWorksCoordinator

EVENT_NEW_WORK = "scottish_road_works_new_work"
_STORAGE_VERSION = 1


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    coordinator: RoadWorksCoordinator = hass.data[DOMAIN][entry.entry_id]
    store = Store(hass, _STORAGE_VERSION, f"{DOMAIN}.{entry.entry_id}.seen_refs")

    stored = await store.async_load()
    seen: set[str] = set(stored or [])

    # Silently absorb whatever is in the feed right now so that existing works
    # don't fire events on every HA restart.
    if coordinator.data:
        seen |= {
            w.reference for w in coordinator.data.active + coordinator.data.upcoming
        }
        await store.async_save(list(seen))

    @callback
    def _on_update() -> None:
        nonlocal seen
        if not coordinator.data:
            return

        all_works = coordinator.data.active + coordinator.data.upcoming
        current_refs = {w.reference for w in all_works}
        new_refs = current_refs - seen

        for work in all_works:
            if work.reference not in new_refs:
                continue
            hass.bus.async_fire(
                EVENT_NEW_WORK,
                {
                    "reference": work.reference,
                    "street_name": work.street_name,
                    "promoter": work.promoter,
                    "works_type": work.works_type,
                    "status": work.status,
                    "start_date": (
                        work.start_date.isoformat() if work.start_date else None
                    ),
                    "end_date": work.end_date.isoformat() if work.end_date else None,
                    "distance_m": work.distance_m,
                    "latitude": work.lat,
                    "longitude": work.lng,
                    "state": (
                        "active" if work in coordinator.data.active else "upcoming"
                    ),
                },
            )

        # Prune refs no longer in the feed; mark all current refs as seen.
        seen = current_refs
        hass.async_create_task(store.async_save(list(seen)))

    entry.async_on_unload(coordinator.async_add_listener(_on_update))
