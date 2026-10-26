"""Acquire and audit official NWDP CGWB quarterly manual groundwater records.

Only explicitly requested CLI runs access the network. Raw CSVs are immutable;
audits and district-month candidates are written to a new output directory.
No database, deployed feature file, or model is changed by this module.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import time
import unicodedata
from urllib.parse import urlparse

import numpy as np
import pandas as pd

from data_ingestion.cgwb_updates import (
    build_district_lookup, normalized_state, resolve_district, spatial_districts,
)

ROOT = Path(__file__).resolve().parents[1]
DATASET = "gwl-manual-quarterly-central-ground-water-board-department"
LANDING_URL = f"https://nwdp.nwic.gov.in/dataset/{DATASET}"
METADATA_URL = f"https://nwdp.nwic.gov.in/api/3/action/package_show?id={DATASET}"
DATUM_URL = "https://www.cgwb.gov.in/ground-water-level-monitoring"
VALUE_COLUMN = "Groundwater Level Quarterly Manual (meter)"
TELEMETRY_VALUE_COLUMN = "Groundwater Level Telemetry 6 Hourly (meter)"
CSV_COLUMNS = (
    "SlNo", "Station", "Agency", "State LGD Code", "State", "District LGD Code",
    "District", "Tehsil", "Block", "Village", "River", "Basin", "Tributary",
    "Subtributary", "SubSubtributary", "Local River", "Latitude", "Longitude",
    "RL_MSL", "Data Acquisition Time", VALUE_COLUMN,
)
VERSION = "nwdp-cgwb-manual-v1"
# Deliberate quarantine limits, not learned thresholds or corrected readings.
# Values outside this range need station-specific verification before use.
MAX_REVIEW_DEPTH_M = 300.0
# Degrees in source WGS84. About 95--111 m in India, not a certified GPS error.
BOUNDARY_MARGIN_DEGREES = 0.001


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _label(value):
    """Case/whitespace normalization only; never strip well suffixes or fuzz."""
    return " ".join(unicodedata.normalize("NFKC", str(value)).casefold().split())


def _fingerprint(state, name, latitude, longitude):
    fields = [normalized_state(state), _label(name), f"{latitude:.5f}", f"{longitude:.5f}"]
    return hashlib.sha256(json.dumps(fields, ensure_ascii=False).encode()).hexdigest()


def _official_url(url):
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.hostname != "nwdp.nwic.gov.in" or parsed.username or parsed.password:
        raise ValueError("Expected a public HTTPS NWDP resource URL")
    return url


def _download(url, destination, *, timeout=(10, 90), max_bytes=128 * 1024 * 1024, session=None):
    """Bounded, atomic, no-overwrite acquisition; caller records provenance."""
    import requests
    url = _official_url(url)
    path = Path(destination)
    if path.exists():
        return {"path": str(path), "sha256": sha256(path), "size_bytes": path.stat().st_size,
                "reused_existing": True}
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".partial")
    if temporary.exists():
        raise ValueError("Partial download already exists; inspect it before retrying")
    client = session or requests.Session()
    own_client = session is None
    try:
        for attempt in range(3):
            try:
                with client.get(url, timeout=timeout, stream=True) as response:
                    response.raise_for_status()
                    _official_url(response.url)
                    declared = response.headers.get("Content-Length")
                    if declared and int(declared) > max_bytes:
                        raise ValueError("NWDP download exceeds the explicit size limit")
                    size = 0
                    with temporary.open("xb") as stream:
                        for chunk in response.iter_content(chunk_size=1024 * 1024):
                            size += len(chunk)
                            if size > max_bytes:
                                raise ValueError("NWDP download exceeds the explicit size limit")
                            stream.write(chunk)
                    if os.name == "nt":
                        # Windows rename atomically fails if the destination exists;
                        # unlike hard links, it needs no additional OS privilege.
                        temporary.rename(path)
                    else:
                        # POSIX rename can overwrite; link gives create-only semantics.
                        path.hardlink_to(temporary)
                        temporary.unlink()
                    return {"path": str(path), "sha256": sha256(path), "size_bytes": size,
                            "http_status": response.status_code,
                            "content_type": response.headers.get("Content-Type"),
                            "http_last_modified": response.headers.get("Last-Modified"),
                            "downloaded_at_utc": datetime.now(timezone.utc).isoformat()}
            except Exception:
                temporary.unlink(missing_ok=True)
                if attempt == 2:
                    raise
                time.sleep(2 * (attempt + 1))
    finally:
        if own_client:
            client.close()


def acquire_recent(output_dir):
    """Discover current resource URLs; acquire the advertised 2021+ CSVs."""
    directory = Path(output_dir)
    directory.mkdir(parents=True, exist_ok=True)
    manifest_path = directory / "manual_acquisition.json"
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        for resource in manifest["resources"]:
            if resource.get("downloaded") and sha256(resource["path"]) != resource["sha256"]:
                raise ValueError("Previously acquired NWDP source hash changed")
        return manifest
    metadata = directory / "manual_metadata.json"
    _download(METADATA_URL, metadata)
    payload = json.loads(metadata.read_text(encoding="utf-8"))
    if payload.get("success") is not True or not isinstance(payload.get("result", {}).get("resources"), list):
        raise ValueError("NWDP metadata schema changed")
    package = payload["result"]
    resources = []
    for resource in package["resources"]:
        if not any(period in resource.get("name", "") for period in ("2021 - 2025", "2026 - 2030")):
            continue
        url = _official_url(resource["url"])
        filename = Path(urlparse(url).path).name
        if not re.fullmatch(r"gwl_manual_quarterly_cgwb_[a-z]+_(2021_2025|2026_2030)\.csv", filename):
            raise ValueError("Unfamiliar NWDP resource name; review metadata before acquiring")
        result = {"id": resource["id"], "name": resource["name"], "url": url,
                  "metadata_last_modified": resource.get("last_modified"),
                  "license_id": package.get("license_id"), "license_title": package.get("license_title"),
                  "license_url": package.get("license_url"), "discovered": True,
                  "accessible": False, "downloaded": False, "parsed": False,
                  "integrated": False, "validated": False}
        try:
            result.update(_download(url, directory / filename), accessible=True, downloaded=True)
        except Exception as error:
            # Do not serialize arbitrary exception URLs/headers or credentials.
            result["error"] = type(error).__name__
        resources.append(result)
    if not resources:
        raise ValueError("No recognized recent NWDP manual resources")
    manifest = {"dataset_url": LANDING_URL, "metadata_url": METADATA_URL,
                "metadata_sha256": sha256(metadata), "metadata_modified": package.get("metadata_modified"),
                "resources": resources}
    manifest_path.write_text(json.dumps(manifest, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    return manifest


def acquire_telemetry_review(output_dir):
    """Acquire the four recent CGWB telemetry files for a separate source audit.

    This deliberately produces no manual observation or forecast candidate.
    The inspected Assam/Bihar resource sizes are below the explicit 128MB limit.
    """
    directory = Path(output_dir)
    directory.mkdir(parents=True, exist_ok=True)
    manifest_path = directory / "telemetry_acquisition.json"
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        for resource in manifest["resources"]:
            if resource.get("downloaded") and sha256(resource["path"]) != resource["sha256"]:
                raise ValueError("Previously acquired telemetry source hash changed")
        return manifest
    dataset = "ground-water-level-telemetry-hourly-central-ground-water-board-cgwb"
    metadata_url = f"https://nwdp.nwic.gov.in/api/3/action/package_show?id={dataset}"
    metadata = directory / "telemetry_metadata.json"
    _download(metadata_url, metadata)
    payload = json.loads(metadata.read_text(encoding="utf-8"))
    if payload.get("success") is not True or not isinstance(payload.get("result", {}).get("resources"), list):
        raise ValueError("NWDP telemetry metadata schema changed")
    package = payload["result"]
    resources = []
    for source in package["resources"]:
        if not any(period in source.get("name", "") for period in ("2021 - 2025", "2026 - 2030")):
            continue
        url = _official_url(source["url"])
        filename = Path(urlparse(url).path).name
        if not re.fullmatch(r"gwl_tel_6_hourly_cgwb_(as|br)_(2021_2025|2026_2030)\.csv", filename):
            raise ValueError("Unreviewed telemetry resource; inspect schema and size before acquiring")
        resources.append({**_download(url, directory / filename),
                          "id": source["id"], "name": source["name"], "url": url,
                          "license_id": package.get("license_id"), "license_title": package.get("license_title"),
                          "metadata_last_modified": source.get("last_modified"),
                          "discovered": True, "accessible": True, "downloaded": True,
                          "parsed": False, "integrated": False, "validated": False})
    if not resources:
        raise ValueError("No recognized recent telemetry resources")
    manifest = {"dataset_url": f"https://nwdp.nwic.gov.in/en/dataset/{dataset}",
                "metadata_url": metadata_url, "metadata_sha256": sha256(metadata), "resources": resources}
    manifest_path.write_text(json.dumps(manifest, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    return manifest


def _parse_product(path, *, source_url, resource_id, expected_sha256, value_column, product):
    path = Path(path)
    if sha256(path) != expected_sha256:
        raise ValueError("NWDP source checksum differs from the acquisition manifest")
    _official_url(source_url)
    frame = pd.read_csv(path, dtype=str, keep_default_na=False, encoding="utf-8-sig")
    if tuple(frame.columns) != (*CSV_COLUMNS[:-1], value_column):
        raise ValueError("Unverified NWDP manual CSV schema, order, or measurement units")
    frame["source_row"] = np.arange(2, len(frame) + 2)
    renamed = {"State": "state_name", "District": "district_name", "Station": "station_name",
               "Latitude": "latitude", "Longitude": "longitude", value_column: "gwl_m_bgl"}
    frame = frame.rename(columns=renamed)
    timestamp = pd.to_datetime(frame["Data Acquisition Time"], format="%d-%m-%Y %H:%M", errors="coerce")
    frame["observation_timestamp"] = timestamp
    frame["observation_date"] = timestamp.dt.normalize()
    frame["date"] = timestamp.dt.to_period("M").dt.to_timestamp()
    frame["source_month"] = timestamp.dt.strftime("%Y-%m").fillna("")
    frame["reported_date"] = timestamp.dt.strftime("%d-%m-%Y").fillna("")
    frame["source_file"] = path.name
    frame["source_url"] = source_url
    frame["source_resource_id"] = resource_id
    frame["source_sha256"] = expected_sha256
    frame["source_product"] = product
    frame["units"] = "m_bgl" if product == "CGWB_quarterly_manual_NWDP" else "m_provider_sign_unverified"
    frame["datum_basis"] = DATUM_URL if product == "CGWB_quarterly_manual_NWDP" else "Telemetry sign/datum continuity with manual positive-depth targets has not been established."
    return frame


def parse_csv(path, *, source_url, resource_id, expected_sha256):
    """Require the observed manual CSV schema; preserve source fields and rows."""
    return _parse_product(path, source_url=source_url, resource_id=resource_id,
                          expected_sha256=expected_sha256, value_column=VALUE_COLUMN,
                          product="CGWB_quarterly_manual_NWDP")


def parse_telemetry_csv(path, *, source_url, resource_id, expected_sha256):
    """Read telemetry for audit only, retaining unverified provider sign/datum.

    These rows cannot pass ``audit_manual``: telemetry product and positive-depth
    convention have not been certified. No sign reversal or pooling is applied.
    """
    return _parse_product(path, source_url=source_url, resource_id=resource_id,
                          expected_sha256=expected_sha256, value_column=TELEMETRY_VALUE_COLUMN,
                          product="CGWB_six_hourly_telemetry_NWDP")


def _raw_identity(frame):
    return [_fingerprint(state, name, lat, lon) for state, name, lat, lon in zip(
        frame.state_name, frame.station_name, frame.latitude, frame.longitude)]


def audit_manual(records, crosswalk, boundaries, *, as_of, existing_raw=None,
                 boundary_margin=BOUNDARY_MARGIN_DEGREES):
    """Quarantine invalid/ambiguous rows, then equal-weight station monthly means.

    Location fingerprints are conservative matching aids, not unique well IDs.
    A coordinate shared by differently named stations in one month is ambiguous:
    exclude all such source records rather than merge suffixes or double-weight.
    """
    if records.empty:
        raise ValueError("No NWDP records to audit")
    if not np.isfinite(boundary_margin) or boundary_margin < BOUNDARY_MARGIN_DEGREES:
        raise ValueError("Boundary margin cannot weaken the declared conservative rule")
    frame = records.copy().reset_index(drop=True)
    cutoff = pd.Timestamp(as_of).normalize()
    if pd.isna(cutoff):
        raise ValueError("Invalid observation cutoff")
    reasons = [[] for _ in range(len(frame))]

    def reject(mask, reason):
        for index in frame.index[pd.Series(mask, index=frame.index).fillna(True)]:
            reasons[index].append(reason)

    for column in ("latitude", "longitude", "gwl_m_bgl"):
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    timestamp = pd.to_datetime(frame.observation_timestamp, errors="coerce")
    frame["observation_timestamp"] = timestamp
    frame["observation_date"] = timestamp.dt.normalize()
    frame["date"] = timestamp.dt.to_period("M").dt.to_timestamp()
    reject(timestamp.isna(), "invalid_reported_timestamp")
    reject(timestamp.dt.normalize().gt(cutoff), "future_observation")
    reject(timestamp.dt.year.lt(2021), "before_declared_enrichment_period")
    reject(frame.units.ne("m_bgl"), "unverified_units")
    if "source_product" in frame:
        reject(frame.source_product.ne("CGWB_quarterly_manual_NWDP"), "unverified_manual_product")
    reject(timestamp.dt.strftime("%Y-%m").fillna("").ne(frame.source_month), "date_disagrees_with_source_month")
    reject(~np.isfinite(frame.latitude) | ~frame.latitude.between(6, 38)
           | ~np.isfinite(frame.longitude) | ~frame.longitude.between(68, 98), "invalid_india_coordinates")
    reject(~np.isfinite(frame.gwl_m_bgl), "nonfinite_depth")
    reject(frame.gwl_m_bgl.lt(0), "negative_depth_review")
    reject(frame.gwl_m_bgl.gt(MAX_REVIEW_DEPTH_M), "depth_over_300m_review")
    reject(frame.station_name.map(_label).isin(("", "-")), "missing_station_label")
    reject(frame.Agency.map(_label).ne("cgwb"), "unverified_agency")
    reject(frame.station_name.str.contains(r"\bspring\b", case=False, na=False), "spring_measurement_type_review")
    lookup = build_district_lookup(crosswalk)
    assignments = spatial_districts(frame, boundaries, lookup)
    frame["district_id"] = [item[0] for item in assignments]
    frame["mapping_basis"] = [item[1] for item in assignments]
    reject(frame.district_id.isna(), "unresolved_canonical_district")
    reject([pd.notna(district) and normalized_state(lookup["canonical"][district][1]) != normalized_state(state)
            for district, state in zip(frame.district_id, frame.state_name)], "source_state_disagrees_with_boundary")
    # Only named district polygons contribute boundaries. No snapping or name-only fallback.
    polygons = boundaries.loc[boundaries.district.notna() & boundaries.district.astype(str).str.strip().ne("")].to_crs("EPSG:4326").copy()
    polygon_ids = [resolve_district(row.st_nm, row.district, lookup)[0] for row in polygons.itertuples()]
    polygons["canonical_id"] = polygon_ids
    dissolved = polygons.dissolve(by="canonical_id").geometry.to_dict()
    from shapely.geometry import Point
    proximity = []
    for district, lat, lon in zip(frame.district_id, frame.latitude, frame.longitude):
        proximity.append(bool(pd.notna(district) and np.isfinite(lat) and np.isfinite(lon)
                              and Point(lon, lat).distance(dissolved[district].boundary) <= boundary_margin))
    reject(proximity, "near_boundary_coordinate_review")
    frame["station_key"] = _raw_identity(frame)
    frame["coordinate_key"] = [json.dumps([normalized_state(state), f"{lat:.5f}", f"{lon:.5f}"])
                               for state, lat, lon in zip(frame.state_name, frame.latitude, frame.longitude)]
    frame["station_label"] = frame.station_name.map(_label)
    aliases = frame.groupby(["coordinate_key", "date"], dropna=False).station_label.transform("nunique").gt(1)
    reject(aliases, "ambiguous_colocated_station_labels")
    identity = ["station_key", "observation_timestamp"]
    conflicts = frame.groupby(identity, dropna=False).gwl_m_bgl.transform("nunique").gt(1)
    reject(conflicts, "conflicting_station_timestamp_depths")
    duplicates = frame.duplicated(identity + ["gwl_m_bgl"], keep="first") & ~conflicts
    reject(duplicates, "duplicate_station_timestamp_reading")
    frame["existing_raw_status"] = "not_compared"
    if existing_raw is not None:
        old = existing_raw.copy()
        for column in ("latitude", "longitude", "currentlevel"):
            old[column] = pd.to_numeric(old[column], errors="coerce")
        old["station_key"] = _raw_identity(old)
        old["observation_date"] = pd.to_datetime(old.date, errors="coerce").dt.normalize()
        groups = old.groupby(["station_key", "observation_date"], dropna=False).currentlevel.agg(lambda values: set(values.dropna()))
        frame["existing_raw_status"] = [
            "new_station_date" if (key, date) not in groups else
            ("exact_station_date_depth_match" if value in groups[(key, date)] else "existing_station_date_conflict")
            for key, date, value in zip(frame.station_key, frame.observation_date, frame.gwl_m_bgl)]
        # This comparison is daily because the old input discarded acquisition times.
        reject(frame.existing_raw_status.eq("exact_station_date_depth_match"), "already_in_existing_raw")
        reject(frame.existing_raw_status.eq("existing_station_date_conflict"), "conflicts_with_existing_raw_review")
    frame["audit_reason"] = [";".join(values) for values in reasons]
    accepted = frame.loc[frame.audit_reason.eq("")].copy()
    station_month = accepted.groupby(["district_id", "date", "station_key"], as_index=False).agg(
        gwl=("gwl_m_bgl", "mean"), reading_count=("gwl_m_bgl", "size"),
        first_observation_date=("observation_date", "min"), last_observation_date=("observation_date", "max"),
        source_resource_count=("source_resource_id", "nunique"))
    monthly = station_month.groupby(["district_id", "date"], as_index=False).agg(
        gwl_mean=("gwl", "mean"), station_count=("station_key", "size"), reading_count=("reading_count", "sum"),
        first_observation_date=("first_observation_date", "min"), last_observation_date=("last_observation_date", "max"))
    for key, value in {"source": "CGWB", "metric": "GWL", "units": "m_bgl", "is_observed": True,
                       "date_basis": "calendar_month_of_source_reported_observation_date",
                       "provenance_product": "NWDP_CGWB_quarterly_manual"}.items():
        monthly[key] = value
    return frame, station_month, monthly


def build_candidates(acquisition, output_dir, *, crosswalk_path, geojson_path, existing_raw_path,
                     as_of, baseline_features=None):
    """Offline replay from hash-verified immutable inputs into a fresh directory."""
    output = Path(output_dir)
    if output.exists():
        raise ValueError("Candidate output directory already exists; choose a new path")
    resources = acquisition["resources"]
    records, parsed_resources = [], []
    for source in resources:
        if not source.get("downloaded"):
            continue
        frame = parse_csv(source["path"], source_url=source["url"], resource_id=source["id"], expected_sha256=source["sha256"])
        records.append(frame)
        dates = frame.observation_date.dropna()
        parsed_resources.append({**source, "parsed": True, "row_count": len(frame),
                                 "first_observation_date": str(dates.min().date()) if len(dates) else None,
                                 "last_observation_date": str(dates.max().date()) if len(dates) else None})
    if not records:
        raise ValueError("No downloaded NWDP resources")
    combined = pd.concat(records, ignore_index=True)
    crosswalk_path, geojson_path, existing_raw_path = map(Path, (crosswalk_path, geojson_path, existing_raw_path))
    crosswalk = pd.read_csv(crosswalk_path, dtype=str, keep_default_na=False)
    import geopandas as gpd
    boundaries = gpd.read_file(geojson_path)
    old = pd.read_csv(existing_raw_path, usecols=["state_name", "station_name", "latitude", "longitude", "date", "currentlevel"], keep_default_na=False)
    # Only recent records can overlap this candidate. Historic raw bytes remain hashed.
    old = old.loc[pd.to_datetime(old.date, errors="coerce").dt.year.ge(2021)]
    audit, station_month, monthly = audit_manual(combined, crosswalk, boundaries, as_of=as_of, existing_raw=old)
    accepted = audit.loc[audit.audit_reason.eq("")].copy()
    output.mkdir(parents=True)
    frames = {"station_records.csv": combined, "station_audit.csv": audit,
              "accepted_station_records.csv": accepted,
              "rejected_station_records.csv": audit.loc[audit.audit_reason.ne("")],
              "station_months.csv": station_month, "canonical_district_month_candidates.csv": monthly}
    coverage = monthly.groupby("district_id", as_index=False).agg(
        candidate_observed_months=("date", "size"), first_observed_month=("date", "min"),
        last_observed_month=("date", "max"), readings=("reading_count", "sum"))
    if baseline_features:
        baseline = pd.read_csv(baseline_features, dtype={"district_id": str})
        observed = baseline.is_observed.astype(str).str.casefold().eq("true")
        old_months = set(zip(baseline.loc[observed, "district_id"], pd.to_datetime(baseline.loc[observed, "date"]).dt.to_period("M")))
        monthly["already_observed_in_baseline"] = [(district, date.to_period("M")) in old_months for district, date in zip(monthly.district_id, monthly.date)]
        gains = monthly.loc[~monthly.already_observed_in_baseline].groupby("district_id").size()
        coverage["new_observed_months"] = coverage.district_id.map(gains).fillna(0).astype(int)
        old_counts = baseline.loc[observed].groupby("district_id").size()
        coverage["baseline_observed_months"] = coverage.district_id.map(old_counts).fillna(0).astype(int)
    frames["district_coverage.csv"] = coverage
    state_coverage = accepted.groupby("state_name", as_index=False).agg(
        accepted_rows=("gwl_m_bgl", "size"), stations=("station_key", "nunique"),
        districts=("district_id", "nunique"), first_observation_date=("observation_date", "min"),
        last_observation_date=("observation_date", "max"), distinct_timestamps=("observation_timestamp", "nunique"))
    frames["state_coverage.csv"] = state_coverage
    hashes = {}
    for name, frame in frames.items():
        frame.to_csv(output / name, index=False, lineterminator="\n")
        hashes[name] = sha256(output / name)
    reasons = Counter(reason for text in audit.audit_reason for reason in text.split(";") if reason)
    manifest = {"artifact_version": VERSION, "processing_version": VERSION,
                "source_url": LANDING_URL, "datum_basis_url": DATUM_URL,
                "metadata_sha256": acquisition.get("metadata_sha256"), "sources": parsed_resources,
                "crosswalk_sha256": sha256(crosswalk_path), "geojson_sha256": sha256(geojson_path),
                "existing_raw_sha256": sha256(existing_raw_path),
                "baseline_features_sha256": sha256(baseline_features) if baseline_features else None,
                "as_of": str(pd.Timestamp(as_of).date()), "candidate_only": True, "database_modified": False,
                "units": {"gwl": "m_bgl"}, "source_rows": len(combined),
                "accepted_source_rows": len(accepted), "rejected_source_rows": len(audit) - len(accepted),
                "rejection_reasons": dict(reasons), "existing_raw_comparison": audit.existing_raw_status.value_counts().to_dict(),
                "unique_station_fingerprints_before_screening": int(audit.station_key.nunique()),
                "unique_station_fingerprints_accepted": int(accepted.station_key.nunique()),
                "accepted_station_timestamps": int(accepted[["station_key", "observation_timestamp"]].drop_duplicates().shape[0]),
                "canonical_districts": int(monthly.district_id.nunique()), "district_months": len(monthly),
                "new_district_months_vs_features": int(coverage.new_observed_months.sum()) if baseline_features else None,
                "newly_locally_observed_districts": int(((coverage.baseline_observed_months == 0) & (coverage.new_observed_months > 0)).sum()) if baseline_features else None,
                "first_observation_date": str(accepted.observation_date.min().date()),
                "last_observation_date": str(accepted.observation_date.max().date()),
                "output_sha256": hashes,
                "boundary_margin_degrees": BOUNDARY_MARGIN_DEGREES, "review_depth_upper_m": MAX_REVIEW_DEPTH_M,
                "mapping": "Coordinates must intersect exactly one fixed canonical district, agree with source state, and exceed the declared boundary margin. No nearest or name-only fallback.",
                "identity": "Exact case/whitespace-normalized station label, state, and coordinates rounded to 5 decimals; district labels excluded; no suffix stripping or fuzzy merging. Ambiguous colocated labels within a month excluded.",
                "aggregation": "Mean of unique timestamps within station-month, then equal-weight station means within district-month. Existing raw daily duplicates/conflicts quarantined; overlay must retain existing genuine district-month observations.",
                "limitations": [
                    "Provider offers station labels, not independently certified globally unique well IDs. Five-decimal location fingerprints are matching aids.",
                    "CGWB monitoring documentation establishes below-ground depth convention; individual well datum, construction and aquifer metadata are not supplied.",
                    "Negative artesian depths and values over 300m are quarantined for verification, not corrected or asserted impossible.",
                    "Boundary artifact has mixed administrative vintages; coordinate mapping is conditional on this project snapshot, not certified historical districts.",
                    "Quarterly manual station composition changes; district means are not same-well trends.",
                    "Portal 2021-2025 and 2026-2030 labels are advertised ranges; actual observation dates in each CSV are reported separately.",
                    "NWDP metadata declares Other (Open) without a specific license URL. Raw files remain local and attribution is required.",
                ]}
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    return manifest


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--acquire", type=Path, help="Explicit new immutable source directory; never run from API startup")
    parser.add_argument("--acquire-telemetry-review", type=Path, help="Acquire separate telemetry audit inputs; no pooling or sign reversal")
    parser.add_argument("--acquisition-manifest", type=Path)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--as-of", default="2026-10-26")
    parser.add_argument("--crosswalk", type=Path, default=ROOT / "data_ingestion/district_crosswalk.csv")
    parser.add_argument("--geojson", type=Path, default=ROOT / "data/raw/india_districts.geojson")
    parser.add_argument("--existing-raw", type=Path, default=ROOT / "data/raw/cgwb_combined.csv")
    parser.add_argument("--baseline-features", type=Path, default=ROOT / "data/processed/features_matrix.csv")
    args = parser.parse_args(argv)
    if args.acquire_telemetry_review:
        telemetry = acquire_telemetry_review(args.acquire_telemetry_review)
        print(json.dumps({"telemetry_resources_downloaded": len(telemetry["resources"]),
                          "integrated": False, "next": "Run scripts/audit_nwdp_sources.py for the sign/cadence/overlap review."}, indent=2))
        if not (args.acquire or args.acquisition_manifest or args.output_dir):
            return 0
    manifest = acquire_recent(args.acquire) if args.acquire else None
    if args.acquisition_manifest:
        manifest = json.loads(args.acquisition_manifest.read_text(encoding="utf-8"))
    if args.output_dir:
        if manifest is None:
            parser.error("Candidate processing requires --acquisition-manifest or --acquire")
        report = build_candidates(manifest, args.output_dir, crosswalk_path=args.crosswalk,
                                  geojson_path=args.geojson, existing_raw_path=args.existing_raw,
                                  as_of=args.as_of, baseline_features=args.baseline_features)
        print(json.dumps({key: report[key] for key in ("source_rows", "accepted_source_rows", "rejected_source_rows", "canonical_districts", "district_months", "new_district_months_vs_features", "newly_locally_observed_districts", "rejection_reasons")}, indent=2))
    elif manifest is not None:
        print(json.dumps({"resources": len(manifest["resources"]), "downloaded": sum(source.get("downloaded", False) for source in manifest["resources"])}, indent=2))
    else:
        print(json.dumps({"status": "offline_plan", "source_url": LANDING_URL, "metadata_url": METADATA_URL,
                          "next": "Explicitly acquire immutable inputs, then build a new candidate directory offline."}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
