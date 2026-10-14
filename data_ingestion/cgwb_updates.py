"""Extract and audit official CGWB depth-to-water-level update PDFs.

This creates candidate CSVs only. It does not change the database, active
feature artifacts or models. The January 2026 CGWB export has a borderless,
eight-column layout; unfamiliar headers/layouts fail rather than guessing.
``pdfplumber`` is imported only when a PDF is actually extracted.
"""

from __future__ import annotations

import argparse
from bisect import bisect_right
import calendar
import hashlib
import json
from pathlib import Path
import re
import unicodedata

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
HEADERS = ("STATE_UT", "DISTRICT", "BLOCK", "VILLAGE", "LATITUDE", "LONGITUDE", "DATE", "DTWL")
FIELDS = ("state_name", "district_name", "block", "village", "latitude", "longitude", "reported_date", "gwl_m_bgl")
# Verified left positions of the column headers on the 792-point CGWB export.
HEADER_X = (98.28, 206.75, 319.99, 420.78, 493.70, 539.60, 611.21, 664.91)
# Data are left-aligned while headings are centered. Boundaries precede the
# independently inspected left edges of the data cells by four points.
COLUMN_BOUNDARIES = (163.95, 279.05, 381.15, 489.70, 535.60, 599.21, 660.91)


def normalized_name(value):
    value = unicodedata.normalize("NFKD", str(value or "")).encode("ascii", "ignore").decode()
    return " ".join(re.sub(r"[^a-z0-9]+", " ", value.lower().replace("&", " and ")).split())


def normalized_state(value):
    normalized = normalized_name(value)
    return {
        "orissa": "odisha", "uttaranchal": "uttarakhand",
        "pondicherry": "puducherry",
        "andaman and nicobar": "andaman and nicobar islands",
        "dadra and nagar haveli": "dadra and nagar haveli and daman and diu",
        "daman and diu": "dadra and nagar haveli and daman and diu",
        "nct of delhi": "delhi", "national capital territory of delhi": "delhi",
        "the dadra and nagar haveli and daman and diu": "dadra and nagar haveli and daman and diu",
    }.get(normalized, normalized)


def build_district_lookup(crosswalk):
    """State-qualified names and verified legacy codes; ambiguity is explicit."""
    required = {"legacy_district_id", "canonical_district_id", "canonical_name", "canonical_state"}
    if not required.issubset(crosswalk.columns):
        raise ValueError("Canonical district crosswalk is missing required columns")
    names, codes, canonical = {}, {}, {}
    for row in crosswalk.to_dict("records"):
        district_id = str(row["canonical_district_id"]).strip()
        state = normalized_state(row["canonical_state"])
        name = normalized_name(row["canonical_name"])
        if not district_id or not state or not name:
            raise ValueError("Empty canonical district identity")
        names.setdefault((state, name), set()).add(district_id)
        codes.setdefault((state, str(row["legacy_district_id"]).strip()), set()).add(district_id)
        identity = (str(row["canonical_name"]), str(row["canonical_state"]))
        if district_id in canonical and (normalized_name(canonical[district_id][0]), normalized_state(canonical[district_id][1])) != (name, state):
            raise ValueError(f"Conflicting canonical identity: {district_id}")
        canonical[district_id] = identity
    return {"names": names, "codes": codes, "canonical": canonical}


def resolve_district(state, name, lookup, code=None):
    state = normalized_state(state)
    named = lookup["names"].get((state, normalized_name(name)), set())
    coded = lookup["codes"].get((state, str(code).strip()), set()) if code is not None else set()
    if named and coded and named != coded:
        return None, "conflicting_name_and_code"
    candidates = coded or named
    if len(candidates) == 1:
        return next(iter(candidates)), "state_qualified_verified_code" if coded else "state_qualified_exact_name"
    return None, "ambiguous_district" if candidates else "unmapped_state_district"


