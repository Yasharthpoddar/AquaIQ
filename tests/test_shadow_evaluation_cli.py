"""Offline CLI and synthetic-only demo controls; no real observation fixtures."""
import json

import pytest

from scripts import shadow_evaluation as cli


def test_default_and_missing_run_are_read_only_plans(tmp_path, capsys):
    destination = tmp_path / "reports/candidates/shadow_not_created"
    for arguments in ([], ["demo", "--ledger", str(destination)], ["record"]):
        result = cli.main(arguments)
        assert result["mode"] == "offline_plan"
        assert result["locked_contract"]["candidate"]["candidate_id"] == "hist_gradient_boosting-2-delta"
        assert result["locked_contract"]["train_target_cutoff"] == "2018-12-31"
        assert result["model_fitted_or_loaded"] is False
        assert result["database_used"] is False
    assert not destination.exists()
    capsys.readouterr()


@pytest.mark.parametrize("flag", ["--issued-at", "--clock", "--timestamp"])
def test_cli_exposes_no_backdating_or_clock_override(flag, capsys):
    with pytest.raises(SystemExit) as error:
        cli.main(["record", "--run", flag, "2000-01-01T00:00:00Z"])
    assert error.value.code == 2
    capsys.readouterr()


def test_synthetic_demo_rejects_real_lanes_and_external_inputs(tmp_path, capsys):
    for extra in (["--lane", "prospective"], ["--input", str(tmp_path / "anything.json")]):
        with pytest.raises(SystemExit):
            cli.main(["demo", "--run", "--ledger", str(tmp_path / "unused"), *extra])
    assert not (tmp_path / "unused").exists()
    capsys.readouterr()


@pytest.mark.parametrize("relative", ["data/shadow_bad", "reports/candidates/not_shadow", "reports/shadow_bad"])
def test_demo_output_scope_cannot_escape_candidate_directory(tmp_path, monkeypatch, relative):
    monkeypatch.setattr(cli, "ROOT", tmp_path)
    destination = tmp_path / relative
    with pytest.raises(ValueError):
        cli.run_demo(destination)
    assert not destination.exists()


def test_demo_has_only_synthetic_evidence_and_never_overwrites(tmp_path, monkeypatch):
    monkeypatch.setattr(cli, "ROOT", tmp_path)
    destination = tmp_path / "reports/candidates/shadow_synthetic_cli_test"
    result = cli.run_demo(destination)
    assert result["mode"] == "SYNTHETIC_ONLY_DRY_RUN"
    assert not result["prospective_skill_established"]
    assert not result["real_observations_read"]
    assert not result["model_fitted_or_loaded"]
    assert result["integrity"]["lane"] == "synthetic"
    assert result["integrity"]["counts"] == {"forecasts": 3, "labels": 1, "evaluations": 1}
    assert all(case["classification"] == "synthetic" for case in result["evaluation"]["cases"])
    for name in ("duplicate_issuance", "late_input", "source_revision_cannot_replace_existing_slot"):
        assert result["checks"][name]["rejected"]
    assert result["checks"]["missing_baseline"]["status"] == "abstained"
    assert result["checks"]["historical_snapshot_immutable_after_revision_and_copy_mutation"]
    fixture = json.loads((destination / "SYNTHETIC_forecast_fixture.json").read_text())
    assert fixture["evidence_kind"] == "synthetic_fixture"
    assert all(well["well_id"].startswith("SYNTHETIC-") for well in fixture["panel"]["wells"])
    before = {file.relative_to(destination): file.read_bytes() for file in destination.rglob("*") if file.is_file()}
    with pytest.raises(FileExistsError):
        cli.run_demo(destination)
    after = {file.relative_to(destination): file.read_bytes() for file in destination.rglob("*") if file.is_file()}
    assert before == after


def test_execution_requires_explicit_output_directory(capsys):
    with pytest.raises(SystemExit) as error:
        cli.main(["init", "--run", "--lane", "synthetic", "--campaign", "SYNTHETIC-test"])
    assert error.value.code == 2
    capsys.readouterr()
