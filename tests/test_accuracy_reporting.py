"""Reporting must preserve failed safety gates and distinguish labels/metrics."""
import json
from pathlib import Path

from scripts.summarize_accuracy_experiments import markdown_report
from scripts.summarize_accuracy_experiments import subgroup_checks, subgroup_gate, differences


def test_subgroup_reference_name_cannot_be_overwritten_by_metric_dictionary():
    metric={'mae_m':1.,'n':70,'districts':20}
    record={'year':2021,
        'subgroup_gates_vs_current':[{'status':'pass','reference':metric}],
        'subgroup_gates_vs_frozen':[{'status':'fail','reference':metric}]}
    checks=subgroup_checks([record])
    assert checks[0]['reference_name']=='current_recipe'
    assert checks[1]['reference_name']=='frozen_fixed_reference'
    assert checks[1]['reference']==metric
    assert subgroup_gate(checks,'current_recipe') is True
    assert subgroup_gate(checks,'frozen_fixed_reference') is False


def test_absent_or_unsupported_subgroups_are_not_claimed_as_passing():
    assert subgroup_gate([],'frozen_fixed_reference') is False
    assert subgroup_gate([{'reference_name':'frozen_fixed_reference','status':'unsupported'}],
                         'frozen_fixed_reference') is False


def test_report_differences_keep_case_macro_and_rmse_signs():
    candidate={'mae_m':1.1,'district_macro_mae_m':2.,'rmse_m':4.,'mean_signed_error_m':.2}
    baseline={'mae_m':1.,'district_macro_mae_m':2.5,'rmse_m':3.,'mean_signed_error_m':0.}
    result=differences(candidate,baseline)
    assert result['mae_difference_m']>0
    assert result['macro_mae_difference_m']<0
    assert result['rmse_difference_m']==1.


def test_completed_scientific_report_renders_without_software_verification_receipt(tmp_path):
    """Render retained completed metadata only; no raw cases, fits or new metrics."""
    source=Path(__file__).resolve().parents[1]/'reports/accuracy_experiments_20261027'
    root=tmp_path/'report';root.mkdir()
    audit=root/'audit';audit.mkdir()
    run=root/'run';run.mkdir()
    (audit/'baseline_audit.json').write_bytes((source/'audit_v2/baseline_audit.json').read_bytes())
    (run/'fold_inputs.json').write_bytes((source/'run_v2/fold_inputs.json').read_bytes())
    protocol=json.loads((source/'protocol_v2.json').read_text(encoding='utf-8'))
    protocol['audit_directory']=str(audit)
    summary=json.loads((source/'analysis_v2/comparison.json').read_text(encoding='utf-8'))
    records=json.loads((source/'run_v2/results.json').read_text(encoding='utf-8'))
    assert not (root/'verification.json').exists()
    assert not (root/'verification_v2.json').exists()

    markdown_report(root,run,source/'protocol_v2.json',summary,protocol,records,None,'analysis_test')

    report=(root/'REPORT_analysis_test.md').read_text(encoding='utf-8')
    assert '## Results and model selection' in report
    assert '2 failed checks and 8 unsupported checks' in report
    assert 'supported subgroup gate versus frozen: False' in report
    assert 'Untouched post-refit test: **absent**' in report
    assert 'Promotion remains prohibited' in report
    assert '## Executed verification and modified files' not in report
    assert 'Full Python integration suite:' not in report
    assert '136 passed' not in report
    assert '160 passed' not in report
    assert 'verification.json' not in report
    assert 'verification_v2.json' not in report
