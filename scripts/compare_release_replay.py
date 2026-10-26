"""Compare complete isolated forecast exports without committing their values."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path


def normalized(value):
    if isinstance(value, dict):
        return {key: normalized(item) for key, item in value.items() if key != 'computed_at'}
    if isinstance(value, list):
        return [normalized(item) for item in value]
    return value


def fingerprint(value):
    encoded = json.dumps(normalized(value), sort_keys=True, separators=(',', ':'), allow_nan=False)
    return hashlib.sha256(encoded.encode('utf-8')).hexdigest()


def compare(expected, replay, output):
    panels = {}
    for name, count in (('districts', 725), ('states', 36)):
        paths = [Path(folder)/(name+'.json') for folder in (expected, replay)]
        values = [json.loads(path.read_text(encoding='utf-8')) for path in paths]
        left, right = values
        if not all(isinstance(value, dict) and len(value) == count for value in values):
            raise ValueError(f'Incomplete {name} inventory in replay exports.')
        if left.keys() != right.keys():
            raise ValueError(f'Replay {name} identifiers differ.')
        for value in values:
            if any(len(item.get('forecast', [])) != 12 for item in value.values()):
                raise ValueError(f'Incomplete {name} horizon in replay exports.')
        hashes = [fingerprint(value) for value in values]
        if hashes[0] != hashes[1]:
            raise ValueError(f'Replay {name} numeric forecasts or metadata differ.')
        panel = {'records': count, 'horizons': count*12, 'complete_objects_equal': True,
                 'normalized_sha256': hashes[0]}
        if name == 'districts':
            panel['tier_counts'] = dict(sorted(Counter(item['evidence_tier'] for item in left.values()).items()))
        panels[name] = panel
    report = {'test': 'independent_environment_complete_forecast_export_comparison',
              'passed': True, 'ignored_fields': ['computed_at'], 'panels': panels,
              'comparison': 'Exact complete numeric values, dates, deltas, bounds, tiers, methods, evidence and provenance; no tolerance.'}
    output = Path(output)
    if output.exists():
        raise FileExistsError('Choose a new export comparison report.')
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(report, indent=2))
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('expected', 'replay', 'output'):
        parser.add_argument('--'+name, type=Path, required=True)
    args = parser.parse_args()
    compare(args.expected, args.replay, args.output)
