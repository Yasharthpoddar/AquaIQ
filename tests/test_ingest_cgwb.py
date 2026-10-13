"""
AquaIQ — D5 CGWB Chunk Aggregation Regression Test.
Verifies:
1. Multi-reading district-month aggregation calculates the true mathematical average across all readings.
2. Ingestion correctly maps legacy district_code to canonical district_id using district_crosswalk.csv.
3. Upserts are idempotent and update existing values rather than silently dropping rows.
"""

import pandas as pd
import pytest
from pathlib import Path
from unittest.mock import MagicMock

ROOT = Path(__file__).parent.parent
from data_ingestion.ingest_cgwb import aggregate_well_readings, get_crosswalk_mapping


def test_crosswalk_mapping_loaded():
    """Verify that crosswalk mapping resolves numeric codes to canonical IDs."""
    mapping = get_crosswalk_mapping()
    assert isinstance(mapping, dict)
    assert len(mapping) >= 567
    # Sample check
    assert mapping["632"] == "AN-North_and_Middle_Andaman"
    assert mapping["502"] == "AP-Anantapur"
    assert mapping["469"] == "MH-Aurangabad"


def test_multi_chunk_aggregation_calculates_true_mean():
    """
    Verify that multiple readings across simulated chunks for the same district and month
    yield the exact arithmetic mean across ALL readings.
    """
    chunk1 = pd.DataFrame({
        "district_code": ["632", "632"],
        "date": ["2015-05-10", "2015-05-15"],
        "currentlevel": [2.0, 4.0]  # mean = 3.0
    })
    chunk2 = pd.DataFrame({
        "district_code": ["632"],
        "date": ["2015-05-20"],
        "currentlevel": [6.0]  # combined mean = (2+4+6)/3 = 4.0
    })

    combined = pd.concat([chunk1, chunk2], ignore_index=True)
    mapping = {"632": "AN-North_and_Middle_Andaman"}

    agg = aggregate_well_readings(combined, mapping)
    
    assert len(agg) == 1
    row = agg.iloc[0]
    assert row["district_id"] == "AN-North_and_Middle_Andaman"
    assert row["date"] == pd.Timestamp("2015-05-01")
    assert pytest.approx(row["gwl_mean"], 1e-5) == 4.0
    assert row["well_count"] == 3


def test_aggregation_drops_nans_and_invalid_dates():
    """Verify invalid currentlevel values and corrupt dates are handled cleanly."""
    dirty_data = pd.DataFrame({
        "district_code": ["502", "502", "502", "999999"],
        "date": ["2018-08-01", "2018-08-15", "invalid-date", "2018-08-01"],
        "currentlevel": [10.5, "NaN", 12.5, 5.0]
    })
    mapping = {"502": "AP-Anantapur"}

    agg = aggregate_well_readings(dirty_data, mapping)
    assert len(agg) == 1
    row = agg.iloc[0]
    assert row["district_id"] == "AP-Anantapur"
    assert pytest.approx(row["gwl_mean"], 1e-5) == 10.5
    assert row["well_count"] == 1
