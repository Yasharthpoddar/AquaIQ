"""
AquaIQ — D7 Spatial Fallback Regression Test.
Verifies:
1. Zero districts are dropped during spatial joins of gridded data to polygons.
2. Boundary / small districts (e.g. Mumbai, Diu, Puducherry) receive nearest-grid assignments.
3. ERA5 PEV conversion accurately accumulates over the days in each calendar month (D3).
"""

import pandas as pd
import numpy as np
import geopandas as gpd
from shapely.geometry import Point, Polygon
import pytest
from pathlib import Path

ROOT = Path(__file__).parent.parent
from data_ingestion.era5_to_district import assign_districts_with_fallback, convert_pev_to_mm_per_month


def test_spatial_fallback_covers_small_districts_outside_grid():
    """
    Test that a small polygon containing 0 grid points is assigned to its nearest grid point.
    """
    # Grid points at (0, 0) and (1, 1)
    pts_df = pd.DataFrame({
        "longitude": [0.0, 1.0],
        "latitude": [0.0, 1.0],
        "lat_idx": [0, 1],
        "lon_idx": [0, 1]
    })
    pts_gdf = gpd.GeoDataFrame(
        pts_df,
        geometry=[Point(xy) for xy in zip(pts_df["longitude"], pts_df["latitude"])],
        crs="EPSG:4326"
    )

    # District 1 contains (0, 0)
    poly1 = Polygon([(-0.2, -0.2), (0.2, -0.2), (0.2, 0.2), (-0.2, 0.2)])
    # District 2 is tiny at (0.4, 0.4), containing NO grid points
    poly2 = Polygon([(0.38, 0.38), (0.42, 0.38), (0.42, 0.42), (0.38, 0.42)])

    districts_gdf = gpd.GeoDataFrame(
        {
            "district": ["DistA", "DistSmall"],
            "st_nm": ["StateA", "StateA"],
        },
        geometry=[poly1, poly2],
        crs="EPSG:4326"
    )

    joined = assign_districts_with_fallback(pts_gdf, districts_gdf)
    
    unique_districts = set(joined["district"])
    assert "DistA" in unique_districts
    assert "DistSmall" in unique_districts, "Small district was dropped by sjoin!"
    assert len(unique_districts) == 2


def test_pev_conversion_incorporates_days_in_month():
    """
    Verify that PEV (m/day avgad) is scaled by -1000 and multiplied by days in month.
    e.g. -0.002 m/day in a 31-day month = -0.002 * -1000 * 31 = 62.0 mm/month.
    e.g. -0.002 m/day in a 28-day month (Feb) = -0.002 * -1000 * 28 = 56.0 mm/month.
    """
    pev_rate = -0.002  # m/day
    
    # January (31 days)
    jan_date = pd.Timestamp("2020-01-01")
    et_jan = convert_pev_to_mm_per_month(pev_rate, jan_date)
    assert pytest.approx(et_jan, 1e-3) == 62.0

    # February leap year 2020 (29 days)
    feb_date = pd.Timestamp("2020-02-01")
    et_feb = convert_pev_to_mm_per_month(pev_rate, feb_date)
    assert pytest.approx(et_feb, 1e-3) == 58.0

    # Positive PEV (condensation/dew) is clamped to 0
    pos_rate = 0.0001
    assert convert_pev_to_mm_per_month(pos_rate, jan_date) == 0.0