def _word_lines(words, tolerance=1.5):
    lines = []
    for word in sorted(words, key=lambda item: (item["top"], item["x0"])):
        if not lines or abs(float(word["top"]) - lines[-1][0]) > tolerance:
            lines.append((float(word["top"]), [word]))
        else:
            lines[-1][1].append(word)
    return [(top, sorted(line, key=lambda item: item["x0"])) for top, line in lines]


def parse_page_words(words, page_number, *, page_width=792., expected_month=None):
    """Parse the inspected CGWB layout, preserving each physical source row."""
    lines = _word_lines(words)
    titles = [" ".join(word["text"] for word in line) for _, line in lines[:3]]
    title = next((line for line in titles if "DEPTH TO WATER LEVEL" in line), "")
    months = "|".join(calendar.month_name[1:])
    match = re.search(rf"\b({months})\s*[-–]\s*(\d{{4}})\b", title, re.IGNORECASE)
    if "mbgl" not in title.lower() or not match:
        raise ValueError(f"Page {page_number}: unverified depth units or observation month")
    month_number = list(calendar.month_name).index(match.group(1).capitalize())
    source_month = f"{match.group(2)}-{month_number:02d}"
    if expected_month is not None and source_month != str(pd.Period(expected_month, freq="M")):
        raise ValueError(f"Page {page_number}: source month disagrees with requested observation month")
    header = next(((top, line) for top, line in lines if tuple(word["text"] for word in line) == HEADERS), None)
    if header is None or abs(page_width - 792.) > .5:
        raise ValueError(f"Page {page_number}: unsupported CGWB table layout")
    if any(abs(word["x0"] - x) > 2 for word, x in zip(header[1], HEADER_X)):
        raise ValueError(f"Page {page_number}: unexpected column positions")
    records = []
    for top, line in lines:
        if top <= header[0] + 2:
            continue
        cells = [[] for _ in HEADERS]
        for word in line:
            cells[bisect_right(COLUMN_BOUNDARIES, word["x0"])].append(word["text"])
        record = dict(zip(FIELDS, (" ".join(cell).strip() for cell in cells)))
        record.update(source_page=page_number, source_line_top=round(top, 3), source_month=source_month,
                      raw_line=" ".join(word["text"] for word in line), units="m_bgl")
        records.append(record)
    if not records:
        raise ValueError(f"Page {page_number}: table contains no source records")
    return records


def extract_pdf(pdf_path, expected_month=None):
    try:
        import pdfplumber
    except ImportError as error:
        raise RuntimeError("PDF extraction requires pdfplumber; install it or use the bundled workspace Python.") from error
    pdf_path = Path(pdf_path)
    digest = hashlib.sha256(pdf_path.read_bytes()).hexdigest()
    records, pages = [], []
    with pdfplumber.open(pdf_path) as pdf:
        for number, page in enumerate(pdf.pages, 1):
            rows = parse_page_words(page.extract_words(x_tolerance=1, y_tolerance=2), number,
                                    page_width=page.width, expected_month=expected_month)
            for row in rows:
                row.update(source_sha256=digest, source_file=pdf_path.name)
            records.extend(rows)
            pages.append({"page": number, "source_rows": len(rows), "source_month": rows[0]["source_month"]})
            page.close()
    return pd.DataFrame(records), {"source_sha256": digest, "source_file": pdf_path.name, "pages": pages}


