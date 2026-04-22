"""Tests for the geo_location platform."""

from datetime import date
from unittest.mock import MagicMock

import pytest

from custom_components.scottish_road_works.coordinator import RoadWork, RoadWorksData
from custom_components.scottish_road_works.geo_location import (
    SOURCE_ACTIVE,
    SOURCE_UPCOMING,
    RoadWorksGeoLocation,
    _ref_slug,
)


def _make_work(
    reference: str = "REF-001",
    street_name: str = "Main Street",
    works_type: str = "Utility works",
    lat: float = 55.95,
    lng: float = -3.19,
    distance_m: float = 200.0,
    status: str = "In progress",
) -> RoadWork:
    return RoadWork(
        reference=reference,
        promoter="Test Council",
        street_name=street_name,
        works_type=works_type,
        status=status,
        start_date=date(2024, 6, 1),
        end_date=date(2024, 6, 30),
        lat=lat,
        lng=lng,
        distance_m=distance_m,
    )


def _make_coordinator(active: list[RoadWork], upcoming: list[RoadWork]) -> MagicMock:
    coordinator = MagicMock()
    coordinator.data = RoadWorksData(active=active, upcoming=upcoming)
    return coordinator


def _make_entity(coordinator, reference: str = "REF-001") -> RoadWorksGeoLocation:
    return RoadWorksGeoLocation(coordinator, reference, "test_entry")


# ---------------------------------------------------------------------------
# entity_id and slugification
# ---------------------------------------------------------------------------


def test_ref_slug_simple():
    assert _ref_slug("REF-001") == "ref_001"


def test_ref_slug_srwr_style():
    assert _ref_slug("SWS/2024/00123456") == "sws_2024_00123456"


def test_ref_slug_strips_leading_trailing_underscores():
    assert _ref_slug("/REF/") == "ref"


def test_entity_id_prefixed_with_domain():
    work = _make_work(reference="SWS/2024/00123456")
    coordinator = _make_coordinator(active=[work], upcoming=[])
    entity = _make_entity(coordinator, "SWS/2024/00123456")
    assert entity.entity_id == "geo_location.scottish_road_works_sws_2024_00123456"


def test_entity_id_stable_regardless_of_name():
    """entity_id must be derived from reference, not the street name."""
    work = _make_work(reference="SWS/001", street_name="See Map")
    coordinator = _make_coordinator(active=[work], upcoming=[])
    entity = _make_entity(coordinator, "SWS/001")
    assert entity.entity_id == "geo_location.scottish_road_works_sws_001"
    assert entity.name == "See Map (Utility works)"


# ---------------------------------------------------------------------------
# source property
# ---------------------------------------------------------------------------


def test_source_active_when_in_active_list():
    work = _make_work()
    coordinator = _make_coordinator(active=[work], upcoming=[])
    entity = _make_entity(coordinator, "REF-001")
    assert entity.source == SOURCE_ACTIVE


def test_source_upcoming_when_in_upcoming_list():
    work = _make_work()
    coordinator = _make_coordinator(active=[], upcoming=[work])
    entity = _make_entity(coordinator, "REF-001")
    assert entity.source == SOURCE_UPCOMING


def test_source_updates_when_work_moves_to_active():
    work = _make_work()
    coordinator = _make_coordinator(active=[], upcoming=[work])
    entity = _make_entity(coordinator, "REF-001")
    assert entity.source == SOURCE_UPCOMING

    coordinator.data = RoadWorksData(active=[work], upcoming=[])
    assert entity.source == SOURCE_ACTIVE


def test_source_falls_back_to_upcoming_when_no_data():
    coordinator = MagicMock()
    coordinator.data = None
    entity = _make_entity(coordinator, "REF-001")
    assert entity.source == SOURCE_UPCOMING


# ---------------------------------------------------------------------------
# name property
# ---------------------------------------------------------------------------


def test_name_includes_street_and_type():
    work = _make_work(reference="REF-001", street_name="High Street", works_type="Utility works")
    coordinator = _make_coordinator(active=[work], upcoming=[])
    entity = _make_entity(coordinator, "REF-001")
    assert entity.name == "High Street (Utility works)"


def test_name_omits_type_when_empty():
    work = _make_work(reference="REF-001", street_name="High Street", works_type="")
    coordinator = _make_coordinator(active=[work], upcoming=[])
    entity = _make_entity(coordinator, "REF-001")
    assert entity.name == "High Street"


def test_name_falls_back_to_reference_when_no_street():
    work = _make_work(reference="REF-001", street_name="", works_type="Utility works")
    coordinator = _make_coordinator(active=[work], upcoming=[])
    entity = _make_entity(coordinator, "REF-001")
    assert entity.name == "REF-001 (Utility works)"


def test_name_falls_back_to_reference_when_no_data():
    coordinator = MagicMock()
    coordinator.data = None
    entity = _make_entity(coordinator, "REF-001")
    assert entity.name == "REF-001"


# ---------------------------------------------------------------------------
# latitude / longitude / distance
# ---------------------------------------------------------------------------


def test_latitude_and_longitude():
    work = _make_work(lat=55.948, lng=-3.200)
    coordinator = _make_coordinator(active=[work], upcoming=[])
    entity = _make_entity(coordinator, "REF-001")
    assert entity.latitude == pytest.approx(55.948)
    assert entity.longitude == pytest.approx(-3.200)


def test_distance_converted_to_km():
    work = _make_work(distance_m=1500.0)
    coordinator = _make_coordinator(active=[work], upcoming=[])
    entity = _make_entity(coordinator, "REF-001")
    assert entity.distance == pytest.approx(1.5)


def test_distance_none_when_not_set():
    work = _make_work()
    work = RoadWork(
        reference=work.reference,
        promoter=work.promoter,
        street_name=work.street_name,
        works_type=work.works_type,
        status=work.status,
        start_date=work.start_date,
        end_date=work.end_date,
        lat=work.lat,
        lng=work.lng,
        distance_m=None,
    )
    coordinator = _make_coordinator(active=[work], upcoming=[])
    entity = _make_entity(coordinator, "REF-001")
    assert entity.distance is None


# ---------------------------------------------------------------------------
# extra_state_attributes
# ---------------------------------------------------------------------------


def test_extra_state_attributes():
    work = _make_work()
    coordinator = _make_coordinator(active=[work], upcoming=[])
    entity = _make_entity(coordinator, "REF-001")
    attrs = entity.extra_state_attributes
    assert attrs["reference"] == "REF-001"
    assert attrs["promoter"] == "Test Council"
    assert attrs["status"] == "In progress"
    assert attrs["start_date"] == "2024-06-01"
    assert attrs["end_date"] == "2024-06-30"
    assert attrs["distance_m"] == 200.0


def test_extra_state_attributes_empty_when_no_data():
    coordinator = MagicMock()
    coordinator.data = None
    entity = _make_entity(coordinator, "REF-001")
    assert entity.extra_state_attributes == {}
