"""Read retained national source bytes/CSVs; never invoke ingestion or models."""
import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
import numpy as np
import pandas as pd

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[2]
path = OUT / 'national_sources_20261023.json'
receipt_path = OUT / 'national_lineage_execution_20261023.json'
stdout_path = OUT / 'national_lineage_stdout_20261023.log'
stderr_path = OUT / 'national_lineage_stderr_20261023.log'
for target in (path, receipt_path, stdout_path, stderr_path):
    if target.exists():
        raise FileExistsError(target.name)

def sha(target):
    h = hashlib.sha256()
    with Path(target).open('rb') as stream:
        for chunk in iter(lambda: stream.read(8*1024*1024), b''):
            h.update(chunk)
    return h.hexdigest()

def load(target):
    return json.loads(Path(target).read_text(encoding='utf-8-sig'))

started = datetime.now(timezone.utc).isoformat()
legacy_path = ROOT / 'data/raw/cgwb_combined.csv'
legacy = pd.read_csv(legacy_path, dtype={'district_code': str}, usecols=['date', 'district_code', 'currentlevel'])
crosswalk = pd.read_csv(ROOT/'data_ingestion/district_crosswalk.csv', dtype=str)
legacy['district_id'] = legacy.district_code.str.strip().map(crosswalk.set_index('legacy_district_id').canonical_district_id.to_dict())
legacy['date'] = pd.to_datetime(legacy.date, errors='coerce')
legacy['value'] = pd.to_numeric(legacy.currentlevel, errors='coerce')
valid = legacy.loc[legacy.district_id.notna() & legacy.date.notna() & np.isfinite(legacy.value)]
lineage = load(ROOT/'reports/candidates/six_month_diagnostics_20261017/raw_lineage.json')
expected_legacy = lineage['input_sha256']['data/raw/cgwb_combined.csv']
legacy_result = {'rows': len(legacy), 'mapped_finite_dated_rows': len(valid),
                 'invalid_or_unmapped_rows': len(legacy)-len(valid),
                 'districts': int(valid.district_id.nunique()),
                 'reported_date_min': str(valid.date.min()), 'reported_date_max': str(valid.date.max()),
                 'duplicate_district_date_value_rows_not_proven_duplicate_wells': int(valid.duplicated(['district_id', 'date', 'value']).sum()),
                 'sha256': sha(legacy_path), 'expected_prior_lineage_sha256': expected_legacy,
                 'hash_matches_prior_lineage': sha(legacy_path) == expected_legacy}

candidate = ROOT/'reports/candidates/groundwater_updates/20261013'
manifest = load(candidate/'manifest.json')
checks = []
for name, expected in manifest['output_sha256'].items():
    actual = sha(candidate/name)
    checks.append({'file': name, 'expected_sha256': expected, 'actual_sha256': actual, 'matches': actual==expected})
pdf_path = ROOT/'data/raw/updates/20261013/cgwb_january_2026.pdf'
pdf_actual = sha(pdf_path)
audit = pd.read_csv(candidate/'station_audit.csv', dtype={'station_key': str}, parse_dates=['date', 'observation_date'])
accepted = audit.loc[audit.audit_reason.isna()].copy()
monthly = pd.read_csv(candidate/'canonical_district_month_candidates.csv', parse_dates=['date'])
station_means = accepted.groupby(['district_id', 'date', 'station_key']).gwl_m_bgl.mean().reset_index()
means = station_means.groupby(['district_id', 'date']).gwl_m_bgl.mean()
joined = monthly.merge(means.rename('independent_mean'), left_on=['district_id', 'date'], right_index=True, validate='one_to_one')
active = pd.read_csv(ROOT/'data/processed/features_matrix.csv', parse_dates=['date'])
comparison = monthly.merge(active.loc[active.date.eq('2026-01-01'), ['district_id', 'date', 'gwl_current', 'is_observed']], on=['district_id', 'date'], validate='one_to_one')
pdf_result = {'source_url_without_query': manifest['source_url'].split('?')[0], 'source_sha256': pdf_actual,
              'expected_source_sha256': manifest['source_sha256'], 'source_hash_matches': pdf_actual == manifest['source_sha256'],
              'output_hash_checks': checks, 'source_rows': len(audit), 'accepted_rows': len(accepted),
              'rejected_rows': int(audit.audit_reason.notna().sum()), 'district_months': len(monthly),
              'accepted_reported_date_counts': {str(k): int(v) for k,v in accepted.observation_date.value_counts().items()},
              'aggregation_recomputed_equal_unique_station_month_means': bool(np.allclose(joined.gwl_mean, joined.independent_mean, rtol=0, atol=1e-10)),
              'max_aggregation_absolute_difference_m': float((joined.gwl_mean-joined.independent_mean).abs().max()),
              'source_backed_january2026_means_match_active_export': bool(np.allclose(comparison.gwl_mean, comparison.gwl_current, rtol=0, atol=1e-5) and comparison.is_observed.all()),
              'active_export_comparison_rows': len(comparison), 'manifest_units': manifest['units'],
              'transport_receipt_or_provider_first_availability': 'Not established by this retained extraction manifest; as_of is process context.',
              'identity_limit': 'station_key is a location/name proxy; stable physical well/datum/replacement continuity unknown.'}

# Reviewed before execution: this helper imports only pandas/numpy/stdlib and
# --verify-only only recomputes/compares its retained JSON, without writing it.
helper = ROOT/'reports/candidates/six_month_diagnostics_20261017/verify_raw_lineage.py'
command = [sys.executable, '-B', str(helper), '--verify-only']
run_started = datetime.now(timezone.utc).isoformat()
process = subprocess.run(command, cwd=ROOT, capture_output=True)
for target, content in ((stdout_path, process.stdout), (stderr_path, process.stderr)):
    with target.open('xb') as stream:
        stream.write(content)
receipt = {'started_utc': run_started, 'completed_utc': datetime.now(timezone.utc).isoformat(),
           'command': command, 'cwd': str(ROOT), 'script_sha256': sha(helper),
           'exit_status': process.returncode, 'stdout_file': stdout_path.name, 'stderr_file': stderr_path.name,
           'stdout_sha256': hashlib.sha256(process.stdout).hexdigest(), 'stderr_sha256': hashlib.sha256(process.stderr).hexdigest()}
with receipt_path.open('x', encoding='utf-8') as stream:
    json.dump(receipt, stream, indent=2)
    stream.write('\n')
passed = legacy_result['hash_matches_prior_lineage'] and pdf_result['source_hash_matches'] and all(c['matches'] for c in checks) and pdf_result['aggregation_recomputed_equal_unique_station_month_means'] and pdf_result['source_backed_january2026_means_match_active_export'] and process.returncode == 0
result = {'started_utc': started, 'completed_utc': datetime.now(timezone.utc).isoformat(),
          'legacy_cgwb': legacy_result, 'january2026_pdf': pdf_result,
          'legacy_lineage_verification_exit_status': process.returncode, 'passed': bool(passed),
          'scope': 'Read retained source and extracted CSV bytes only; no PDF extraction, DB reconciliation, ingestion, model loads or forecasts.'}
with path.open('x', encoding='utf-8') as stream:
    json.dump(result, stream, indent=2, allow_nan=False)
    stream.write('\n')
print(json.dumps(result, indent=2))
print(process.stdout.decode('utf-8', errors='replace'))
if process.stderr:
    print(process.stderr.decode('utf-8', errors='replace'), file=sys.stderr)
sys.exit(0 if passed else 1)
