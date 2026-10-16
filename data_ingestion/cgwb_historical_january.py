"""Extract the visually inspected January 2025 section of CGWB's archive.

This is a candidate-only parser for pages 1--332 of the verified archive. It
does not infer dates from filenames or accept unfamiliar year/layout sections.
The source title identifies an unconfined aquifer dataset, not individual wells.
"""
from __future__ import annotations

import argparse
from bisect import bisect_right
import hashlib
import json
from pathlib import Path
import re

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
TITLE = "January month Depth to Water Level (In mbgl) Data of Unconfined Aquifer"
HEADERS = ("State", "District", "Block", "Village", "Latitute", "Longitude", "Date", "WL(mbgl)")
HEADER_X = (20.28, 195.84, 355.32, 480.84, 633.12, 686.76, 740.40, 779.76)
BOUNDARIES = tuple(value - 2 for value in HEADER_X[1:])
FIELDS = ("state_name", "district_name", "block", "village", "latitude", "longitude", "reported_date", "gwl_m_bgl")
SOURCE_URL = "https://cgwb.gov.in/wl_data/January_WL_1994-2025.pdf"


def _lines(words):
    lines = []
    for word in sorted(words, key=lambda row: (row["top"], row["x0"])):
        if not lines or abs(word["top"] - lines[-1][0]) > 1.5:
            lines.append((float(word["top"]), [word]))
        else:
            lines[-1][1].append(word)
    return [(top, sorted(line, key=lambda row: row["x0"])) for top, line in lines]


def parse_archive_page(words, page_number, *, page_width, page_height):
    if abs(page_width - 841.92004) > .5 or abs(page_height - 595.32001) > .5:
        raise ValueError(f"Page {page_number}: unverified January 2025 layout dimensions")
    lines = _lines(words)
    if not lines or " ".join(word["text"] for word in lines[0][1]) != TITLE:
        raise ValueError(f"Page {page_number}: unverified January mbgl/unconfined title")
    header = next(((top, line) for top, line in lines if tuple(word["text"] for word in line) == HEADERS), None)
    if header is None or any(abs(word["x0"] - expected) > 1 for word, expected in zip(header[1], HEADER_X)):
        raise ValueError(f"Page {page_number}: unverified table header positions")
    rows = []
    for top, line in lines:
        if top <= header[0] + 2:
            continue
        cells = [[] for _ in FIELDS]
        for word in line:
            cells[bisect_right(BOUNDARIES, word["x0"])].append(word["text"])
        row = dict(zip(FIELDS, (" ".join(cell).strip() for cell in cells)))
        raw_date = row["reported_date"]
        if not re.fullmatch(r"\d{2}-01-25", raw_date):
            raise ValueError(f"Page {page_number}: unsupported/non-January-2025 source date {raw_date!r}")
        parsed = pd.to_datetime(raw_date, format="%d-%m-%y", errors="coerce")
        if pd.isna(parsed) or parsed.year != 2025 or parsed.month != 1:
            raise ValueError(f"Page {page_number}: invalid January 2025 source date")
        row.update(reported_date=parsed.strftime("%d-%m-%Y"), raw_reported_date=raw_date,
            source_page=page_number, source_line_top=round(top, 3), source_month="2025-01",
            units="m_bgl", source_dataset_aquifer="Unconfined", source_dataset_aquifer_basis="dataset_title_not_well_log",
            raw_line=" ".join(word["text"] for word in line))
        rows.append(row)
    if not rows:
        raise ValueError(f"Page {page_number}: no source observations")
    return rows


def extract_january_2025(pdf_path):
    """Validate every selected page and the independently inspected next section."""
    try:
        import pdfplumber
    except ImportError as error:
        raise RuntimeError("PDF extraction requires optional pdfplumber") from error
    pdf_path = Path(pdf_path)
    digest = hashlib.sha256(pdf_path.read_bytes()).hexdigest()
    records, pages = [], []
    with pdfplumber.open(pdf_path) as pdf:
        if len(pdf.pages) != 10574:
            raise ValueError("Archive page count differs from inspected source; reverify section boundaries")
        for index in range(332):
            page = pdf.pages[index]
            rows = parse_archive_page(page.extract_words(x_tolerance=1, y_tolerance=2), index + 1,
                page_width=page.width, page_height=page.height)
            for row in rows:
                row.update(source_sha256=digest, source_file=pdf_path.name, source_url=SOURCE_URL)
            records.extend(rows)
            pages.append({"page": index + 1, "rows": len(rows)})
            page.close()
            if (index + 1) % 25 == 0:
                print(f"Verified {index + 1}/332 January 2025 pages", flush=True)
        following = pdf.pages[332]
        next_text = following.extract_text() or ""
        if abs(following.width - 792) > .5 or not re.search(r"\b\d{2}-01-24\b", next_text):
            raise ValueError("Page 333 no longer establishes the inspected January 2024 boundary")
        following.close()
    return pd.DataFrame(records), {"source_url": SOURCE_URL, "source_sha256": digest,
        "source_file": pdf_path.name, "source_size_bytes": pdf_path.stat().st_size,
        "archive_pages": 10574, "extracted_pages": [1, 332], "next_section_page": 333,
        "selected_observation_month": "2025-01", "date_basis": "actual table dates DD-MM-25, not filename",
        "units": "m_bgl", "source_dataset_aquifer": "Unconfined", "aquifer_basis": "dataset title, not well-specific log",
        "rows": len(records), "pages": pages, "production_changed": False}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pdf", type=Path)
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args(argv)
    if not args.pdf:
        print(json.dumps({"status": "offline_plan", "source_url": SOURCE_URL,
            "verified_section": "January 2025, pages 1-332; page 333 begins January 2024",
            "outputs": "New candidate station_records.csv and extraction_manifest.json only"}, indent=2))
        return 0
    if not args.output_dir:
        raise ValueError("An explicit new candidate output directory is required")
    output = args.output_dir.resolve()
    if not output.is_relative_to((ROOT / "reports/candidates").resolve()) or output.exists():
        raise ValueError("Output directory must be new and inside reports/candidates")
    frame, manifest = extract_january_2025(args.pdf)
    output.mkdir(parents=True)
    frame.to_csv(output / "station_records.csv", index=False)
    manifest["records_sha256"] = hashlib.sha256((output / "station_records.csv").read_bytes()).hexdigest()
    (output / "extraction_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: value for key, value in manifest.items() if key != "pages"}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
