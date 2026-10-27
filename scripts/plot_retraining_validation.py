"""Plot the locked winner's retrospective validation on common measured cases.

Reads only the two hashed validation CSVs named by the locked selection. It
never fits a learner, reads final-diagnostic cases or changes model selection.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import uuid

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.ticker import MaxNLocator
import numpy as np
import pandas as pd

from data_ingestion.weather_enrichment import publish_new_file


ROOT = Path(__file__).resolve().parents[1]
DEFAULT = ROOT / 'reports/retraining_20261027'
METHODS = ('frozen', 'retrained', 'persistence', 'seasonal')
LABELS = ('Frozen XGBoost', 'Selected configuration', 'Persistence', 'Seasonal naive')
COLORS = ('#667085', '#007F7A', '#C77716', '#9467A9')


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _read_cases(selection_path, cases_directory):
    selection = json.loads(selection_path.read_text(encoding='utf-8'))
    if (selection.get('phase') != 'locked_before_retrospective_final_diagnostic'
            or selection.get('selection_uses_january2026_labels') is not False):
        raise ValueError('Use the locked earlier-validation selection, not final diagnostic outcomes.')
    winner = selection['selected']
    folds = [record for record in selection['fold_results'] if record['candidate'] == winner]
    if len(folds) != 2 or len({record['fold']['name'] for record in folds}) != 2:
        raise ValueError('The locked winner must have exactly two distinct validation folds.')
    tables, sources = [], []
    for record in folds:
        path = (cases_directory / record['validation_cases_file']).resolve()
        if (record['phase'] != 'earlier_validation' or not path.is_relative_to(cases_directory)
                or sha(path) != record['validation_cases_sha256']):
            raise ValueError('Selected validation source path, phase or SHA-256 differs from the lock.')
        table = pd.read_csv(path, float_precision='round_trip', parse_dates=['origin_date', 'target_date'])
        required = {'district_id', 'origin_date', 'target_date', 'horizon', 'actual', *METHODS}
        if required - set(table) or table.empty or table.duplicated(['district_id', 'origin_date', 'horizon']).any():
            raise ValueError('Validation cases require nonempty unique district/origin/horizon keys.')
        if (table[['origin_date', 'target_date']].isna().any().any()
                or not table.horizon.between(1, 12).all() or table.horizon.mod(1).ne(0).any()
                or not table.origin_date.dt.is_month_start.all()
                or not table.target_date.dt.is_month_start.all()):
            raise ValueError('Validation source contains invalid calendar dates or horizons.')
        expected = [date + pd.DateOffset(months=int(h)) for date, h in zip(table.origin_date, table.horizon)]
        fold = record['fold']
        if (not table.target_date.eq(expected).all()
                or not table.origin_date.between(fold['validation_origin_start'], fold['validation_origin_end']).all()
                or table.target_date.gt(pd.Timestamp(fold['validation_target_end'])).any()
                or table.origin_date.min() <= pd.Timestamp(fold['train_target_cutoff'])):
            raise ValueError('Cases do not satisfy their locked chronological fold.')
        for name in ('actual', 'frozen', 'retrained', 'persistence'):
            if not np.isfinite(table[name]).all() or table[name].lt(0).any():
                raise ValueError('A method cannot drop its nonfinite or invalid difficult cases.')
        seasonal = table.seasonal.dropna()
        if not np.isfinite(seasonal).all() or seasonal.lt(0).any():
            raise ValueError('Seasonal baseline must be finite and nonnegative where available.')
        common = table.loc[table.seasonal.notna()]
        for name in METHODS:
            saved = record['metrics']['seasonal_paired'][name]
            if saved['n'] != len(common):
                raise ValueError('Common case counts differ from the locked selection.')
            if len(common) and not np.isclose(np.abs(common[name] - common.actual).mean(),
                    saved['mae_m'], rtol=0, atol=1e-12):
                raise ValueError('Common case metrics differ from the locked selection.')
        table['fold'] = fold['name']
        tables.append(table)
        sources.append({'fold': fold['name'], 'file': str(path.relative_to(ROOT)),
            'sha256': record['validation_cases_sha256'], 'all_cases': len(table),
            'common_cases': len(common), 'common_districts': int(common.district_id.nunique()),
            'train_target_cutoff': fold['train_target_cutoff']})
    combined = pd.concat(tables, ignore_index=True)
    if combined.duplicated(['district_id', 'origin_date', 'horizon']).any():
        raise ValueError('Validation fold case keys overlap.')
    return selection, combined, sources


def _aggregate(table):
    rows = []
    for horizon in range(1, 13):
        available = table.loc[table.horizon.eq(horizon)]
        common = available.loc[available.seasonal.notna()]
        rows.append({'horizon': horizon, 'all_eligible_cases': len(available),
            'common_cases': len(common), 'excluded_missing_seasonal': len(available) - len(common),
            'common_districts': int(common.district_id.nunique()),
            'mae_m': {name: float(np.abs(common[name] - common.actual).mean()) if len(common) else None
                      for name in METHODS}})
    return rows


def _figure(rows, table):
    style = {'font.family': 'DejaVu Sans', 'font.size': 10,
        'axes.labelcolor': '#344054', 'text.color': '#172B3A',
        'xtick.color': '#475467', 'ytick.color': '#475467',
        'axes.edgecolor': '#98A2B3', 'axes.linewidth': .7,
        'axes.spines.top': False, 'axes.spines.right': False,
        'savefig.facecolor': 'white'}
    with plt.rc_context(style):
        fig, (main, counts) = plt.subplots(2, 1, figsize=(12.5, 8.0), sharex=True,
            gridspec_kw={'height_ratios': [3.2, 1.25]})
        fig.subplots_adjust(left=.075, right=.98, top=.815, bottom=.215, hspace=.42)
        fig.text(.075, .952, 'Groundwater depth forecasting: rolling validation',
            fontsize=18, weight='bold', ha='left')
        fig.text(.075, .910, 'Observed-origin forecasts · four methods on identical seasonal-supported cases',
            fontsize=11.5, color='#475467', ha='left')
        horizons = np.arange(1, 13)
        markers = ('s', 'o', 'D', '^')
        linestyles = ('--', '-', ':', '-.')
        for method, label, color, marker, linestyle in zip(METHODS, LABELS, COLORS, markers, linestyles):
            values = [np.nan if row['mae_m'][method] is None else row['mae_m'][method] for row in rows]
            main.plot(horizons, values, label=label, color=color, marker=marker,
                linestyle=linestyle, linewidth=2.0, markersize=5.2, markeredgewidth=.8,
                markeredgecolor='white' if method == 'retrained' else color,
                zorder=4 if method == 'retrained' else 3)
        main.set_ylabel('Mean absolute error (m)', labelpad=10)
        main.set_ylim(bottom=0)
        main.yaxis.set_major_locator(MaxNLocator(nbins=6))
        main.grid(axis='y', color='#D0D5DD', linewidth=.65, linestyle=':', zorder=0)
        main.text(.985, .965, 'Lower is better', transform=main.transAxes,
            ha='right', va='top', color='#667085', fontsize=9.5)
        main.legend(loc='lower left', bbox_to_anchor=(-.008, 1.025), ncols=4,
            frameon=False, fontsize=10, columnspacing=1.8, handlelength=2.4)
        main.text(-.055, 1.0, 'a', transform=main.transAxes, weight='bold', fontsize=13)
        common = np.array([row['common_cases'] for row in rows])
        available = np.array([row['all_eligible_cases'] for row in rows])
        counts.set_facecolor('#FAFBFC')
        counts.bar(horizons, available, width=.65, color='#E4E7EC', edgecolor='#98A2B3',
            linewidth=.6, label='All eligible measured targets', zorder=2)
        counts.bar(horizons, common, width=.45, color='#007F7A', alpha=.88,
            label='Common seasonal-supported cases', zorder=3)
        maximum = max(1, int(available.max()))
        for horizon, n, total in zip(horizons, common, available):
            counts.text(horizon, total + maximum * .035, f'{n:,}/{total:,}',
                ha='center', va='bottom', fontsize=8.4, color='#344054')
            if n == 0:
                main.text(horizon, .035, 'No cases', transform=main.get_xaxis_transform(),
                    rotation=90, ha='center', va='bottom', fontsize=8, color='#667085')
        counts.set_ylim(0, maximum * 1.28)
        counts.set_ylabel('Cases (n / N)', labelpad=10)
        counts.yaxis.set_major_locator(MaxNLocator(nbins=3, integer=True))
        counts.grid(axis='y', color='#E4E7EC', linewidth=.6, zorder=0)
        counts.set_xticks(horizons, [f'M+{h}' for h in horizons])
        counts.set_xlim(.5, 12.5)
        counts.set_xlabel('Forecast horizon after the observed origin', labelpad=9)
        counts.legend(loc='lower right', bbox_to_anchor=(1, 1.08), ncols=2,
            frameon=False, fontsize=8.8, columnspacing=1.7)
        counts.text(-.055, 1.0, 'b', transform=counts.transAxes, weight='bold', fontsize=13)
        origin_start, origin_end = table.origin_date.min(), table.origin_date.max()
        target_end = table.target_date.max()
        total = int(common.sum())
        caption = [
            f'Retrospective validation; not a blind test. Two locked folds: origins {origin_start:%b %Y}–{origin_end:%b %Y}; targets end {target_end:%b %Y}.',
            f'Pooled case-weighted MAE on {total:,} common cases. Bars show common / all eligible cases; missing horizons are explicit gaps.',
            'Selected configuration uses fold-specific fits here, not the final refit. Selection used mean fold district-macro MAE.',
            'Cases share districts and target periods. This figure establishes neither prospective/local skill nor interval calibration.'
        ]
        for index, line in enumerate(caption):
            fig.text(.075, .130 - index * .026, line, fontsize=8.8, color='#475467', ha='left')
        return fig


def run(selection_path, cases_directory, output, aggregate_path):
    selection_path, output, aggregate_path = map(lambda path: Path(path).resolve(),
        (selection_path, output, aggregate_path))
    cases_directory = Path(cases_directory or selection_path.parent).resolve()
    for path in (output, aggregate_path):
        if not path.is_relative_to(ROOT / 'reports') or path.exists():
            raise ValueError('Choose new figure/aggregate files under reports/.')
    if output.suffix.lower() != '.png' or aggregate_path.suffix.lower() != '.json':
        raise ValueError('The figure must be PNG and the aggregate must be JSON.')
    selection_sha = sha(selection_path)
    selection, table, sources = _read_cases(selection_path, cases_directory)
    rows = _aggregate(table)
    aggregate = {'selected_configuration': selection['selected'],
        'source_selection': str(selection_path.relative_to(ROOT)), 'selection_sha256': selection_sha,
        'sources': sources, 'methods': list(METHODS),
        'population': 'Identical seasonal-supported rows for all four methods; pooled across the two locked folds.',
        'metric': 'case-weighted mean absolute depth error in metres; selection itself used mean fold district-macro MAE',
        'scope': 'Retrospective earlier validation of fold models; not final-refit, blind-test or prospective performance.',
        'new_blind_evaluation': False, 'model_training_or_selection_performed': False,
        'rows': rows, 'figure_script_sha256': sha(Path(__file__))}
    output.parent.mkdir(parents=True, exist_ok=True)
    aggregate_path.parent.mkdir(parents=True, exist_ok=True)
    token = uuid.uuid4().hex
    temporary_png = output.with_name(output.stem + '.' + token + '.partial.png')
    temporary_json = aggregate_path.with_name(aggregate_path.stem + '.' + token + '.partial.json')
    figure = _figure(rows, table)
    try:
        figure.savefig(temporary_png, dpi=260)
        if temporary_png.stat().st_size >= 5 * 1024 * 1024:
            raise ValueError('Figure exceeds the five MiB research-artifact bound.')
        aggregate['figure_sha256'] = sha(temporary_png)
        temporary_json.write_text(json.dumps(aggregate, indent=2, allow_nan=False) + '\n', encoding='utf-8')
        if sha(selection_path) != selection_sha or any(sha(ROOT / item['file']) != item['sha256'] for item in sources):
            raise ValueError('A locked source changed while plotting; no figure was published.')
        publish_new_file(temporary_png, output)
        publish_new_file(temporary_json, aggregate_path)
    finally:
        plt.close(figure)
        temporary_png.unlink(missing_ok=True)
        temporary_json.unlink(missing_ok=True)
    print(json.dumps({'figure': str(output.relative_to(ROOT)), 'size_bytes': output.stat().st_size,
        'aggregate': str(aggregate_path.relative_to(ROOT)), 'common_cases': sum(row['common_cases'] for row in rows),
        'selected': selection['selected'], 'source_hashes_verified': True}, indent=2))
    return aggregate


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--selection', type=Path, default=DEFAULT / 'training/selection.json')
    parser.add_argument('--cases-directory', type=Path)
    parser.add_argument('--output', type=Path, default=DEFAULT / 'validation_horizons.png')
    parser.add_argument('--aggregate', type=Path, default=DEFAULT / 'validation_horizons.json')
    args = parser.parse_args()
    run(args.selection, args.cases_directory, args.output, args.aggregate)
