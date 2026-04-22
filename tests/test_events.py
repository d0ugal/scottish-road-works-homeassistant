"""Tests for the events module."""

from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.scottish_road_works.coordinator import RoadWork, RoadWorksData
from custom_components.scottish_road_works.events import EVENT_NEW_WORK, async_setup_entry


def _make_work(
    reference: str = "REF-001",
    street_name: str = "High Street",
    works_type: str = "Utility works",
    status: str = "In progress",
    distance_m: int = 200,
) -> RoadWork:
    return RoadWork(
        reference=reference,
        promoter="Test Council",
        street_name=street_name,
        works_type=works_type,
        status=status,
        start_date=date(2024, 6, 1),
        end_date=date(2024, 6, 30),
        lat=55.95,
        lng=-3.19,
        distance_m=distance_m,
    )


def _make_hass() -> tuple[MagicMock, list]:
    fired: list[tuple[str, dict]] = []
    hass = MagicMock()
    hass.bus.async_fire = MagicMock(side_effect=lambda name, data: fired.append((name, data)))
    hass.async_create_task = MagicMock()
    return hass, fired


def _make_coordinator(active=None, upcoming=None):
    coordinator = MagicMock()
    coordinator.data = RoadWorksData(active=list(active or []), upcoming=list(upcoming or []))
    listeners: list = []

    def _add_listener(cb):
        listeners.append(cb)

        def _remove():
            listeners.remove(cb)

        return _remove

    coordinator.async_add_listener = _add_listener
    coordinator._listeners = listeners
    return coordinator


def _make_entry(coordinator, entry_id: str = "test_entry"):
    entry = MagicMock()
    entry.entry_id = entry_id
    unload_cbs: list = []
    entry.async_on_unload = lambda cb: unload_cbs.append(cb)
    entry._unload_cbs = unload_cbs
    return entry


async def _setup(hass, coordinator, entry, stored_refs=None):
    hass.data = {coordinator._domain: {entry.entry_id: coordinator}}
    from custom_components.scottish_road_works.const import DOMAIN

    hass.data = {DOMAIN: {entry.entry_id: coordinator}}
    store = MagicMock()
    store.async_load = AsyncMock(return_value=stored_refs)
    store.async_save = AsyncMock()
    with patch("custom_components.scottish_road_works.events.Store", return_value=store):
        await async_setup_entry(hass, entry)
    return store


def _trigger(coordinator):
    for cb in coordinator._listeners:
        cb()


# ---------------------------------------------------------------------------
# Startup behaviour — no events for works already in feed on HA restart
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_no_events_on_startup_first_run():
    """Works present when HA starts must not fire events (first ever run)."""
    work = _make_work()
    coordinator = _make_coordinator(active=[work])
    hass, fired = _make_hass()
    entry = _make_entry(coordinator)

    await _setup(hass, coordinator, entry, stored_refs=None)

    assert fired == []


@pytest.mark.asyncio
async def test_no_events_on_startup_with_stored_refs():
    """Works that were already seen before restart must not fire on startup."""
    work = _make_work()
    coordinator = _make_coordinator(active=[work])
    hass, fired = _make_hass()
    entry = _make_entry(coordinator)

    await _setup(hass, coordinator, entry, stored_refs=["REF-001"])

    assert fired == []


@pytest.mark.asyncio
async def test_no_events_when_listener_fires_with_same_works():
    """Coordinator update with no new refs must fire no events."""
    work = _make_work()
    coordinator = _make_coordinator(active=[work])
    hass, fired = _make_hass()
    entry = _make_entry(coordinator)

    await _setup(hass, coordinator, entry)
    _trigger(coordinator)

    assert fired == []


# ---------------------------------------------------------------------------
# New works fire events
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_new_work_fires_event():
    """A work appearing after startup fires exactly one event."""
    existing = _make_work(reference="REF-001")
    coordinator = _make_coordinator(active=[existing])
    hass, fired = _make_hass()
    entry = _make_entry(coordinator)

    await _setup(hass, coordinator, entry)

    new_work = _make_work(reference="REF-002", street_name="New Road")
    coordinator.data = RoadWorksData(active=[existing, new_work], upcoming=[])
    _trigger(coordinator)

    assert len(fired) == 1
    name, data = fired[0]
    assert name == EVENT_NEW_WORK
    assert data["reference"] == "REF-002"
    assert data["street_name"] == "New Road"
    assert data["state"] == "active"


