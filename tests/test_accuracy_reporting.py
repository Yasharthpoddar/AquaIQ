"""Reporting must preserve failed safety gates and distinguish labels/metrics."""
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