def spatial_districts(frame, boundaries, lookup):
    """Assign actual stations to the project's fixed polygons, without snapping.

    Names in the source describe today's geography; coordinates establish the
    canonical historical geography used by this model. Multiple polygon parts
    for the same district are allowed, overlapping different districts are not.
    """
    import geopandas as gpd
    if boundaries.crs is None:
        raise ValueError("District boundaries require an explicit CRS")
    # The source GeoJSON also includes unnamed state outline polygons.
    # They are not district observations and must not compete in the join.
    polygons = boundaries.loc[boundaries.district.notna() & boundaries.district.astype(str).str.strip().ne("")].to_crs("EPSG:4326").copy()
    ids = [resolve_district(row.st_nm, row.district, lookup)[0]
           for row in polygons.itertuples()]
    if any(value is None for value in ids):
        raise ValueError("A boundary has no unambiguous canonical district identity")
    polygons["canonical_id"] = ids
    valid = (np.isfinite(frame.latitude) & frame.latitude.between(6, 38)
             & np.isfinite(frame.longitude) & frame.longitude.between(68, 98))
    points = gpd.GeoDataFrame(frame.loc[valid, ["latitude", "longitude"]],
                             geometry=gpd.points_from_xy(frame.loc[valid, "longitude"],
                                                         frame.loc[valid, "latitude"]),
                             crs="EPSG:4326")
    joined = gpd.sjoin(points, polygons[["canonical_id", "geometry"]],
                       how="left", predicate="intersects")
    choices = joined.groupby(level=0).canonical_id.agg(lambda values: set(values.dropna()))
    assignments = []
    for index in frame.index:
        candidates = choices.get(index, set())
        if len(candidates) == 1:
            assignments.append((next(iter(candidates)), "station_within_fixed_canonical_boundary"))
        else:
            assignments.append((None, "ambiguous_boundary" if candidates else "outside_canonical_boundaries"))
    return assignments


def audit_records(records, crosswalk, *, as_of, boundaries=None):
    """Resolve and validate stations, then average unique station-month means.

    Conflicting readings at the same named location on the same source date
    are all excluded. Identical duplicate source rows contribute only once.
    Multiple actual dates in one month are first averaged within a station so
    more frequently sampled stations do not receive extra district weight.
    """
    lookup = build_district_lookup(crosswalk)
    frame = records.copy().reset_index(drop=True)
    if frame.empty:
        raise ValueError("No groundwater records to audit")
    cutoff = pd.Timestamp(as_of).normalize()
    frame["audit_reason"] = ""
    for column in ("latitude", "longitude", "gwl_m_bgl"):
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    frame["observation_date"] = pd.to_datetime(frame["reported_date"], format="%d-%m-%Y", errors="coerce")
    frame["date"] = frame["observation_date"].dt.to_period("M").dt.to_timestamp()
    def reject(mask, reason):
        frame.loc[mask, "audit_reason"] = frame.loc[mask, "audit_reason"].apply(lambda value: value + (";" if value else "") + reason)
    reject(~np.isfinite(frame.gwl_m_bgl), "nonfinite_depth")
    reject(frame.gwl_m_bgl.lt(0), "negative_depth")
    reject(~np.isfinite(frame.latitude) | ~frame.latitude.between(6., 38.) |
           ~np.isfinite(frame.longitude) | ~frame.longitude.between(68., 98.), "invalid_india_coordinates")
    reject(frame.observation_date.isna(), "invalid_reported_date")
    reject(frame.observation_date.gt(cutoff), "future_observation")
    actual_month = frame.observation_date.dt.strftime("%Y-%m")
    reject(frame.observation_date.notna() & actual_month.ne(frame.source_month), "date_disagrees_with_source_month")
    reject(frame.state_name.fillna("").eq("") | frame.district_name.fillna("").eq(""), "missing_state_district")
    resolved = (spatial_districts(frame, boundaries, lookup) if boundaries is not None else
                [resolve_district(row.state_name, row.district_name, lookup,
                                  getattr(row, "district_code", None)) for row in frame.itertuples()])
    frame["district_id"] = [value[0] for value in resolved]
    frame["mapping_basis"] = [value[1] for value in resolved]
    # A conflicting state is a likely coordinate/source error; renamed or split
    # districts within the same state remain eligible via their actual location.
    if boundaries is not None:
        reject(pd.Series([pd.notna(did) and normalized_state(lookup["canonical"][did][1])
                          != normalized_state(state)
                          for did, state in zip(frame.district_id, frame.state_name)], index=frame.index),
               "source_state_disagrees_with_boundary")
    reject(frame.district_id.isna(), "unresolved_canonical_district")
    station_columns = ["state_name", "district_name", "block", "village"]
    station = frame[station_columns].fillna("").map(normalized_name)
    coordinates = frame[["latitude", "longitude"]].round(5).astype(str).fillna("missing")
    frame["station_key"] = (station.astype(str).agg("|".join, axis=1) + "|" + coordinates.agg("|".join, axis=1))
    identity = ["station_key", "observation_date"]
    conflicts = frame.groupby(identity, dropna=False).gwl_m_bgl.transform("nunique").gt(1)
    reject(conflicts, "conflicting_station_date_depths")
    duplicates = frame.duplicated(identity + ["gwl_m_bgl"], keep="first") & ~conflicts
    reject(duplicates, "duplicate_station_date_reading")
    accepted = frame.loc[frame.audit_reason.eq("")].copy()
    if accepted.empty:
        monthly = pd.DataFrame(columns=["district_id", "date", "gwl_mean", "station_count", "reading_count", "first_observation_date", "last_observation_date"])
    else:
        station_month = accepted.groupby(["district_id", "date", "station_key"], as_index=False).agg(
            gwl=("gwl_m_bgl", "mean"), reading_count=("gwl_m_bgl", "size"),
            first_observation_date=("observation_date", "min"), last_observation_date=("observation_date", "max"))
        monthly = station_month.groupby(["district_id", "date"], as_index=False).agg(
            gwl_mean=("gwl", "mean"), station_count=("station_key", "size"), reading_count=("reading_count", "sum"),
            first_observation_date=("first_observation_date", "min"), last_observation_date=("last_observation_date", "max"))
    monthly["source"] = "CGWB"
    monthly["metric"] = "GWL"
    monthly["units"] = "m_bgl"
    monthly["is_observed"] = True
    monthly["date_basis"] = "calendar_month_of_source_reported_observation_date"
    return frame, monthly


