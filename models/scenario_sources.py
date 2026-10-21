"""Pinned, file-only canonical district histories for experimental scenarios.

No DB fallback, source refresh, identity guessing, zone borrowing or writes.
These are repository observed flags, not certified acquisition/availability.
"""
from functools import lru_cache
import csv
import hashlib
import io
import json
from pathlib import Path
import re

import numpy as np
import pandas as pd

from models.research_forecast import ResearchContractError, _canonical_hash

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = "research/experimental_scenario_sources.json"
CONFIG_SHA256 = "1f12ed7df01913dcd69fbe1a6a3369905fdad3c43a9d4385814e4efc775dd5a0"
REQUIRED_COLUMNS = {"district_id", "date", "GWL_current", "gwl_current", "is_observed", "is_imputed", "feature_generation"}


def _fail(message):
    raise ResearchContractError(message)


def _json(raw):
    try:
        value = json.loads(raw, parse_constant=lambda _: _fail("Scenario source metadata is nonfinite."))
    except (UnicodeError, ValueError, TypeError):
        _fail("Scenario source metadata is unreadable or incompatible.")
    if not isinstance(value, dict):
        _fail("Scenario source metadata must be an object.")
    return value


def _path(relative):
    if not isinstance(relative, str) or Path(relative).is_absolute():
        _fail("Scenario source paths must remain in the repository.")
    path = (ROOT / relative).resolve()
    if not path.is_relative_to(ROOT.resolve()) or path == ROOT.resolve():
        _fail("Scenario source paths must remain in the repository.")
    return path


def _read(path):
    try:
        return path.read_bytes()
    except OSError:
        _fail("A pinned local scenario source is missing or unreadable.")


def _verify(raw, expected):
    if not isinstance(expected, str) or not re.fullmatch(r"[0-9a-f]{64}", expected) or hashlib.sha256(raw).hexdigest() != expected:
        _fail("Scenario source checksum mismatch; revised sources require a separately reviewed version.")


