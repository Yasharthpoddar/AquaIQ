"""Run the unchanged paired serving evaluator in bounded independent processes.

Workers use the original CLI, feature snapshot and model bundles. This driver
only validates and merges their already evaluated cases; it never trains a
model, selects parameters, calibrates intervals or writes a database.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import time

import pandas as pd

from models.xgboost_model import sha256_file
from scripts import evaluate_retrained_model as original


ROOT = Path(__file__).resolve().parents[1]
ORIGINAL_PATH = Path(original.__file__).resolve()
DRIVER_PATH = Path(__file__).resolve()
VERSION = 'unchanged-retraining-evaluator-parallel-v1'


def _new_directory(path, parent, label):
    path = Path(path).resolve()
    if not path.is_relative_to(parent.resolve()) or path == parent.resolve():
        raise ValueError(f'{label} must be a new directory within {parent.relative_to(ROOT)}.')
    if path.exists() or path.is_symlink():
        raise FileExistsError(f'{label} already exists; choose a new path.')
    return path


def _origins(protocol):
    origins = protocol.get('final_diagnostic_origins')
    if not isinstance(origins, list) or len(origins) != 12 or any(not isinstance(value, str) for value in origins):
        raise ValueError('The locked protocol must prescribe twelve diagnostic origins.')
    parsed = pd.DatetimeIndex(pd.to_datetime(origins, errors='raise'))
    if (parsed.has_duplicates or parsed.tz is not None or not parsed.is_month_end.all()
            or not parsed.equals(parsed.normalize()) or parsed.isna().any()):
        raise ValueError('Protocol origins must be unique timezone-free calendar month ends.')
    return [value.date().isoformat() for value in sorted(parsed)]


def _model_source(pointer_path):
    pointer_path = Path(pointer_path).resolve()
    pointer = json.loads(pointer_path.read_text(encoding='utf-8'))
    model = (pointer_path.parent / pointer['model_path']).resolve()
    if not model.is_relative_to(pointer_path.parent):
        raise ValueError('Model pointer escapes its containing bundle directory.')
    actual = sha256_file(model)
    if actual != pointer.get('model_sha256'):
        raise ValueError('Model bytes differ from their pointer before evaluation.')
    return model, actual


def _stop_workers(children):
    # These are only the children started by this invocation. No unrelated
    # evaluator, test-suite or service process is inspected or interrupted.
    for process in children:
        if process.poll() is None:
            process.terminate()
    for process in children:
        if process.poll() is None:
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)


def _run_workers(arguments, origins, work_dir):
    count = arguments.workers
    # Consecutive chunks, then ordered concatenation, retain the original
    # evaluator's origin/registry row order and floating aggregation order.
    quotient, remainder = divmod(len(origins), count)
    chunks, position = [], 0
    for index in range(count):
        size = quotient + int(index < remainder)
        chunks.append(origins[position:position + size])
        position += size
    children, logs, workers = [], [], []
    try:
        for index, chunk in enumerate(chunks):
            destination = work_dir / f'group{index + 1}'
            log_path = work_dir / f'group{index + 1}.log'
            command = [sys.executable, '-u', '-B', '-m', 'scripts.evaluate_retrained_model',
                '--features', str(arguments.features),
                '--frozen-checkpoint', str(arguments.frozen_checkpoint),
                '--candidate-checkpoint', str(arguments.candidate_checkpoint),
                '--output', str(destination), '--origins', *chunk]
            if arguments.added_districts is not None:
                command.extend(['--added-districts', str(arguments.added_districts)])
            log = log_path.open('x', encoding='utf-8')
            logs.append(log)
            process = subprocess.Popen(command, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
            children.append(process)
            workers.append({'group': index + 1, 'origins': chunk,
                'output_directory': str(destination.relative_to(ROOT)),
                'log_file': str(log_path.relative_to(ROOT)), 'command': command})
            print(f'Started group {index + 1}/{count}: {len(chunk)} original-evaluator origins.', flush=True)
        finished = set()
        while len(finished) < len(children):
            for index, process in enumerate(children):
                status = process.poll()
                if status is not None and index not in finished:
                    workers[index]['exit_code'] = status
                    if status:
                        raise RuntimeError(f'Original evaluator group {index + 1} failed; inspect {workers[index]["log_file"]}. No merged report was published.')
                    finished.add(index)
                    print(f'Completed group {index + 1}/{count}.', flush=True)
            if len(finished) < len(children):
                time.sleep(.25)
    except BaseException:
        _stop_workers(children)
        raise
    finally:
        for log in logs:
            log.close()
    return workers


def _merge(workers, work_dir, origins, expected_inputs):
    tables = []
    forecasted = 0
    common_inputs = None
    for worker in workers:
        folder = ROOT / worker['output_directory']
        summary_path, cases_path = folder / 'summary.json', folder / 'cases.csv'
        summary = json.loads(summary_path.read_text(encoding='utf-8'))
        if summary.get('cases_sha256') != sha256_file(cases_path):
            raise ValueError('Worker case CSV differs from its completed summary.')
        inputs = summary.get('inputs')
        if not isinstance(inputs, dict) or any(inputs.get(key) != value for key, value in expected_inputs.items()):
            raise ValueError('A worker evaluated different model, source or implementation inputs.')
        if common_inputs is None:
            common_inputs = inputs
        elif inputs != common_inputs:
            raise ValueError('Worker input fingerprints are not identical.')
        table = pd.read_csv(cases_path, float_precision='round_trip')
        if set(original.COLUMNS) != set(table) or table.duplicated(original.CASE_KEYS).any():
            raise ValueError('Worker cases have an invalid schema or duplicate exact case keys.')
        if set(table.origin) != set(worker['origins']):
            raise ValueError('Every prescribed worker origin must have its original observed cases.')
        coverage = summary.get('coverage', {})
        potential = 725 * len(worker['origins']) * 12
        if (coverage.get('canonical_districts') != 725
                or coverage.get('requested_origins') != worker['origins']
                or coverage.get('potential_target_slots') != potential
                or coverage.get('observed_paired_cases') != len(table)
                or coverage.get('unavailable_target_slots') != potential - len(table)
                or not isinstance(coverage.get('forecasted_district_origins'), int)
                or not 0 <= coverage['forecasted_district_origins'] <= 725 * len(worker['origins'])
                or summary.get('new_blind_evaluation') is not False
                or summary.get('model_or_interval_selection_performed') is not False):
            raise ValueError('Worker coverage or retrospective/no-selection evidence is inconsistent.')
        forecasted += coverage['forecasted_district_origins']
        worker.update(observed_paired_cases=len(table), cases_sha256=summary['cases_sha256'],
            summary_sha256=sha256_file(summary_path))
        tables.append(table)
    merged = pd.concat(tables, ignore_index=True).loc[:, original.COLUMNS]
    if merged.duplicated(original.CASE_KEYS).any() or set(merged.origin) != set(origins):
        raise ValueError('Merged exact case keys or requested-origin coverage are inconsistent.')
    if len(merged) != sum(worker['observed_paired_cases'] for worker in workers):
        raise ValueError('Merging lost or duplicated original observed cases.')
    potential = 725 * len(origins) * 12
    merged.attrs['evaluation_coverage'] = {
        'canonical_districts': 725, 'requested_origins': origins,
        'potential_target_slots': potential, 'observed_paired_cases': len(merged),
        'unavailable_target_slots': potential - len(merged),
        'forecasted_district_origins': forecasted,
        'enrichment_membership_supplied': tables[0].attrs.get('enrichment_membership_supplied', False)}
    # This metadata is present in each original summary, not in a CSV's attrs.
    first = json.loads((ROOT / workers[0]['output_directory'] / 'summary.json').read_text(encoding='utf-8'))['coverage']
    merged.attrs['evaluation_coverage'].update({key: first[key] for key in
        ('enrichment_membership_supplied', 'newly_enriched_districts_supplied')})
    for worker in workers[1:]:
        coverage = json.loads((ROOT / worker['output_directory'] / 'summary.json').read_text(encoding='utf-8'))['coverage']
        if any(coverage.get(key) != first[key] for key in
               ('enrichment_membership_supplied', 'newly_enriched_districts_supplied')):
            raise ValueError('Worker enrichment-membership panels differ.')
    return merged, common_inputs


def _publish(staging, output):
    output.parent.mkdir(parents=True, exist_ok=True)
    if os.name == 'nt':
        # Windows rename is atomic and refuses an existing destination.
        staging.rename(output)
    else:
        # POSIX rename can replace an empty directory. Reserve it exclusively
        # first so only this invocation's own empty reservation is replaced.
        output.mkdir(exist_ok=False)
        staging.rename(output)


def run(arguments):
    if arguments.workers not in (1, 2, 3):
        raise ValueError('Use at most three independent evaluator workers.')
    arguments.features = Path(arguments.features).resolve()
    arguments.frozen_checkpoint = Path(arguments.frozen_checkpoint).resolve()
    arguments.candidate_checkpoint = Path(arguments.candidate_checkpoint).resolve()
    arguments.protocol = Path(arguments.protocol).resolve()
    if arguments.added_districts is not None:
        arguments.added_districts = Path(arguments.added_districts).resolve()
    work_dir = _new_directory(arguments.work_dir, ROOT / 'scratch', 'Worker directory')
    output = _new_directory(arguments.output, ROOT / 'reports', 'Aggregate report directory')
    protocol = json.loads(arguments.protocol.read_text(encoding='utf-8'))
    origins = _origins(protocol)
    frozen_model, frozen_sha = _model_source(arguments.frozen_checkpoint)
    candidate_model, candidate_sha = _model_source(arguments.candidate_checkpoint)
    if protocol.get('frozen_model_sha256') != frozen_sha:
        raise ValueError('The frozen model differs from the locked retraining protocol.')
    sources = [ORIGINAL_PATH, DRIVER_PATH, arguments.protocol, arguments.frozen_checkpoint,
               arguments.candidate_checkpoint, frozen_model, candidate_model]
    if arguments.added_districts is not None:
        sources.append(arguments.added_districts)
    locked = {path: sha256_file(path) for path in sources}
    expected = {'frozen_model_sha256': frozen_sha, 'candidate_model_sha256': candidate_sha,
        'feature_generation_id': protocol['feature_generation'],
        'feature_csv_sha256': protocol['feature_csv_sha256'],
        'frozen_pointer_sha256': locked[arguments.frozen_checkpoint],
        'candidate_pointer_sha256': locked[arguments.candidate_checkpoint],
        'evaluation_code_sha256': locked[ORIGINAL_PATH],
        'added_districts_sha256': locked[arguments.added_districts] if arguments.added_districts else None}
    work_dir.mkdir(parents=True, exist_ok=False)
    start = time.perf_counter()
    workers = _run_workers(arguments, origins, work_dir)
    table, common_inputs = _merge(workers, work_dir, origins, expected)
    if any(sha256_file(path) != fingerprint for path, fingerprint in locked.items()):
        raise ValueError('A locked evaluator, protocol or model changed during worker execution.')
    report = original.summarize(table)
    report.update(created_at_utc=datetime.now(timezone.utc).isoformat(),
        inputs={**common_inputs, 'parallel_driver_sha256': locked[DRIVER_PATH],
            'protocol_sha256': locked[arguments.protocol]},
        parallel_execution={'version': VERSION, 'workers': len(workers), 'worker_runs': workers,
            'duration_seconds': time.perf_counter() - start,
            'original_cli': 'python -u -B -m scripts.evaluate_retrained_model',
            'original_cli_unmodified': True, 'xgboost_model_fitting_performed': False,
            'selection_or_calibration_performed': False,
            'production_anchor_fits': 'Unchanged original serving-path computation in every worker.',
            'merge_float_precision': 'round_trip', 'merge_order': 'Contiguous chronological chunks; original registry order within each origin.',
            'environment': {'python': platform.python_version(), 'platform': platform.platform(),
                'packages': {name: importlib.metadata.version(name) for name in ('numpy', 'pandas', 'xgboost')},
                'worker_configuration': 'Inherited environment; credential values are not recorded.'}})
    # Build the entire aggregate in the ignored workspace, then atomically
    # expose the complete directory. Failed workers never create this report.
    staging = work_dir / 'merged_output'
    staging.mkdir(exist_ok=False)
    table.to_csv(staging / 'cases.csv', index=False)
    report['cases_sha256'] = sha256_file(staging / 'cases.csv')
    (staging / 'summary.json').write_text(json.dumps(report, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    if output.exists() or output.is_symlink():
        raise FileExistsError('Aggregate destination appeared during execution; nothing was replaced.')
    _publish(staging, output)
    print(json.dumps(report['overall'], indent=2, allow_nan=False))
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('features', 'frozen-checkpoint', 'candidate-checkpoint', 'protocol', 'work-dir', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--added-districts', type=Path)
    parser.add_argument('--workers', type=int, choices=(1, 2, 3), default=3)
    arguments = parser.parse_args(argv)
    run(arguments)


if __name__ == '__main__':
    main()
