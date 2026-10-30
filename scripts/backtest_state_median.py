"""Compare an existing experimental state artifact with unchanged production district forecasts."""
import argparse
import hashlib
import json
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor

from models import climate_forecast_12m as climate
from models.district_registry import get_registry
from models.state_median_evaluation import DEFAULT_ORIGINS, merge_origin_evaluations, run_evaluation, write_report
from models.state_median_forecast import build_state_history, load_models
from models.xgboost_model import load_feature_matrix


def evaluate_snapshot(artifacts, processed_dir, checkpoint, origins):
    """Each worker loads the same verified immutable assets and owns its cache."""
    models, card = load_models(Path(artifacts))
    frame = load_feature_matrix(Path(processed_dir) if processed_dir is not None else None)
    policy = card.get('policy') or card.get('config') or {}
    min_coverage = policy.get('min_coverage', card.get('min_coverage', .5))
    registry = get_registry()
    history = build_state_history(frame, registry=registry, min_coverage=min_coverage)
    bundle = climate.load_bundle(checkpoint=Path(checkpoint) if checkpoint is not None else None,
                                 expected_generation=frame.attrs.get('feature_generation_id'))
    return run_evaluation(frame, history, models, card, origins, registry=registry, bundle=bundle)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--artifacts', type=Path, required=True, help='Existing separate state median artifact directory; no training occurs.')
    parser.add_argument('--output', type=Path, required=True, help='New report directory; existing directories are never overwritten.')
    parser.add_argument('--origins', nargs='+', default=DEFAULT_ORIGINS, help='Month-start origins, at least twelve months after both model training cutoffs.')
    parser.add_argument('--processed-dir', type=Path, help='Explicit verified feature snapshot; default uses the existing verified runtime snapshot.')
    parser.add_argument('--checkpoint', type=Path, help='Matching frozen district checkpoint pointer for an explicit feature generation; never retrained.')
    parser.add_argument('--workers', type=int, default=1, choices=range(1, 5), help='Independent origin replay processes; predictions and artifacts are unchanged.')
    args = parser.parse_args(argv)
    if args.output.exists():
        parser.error('--output must be a new directory.')
    inputs = (args.artifacts, args.processed_dir, args.checkpoint)
    if args.workers == 1:
        report, cases = evaluate_snapshot(*inputs, args.origins)
    else:
        chunks = [list(args.origins)[worker::args.workers] for worker in range(args.workers)]
        chunks = [chunk for chunk in chunks if chunk]
        with ProcessPoolExecutor(max_workers=len(chunks)) as pool:
            futures = [pool.submit(evaluate_snapshot, *inputs, chunk) for chunk in chunks]
            results = [future.result() for future in futures]
        report, cases = merge_origin_evaluations(results, args.origins)
    report['replay_workers'] = args.workers
    report['candidate_model_card_sha256'] = hashlib.sha256((args.artifacts/'model_card.json').read_bytes()).hexdigest()
    if args.checkpoint is not None:
        report['baseline_checkpoint_sha256'] = hashlib.sha256(args.checkpoint.read_bytes()).hexdigest()
    write_report(args.output, report, cases)
    print(json.dumps(report['comparison'], indent=2, allow_nan=False))
    return report


if __name__ == '__main__':
    main()
