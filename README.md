# Scottish Road Works

A Home Assistant custom integration for the [Scottish Road Works Register](https://www.roadworks.scot/) (SRWR).

Configure your postcode and search radius to see active and upcoming road works near you, sourced from the SRWR open data daily export.

## Installation

Install via [HACS](https://hacs.xyz/) or copy `custom_components/scottish_road_works/` into your Home Assistant config directory.

## Configuration

1. Go to **Settings → Devices & Services → Add Integration**
2. Search for **Scottish Road Works**
3. Enter your postcode and search radius (default 1 km)

## Sensors

Two sensors are created per configured postcode:

| Sensor | Description |
|--------|-------------|
| `sensor.scottish_road_works_active` | Count of road works currently in progress within your radius |
| `sensor.scottish_road_works_upcoming` | Count of upcoming road works within your radius |

Both sensors include a `works` attribute listing up to 20 entries with reference, street, promoter, works type, start/end dates, status, and distance.

## Data Source

Data is fetched from the [SRWR open data daily export](https://downloads.srwr.scot/export/daily/), updated each night. The integration refreshes every 12 hours.

Licensed under the [Open Government Licence v3](http://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/).