def write_candidates(pdf_path, crosswalk_path, output_dir, *, as_of, expected_month=None,
                     source_url=None, geojson_path=None, extracted_records=None):
    if extracted_records is None:
        records, source = extract_pdf(pdf_path, expected_month)
    else:
        records = pd.read_csv(extracted_records, keep_default_na=False)
        digest = hashlib.sha256(Path(pdf_path).read_bytes()).hexdigest()
        if not records.source_sha256.eq(digest).all():
            raise ValueError("Extracted rows do not match the source PDF hash")
        if expected_month and not records.source_month.eq(expected_month).all():
            raise ValueError("Extracted rows disagree with the expected month")
        source = {"source_sha256": digest, "source_file": Path(pdf_path).name,
                  "pages": records.groupby("source_page").size().rename("source_rows").reset_index().to_dict("records")}
    crosswalk_path = Path(crosswalk_path)
    crosswalk = pd.read_csv(crosswalk_path, dtype=str, keep_default_na=False)
    boundaries = None
    if geojson_path is not None:
        import geopandas as gpd
        boundaries = gpd.read_file(geojson_path)
    audit, monthly = audit_records(records, crosswalk, as_of=as_of, boundaries=boundaries)
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    frames = {"station_records.csv": records, "station_audit.csv": audit,
              "rejected_station_records.csv": audit.loc[audit.audit_reason.ne("")],
              "canonical_district_month_candidates.csv": monthly}
    hashes = {}
    for name, frame in frames.items():
        target = output / name
        frame.to_csv(target, index=False)
        hashes[name] = hashlib.sha256(target.read_bytes()).hexdigest()
    unmapped = audit.loc[audit.district_id.isna()].groupby(["state_name", "district_name", "mapping_basis"], dropna=False).size().reset_index(name="source_rows")
    unmapped.to_csv(output / "unmapped_districts.csv", index=False)
    reasons = audit.loc[audit.audit_reason.ne(""), "audit_reason"].str.split(";").explode().value_counts().to_dict()
    manifest = {**source, "artifact_version": "cgwb-pdf-update-v1", "source_url": source_url,
                "crosswalk_sha256": hashlib.sha256(crosswalk_path.read_bytes()).hexdigest(),
                "as_of": str(pd.Timestamp(as_of).date()), "source_months": sorted(records.source_month.unique()),
                "units": {"gwl": "m_bgl"}, "candidate_only": True, "database_modified": False,
                "source_rows": len(records), "accepted_source_rows": int(audit.audit_reason.eq("").sum()),
                "rejected_source_rows": int(audit.audit_reason.ne("").sum()), "rejection_reasons": reasons,
                "canonical_districts": int(monthly.district_id.nunique()), "district_months": len(monthly),
                "output_sha256": hashes,
                "aggregation": "Mean across unique station-month means; exact duplicate station/date readings excluded, conflicting values excluded.",
                "mapping": ("Actual station coordinates intersect exactly one canonical district in the fixed project boundary artifact; no nearest-district fallback."
                            if geojson_path is not None else "State-qualified exact district names; geographic boundaries not verified."),
                "geojson_sha256": hashlib.sha256(Path(geojson_path).read_bytes()).hexdigest() if geojson_path else None,
                "limitations": ["District station coverage can change; aggregated depths are not a comparison of identical wells across years.",
                                "A station identity combines state, district, block, village and coordinates; the PDF supplies no unique well identifier.",
                                "January observations do not establish fresh readings for later months."]}
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2, allow_nan=False), encoding="utf-8")
    return manifest


