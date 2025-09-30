# SPDX-License-Identifier: Apache-2.0
from datetime import datetime

import shapefile

from zyra.transform.geospatial import csv_points_to_geojson, shapefile_to_geojson


def _write_wgs84_prj(path):
    path.write_text(
        'GEOGCS["GCS_WGS_1984",DATUM["D_WGS_1984",SPHEROID["WGS_1984",6378137.0,298.257223563]],PRIMEM["Greenwich",0.0],UNIT["Degree",0.0174532925199433]]',
        encoding="ascii",
    )


def test_normalize_fire_warnings(tmp_path):
    shp_path = tmp_path / "warnings.shp"
    w = shapefile.Writer(str(shp_path))
    w.autoBalance = 1
    w.field("ReqAgency", "C")
    w.field("NWSOffice", "C")
    w.field("Year", "N", decimal=0)
    w.field("Month", "N", decimal=0)
    w.field("Day", "N", decimal=0)
    w.field("Time", "N", decimal=0)
    w.field("Fire_Name", "C")
    w.field("WhoInit", "C")
    w.field("LocalTime", "C")
    ring = [(-97.0, 35.5), (-97.0, 36.0), (-96.5, 36.0), (-96.5, 35.5), (-97.0, 35.5)]
    w.poly([ring])
    w.record("FWT", "KOUN", 2025, 3, 14, 934, "Test Fire", "Forecaster", "3/14 934 PM")
    w.close()
    _write_wgs84_prj(tmp_path / "warnings.prj")

    result = shapefile_to_geojson(
        shp_path,
        timezone_name="America/Chicago",
        default_year=2025,
        time_fields=["LocalTime"],
    )
    assert result["metadata"]["feature_count"] == 1
    feature = result["features"][0]
    assert feature["properties"]["time_utc_iso"] == "2025-03-15T02:34:00+00:00"
    assert feature["geometry"]["type"] == "Polygon"


def test_convert_hotspots_csv(tmp_path):
    csv_path = tmp_path / "hotspots.csv"
    rows = [
        [
            "WFO",
            "County",
            "Location",
            "Time (CDT)",
            "Time (Z)",
            "Lat",
            "Lon",
            "Type",
            "PDS?",
            "Comment",
            "",
            "",
        ],
        [
            "OUN",
            "Payne",
            "4 NNW Drumright",
            "10:23:00 AM",
            "15:23",
            "36.0383",
            "-96.6275",
            "Update",
            "",
            "",
            "",
            "",
        ],
    ]
    csv_path.write_text("\n".join(",".join(r) for r in rows), encoding="utf-8")

    result = csv_points_to_geojson(
        csv_path,
        event_date=datetime(2025, 3, 14).date(),
        timezone_name="America/Chicago",
        local_time_fields=["Time (CDT)"],
        utc_time_fields=["Time (Z)"],
    )
    assert result["metadata"]["feature_count"] == 1
    feature = result["features"][0]
    assert feature["geometry"]["type"] == "Point"
    assert feature["properties"]["time_utc_iso"] == "2025-03-14T15:23:00+00:00"
    assert feature["properties"]["WFO"] == "OUN"
