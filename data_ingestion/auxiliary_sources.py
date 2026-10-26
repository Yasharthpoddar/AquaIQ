"""Bounded, explicit acquisition of auxiliary scientific source evidence.

These are contextual candidates, not groundwater-depth observations or active
model inputs. No imports from the API, DB writes, training, or automatic updates.
The system HTTPS trust store is retained; certificate validation is never disabled.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import time
from urllib.request import Request, urlopen
import xml.etree.ElementTree as ET

VERSION = "auxiliary-source-audit-v1"
ROOT = Path(__file__).resolve().parents[1]
MAX_BYTES = 30_000_000
SOURCES = {
    "cgwb_gwra_2025_blocks": {
        "url": "https://cgwb.gov.in/cgwbpnm/public/uploads/documents/1767356717630008751file.pdf",
        "format": "pdf", "role": "contextual_assessment_categories",
        "sha256": "7a30b79ce2b25020da5c574f6ae50ee4335fbe409ee2600a9f2a8f9449e2231f",
    },
    "cgwb_gwra_2025_facts": {
        "url": "https://cgwb.gov.in/sites/default/files/2025-12/fact_sheet_2025_website_links_0.pdf",
        "format": "pdf", "role": "fact_sheet_link_index_only",
        "sha256": "6d59fb18c5c7eacf41dd7450de5eec5efc2ffe601232f0f6ddf754045401b553",
    },
    "soilgrids_clay_vrt": {
        "url": "https://files.isric.org/soilgrids/latest/data/clay/clay_0-5cm_mean.vrt",
        "format": "vrt", "role": "raster_metadata_not_raster_values",
        "sha256": "ad1a77d56090bf543e3600bc48d4cd6fa80f8e1a9eb37177044de65a64848ede",
    },
    "soilgrids_point_rural": {
        "url": "https://rest.isric.org/soilgrids/v2.0/properties/query?lon=77.5&lat=28.5&property=clay&depth=0-5cm&value=mean",
        "format": "json", "role": "single_pixel_modeled_soil_sample_not_groundwater",
        # Response includes a non-deterministic query duration. The manifest
        # hashes exact response bytes; no fixed checksum can certify this API.
    },
    "worldcover_tile_index": {
        "url": "https://esa-worldcover.s3.eu-central-1.amazonaws.com/esa_worldcover_grid.geojson",
        "format": "geojson", "role": "tile_index_not_landcover_values",
        "sha256": "eeb5074bf182c411b3872b2494f6514401ecd9ba8ba0c353fe282f1e2b822f5b",
    },
    "grace_gsfc_availability": {
        "url": "https://earth.gsfc.nasa.gov/sites/default/files/geo/gsfc.glb_.200204_202603_rl06v2.0_obp-ice6gd_halfdegree.nc",
        "format": "head", "role": "availability_probe_only_not_downloaded",
    },
}
CATEGORIES = {"safe", "semi_critical", "critical", "over_exploited", "salinity"}


def validate_content(content, file_format):
    """Reject HTML error bodies masquerading as downloadable scientific data."""
    if file_format == "pdf":
        if not content.startswith(b"%PDF-"):
            raise ValueError("Resource is not a PDF")
        return {"schema_checked": "pdf_magic_only"}
    if file_format == "vrt":
        root = ET.fromstring(content)
        if root.tag != "VRTDataset" or root.find("SRS") is None or not root.findall(".//SourceFilename"):
            raise ValueError("Resource is not a georeferenced VRT source index")
        return {"raster_width": int(root.attrib["rasterXSize"]),
                "raster_height": int(root.attrib["rasterYSize"]),
                "referenced_rasters": len(root.findall(".//SourceFilename")),
                "raster_values_downloaded": False}
    data = json.loads(content)
    if file_format == "geojson":
        if data.get("type") != "FeatureCollection" or not isinstance(data.get("features"), list):
            raise ValueError("Resource is not a GeoJSON tile index")
        return {"tile_index_features": len(data["features"]), "landcover_pixels_downloaded": False}
    if data.get("type") != "Feature" or data.get("geometry", {}).get("coordinates") != [77.5, 28.5]:
        raise ValueError("Unexpected SoilGrids response location/schema")
    layers = data.get("properties", {}).get("layers", [])
    if len(layers) != 1 or layers[0].get("name") != "clay":
        raise ValueError("Unexpected SoilGrids variable")
    layer = layers[0]
    if layer.get("unit_measure", {}).get("mapped_units") != "g/kg":
        raise ValueError("Unexpected SoilGrids units")
    if len(layer.get("depths", [])) != 1 or layer["depths"][0].get("label") != "0-5cm":
        raise ValueError("Unexpected SoilGrids depth interval")
    value = layer["depths"][0].get("values", {}).get("mean")
    if value is not None and (isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 <= value <= 1000):
        raise ValueError("Invalid SoilGrids clay mean")
    return {"sample_rows": 1, "valid_soil_values": int(value is not None),
            "clay_g_per_kg": value, "clay_percent": value / 10 if value is not None else None,
            "groundwater_observations": 0}


def acquire(source_id, output_directory, *, opener=urlopen, timeout=40, retries=1):
    """Retrieve one fixed public resource into a new immutable file.

    A changed fixed-source checksum fails and requires a reviewed catalog update.
    HTTP failures and parser/checksum failures remain different manifest states.
    """
    source = SOURCES[source_id]
    destination = Path(output_directory) / f"{source_id}.{source['format']}"
    if destination.exists():
        raise FileExistsError(f"Immutable destination already exists: {destination}")
    if not 0 < timeout <= 60 or retries not in (0, 1, 2):
        raise ValueError("Use bounded timeout <=60 seconds and at most two retries")
    record = {"source_id": source_id, "url": source["url"], "role": source["role"],
              "checked_at_utc": datetime.now(timezone.utc).isoformat(),
              "status": {"discovered": True, "accessible": False, "downloaded": False,
                         "parsed": False, "integrated": False, "validated": False}, "attempts": []}
    for attempt in range(retries + 1):
        try:
            request = Request(source["url"], method="HEAD" if source["format"] == "head" else "GET",
                              headers={"User-Agent": "AquaIQ academic data-source audit"})
            with opener(request, timeout=timeout) as response:
                record.update(http_status=response.status, final_url=response.url,
                              content_type=response.headers.get("Content-Type"),
                              last_modified=response.headers.get("Last-Modified"),
                              content_length=response.headers.get("Content-Length"), etag=response.headers.get("ETag"))
                record["attempts"].append({"http_status": response.status})
                if response.status != 200:
                    raise ValueError("Expected successful HTTP status")
                if response.url.split(":", 1)[0] != "https":
                    raise ValueError("Refusing insecure redirect")
                record["status"]["accessible"] = True
                if source["format"] == "head":
                    return record
                size = response.headers.get("Content-Length")
                if size is not None and int(size) > MAX_BYTES:
                    raise ValueError("Resource exceeds explicit size budget")
                content = response.read(MAX_BYTES + 1)
            if len(content) > MAX_BYTES:
                raise ValueError("Resource exceeds explicit size budget")
            digest = hashlib.sha256(content).hexdigest()
            if source.get("sha256") and digest != source["sha256"]:
                raise ValueError("Source checksum changed; reverify before updating catalog")
            parsed = validate_content(content, source["format"])
            destination.parent.mkdir(parents=True, exist_ok=True)
            with destination.open("xb") as stream:
                stream.write(content)
            record.update(path=str(destination), size_bytes=len(content), sha256=digest, schema=parsed)
            record["status"].update(downloaded=True, parsed=source["format"] != "pdf", validated=True)
            record["validation_scope"] = "source_integrity_and_format_only_not_predictive_validation"
            return record
        except Exception as error:
            record["attempts"].append({"error_type": type(error).__name__, "message": str(error)[:300]})
            # A changed/malformed source cannot be repaired by retrying bytes.
            if isinstance(error, (ValueError, FileExistsError, ET.ParseError)):
                break
            if attempt < retries:
                time.sleep(attempt + 1)
    return record


def validate_gwra_tables(tables):
    """Parse the inspected five-column 2025 assessment layout, never depth labels."""
    rows = []
    header = ["S. No.", "State", "District", "Assessment Unit Name", "Categorization"]
    for page_number, table in enumerate(tables, 1):
        if not table or table[0] != ["GWRA - 2025", None, None, None, None] or table[1] != header:
            raise ValueError(f"Page {page_number}: unverified GWRA2025 header/layout")
        for cells in table[2:]:
            if len(cells) != 5 or any(not isinstance(value, str) or not value.strip() for value in cells):
                raise ValueError(f"Page {page_number}: incomplete assessment row")
            serial, state, district, unit, raw_category = [" ".join(value.split()) for value in cells]
            # The verified Puducherry rows use title case (Safe/Salinity).
            category = raw_category.lower()
            if not re.fullmatch(r"[1-9][0-9]*", serial) or int(serial) != len(rows) + 1 or category not in CATEGORIES:
                raise ValueError(f"Page {page_number}: unexpected serial/category")
            rows.append({"serial": int(serial), "state": state, "district": district,
                         "assessment_unit": unit, "category": category,
                         "raw_category": raw_category, "source_page": page_number})
    if not rows:
        raise ValueError("No assessment rows")
    return rows


def parse_gwra_pdf(path):
    """Optional offline contextual extraction. pdfplumber is not an API dependency."""
    import pdfplumber
    path = Path(path)
    if hashlib.sha256(path.read_bytes()).hexdigest() != SOURCES["cgwb_gwra_2025_blocks"]["sha256"]:
        raise ValueError("Unverified GWRA2025 PDF checksum")
    with pdfplumber.open(path) as pdf:
        if len(pdf.pages) != 97:
            raise ValueError("Unverified GWRA2025 page count")
        tables = []
        for page in pdf.pages:
            extracted = page.extract_tables()
            if len(extracted) != 1:
                raise ValueError("Expected one contextual assessment table per page")
            tables.append(extracted[0])
            page.close()
    rows = validate_gwra_tables(tables)
    if len(rows) != 6762:
        raise ValueError("Inspected source row count changed")
    return rows, {"rows": len(rows), "categories": dict(Counter(row["category"] for row in rows)),
                  "states": len({row["state"] for row in rows}),
                  "source_district_labels": len({(row["state"], row["district"]) for row in rows}),
                  "groundwater_depth_observations": 0, "role": "contextual_resource_assessment_only"}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--download", action="store_true", help="Explicitly permit network acquisition")
    parser.add_argument("--source", choices=sorted(SOURCES), action="append")
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--parse-gwra", type=Path, help="Offline parse of checksum-verified contextual PDF")
    args = parser.parse_args(argv)
    if not args.download and not args.parse_gwra:
        print(json.dumps({"status": "offline_plan", "version": VERSION, "sources": SOURCES}, indent=2))
        return 0
    output = args.output_dir.resolve() if args.output_dir else None
    if output is None or output.exists() or not output.is_relative_to((ROOT / "data/raw/official_enrichment").resolve()):
        raise ValueError("An explicit new directory inside data/raw/official_enrichment is required")
    output.mkdir(parents=True)
    report = {"processing_version": VERSION, "integrated_into_model": False, "sources": []}
    if args.download:
        report["sources"] = [acquire(source_id, output) for source_id in args.source or SOURCES]
    if args.parse_gwra:
        rows, summary = parse_gwra_pdf(args.parse_gwra)
        (output / "gwra_contextual_rows.json").write_text(json.dumps(rows) + "\n", encoding="utf-8")
        report["gwra_contextual_summary"] = summary
    (output / "acquisition_manifest.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return int(any(not item["status"]["accessible"] or (item["role"] != "availability_probe_only_not_downloaded"
                and not item["status"]["validated"]) for item in report["sources"]))


if __name__ == "__main__":
    raise SystemExit(main())