@lru_cache(maxsize=1)
def _parse(feature_bytes, manifest_bytes, registry_bytes, config_bytes):
    """Cache parsing only after every request has verified pinned source bytes."""
    config = _json(config_bytes)
    manifest = _json(manifest_bytes)
    if (manifest.get("generation_id") != config["feature_generation_id"]
            or manifest.get("units", {}).get("gwl") != "m_bgl"
            or manifest.get("causal_preprocessing") is not True or manifest.get("sample_only") is not False
            or manifest.get("feature_csv_sha256") != config["feature_csv_sha256"]
            or manifest.get("observation_column") != "is_observed"):
        _fail("Scenario feature generation, units or observed-source metadata is incompatible.")
    try:
        registry = pd.read_csv(io.BytesIO(registry_bytes), dtype=str, keep_default_na=False)
        if not {"canonical_district_id", "canonical_name", "canonical_state", "legacy_district_id"}.issubset(registry.columns):
            _fail("Scenario district registry schema is incomplete.")
        if (registry[list(("canonical_district_id", "canonical_name", "canonical_state"))].eq("").any().any()
                or not registry.canonical_district_id.str.fullmatch(r"[A-Z]{2}-[A-Za-z0-9_.-]+").all()):
            _fail("Scenario district registry identities are incompatible.")
        identities = {}
        for district, rows in registry.groupby("canonical_district_id", sort=True):
            # Prefer the recorded canonical self-row for display. State-label
            # spelling variants never alter identity or source selection.
            display = rows.loc[rows.legacy_district_id.eq(district)]
            display = display.iloc[0] if len(display) else rows.iloc[0]
            identities[district] = {"district_name": display.canonical_name, "state_name": display.canonical_state}
        if len(identities) != config["district_count"]:
            _fail("Scenario district registry count is incompatible.")
        header = next(csv.reader(io.StringIO(feature_bytes.decode("utf-8-sig"))))
        if len(header) != len(set(header)) or REQUIRED_COLUMNS - set(header):
            _fail("Scenario observed-history schema is incomplete or ambiguous.")
        frame = pd.read_csv(io.BytesIO(feature_bytes), usecols=sorted(REQUIRED_COLUMNS), dtype={"district_id":str, "is_observed":str, "is_imputed":str})
        frame["date"] = pd.to_datetime(frame.date, errors="raise")
        if (frame.empty or frame.date.isna().any() or frame.date.dt.tz is not None
                or (frame.date.dt.day != 1).any() or (frame.date != frame.date.dt.normalize()).any()
                or frame.duplicated(["district_id", "date"]).any()
                or not frame.feature_generation.eq(config["feature_generation_id"]).all()
                or set(frame.district_id) != set(identities)
                or frame.date.min() != pd.Timestamp(manifest["date_start"])
                or frame.date.max() != pd.Timestamp(manifest["date_end"])):
            _fail("Scenario history dates, identities, generation or monthly keys are incompatible.")
        for flag in ("is_observed", "is_imputed"):
            values = frame[flag].str.strip().str.lower().map({"true": True,"false":False,"1":True,"0":False})
            if values.isna().any():
                _fail("Scenario observation flags are unknown or incompatible.")
            frame[flag] = values.astype(bool)
        if (frame.is_observed & frame.is_imputed).any():
            _fail("Scenario history cannot be both observed and imputed.")
        for field in ("gwl_current", "GWL_current"):
            frame[field] = pd.to_numeric(frame[field], errors="raise")
        equal = frame.gwl_current.eq(frame.GWL_current) | (frame.gwl_current.isna() & frame.GWL_current.isna())
        if not equal.all() or (frame.is_observed & (~np.isfinite(frame.gwl_current) | frame.gwl_current.lt(0))).any():
            _fail("Scenario groundwater values or aliases are incompatible.")
        frame["_observed"] = frame.is_observed & ~frame.is_imputed & np.isfinite(frame.gwl_current) & frame.gwl_current.ge(0)
        return frame, identities
    except ResearchContractError:
        raise
    except (ValueError, TypeError, KeyError, UnicodeError, StopIteration, AttributeError):
        _fail("Scenario observed history or registry is unreadable or incompatible.")


def load_district(district_id, config_path=None):
    config_bytes = _read(Path(config_path) if config_path else _path(DEFAULT_CONFIG))
    config = _json(config_bytes)
    if (_canonical_hash(config) != CONFIG_SHA256 or config.get("schema_version") != 1
            or config.get("product") != "experimental_12month_scenario_sources"
            or config.get("units") != "m_bgl" or config.get("scope") != "canonical_district_own_observed_history"):
        _fail("Scenario source configuration differs from its pinned reviewed version.")
    assets = {}
    for key in ("feature_csv", "feature_manifest", "district_crosswalk"):
        assets[key] = _read(_path(config.get(key+"_path")))
        _verify(assets[key], config.get(key+"_sha256"))
    frame, identities = _parse(assets["feature_csv"],assets["feature_manifest"],assets["district_crosswalk"],config_bytes)
    metadata = {"name":config["source_name"], "scope":"district_own_observed_history",
                "units_qualification":config["units_qualification"], "availability_verified":False,
                "source_kind":"canonical_feature_export", "source_configuration_sha256":CONFIG_SHA256,
                "source_manifest_sha256":config["feature_manifest_sha256"],
                "registry_sha256":config["district_crosswalk_sha256"],
                "district_known":district_id in identities, **identities.get(district_id,{})}
    # Always return a private district slice. Callers cannot mutate the cache or
    # borrow another district's observed values.
    return {"frame":frame.loc[frame.district_id.eq(district_id)].copy(),
            "contract":{"feature_generation_id":config["feature_generation_id"]},
            "manifest":{"snapshot_sha256":config["feature_csv_sha256"]},
            "config_sha256":CONFIG_SHA256, "source_metadata":metadata}
