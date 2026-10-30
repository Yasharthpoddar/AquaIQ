"""Immutable state-only release packaging and origin-safe generation.

Product selection is independent of evidence strength. A release may be the
primary visualization while its forecasting evidence remains experimental.
"""
from datetime import datetime, timezone
import json
from pathlib import Path
import platform
import re
import shutil

import numpy as np
import pandas as pd
import sklearn
import xgboost

from db.connection import finite_json
from models import state_median_forecast as median
from models import state_median_policy as policy
from models.district_registry import get_registry, registry_hash
from models.ensemble import _as_of, _completed_feature_month
from models.state_mapping import STATES_REGISTRY
from models.xgboost_model import sha256_file, load_feature_matrix


def package_versions():
    return dict(python=platform.python_version(), numpy=np.__version__, pandas=pd.__version__,
                sklearn=sklearn.__version__, xgboost=xgboost.__version__)


def _json(path, value):
    with Path(path).open('x', encoding='utf-8') as handle:
        json.dump(finite_json(value), handle, indent=2, allow_nan=False)


def prepare_release(directory, artifact_release, processed_dir, as_of,
                    evaluation_path=None, evaluation_artifacts=None, trained_artifacts=None,
                    forecast_policy='tiered_observed'):
    """Refit fixed parameters to all origin-available labels after frozen testing.

    A fresh directory is mandatory. Failed/partial preparations cannot load or
    publish without a complete verified manifest. District assets are read only.
    """
    if not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9._-]{0,63}', artifact_release):
        raise ValueError('Invalid artifact release identifier.')
    if forecast_policy not in ('tiered_observed', 'xgboost_only'):
        raise ValueError('Unknown state forecasting policy.')
    directory, processed_dir = Path(directory), Path(processed_dir)
    cutoff = _completed_feature_month(_as_of(as_of))
    frame = load_feature_matrix(processed_dir)
    history = median.build_state_history(frame)
    if history.date.max() < cutoff:
        # Missing most recent groundwater is permitted; an absent source
        # calendar is not silently relabelled as a newer generation.
        raise ValueError('Verified source calendar does not extend to the completed input month.')
    report, frozen_card_hash = None, None
    if evaluation_path:
        if not evaluation_artifacts:
            raise ValueError('Historical evidence requires its exact frozen artifact directory.')
        _, frozen = median.load_models(evaluation_artifacts)
        frozen_card_hash = sha256_file(Path(evaluation_artifacts)/'model_card.json')
        report = json.loads(Path(evaluation_path).read_text(encoding='utf-8'))
        if (report.get('candidate_model_card_sha256') != frozen_card_hash
                or frozen.get('feature_generation_id') != history.attrs.get('feature_generation_id')
                or frozen.get('data_sha256') != history.attrs.get('data_sha256')
                or report.get('data_sha256') != history.attrs.get('data_sha256')
                or set(report.get('by_horizon', {})) != {str(h) for h in range(1, 13)}):
            raise ValueError('Historical comparison does not match the source/frozen artifact or all horizon disclosures.')
        if frozen['features'] != median.FEATURES or frozen['parameters'] != median.PARAMETERS:
            raise ValueError('Historical evidence describes a different model methodology.')
        if any(g.get('candidate', {}).get('period_end') and
               pd.Timestamp(g['candidate']['period_end']) > _as_of(as_of)
               for g in report.get('by_state', {}).values()):
            raise ValueError('Historical evidence extends beyond the release vintage.')
    if trained_artifacts:
        models, card = median.load_models(trained_artifacts)
        required = dict(training_cutoff=cutoff.date().isoformat(), features=median.FEATURES,
            parameters=median.PARAMETERS, feature_generation_id=history.attrs['feature_generation_id'],
            data_sha256=history.attrs['data_sha256'], registry_sha256=registry_hash(), min_coverage=median.MIN_COVERAGE)
        if any(card.get(key) != value for key, value in required.items()):
            raise ValueError('Pretrained refit does not match the exact latest source, cutoff or model configuration.')
    directory.mkdir(parents=True, exist_ok=False)
    if trained_artifacts:
        (directory/'models').mkdir()
        for name in ['model_card.json'] + [card['states'][code]['file'] for code in models]:
            shutil.copyfile(Path(trained_artifacts)/name, directory/'models'/name)
        models, card = median.load_models(directory/'models')
    else:
        models, card = median.train_state_models(history, directory/'models', cutoff, '2017-01-01')
    # No raw/processed observations are copied into the distributable artifact.
    manifest = dict(format_version=1, artifact_release=artifact_release,
        model_version=median.MODEL_VERSION, model_name=median.MODEL_NAME,
        model_card_sha256=sha256_file(directory/'models/model_card.json'),
        model_algorithm_sha256=sha256_file(median.__file__),
        training_cutoff=card['training_cutoff'], as_of=_as_of(as_of).date().isoformat(),
        feature_generation_id=history.attrs['feature_generation_id'], data_sha256=history.attrs['data_sha256'],
        source_manifest_sha256=sha256_file(processed_dir/'feature_manifest.json'),
        source_csv_sha256=frame.attrs['feature_manifest']['feature_csv_sha256'],
        registry_sha256=registry_hash(), features=card['features'], parameters=card['parameters'],
        min_coverage=card['min_coverage'], package_versions=package_versions(),
        models={code: card['states'][code]['model_sha256'] for code in models},
        created_at=datetime.now(timezone.utc).isoformat(), evidence_status='limited_historical_evidence',
        promotion_status='experimental', product_selection='primary_states_page',
        evaluation_report_sha256=sha256_file(evaluation_path) if report else None,
        evaluated_model_card_sha256=frozen_card_hash,
        evaluated_artifact_training_cutoff=report.get('candidate_training_cutoff') if report else None,
        evaluation_horizons=[int(h) for h, g in report['by_horizon'].items()
                             if g['paired']['candidate']['n']] if report else [],
        evaluation_summary=dict(report['comparison']['paired']['candidate'],
            status='limited_historical_evidence', comparison_scope='paired',
            horizons=[int(h) for h, g in report['by_horizon'].items() if g['paired']['candidate']['n']],
            evaluated_artifact_training_cutoff=report.get('candidate_training_cutoff'),
            evaluated_model_card_sha256=frozen_card_hash,
            artifact_role='frozen_historical_reference', is_current_artifact_evaluation=False) if report else None,
        evaluation_role='frozen_historical_reference_not_released_weights',
        refit_policy='Fixed parameters refit to latest completed inputs after retrospective evaluation; no test-outcome tuning.')
    if report:
        shutil.copyfile(evaluation_path, directory/'evaluation.json')
    if forecast_policy == 'tiered_observed':
        choices = {code: policy.forecast_state(code, history, models, card, as_of) for code in STATES_REGISTRY}
        states = {code: {key: result.get(key) for key in ('state_id', 'status', 'forecast_method',
            'genuine_observed_months', 'genuine_observation_count', 'latest_observation_date',
            'observation_age_months', 'historical_reference_date', 'reference_age_months',
            'reference_training_eligible', 'reference_is_stale', 'fallback_reason')}
            for code, result in choices.items()}
        release_card = dict(format_version=2, model_name=policy.MODEL_NAME, model_version=policy.MODEL_VERSION,
            artifact_release=artifact_release, policy_version=policy.POLICY_VERSION,
            policy_sha256=sha256_file(policy.__file__), policy_details=policy.POLICY_DETAILS,
            xgboost_model_card_sha256=manifest['model_card_sha256'],
            xgboost_model_version=median.MODEL_VERSION, training_cutoff=card['training_cutoff'],
            training_cutoff_scope='XGBoost component only; persistence is not trained.',
            feature_generation_id=history.attrs['feature_generation_id'], data_sha256=history.attrs['data_sha256'],
            registry_sha256=registry_hash(), states=states,
            xgboost_training_eligibility=card['states'],
            created_at=datetime.now(timezone.utc).isoformat())
        _json(directory/'release_model_card.json', release_card)
        manifest.update(format_version=2, model_version=policy.MODEL_VERSION, model_name=policy.MODEL_NAME,
            xgboost_model_card_sha256=manifest['model_card_sha256'],
            model_card_sha256=sha256_file(directory/'release_model_card.json'),
            policy_version=policy.POLICY_VERSION, policy_sha256=sha256_file(policy.__file__),
            policy_details=policy.POLICY_DETAILS,
            state_methods={code: result['forecast_method'] for code, result in choices.items()},
            policy_model_card='release_model_card.json')
        if manifest['evaluation_summary'] is not None:
            manifest['evaluation_summary'].update(forecast_method='state_median_xgboost',
                excludes_persistence_fallback=True,
                description='Frozen XGBoost component evidence only; persistence fallback has not been evaluated.')
    _json(directory/'release_manifest.json', manifest)
    return verify_release(directory, artifact_release)