def validate_candidates(directory, *, as_of):
    """Fail closed on altered/unverified artifacts before opening the DB."""
    directory = Path(directory)
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    candidate = directory / "canonical_district_month_candidates.csv"
    if (manifest.get("artifact_version") != "cgwb-pdf-update-v1"
            or not manifest.get("geojson_sha256") or manifest.get("units", {}).get("gwl") != "m_bgl"):
        raise ValueError("Groundwater candidate needs verified depth units and geographic mapping")
    if hashlib.sha256(candidate.read_bytes()).hexdigest() != manifest["output_sha256"].get(candidate.name):
        raise ValueError("Groundwater candidate hash differs from the manifest")
    if manifest["geojson_sha256"] != hashlib.sha256((ROOT / "data/raw/india_districts.geojson").read_bytes()).hexdigest():
        raise ValueError("Groundwater candidate used a different district boundary generation")
    frame = pd.read_csv(candidate, dtype={"district_id": str})
    for column in ("date", "first_observation_date", "last_observation_date"):
        frame[column] = pd.to_datetime(frame[column], errors="coerce")
    if frame.empty or frame.duplicated(["district_id", "date"]).any():
        raise ValueError("Groundwater candidate must contain unique nonempty district months")
    values = pd.to_numeric(frame.gwl_mean, errors="coerce")
    dates = frame.date
    if (not np.isfinite(values).all() or values.lt(0).any() or dates.isna().any()
            or not dates.dt.is_month_start.all() or dates.gt(pd.Timestamp(as_of)).any()
            or frame.last_observation_date.gt(pd.Timestamp(as_of)).any()
            or frame.first_observation_date.isna().any() or frame.last_observation_date.isna().any()
            or frame.first_observation_date.gt(frame.last_observation_date).any()
            or not frame.first_observation_date.dt.to_period("M").eq(dates.dt.to_period("M")).all()
            or not frame.last_observation_date.dt.to_period("M").eq(dates.dt.to_period("M")).all()
            or not frame.source.eq("CGWB").all() or not frame.metric.eq("GWL").all()
            or not frame.units.eq("m_bgl").all() or not frame.is_observed.eq(True).all()
            or frame.station_count.lt(1).any() or frame.reading_count.lt(frame.station_count).any()):
        raise ValueError("Groundwater candidate has invalid observations, dates or units")
    return frame, manifest


