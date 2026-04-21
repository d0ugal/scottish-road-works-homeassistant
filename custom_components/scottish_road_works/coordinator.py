"""SRWR data coordinator."""

from __future__ import annotations

import csv
import io
import logging
import math
import re
import zipfile
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import CONF_EASTING, CONF_NORTHING, CONF_RADIUS_KM, DOMAIN

_LOGGER = logging.getLogger(__name__)

_SRWR_DAILY_API = "https://downloads.srwr.scot/export/api/v1/daily/"

_ACTIVE_STATUSES = {"05", "14", "15", "16"}  # In Progress, In Force, Commenced, Overrun
_UPCOMING_STATUSES = {"01", "03", "04"}  # Potential, Advance Planning, Proposed

_WORKS_TYPES: dict[str, str] = {
    "01": "Minor With Excavation",
    "02": "Minor Without Excavation",
    "03": "Minor Mobile and Short Duration",
    "04": "Major",
    "05": "Standard",
    "06": "Urgent",
    "07": "Emergency",
    "09": "Remedial Other",
    "10": "Remedial Dangerous",
    "12": "Bar Hole",
    "13": "Dial Before You Dig",
    "14": "Unattributable Works",
    "15": "Defective Apparatus",
    "16": "Road Restriction",
    "17": "Diversionary Works",
    "18": "Works Licence",
    "19": "Traffic Regulation Order",
    "20": "Permission",
    "21": "Removal",
    "22": "Event/Disruption",
    "23": "Damage Report",
    "24": "Accepted Works",
    "26": "Unexpected Buried Object",
}

_ACTIVITY_STATUSES: dict[str, str] = {
    "01": "Potential",
    "03": "Advance Planning",
    "04": "Proposed",
    "05": "In Progress",
    "06": "Cleared",
    "07": "Closed",
    "08": "Closed No Excavation",
    "09": "Abandoned",
    "10": "Active",
    "11": "Lapsed",
    "12": "Awaiting Response",
    "13": "Accepted",
    "14": "In Force",
    "15": "Commenced",
    "16": "Overrun",
    "17": "Completed",
}


@dataclass
class RoadWork:
    reference: str
    street_name: str
    promoter: str
    works_type: str
    start_date: date | None
    end_date: date | None
    status: str
    distance_m: int | None = None


@dataclass
class RoadWorksData:
    active: list[RoadWork] = field(default_factory=list)
    upcoming: list[RoadWork] = field(default_factory=list)


class RoadWorksCoordinator(DataUpdateCoordinator[RoadWorksData]):
    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(hours=12),
        )
        self._home_easting: float = entry.data[CONF_EASTING]
        self._home_northing: float = entry.data[CONF_NORTHING]
        self._radius_m: int = round(entry.data[CONF_RADIUS_KM] * 1000)
        self.session = async_get_clientsession(hass)

    async def _async_update_data(self) -> RoadWorksData:
        try:
            return await self._fetch()
        except UpdateFailed:
            raise
        except Exception as err:
            raise UpdateFailed(f"Error fetching SRWR data: {err}") from err

    async def _fetch(self) -> RoadWorksData:
        async with self.session.get(_SRWR_DAILY_API) as resp:
            resp.raise_for_status()
            meta = await resp.json()
        url = meta.get("url")
        if not url:
            raise UpdateFailed("SRWR API returned no download URL")

        async with self.session.get(url) as resp:
            resp.raise_for_status()
            zip_bytes = await resp.read()

        return await self.hass.async_add_executor_job(self._parse_and_filter, zip_bytes)

    def _parse_and_filter(self, zip_bytes: bytes) -> RoadWorksData:
        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
            csv_name = next(n for n in zf.namelist() if n.endswith(".csv"))
            csv_bytes = zf.read(csv_name)

        activities = _parse_csv(csv_bytes)
        today = date.today()
        active: list[RoadWork] = []
        upcoming: list[RoadWork] = []

        for act in activities.values():
            status_code = act.get("status_code", "")
            geometry = act.get("geometry", "")
            if not geometry:
                continue

            centroid = _wkt_centroid(geometry)
            if centroid is None:
                continue
            e, n = centroid

            dist_m = round(
                math.sqrt((e - self._home_easting) ** 2 + (n - self._home_northing) ** 2)
            )
            if dist_m > self._radius_m:
                continue

            start = _parse_date(act.get("proposed_start", "") or act.get("actual_start", ""))
            end = _parse_date(act.get("actual_end", "") or act.get("estimated_end", ""))

            works_type_code: str = act.get("works_type_code") or ""
            rw = RoadWork(
                reference=act.get("activity_reference") or "",
                street_name=act.get("location") or "",
                promoter=act.get("promoter") or "",
                works_type=_WORKS_TYPES.get(works_type_code, works_type_code),
                start_date=start,
                end_date=end,
                status=_ACTIVITY_STATUSES.get(status_code, status_code),
                distance_m=dist_m,
            )

            if start and end and start <= today <= end:
                active.append(rw)
            elif start and start > today:
                upcoming.append(rw)
            elif status_code in _ACTIVE_STATUSES:
                active.append(rw)
            elif status_code in _UPCOMING_STATUSES:
                upcoming.append(rw)

        active.sort(key=lambda w: w.start_date or date.min)
        upcoming.sort(key=lambda w: w.start_date or date.max)

        return RoadWorksData(active=active, upcoming=upcoming[:20])


