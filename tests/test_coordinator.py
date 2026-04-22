"""Tests for the SRWR coordinator."""

import io
import zipfile
from datetime import date

import pytest

from custom_components.scottish_road_works.coordinator import (
    _BNG_TO_WGS84,
    _filter_works,
    _parse_csv,
    _parse_date,
    _wkt_centroid,
)

# ---------------------------------------------------------------------------
# BNG → WGS84 coordinate conversion
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "easting, northing, expected_lat, expected_lon, tol",
    [
        # Edinburgh Castle
        (325132, 673523, 55.948, -3.200, 0.01),
        # Inverness city centre
        (266530, 845740, 57.477, -4.224, 0.01),
        # Glasgow George Square
        (259550, 665030, 55.861, -4.251, 0.01),
    ],
)
def test_bng_to_wgs84(easting, northing, expected_lat, expected_lon, tol):
    lon, lat = _BNG_TO_WGS84.transform(easting, northing)
    assert abs(lat - expected_lat) < tol, f"lat {lat} not within {tol} of {expected_lat}"
    assert abs(lon - expected_lon) < tol, f"lon {lon} not within {tol} of {expected_lon}"


# ---------------------------------------------------------------------------
# WKT centroid
# ---------------------------------------------------------------------------


def test_wkt_centroid_point():
    assert _wkt_centroid("POINT (325000 673000)") == (325000.0, 673000.0)


def test_wkt_centroid_linestring():
    e, n = _wkt_centroid("LINESTRING (324000 672000, 326000 674000)")
    assert abs(e - 325000.0) < 0.01
    assert abs(n - 673000.0) < 0.01


def test_wkt_centroid_invalid():
    assert _wkt_centroid("") is None
    assert _wkt_centroid("GEOMETRYCOLLECTION EMPTY") is None


# ---------------------------------------------------------------------------
# Date parsing
# ---------------------------------------------------------------------------


def test_parse_date_iso():
    assert _parse_date("2024-06-15") == date(2024, 6, 15)


def test_parse_date_datetime():
    assert _parse_date("2024-06-15T08:00:00") == date(2024, 6, 15)


def test_parse_date_empty():
    assert _parse_date("") is None
    assert _parse_date(None) is None


# ---------------------------------------------------------------------------
# CSV parsing
#
# Column layouts (from coordinator.py comments):
#   099: Version,099,InternalRef,OrgID,DistrictID,Name,...        (>=6 cols)
#   001: Version,001,ActivityID,Created,Updated,PromoterOrgDistrict,ActivityRef,...[12]=USRN  (>=13 cols)
#   007: Version,007,ActivityID,Created,Updated,Desc,Location,Phase,Template,Category,Status,Cancelled,Geometry  (>=13 cols)
#   008: Version,008,ActivityID,Phase,ProposedStart,HasProposedTime,ActualStart,HasActualTime,EstimatedEnd,ActualEnd  (>=10 cols)
# ---------------------------------------------------------------------------


def _row(*fields: str) -> str:
    return ",".join(fields)


# 099 org row: OrgID at [3], DistrictID at [4], Name at [5]
_ORG_ROW = _row("1", "099", "", "000001", "002", "Test Council")


# 001 activity row: PromoterOrgDistrict at [5], ActivityRef at [6], USRN at [12]
def _act_row(activity_id: str, ref: str, org_district: str = "000001002") -> str:
    fields = ["1", "001", activity_id, "2024-01-01", "2024-01-02", org_district, ref]
    fields += [""] * 5  # cols 7-11
    fields += ["USRN001"]  # col 12
    return ",".join(fields)


# 007 works row: Location at [6], works_type_code at [9], status_code at [10], geometry at [12]
def _works_row(
    activity_id: str, location: str, status: str, geometry: str, wtype: str = "01"
) -> str:
    fields = ["1", "007", activity_id, "2024-01-01", "2024-01-02", "Desc", location]
    fields += ["1", "Tmpl", wtype, status, "0", geometry]
    return ",".join(fields)


# 008 dates row: ProposedStart at [4], ActualStart at [6], EstimatedEnd at [8], ActualEnd at [9]
def _dates_row(activity_id: str, proposed: str, estimated_end: str, actual_end: str = "") -> str:
    return _row("1", "008", activity_id, "1", proposed, "0", "", "0", estimated_end, actual_end)