@pytest.mark.asyncio
async def test_new_upcoming_work_fires_event_with_upcoming_state():
    """A new upcoming work fires an event with state='upcoming'."""
    coordinator = _make_coordinator()
    hass, fired = _make_hass()
    entry = _make_entry(coordinator)

    await _setup(hass, coordinator, entry)

    work = _make_work(reference="REF-010")
    coordinator.data = RoadWorksData(active=[], upcoming=[work])
    _trigger(coordinator)

    assert len(fired) == 1
    assert fired[0][1]["state"] == "upcoming"


@pytest.mark.asyncio
async def test_event_payload_fields():
    """Event payload must include all expected fields."""
    coordinator = _make_coordinator()
    hass, fired = _make_hass()
    entry = _make_entry(coordinator)

    await _setup(hass, coordinator, entry)

    work = _make_work(reference="REF-020", distance_m=500)
    coordinator.data = RoadWorksData(active=[work], upcoming=[])
    _trigger(coordinator)

    data = fired[0][1]
    assert data["reference"] == "REF-020"
    assert data["promoter"] == "Test Council"
    assert data["works_type"] == "Utility works"
    assert data["status"] == "In progress"
    assert data["start_date"] == "2024-06-01"
    assert data["end_date"] == "2024-06-30"
    assert data["distance_m"] == 500
    assert data["latitude"] == pytest.approx(55.95)
    assert data["longitude"] == pytest.approx(-3.19)


@pytest.mark.asyncio
async def test_multiple_new_works_each_fire_once():
    """Each new work fires exactly one event."""
    coordinator = _make_coordinator()
    hass, fired = _make_hass()
    entry = _make_entry(coordinator)

    await _setup(hass, coordinator, entry)

    works = [_make_work(reference=f"REF-{i:03d}") for i in range(3)]
    coordinator.data = RoadWorksData(active=works, upcoming=[])
    _trigger(coordinator)

    assert len(fired) == 3
    refs = {d["reference"] for _, d in fired}
    assert refs == {"REF-000", "REF-001", "REF-002"}


# ---------------------------------------------------------------------------
# Known works do not re-fire
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_known_work_does_not_refire_on_next_update():
    """A new work fires once; the next coordinator update must not re-fire it."""
    coordinator = _make_coordinator()
    hass, fired = _make_hass()
    entry = _make_entry(coordinator)

    await _setup(hass, coordinator, entry)

    work = _make_work(reference="REF-001")
    coordinator.data = RoadWorksData(active=[work], upcoming=[])
    _trigger(coordinator)
    assert len(fired) == 1

    _trigger(coordinator)
    assert len(fired) == 1  # still 1, not 2


# ---------------------------------------------------------------------------
# Pruning and reappearance
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_work_that_disappears_and_reappears_refires():
    """A work removed from the feed loses its 'seen' status; if it reappears it fires again."""
    coordinator = _make_coordinator()
    hass, fired = _make_hass()
    entry = _make_entry(coordinator)

    await _setup(hass, coordinator, entry)

    work = _make_work(reference="REF-001")
    coordinator.data = RoadWorksData(active=[work], upcoming=[])
    _trigger(coordinator)
    assert len(fired) == 1

    # Work disappears from feed
    coordinator.data = RoadWorksData(active=[], upcoming=[])
    _trigger(coordinator)
    assert len(fired) == 1

    # Work reappears
    coordinator.data = RoadWorksData(active=[work], upcoming=[])
    _trigger(coordinator)
    assert len(fired) == 2


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_store_saved_after_startup_with_data():
    """Seen refs must be persisted immediately on startup when data is present."""
    work = _make_work()
    coordinator = _make_coordinator(active=[work])
    hass, _ = _make_hass()
    entry = _make_entry(coordinator)

    store = await _setup(hass, coordinator, entry)
    store.async_save.assert_awaited_once()
    saved = store.async_save.call_args[0][0]
    assert "REF-001" in saved


@pytest.mark.asyncio
async def test_store_saved_after_new_work():
    """Seen refs must be persisted (via async_create_task) after a new work fires."""
    coordinator = _make_coordinator()
    hass, _ = _make_hass()
    entry = _make_entry(coordinator)

    await _setup(hass, coordinator, entry)

    work = _make_work(reference="REF-001")
    coordinator.data = RoadWorksData(active=[work], upcoming=[])
    _trigger(coordinator)

    # async_create_task should have been called with the save coroutine
    hass.async_create_task.assert_called()
