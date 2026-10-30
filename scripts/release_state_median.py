"""Prepare, verify, stage, publish or roll back the state-only release.

Production writes require explicit flags and a verified backup file. This tool
never updates district/legacy tables, .env, or the selected dashboard build.
"""
import argparse
import json
from pathlib import Path

from models import state_median_release as release


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    prepare = commands.add_parser('prepare')
    prepare.add_argument('--release-dir', type=Path, required=True)
    prepare.add_argument('--artifact-release', required=True)
    prepare.add_argument('--processed-dir', type=Path, required=True)
    prepare.add_argument('--as-of', required=True)
    prepare.add_argument('--evaluation', type=Path)
    prepare.add_argument('--evaluation-artifacts', type=Path)
    prepare.add_argument('--trained-artifacts', type=Path, help='Optional verified latest refit; never accepts a mismatched source, cutoff or configuration.')
    prepare.add_argument('--forecast-policy', choices=['tiered_observed', 'xgboost_only'], default='tiered_observed',
                         help='New releases use explicit XGBoost/persistence/no-observations tiers. Legacy reproduction is opt-in.')
    verify = commands.add_parser('verify')
    verify.add_argument('--release-dir', type=Path, required=True)
    verify.add_argument('--expected-release')
    verify.add_argument('--expected-manifest-sha256')
    status = commands.add_parser('status')
    status.add_argument('--test-schema')
    generate = commands.add_parser('generate')
    generate.add_argument('--release-dir', type=Path, required=True)
    generate.add_argument('--processed-dir', type=Path, required=True)
    generate.add_argument('--as-of', required=True)
    generate.add_argument('--output', type=Path, required=True)
    generate.add_argument('--test-schema')
    for name in ('migrate', 'stage', 'publish', 'rollback'):
        sub = commands.add_parser(name)
        sub.add_argument('--test-schema')
        sub.add_argument('--allow-production-write', action='store_true')
        sub.add_argument('--backup', type=Path)
        if name == 'stage':
            sub.add_argument('--release-dir', type=Path, required=True)
            sub.add_argument('--input', type=Path, required=True)
        elif name != 'migrate':
            sub.add_argument('--release-id', required=True)
            sub.add_argument('--expected-active', required=True, help='Exact active UUID, or none for first publication.')
            sub.add_argument('--reason', required=True)
    args = parser.parse_args(argv)
    if args.command == 'prepare':
        models, card, manifest, signature = release.prepare_release(args.release_dir, args.artifact_release,
            args.processed_dir, args.as_of, args.evaluation, args.evaluation_artifacts, args.trained_artifacts,
            args.forecast_policy)
        print(json.dumps(dict(artifact_release=manifest['artifact_release'], manifest_sha256=signature,
            training_cutoff=card['training_cutoff'], trained_states=len(models), status='prepared_not_published')))
    elif args.command == 'verify':
        models, card, manifest, signature = release.verify_release(args.release_dir, args.expected_release,
                                                                  args.expected_manifest_sha256)
        print(json.dumps(dict(artifact_release=manifest['artifact_release'], manifest_sha256=signature,
                              trained_states=len(models), training_cutoff=card['training_cutoff'], status='verified')))
    elif args.command == 'generate':
        if args.output.exists():
            raise FileExistsError('Choose a new generation output path.')
        payloads, manifest = release.generate_release(args.release_dir, args.processed_dir, args.as_of)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        release._json(args.output, payloads)
        staged = None
        if args.test_schema:
            from models.state_median_release_storage import stage_release
            staged = stage_release(payloads, manifest, test_schema=args.test_schema)
        print(json.dumps(dict(status='generated_not_published', staged=staged,
            forecasts=sum(p['status']=='forecast' for p in payloads.values()), states_total=len(payloads))))
    elif args.command == 'status':
        from models.state_median_release_storage import get_active_release
        print(json.dumps(get_active_release(test_schema=args.test_schema) or {'status':'unpublished'}))
    else:
        from models import state_median_release_storage as storage
        if not args.test_schema:
            if not args.allow_production_write or not args.backup or not args.backup.is_file():
                raise ValueError('Production writes require explicit --allow-production-write and a verified PostgreSQL custom-format --backup.')
            with args.backup.open('rb') as handle:
                if handle.read(5) != b'PGDMP':
                    raise ValueError('Backup must be a nonempty PostgreSQL custom-format dump; test restore it before release.')
            if args.backup.stat().st_size < 100:
                raise ValueError('Backup is incomplete.')
        if args.command == 'migrate':
            result = storage.migrate_release_storage(test_schema=args.test_schema)
        elif args.command == 'stage':
            _, _, manifest, _ = release.verify_release(args.release_dir)
            payloads = json.loads(args.input.read_text(encoding='utf-8'))
            result = storage.stage_release(payloads, manifest, test_schema=args.test_schema)
        else:
            expected = None if args.expected_active == 'none' else args.expected_active
            action = storage.publish_release if args.command == 'publish' else storage.rollback_release
            result = action(args.release_id, expected_active=expected, test_schema=args.test_schema, reason=args.reason)
        print(json.dumps(result))


if __name__ == '__main__':
    main()