def verify_release(directory, expected_release=None, expected_manifest_sha256=None):
    directory = Path(directory)
    path = directory/'release_manifest.json'
    signature = sha256_file(path)
    if expected_manifest_sha256 is not None and signature != expected_manifest_sha256:
        raise ValueError('State median release manifest checksum mismatch.')
    manifest = json.loads(path.read_text(encoding='utf-8'))
    tiered = manifest.get('format_version') == 2 and manifest.get('model_version') == policy.MODEL_VERSION
    legacy = manifest.get('format_version') == 1 and manifest.get('model_version') == median.MODEL_VERSION
    if (not (tiered or legacy)
            or (expected_release is not None and manifest.get('artifact_release') != expected_release)
            or manifest.get('package_versions') != package_versions()
            or manifest.get('model_algorithm_sha256') != sha256_file(median.__file__)
            or manifest.get('registry_sha256') != registry_hash()
            or manifest.get('features') != median.FEATURES or manifest.get('parameters') != median.PARAMETERS):
        raise ValueError('Incompatible state median release identity, packages, registry or feature schema.')
    xgb_card_sha = manifest.get('xgboost_model_card_sha256') if tiered else manifest.get('model_card_sha256')
    if sha256_file(directory/'models/model_card.json') != xgb_card_sha:
        raise ValueError('State median model card checksum mismatch.')
    models, card = median.load_models(directory/'models')
    actual = {code: card['states'][code]['model_sha256'] for code in models}
    if actual != manifest.get('models'):
        raise ValueError('State median model inventory differs from the released manifest.')
    for key in ('training_cutoff', 'feature_generation_id', 'data_sha256',
                'registry_sha256', 'features', 'parameters', 'min_coverage'):
        if card.get(key) != manifest.get(key):
            raise ValueError(f'State median model card and manifest disagree on {key}.')
    if tiered:
        if (manifest.get('model_name') != policy.MODEL_NAME or manifest.get('policy_version') != policy.POLICY_VERSION
                or manifest.get('policy_sha256') != sha256_file(policy.__file__)
                or manifest.get('policy_details') != policy.POLICY_DETAILS
                or set(manifest.get('state_methods', {})) != set(STATES_REGISTRY)
                or any(method not in policy.METHODS for method in manifest['state_methods'].values())
                or manifest.get('policy_model_card') != 'release_model_card.json'):
            raise ValueError('Incompatible state median fallback policy or method inventory.')
        if sha256_file(directory/'release_model_card.json') != manifest['model_card_sha256']:
            raise ValueError('State policy model card checksum mismatch.')
        release_card = json.loads((directory/'release_model_card.json').read_text(encoding='utf-8'))
        for key in ('artifact_release', 'model_name', 'model_version', 'policy_version', 'policy_sha256',
                    'policy_details', 'xgboost_model_card_sha256', 'training_cutoff', 'feature_generation_id',
                    'data_sha256', 'registry_sha256'):
            if release_card.get(key) != manifest.get(key):
                raise ValueError(f'State policy card and manifest disagree on {key}.')
        if {code: row['forecast_method'] for code, row in release_card['states'].items()} != manifest['state_methods']:
            raise ValueError('State policy card method inventory mismatch.')
    if manifest.get('evaluation_report_sha256') and sha256_file(directory/'evaluation.json') != manifest['evaluation_report_sha256']:
        raise ValueError('Historical evaluation checksum mismatch.')
    return models, card, manifest, signature