def apply_candidates(conn, directory, *, as_of):
    """Insert only missing months; retain all existing historical aggregates.

    The caller owns the transaction. Source station/audit CSVs and the hashed
    manifest must be kept with the candidate directory for provenance.
    """
    import psycopg2.extras
    frame, manifest = validate_candidates(directory, as_of=as_of)
    with conn.cursor() as cur:
        cur.execute("SELECT district_id FROM districts")
        known = {row[0] for row in cur.fetchall()}
        if set(frame.district_id) - known:
            raise ValueError("Groundwater update contains unknown canonical districts")
        cur.execute("SELECT district_id, date, value FROM raw_data WHERE source='CGWB' AND metric='GWL'")
        old = pd.DataFrame(cur.fetchall(), columns=["district_id", "date", "old_value"])
        old["date"] = pd.to_datetime(old.date)
        merged = frame.merge(old, on=["district_id", "date"], how="left", validate="one_to_one")
        overlaps = merged.loc[merged.old_value.notna()]
        overlaps.to_csv(Path(directory) / "retained_existing_district_months.csv", index=False)
        rows = [(row.district_id, row.date.date(), "CGWB", "GWL", float(row.gwl_mean))
                for row in frame.itertuples()]
        inserted = 0
        for offset in range(0, len(rows), 1000):
            psycopg2.extras.execute_values(cur, """
                INSERT INTO raw_data (district_id, date, source, metric, value) VALUES %s
                ON CONFLICT (district_id, date, source, metric) DO NOTHING
            """, rows[offset:offset + 1000], page_size=1000)
            inserted += cur.rowcount
    return {"source_sha256": manifest["source_sha256"], "candidate_months": len(frame),
            "inserted_months": inserted, "retained_existing_months": len(overlaps),
            "newest_observation_month": str(frame.date.max().date()),
            "aggregation_caveat": "Station coverage may differ from earlier observations; district averages do not track identical wells."}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pdf", type=Path)
    parser.add_argument("--crosswalk", type=Path, default=ROOT / "data_ingestion/district_crosswalk.csv")
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--as-of", required=True)
    parser.add_argument("--expected-month", help="Fail unless every page states this observation month (YYYY-MM)")
    parser.add_argument("--source-url")
    parser.add_argument("--geojson", type=Path, default=ROOT / "data/raw/india_districts.geojson")
    parser.add_argument("--extracted-records", type=Path, help="Reuse hash-verified extraction from this PDF")
    parser.add_argument("--apply-candidates", type=Path, help="Insert only missing verified district months from this candidate directory")
    args = parser.parse_args(argv)
    if args.apply_candidates is not None:
        from db.connection import get_connection
        validate_candidates(args.apply_candidates, as_of=args.as_of)
        conn = get_connection()
        try:
            with conn:
                result = apply_candidates(conn, args.apply_candidates, as_of=args.as_of)
        finally:
            conn.close()
        (args.apply_candidates / "applied.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
        print(json.dumps(result, indent=2))
        return
    if args.pdf is None:
        parser.error("--pdf is required unless --apply-candidates is supplied")
    if args.output_dir is None:
        parser.error("--output-dir is required when extracting a PDF")
    manifest = write_candidates(args.pdf, args.crosswalk, args.output_dir, as_of=args.as_of,
                                expected_month=args.expected_month, source_url=args.source_url,
                                geojson_path=args.geojson, extracted_records=args.extracted_records)
    print(json.dumps({key: manifest[key] for key in ("source_rows", "accepted_source_rows", "rejected_source_rows", "canonical_districts", "district_months", "rejection_reasons")}, indent=2))


if __name__ == "__main__":
    main()
