"""Train or generate isolated experimental state medians; never publish production.

python -m scripts.state_median_forecasts train --artifacts scratch/median_models --train-cutoff 2019-12-31
python -m scripts.state_median_forecasts generate --artifacts scratch/median_models --as-of 2026-10-29 --output scratch/median_generation.json
"""
import argparse
import json
from pathlib import Path
import pandas as pd

from models import state_median_forecast as median
from models.state_mapping import STATES_REGISTRY
from models.xgboost_model import sha256_file


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    train = commands.add_parser('train')
    train.add_argument('--artifacts', type=Path, required=True, help='New candidate-only directory.')
    train.add_argument('--train-cutoff', default='2019-12-31')
    train.add_argument('--validation-start', default='2017-01-01')
    train.add_argument('--min-coverage', type=float, default=median.MIN_COVERAGE)
    train.add_argument('--processed-dir', type=Path)
    generate = commands.add_parser('generate')
    generate.add_argument('--artifacts', type=Path, required=True)
    generate.add_argument('--as-of', required=True)
    generate.add_argument('--output', type=Path, required=True, help='New JSON output; never overwritten.')
    generate.add_argument('--evaluation', type=Path, help='Matching independent comparison report.')
    generate.add_argument('--processed-dir', type=Path)
    generate.add_argument('--test-schema', help='Persist candidate only in an aquaiq_test_* PostgreSQL namespace.')
    args = parser.parse_args(argv)
    if args.command == 'train':
        history = median.load_history(args.processed_dir, min_coverage=args.min_coverage)
        models, card = median.train_state_models(history, args.artifacts, args.train_cutoff, args.validation_start)
        history.to_csv(args.artifacts/'historical_state_medians.csv', index=False)
        print(json.dumps(dict(trained_states=len(models), registered_states=len(card['states']),
                              artifacts=str(args.artifacts), promotion_status='experimental')))
        return
    if args.output.exists():
        raise FileExistsError('Forecast output already exists; choose a new path.')
    models, card = median.load_models(args.artifacts)
    history = median.load_history(args.processed_dir, min_coverage=card['min_coverage'])
    report = None
    if args.evaluation:
        report = json.loads(args.evaluation.read_text(encoding='utf-8'))
        if report.get('candidate_model_card_sha256') != sha256_file(args.artifacts/'model_card.json'):
            raise ValueError('Backtest report does not match this candidate artifact.')
        if any(metrics.get('candidate', {}).get('period_end') and
               pd.Timestamp(metrics['candidate']['period_end']) > pd.Timestamp(args.as_of)
               for metrics in report.get('by_state', {}).values()):
            raise ValueError('Backtest evidence extends after the requested forecast vintage.')
    payloads = {}
    for code in STATES_REGISTRY:
        evaluation = None
        if report:
            metrics = report.get('by_state', {}).get(code, {}).get('candidate', {})
            evaluation = dict(status='retrospective_experimental', n=metrics.get('n', 0),
                mae_m=metrics.get('mae_m'), rmse_m=metrics.get('rmse_m'),
                period_start=metrics.get('period_start'), period_end=metrics.get('period_end'),
                description='Held-out retrospective median targets; repeated targets across origins are dependent.',
                report_sha256=sha256_file(args.evaluation))
        payloads[code] = median.forecast_state(code, history, models, card, args.as_of, evaluation=evaluation)
    # Validate without needing database access, even for export-only operation.
    from models.state_median_storage import validate_generation, save_generation
    validate_generation(payloads)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x', encoding='utf-8') as handle:
        json.dump(payloads, handle, indent=2, allow_nan=False)
    persisted = save_generation(payloads, test_schema=args.test_schema) if args.test_schema else None
    print(json.dumps(dict(states=len(payloads), forecasts=sum(p['status']=='forecast' for p in payloads.values()),
                          output=str(args.output), persistence=persisted, promotion_status='experimental')))


if __name__ == '__main__':
    main()
