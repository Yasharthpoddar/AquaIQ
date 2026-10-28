"""Fail clearly when the existing regression suite's private assets are absent.

This is a read-only presence/metadata/hash preflight, not a replacement for the
unchanged tests. It does not load a model, parse observation rows, contact a
database, read environment files, download data or write an asset.
"""
import hashlib
import json
from pathlib import Path, PurePosixPath
import re


ROOT = Path(__file__).resolve().parents[1]
GUIDE = 'docs/FINAL_RELEASE_REPRODUCTION.md'
FEATURE_CSV = 'data/processed/features_matrix.csv'
FEATURE_MANIFEST = 'data/processed/feature_manifest.json'
SCENARIO_CONTRACT = 'research/experimental_scenario_sources.json'
MONTHLY_POINTER = 'models/checkpoints/aquaiq_monthly_climate.json'
MONTHLY_EVALUATION = 'reports/climate_forecast_evaluation.json'
PRODUCTION_POINTER = 'models/artifacts/aquaiq_climate_12m.json'


def repository_path(root, name, *, parent=None):
    """Resolve metadata paths without allowing escapes or private-file reads."""
    if (not isinstance(name, str) or not name or '\\' in name or ':' in name
            or any(ord(c) < 32 for c in name)):
        raise ValueError('Expected a safe repository-relative file path.')
    relative = PurePosixPath(name)
    if (relative.is_absolute() or '..' in relative.parts or not relative.parts
            or any(part.lower() == '.git' or part.lower().startswith('.env') for part in relative.parts)
            or relative.suffix.lower() in {'.pem', '.key', '.pfx', '.db', '.sqlite', '.sqlite3', '.dump'}):
        raise ValueError('Expected a safe repository-relative file path.')
    root = Path(root).resolve()
    path = (root if parent is None else parent) / Path(*relative.parts)
    if not path.is_relative_to(root):
        raise ValueError('Asset path is outside the repository.')
    for item in (path, *path.parents):
        if item == root.parent:
            break
        if item.is_symlink() or getattr(item, 'is_junction', lambda: False)():
            raise ValueError('Asset paths must not traverse links or junctions.')
    if not path.resolve().is_relative_to(root):
        raise ValueError('Asset path is outside the repository.')
    return path


def validate_assets(root=ROOT):
    """Check genuine pinned local inputs without inspecting their data values."""
    root = Path(root).resolve()
    issues, checked, digests = [], set(), {}

    def problem(message):
        if message not in issues:
            issues.append(message)

    def asset(name, *, parent=None, context=None):
        try:
            path = repository_path(root, name, parent=parent)
        except ValueError:
            # Never echo an untrusted metadata value, which could contain userinfo.
            problem(f'Unsafe or missing file-path field: {context or "required asset"}.')
            return None
        relative = path.relative_to(root).as_posix()
        if not path.is_file():
            problem(f'Missing required asset: {relative}.')
            return None
        checked.add(relative)
        return path

    def metadata(path):
        if path is None:
            return None
        try:
            value = json.loads(path.read_text(encoding='utf-8-sig'))
            if not isinstance(value, dict):
                raise ValueError()
            return value
        except (OSError, UnicodeError, ValueError):
            problem(f'Invalid JSON metadata object: {path.relative_to(root).as_posix()}.')
            return None

    def bound_hash(path, expected, context):
        if not isinstance(expected, str) or not re.fullmatch(r'[0-9a-f]{64}', expected):
            problem(f'Missing or invalid SHA-256 field: {context}.')
            return
        if path is None:
            return
        try:
            if path not in digests:
                digest = hashlib.sha256()
                with path.open('rb') as handle:
                    for block in iter(lambda: handle.read(1024 * 1024), b''):
                        digest.update(block)
                digests[path] = digest.hexdigest()
            if digests[path] != expected:
                problem(f'Asset checksum differs from its metadata: {path.relative_to(root).as_posix()}.')
        except OSError:
            problem(f'Cannot read required asset: {path.relative_to(root).as_posix()}.')

    matrix = asset(FEATURE_CSV)
    manifest = metadata(asset(FEATURE_MANIFEST))
    if manifest is not None:
        if manifest.get('sample_only') is not False:
            problem(f'A full, non-sample feature manifest is required: {FEATURE_MANIFEST}.')
        if not isinstance(manifest.get('generation_id'), str) or not manifest['generation_id']:
            problem(f'Missing feature generation identity: {FEATURE_MANIFEST}.')
        bound_hash(matrix, manifest.get('feature_csv_sha256'), FEATURE_MANIFEST + ':feature_csv_sha256')

    contract = metadata(asset(SCENARIO_CONTRACT))
    if contract is not None:
        for field in ('feature_csv', 'feature_manifest', 'district_crosswalk'):
            member = asset(contract.get(field + '_path'), context=SCENARIO_CONTRACT + ':' + field + '_path')
            bound_hash(member, contract.get(field + '_sha256'), SCENARIO_CONTRACT + ':' + field + '_sha256')
        if manifest is not None and contract.get('feature_generation_id') != manifest.get('generation_id'):
            problem('Scenario contract and feature manifest generation identities differ.')

    evaluation = metadata(asset(MONTHLY_EVALUATION))
    for name in (MONTHLY_POINTER, PRODUCTION_POINTER):
        pointer_path = asset(name)
        pointer = metadata(pointer_path)
        if pointer is None:
            continue
        if pointer.get('bundle_schema_version') != 1:
            problem(f'Unsupported model bundle pointer schema: {name}.')
        members = {}
        for kind in ('model', 'card'):
            member = asset(pointer.get(kind + '_path'), parent=pointer_path.parent,
                           context=name + ':' + kind + '_path')
            members[kind] = member
            bound_hash(member, pointer.get(kind + '_sha256'), name + ':' + kind + '_sha256')
        card = metadata(members['card'])
        if card is None:
            continue
        if card.get('model_sha256') != pointer.get('model_sha256'):
            problem(f'Model card and pointer model identities differ: {name}.')
        if manifest is not None and card.get('feature_generation_id') != manifest.get('generation_id'):
            problem(f'Model card and feature manifest generation identities differ: {name}.')
        if name == MONTHLY_POINTER and evaluation is not None:
            for field in ('model_sha256', 'feature_generation_id', 'data_sha256'):
                if not evaluation.get(field) or card.get(field) != evaluation[field]:
                    problem(f'Monthly bundle differs from its retained evaluation identity: {field}.')

    return {'ok': not issues, 'checked_files': sorted(checked), 'issues': issues}


def main(root=ROOT):
    result = validate_assets(root)
    if not result['ok']:
        print('AquaIQ regression validation assets are missing or incompatible.')
        for issue in result['issues']:
            print('- ' + issue)
        print('Restore the matching private full feature export/manifest and complete monthly model bundle '
              'from the verified release backup before running the unchanged regression suite.')
        print(f'See {GUIDE}. Hosted CI has no private-asset provisioning configured; '
              'this failure does not mean the regression suite passed.')
        return 1
    print(f'Validated {len(result["checked_files"])} required asset paths and metadata/hash bindings. '
          'Run the unchanged regression suite; this preflight does not establish forecasting accuracy '
          'or deployment readiness.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
