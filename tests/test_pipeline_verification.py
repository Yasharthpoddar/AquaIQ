"""The isolated verification command must never overwrite an existing release."""
import json
import pytest
from scripts import verify_pipeline


@pytest.mark.parametrize("path", ["data/processed", "models/checkpoints", "../outside", "scratch/../data"])
def test_verification_output_must_stay_in_scratch(path):
    with pytest.raises(ValueError, match="new directory inside"):
        verify_pipeline.output_directory(path)


def test_existing_output_is_refused(tmp_path, monkeypatch):
    monkeypatch.setattr(verify_pipeline, "ROOT", tmp_path)
    (tmp_path / "scratch/existing").mkdir(parents=True)
    with pytest.raises(ValueError):
        verify_pipeline.output_directory("scratch/existing")


def test_default_is_an_offline_plan(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(verify_pipeline, "ROOT", tmp_path)
    verify_pipeline.main(["--output-dir", "scratch/new-run"])
    assert json.loads(capsys.readouterr().out)["status"] == "plan"
    assert not (tmp_path / "scratch").exists()