def _make_csv(*rows: str) -> bytes:
    return "\n".join(rows).encode("utf-8")


def test_parse_csv_org_and_activity():
    csv_bytes = _make_csv(
        _ORG_ROW,
        _act_row("ACT001", "REF-001"),
        _works_row("ACT001", "Main Street", "05", "POINT (325000 673000)"),
        _dates_row("ACT001", "2024-06-01", "2024-06-30"),
    )
    result = _parse_csv(csv_bytes)
    assert "ACT001" in result
    act = result["ACT001"]
    assert act["activity_reference"] == "REF-001"
    assert act["location"] == "Main Street"
    assert act["status_code"] == "05"
    assert act["geometry"] == "POINT (325000 673000)"
    assert act["proposed_start"] == "2024-06-01"
    assert act["estimated_end"] == "2024-06-30"


def test_parse_csv_org_name_resolved():
    csv_bytes = _make_csv(
        _ORG_ROW,
        _act_row("ACT002", "REF-002"),
    )
    result = _parse_csv(csv_bytes)
    assert result["ACT002"]["promoter"] == "Test Council"


def test_parse_csv_skips_short_rows():
    csv_bytes = _make_csv(
        "1,007",  # too short
        "bad",  # too short
        _act_row("ACT003", "REF-003"),
    )
    result = _parse_csv(csv_bytes)
    assert "ACT003" in result


# ---------------------------------------------------------------------------
# _filter_works (zip → RoadWorksData)
# ---------------------------------------------------------------------------

_HOME_E = 325000.0
_HOME_N = 673000.0
_RADIUS_M = 2000


def _build_zip(csv_content: str) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("srwr_export.csv", csv_content)
    return buf.getvalue()


_CSV_NEARBY = "\n".join(
    [
        _ORG_ROW,
        _act_row("ACT010", "REF-010"),
        _works_row("ACT010", "High Street", "05", "POINT (325100 673100)"),
        _dates_row("ACT010", "2024-06-01", "2030-12-31"),
    ]
)

_CSV_FAR = "\n".join(
    [
        _ORG_ROW,
        _act_row("ACT011", "REF-011"),
        _works_row("ACT011", "Far Street", "05", "POINT (400000 700000)"),
        _dates_row("ACT011", "2024-06-01", "2030-12-31"),
    ]
)

_CSV_UPCOMING = "\n".join(
    [
        _ORG_ROW,
        _act_row("ACT012", "REF-012"),
        _works_row("ACT012", "Future Road", "04", "POINT (325100 673100)"),
        _dates_row("ACT012", "2099-01-01", "2099-12-31"),
    ]
)


def test_filter_works_includes_nearby():
    result = _filter_works(_build_zip(_CSV_NEARBY), _HOME_E, _HOME_N, _RADIUS_M)
    all_refs = {w.reference for w in result.active + result.upcoming}
    assert "REF-010" in all_refs


def test_filter_works_excludes_far():
    result = _filter_works(_build_zip(_CSV_FAR), _HOME_E, _HOME_N, _RADIUS_M)
    all_refs = {w.reference for w in result.active + result.upcoming}
    assert "REF-011" not in all_refs


def test_filter_works_sets_latlon():
    result = _filter_works(_build_zip(_CSV_NEARBY), _HOME_E, _HOME_N, _RADIUS_M)
    all_works = result.active + result.upcoming
    assert all_works, "expected at least one road work"
    w = all_works[0]
    assert w.lat is not None
    assert w.lng is not None
    # Should be near Edinburgh
    assert 55.0 < w.lat < 57.0
    assert -5.0 < w.lng < -1.0


def test_filter_works_upcoming_bucket():
    result = _filter_works(_build_zip(_CSV_UPCOMING), _HOME_E, _HOME_N, _RADIUS_M)
    upcoming_refs = {w.reference for w in result.upcoming}
    assert "REF-012" in upcoming_refs
    assert not result.active


def test_filter_works_distance_m():
    result = _filter_works(_build_zip(_CSV_NEARBY), _HOME_E, _HOME_N, _RADIUS_M)
    all_works = result.active + result.upcoming
    assert all_works
    w = all_works[0]
    # centroid is (325100, 673100), home is (325000, 673000) → ~141 m
    assert w.distance_m is not None
    assert abs(w.distance_m - 141) < 5
