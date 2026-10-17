"""Offline source-CSV coverage using canonical IDs and configured calendar months.

Coverage counts distinct months with finite values, never rows or imputed features.
Reports describe named CSVs; database-only updates are outside their scope.
Run: python -m data_ingestion.data_completeness
"""
from pathlib import Path
import argparse
import json
import numpy as np
import pandas as pd
import yaml
from data_ingestion.ingest_imd_era5 import NAME_ALIASES, norm_state, norm_str

ROOT = Path(__file__).resolve().parents[1]
CONFIG = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))
DATA_RAW = ROOT / CONFIG["paths"]["data_raw"]
PROCESSED_DIR = ROOT / CONFIG["paths"]["data_processed"]
CROSSWALK_PATH = ROOT / "data_ingestion" / "district_crosswalk.csv"


def study_months(config=None):
    """The study window is inclusive and may end during its last month."""
    dates = (config or CONFIG)["date_range"]
    start, end = pd.Period(dates["start"], "M"), pd.Period(dates["end"], "M")
    if end < start:
        raise ValueError("Study end must not precede its start")
    return pd.period_range(start, end, freq="M")


EXPECTED_MONTHS = len(study_months())


def canonical_mapping(crosswalk=None):
    frame = pd.read_csv(CROSSWALK_PATH, dtype=str) if crosswalk is None else crosswalk.copy()
    required = {"legacy_district_id", "canonical_district_id", "canonical_name", "canonical_state"}
    if not required.issubset(frame):
        raise ValueError("Canonical crosswalk columns are missing")
    if frame[list(required)].isna().any().any():
        raise ValueError("Canonical crosswalk identities must not be missing")
    for col in required:
        frame[col] = frame[col].str.strip()
        if frame[col].eq("").any():
            raise ValueError("Canonical crosswalk identities must not be blank")
    if (frame.groupby("legacy_district_id").canonical_district_id.nunique() > 1).any():
        raise ValueError("Ambiguous legacy district ID")
    legacy = dict(zip(frame.legacy_district_id, frame.canonical_district_id))
    names = {}
    for row in frame.itertuples():
        name, state = norm_str(row.canonical_name), norm_state(row.canonical_state)
        for alias in [name, *NAME_ALIASES.get(name, [])]:
            names.setdefault((norm_str(alias), state), set()).add(row.canonical_district_id)
    return frame, legacy, names


def _coverage(path, source, mapping, config=None):
    _, legacy, names = mapping
    months = study_months(config)
    result = {}
    diagnostics = {"path": str(path), "rows": 0, "unmapped_rows": 0,
                   "invalid_date_rows": 0, "nonfinite_or_missing_rows": 0,
                   "outside_study_rows": 0, "scope": "source CSV only; excludes database-only updates"}
    if not Path(path).exists():
        diagnostics["available"] = False
        out = pd.DataFrame(columns=["district_id", f"{source}_months"])
        out.attrs["diagnostics"] = diagnostics
        return out
    diagnostics["available"] = True
    for frame in pd.read_csv(path, dtype=str, chunksize=100_000):
        diagnostics["rows"] += len(frame)
        if source == "cgwb":
            ids = frame["district_code"].str.strip().map(legacy)
            dates = pd.to_datetime(frame["date"], errors="coerce", format="mixed").dt.to_period("M")
            values = frame[["currentlevel"]].apply(pd.to_numeric, errors="coerce")
        else:
            if not {"district", "st_nm", "year", "month"}.issubset(frame):
                raise ValueError("Weather coverage requires state, district, year and month")
            pairs = zip(frame.district.map(norm_str), frame.st_nm.map(norm_state))
            ids = pd.Series([next(iter(names[p])) if len(names.get(p, ())) == 1 else None
                             for p in pairs], index=frame.index)
            dates = pd.to_datetime(dict(year=pd.to_numeric(frame.year, errors="coerce"),
                                        month=pd.to_numeric(frame.month, errors="coerce"), day=1),
                                   errors="coerce").dt.to_period("M")
            cols = ["rainfall_mm"] if source == "imd" else ["temperature", "evapotranspiration"]
            values = frame[cols].apply(pd.to_numeric, errors="coerce")
        finite = pd.Series(np.isfinite(values.to_numpy(dtype=float)).all(axis=1), index=frame.index)
        in_period = dates.isin(months)
        diagnostics["unmapped_rows"] += int(ids.isna().sum())
        diagnostics["invalid_date_rows"] += int(dates.isna().sum())
        diagnostics["nonfinite_or_missing_rows"] += int((~finite).sum())
        diagnostics["outside_study_rows"] += int((dates.notna() & ~in_period).sum())
        valid = ids.notna() & dates.notna() & finite & in_period
        for district, month in zip(ids[valid], dates[valid]):
            result.setdefault(district, set()).add(month)
    out = pd.DataFrame([(did, len(dates)) for did, dates in sorted(result.items())],
                       columns=["district_id", f"{source}_months"])
    out.attrs["diagnostics"] = diagnostics
    return out


def check_cgwb(mapping=None, config=None):
    return _coverage(DATA_RAW / "cgwb_combined.csv", "cgwb", mapping or canonical_mapping(), config)


def check_imd(mapping=None, config=None):
    return _coverage(PROCESSED_DIR / "imd_rainfall_district_monthly.csv", "imd", mapping or canonical_mapping(), config)


def check_era5(mapping=None, config=None):
    return _coverage(PROCESSED_DIR / "era5_district_monthly.csv", "era5", mapping or canonical_mapping(), config)


def compute_report(crosswalk=None, config=None):
    mapping = canonical_mapping(crosswalk)
    report = pd.DataFrame({"district_id": sorted(mapping[0].canonical_district_id.unique())})
    expected = len(study_months(config))
    diagnostics = {}
    for source, loader in [("cgwb", check_cgwb), ("imd", check_imd), ("era5", check_era5)]:
        coverage = loader(mapping, config)
        diagnostics[source] = coverage.attrs["diagnostics"]
        report = report.merge(coverage, on="district_id", how="left", validate="one_to_one")
        column = f"{source}_months"
        report[column] = report[column].fillna(0).astype(int)
        report[f"{source}_pct"] = (report[column] / expected * 100).round(1)
    report["expected_months"] = expected
    report["overall_pct"] = report[["cgwb_pct", "imd_pct", "era5_pct"]].min(axis=1)
    report["coverage_tier"] = pd.cut(report.overall_pct, [-1, 25, 50, 75, 100],
                                    labels=["Poor (<25%)", "Fair (25-50%)", "Good (50-75%)", "Excellent (>75%)"])
    report.attrs["source_diagnostics"] = diagnostics
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "reports" / "data_completeness_report.csv")
    args = parser.parse_args(argv)
    report = compute_report()
    output = args.output.resolve()
    for protected in (DATA_RAW.resolve(), PROCESSED_DIR.resolve(), CROSSWALK_PATH.resolve().parent):
        if output == protected or protected in output.parents:
            raise ValueError("Coverage report must be outside source and processed dataset directories")
    output.parent.mkdir(parents=True, exist_ok=True)
    report.to_csv(output, index=False)
    output.with_suffix(".json").write_text(json.dumps({
        "expected_months": int(report.expected_months.iloc[0]), "districts": len(report),
        "sources": report.attrs["source_diagnostics"]}, indent=2), encoding="utf-8")
    print(f"{len(report)} canonical districts; {len(study_months())} configured months; report: {output}")


if __name__ == "__main__":
    main()