def generate_release(directory, processed_dir, as_of, expected_release=None, expected_manifest_sha256=None):
    models, card, manifest, signature = verify_release(directory, expected_release, expected_manifest_sha256)
    tiered = manifest['format_version'] == 2
    if tiered and _as_of(as_of).date().isoformat() != manifest['as_of']:
        raise ValueError('Tiered policy releases pin one vintage; prepare a new immutable release for a different as_of.')
    source = Path(processed_dir)
    if (sha256_file(source/'feature_manifest.json') != manifest['source_manifest_sha256']
            or sha256_file(source/'features_matrix.csv') != manifest['source_csv_sha256']):
        raise ValueError('Forecast source files differ from the released source identity.')
    history = median.load_history(source, min_coverage=card['min_coverage'])
    report = json.loads((Path(directory)/'evaluation.json').read_text(encoding='utf-8')) if manifest['evaluation_report_sha256'] else None
    registry = get_registry()
    payloads = {}
    for code in STATES_REGISTRY:
        evaluation = None
        if report:
            group = report['by_state'][code]
            metrics = group['paired']['candidate']
            horizons = metrics.get('horizons', [int(h) for h, g in report['by_horizon'].items() if g['paired']['candidate']['n']])
            summary = report['comparison']['paired']['candidate']
            evaluation = dict(status='limited_historical_evidence', n=metrics['n'],
                mae_m=metrics['mae_m'], rmse_m=metrics['rmse_m'], period_start=metrics['period_start'],
                period_end=metrics['period_end'], horizons=horizons,
                states_evaluated=metrics['states'], unique_state_month_targets=metrics['valid_state_month_observations'],
                comparison_states_evaluated=summary['states'],
                comparison_unique_state_month_targets=summary['valid_state_month_observations'],
                state_unique_target_count=metrics['valid_state_month_observations'],
                comparison_scope='paired', evaluated_artifact_training_cutoff=manifest['evaluated_artifact_training_cutoff'],
                evaluated_model_card_sha256=manifest['evaluated_model_card_sha256'],
                artifact_role='frozen_historical_reference', is_current_artifact_evaluation=False,
                description='Historical backtest of the frozen model methodology; not held-out validation of these refitted weights or a guarantee for the next twelve months.',
                report_sha256=manifest['evaluation_report_sha256'])
        forecaster = policy.forecast_state if tiered else median.forecast_state
        result = forecaster(code, history, models, card, as_of, evaluation)
        if tiered and result['forecast_method'] != manifest['state_methods'][code]:
            raise ValueError('Generated state method differs from the immutable policy card.')
        result.update(artifact_release=manifest['artifact_release'], release_manifest_sha256=signature,
            model_card_sha256=manifest['model_card_sha256'], evidence_status=manifest['evidence_status'],
            product_selection='primary_states_page',
            districts=[r['district_id'] for r in registry if r['state_id'] == code])
        payloads[code] = result
    from models.state_median_storage import validate_generation
    validate_generation(payloads)
    return payloads, manifest
