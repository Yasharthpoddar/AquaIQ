"""Regressions for audit findings in clean ingestion and reference identities."""
import numpy as np
import pandas as pd
import pytest

from data_ingestion import ingest_cgwb, enrich_districts
from scripts import run_pipeline


def test_nonfinite_groundwater_cannot_poison_district_mean():
    source = pd.DataFrame({"district_code": ["7"] * 4, "date": ["2020-01-01"] * 4,
                           "currentlevel": [8.0, np.inf, -np.inf, "invalid"]})
    actual = ingest_cgwb.aggregate_well_readings(source, {"7": "RJ-Jaipur"})
    assert actual.gwl_mean.tolist() == [8.0]
    assert actual.well_count.tolist() == [1]


def test_conflicting_crosswalk_does_not_silently_use_last_row(tmp_path, monkeypatch):
    path = tmp_path / "crosswalk.csv"
    pd.DataFrame({"legacy_district_id": ["7", "7"],
                  "canonical_district_id": ["RJ-Jaipur", "RJ-Ajmer"]}).to_csv(path, index=False)
    monkeypatch.setattr(ingest_cgwb, "CROSSWALK_PATH", path)
    with pytest.raises(ValueError, match="Ambiguous"):
        ingest_cgwb.get_crosswalk_mapping()


def test_boundary_match_is_state_qualified_and_uses_only_recorded_aliases():
    boundaries = pd.DataFrame({"district": ["Aurangabad", "Aurangabad", "Allahabad", "Puna"],
                               "st_nm": ["Bihar", "Maharashtra", "Uttar Pradesh", "Maharashtra"]})
    match = enrich_districts.match_geojson_name
    assert match("Aurangabad", "Bihar", boundaries) == "Aurangabad"
    assert match("Aurangabad", "Rajasthan", boundaries) is None
    assert match("Prayagraj", "Uttar Pradesh", boundaries) == "Allahabad"
    assert match("Pune", "Maharashtra", boundaries) is None


def test_state_zone_lookup_has_no_fuzzy_geography():
    assert enrich_districts.zone_for_state("Orissa") == "Eastern Plateau and Hills"
    assert enrich_districts.zone_for_state("Unknown state") is None


def test_clean_ingestion_enriches_before_weather(monkeypatch):
    calls = []
    monkeypatch.setattr(ingest_cgwb, "main", lambda: calls.append("groundwater"))
    monkeypatch.setattr(enrich_districts, "main", lambda: calls.append("enrichment"))
    monkeypatch.setattr("data_ingestion.ingest_imd_era5.main", lambda argv: calls.append("weather"))
    assert run_pipeline.step_ingest()
    assert calls == ["groundwater", "enrichment", "weather"]