def _parse_csv(csv_bytes: bytes) -> dict[str, dict]:
    """Parse SRWR multi-record-type CSV. Returns dict keyed by activity_id."""
    text = csv_bytes.decode("utf-8-sig")
    reader = csv.reader(io.StringIO(text))

    orgs: dict[str, str] = {}
    activities: dict[str, dict] = {}

    for row in reader:
        if len(row) < 2:
            continue
        record_type = row[1].strip()

        if record_type == "099" and len(row) >= 6:
            # Version,099,InternalRef,OrgID,DistrictID,Name,...
            org_id = row[3].strip().zfill(6)
            district_id = row[4].strip().zfill(3)
            orgs[org_id + district_id] = row[5].strip()

        elif record_type == "001" and len(row) >= 13:
            # Version,001,ActivityID,Created,Updated,PromoterOrgDistrict,ActivityRef,...,USRN,...
            activity_id = row[2].strip()
            act = activities.setdefault(activity_id, {})
            act["activity_id"] = activity_id
            act["promoter_org_district"] = row[5].strip().zfill(9)
            act["activity_reference"] = row[6].strip()
            act["usrn"] = row[12].strip()

        elif record_type == "007" and len(row) >= 13:
            # Version,007,ActivityID,Created,Updated,Desc,Location,Phase,Template,Category,Status,Cancelled,Geometry,...
            activity_id = row[2].strip()
            act = activities.setdefault(activity_id, {})
            if "location" not in act:
                act["location"] = row[6].strip()
                act["works_type_code"] = row[9].strip()
                act["status_code"] = row[10].strip()
                act["geometry"] = row[12].strip()

        elif record_type == "008" and len(row) >= 10:
            # Version,008,ActivityID,Phase,ProposedStart,HasProposedTime,ActualStart,HasActualTime,EstimatedEnd,ActualEnd,...
            activity_id = row[2].strip()
            act = activities.setdefault(activity_id, {})
            if "proposed_start" not in act:
                act["proposed_start"] = row[4].strip()
                act["actual_start"] = row[6].strip()
                act["estimated_end"] = row[8].strip()
                act["actual_end"] = row[9].strip()

    for act in activities.values():
        act["promoter"] = orgs.get(act.get("promoter_org_district", ""), "")

    return activities


def _wkt_centroid(wkt: str) -> tuple[float, float] | None:
    """Return the centroid of a WKT geometry as (easting, northing)."""
    pairs = re.findall(r"(-?\d+\.?\d*)\s+(-?\d+\.?\d*)", wkt)
    if not pairs:
        return None
    eastings = [float(x) for x, _ in pairs]
    northings = [float(y) for _, y in pairs]
    return sum(eastings) / len(eastings), sum(northings) / len(northings)


def _parse_date(raw: str) -> date | None:
    """Parse SRWR date/datetime string to a date."""
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw[:10]).date()
    except ValueError:
        return None
