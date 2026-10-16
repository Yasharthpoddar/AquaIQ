"""Offline agreement diagnostics against explicitly independent crisis labels.

This module never fits scoring weights. Four-tier labels require a documented
external mapping; CGWB assessment categories must not be silently renamed to
AquaIQ tiers. A score is an index, not a crisis probability.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
TIERS = ("Safe", "Watch", "Warning", "Crisis")
SCORE_COLUMNS = {"district_id", "score", "tier", "evidence_as_of", "published_at",
                 "target_date", "model_version", "scoring_signature", "evidence_kind"}
EVIDENCE_COLUMNS = {"district_id", "target_date", "label", "assessed_at", "available_at",
                    "source_url", "source_sha256", "evidence_id", "label_definition",
                    "mapping_provenance", "independent_of_aquaiq", "derivation_method",
                    "geography_version"}
METHODS = {"independent_external_assessment", "independently_adjudicated_field_assessment"}


def readiness_report():
    return {"status": "independent_evidence_required", "calibrated": False,
        "weights_changed": False, "score_is_probability": False,
        "required_score_columns": sorted(SCORE_COLUMNS),
        "required_evidence_columns": sorted(EVIDENCE_COLUMNS),
        "allowed_derivation_methods": sorted(METHODS),
        "label_values": list(TIERS), "evidence_kind_values": ["district", "zone_fallback"],
        "date_contract": "Exact district/target-date join; evidence_as_of <= publication <= target <= assessment <= availability <= evaluation cutoff.",
        "requirements": [
            "Provide prospectively archived scores and independent outcomes for the same canonical geography and exact target dates.",
            "Document the external label definition and mapping to four AquaIQ tiers; groundwater assessment categories are not automatically equivalent.",
            "Labels from AquaIQ depth thresholds, fuzzy rules, predictions, simulations or scores are not independent evidence.",
            "Source URL, digest and independence statement are provenance attestations requiring human review; this tool cannot establish scientific independence.",
            "Agreement diagnostics do not calibrate probabilities, thresholds or weights, and do not establish current-period accuracy.",
            "The current historical score CSV may lack prospective publication/target metadata; export a documented evaluation fixture rather than guessing dates."]}


def _required(frame, columns, kind):
    missing = columns - set(frame)
    if missing:
        raise ValueError(f"{kind} CSV missing required columns: {sorted(missing)}")
    if frame.empty:
        raise ValueError(f"{kind} CSV is empty")
    result = frame.copy()
    for column in columns:
        if result[column].isna().any() or result[column].astype(str).str.strip().eq("").any():
            raise ValueError(f"{kind} has missing {column}")
    return result


def _dates(frame, columns, cutoff):
    for column in columns:
        # Calendar dates are explicit: month coercion or nearest-date matching
        # could turn an observation into a mislabeled future outcome.
        text = frame[column].astype(str)
        parsed = pd.to_datetime(text, format="%Y-%m-%d", errors="coerce")
        if parsed.isna().any() or not text.str.fullmatch(r"\d{4}-\d{2}-\d{2}").all():
            raise ValueError(f"{column} must contain valid YYYY-MM-DD dates")
        if parsed.gt(cutoff).any():
            raise ValueError(f"{column} contains future dates")
        frame[column] = parsed


def _metrics(frame):
    matrix = {actual: {predicted: 0 for predicted in TIERS} for actual in TIERS}
    for row in frame.itertuples():
        matrix[row.label][row.tier] += 1
    count = len(frame)
    matches = int(frame.label.eq(frame.tier).sum())
    distance = [abs(TIERS.index(actual) - TIERS.index(predicted)) for actual, predicted in zip(frame.label, frame.tier)]
    per_tier = {}
    for tier in TIERS:
        true_positive = matrix[tier][tier]
        actual = sum(matrix[tier].values())
        predicted = sum(matrix[value][tier] for value in TIERS)
        per_tier[tier] = {"actual_count": actual, "predicted_count": predicted,
            "precision": true_positive / predicted if predicted else None,
            "recall": true_positive / actual if actual else None}
    return {"cases": count, "exact_agreement": matches / count if count else None,
        "within_one_tier": sum(value <= 1 for value in distance) / count if count else None,
        "mean_absolute_tier_distance": float(np.mean(distance)) if distance else None,
        "confusion_matrix_actual_rows_predicted_columns": matrix, "per_tier": per_tier}


def evaluate_scores(scores, evidence, *, as_of, geography_version):
    """Evaluate exact prospective cases. Reject chronology/provenance failures.

    Independence declarations cannot prove independence. Metrics describe only
    supplied matched labels and must not be presented as national accuracy.
    """
    if evidence is None:
        return readiness_report()
    cutoff = pd.Timestamp(as_of).normalize()
    if pd.isna(cutoff) or cutoff > pd.Timestamp.today().normalize():
        raise ValueError("as_of must be a valid date no later than today")
    scores = _required(scores, SCORE_COLUMNS, "Scores")
    evidence = _required(evidence, EVIDENCE_COLUMNS, "Evidence")
    if not geography_version or not str(geography_version).strip():
        raise ValueError("Explicit score geography_version is required")
    if not evidence.geography_version.eq(geography_version).all():
        raise ValueError("Evidence and scores must use the same documented canonical geography")
    _dates(scores, ("evidence_as_of", "published_at", "target_date"), cutoff)
    _dates(evidence, ("target_date", "assessed_at", "available_at"), cutoff)
    if (scores.evidence_as_of.gt(scores.published_at) | scores.published_at.gt(scores.target_date)).any():
        raise ValueError("Scores are not prospective: evidence_as_of <= published_at <= target_date is required")
    if (evidence.target_date.gt(evidence.assessed_at) | evidence.assessed_at.gt(evidence.available_at)).any():
        raise ValueError("Evidence requires target_date <= assessed_at <= available_at")
    for frame, label in ((scores, "Scores"), (evidence, "Evidence")):
        if frame.duplicated(["district_id", "target_date"]).any():
            raise ValueError(f"{label} has duplicate district/target cases")
    if evidence.evidence_id.duplicated().any():
        raise ValueError("Evidence IDs must uniquely identify district/target assessments")
    independent = evidence.independent_of_aquaiq.astype(str).str.strip().str.lower()
    if not independent.isin(("true", "1")).all():
        raise ValueError("Every label must declare independence from AquaIQ")
    if not evidence.derivation_method.isin(METHODS).all():
        raise ValueError("Labels must come from an independent external or independently adjudicated field assessment")
    if not evidence.source_sha256.astype(str).str.fullmatch(r"[0-9a-fA-F]{64}").all():
        raise ValueError("Independent evidence requires source SHA256 digests")
    if not evidence.source_url.astype(str).str.match(r"https://[^/\s]+(?:/[^\s]*)?$").all():
        raise ValueError("Independent evidence requires HTTPS source URLs")
    if not evidence.label.isin(TIERS).all() or not scores.tier.isin(TIERS).all():
        raise ValueError("Scores and externally mapped labels must use Safe/Watch/Warning/Crisis")
    if not scores.evidence_kind.isin(("district", "zone_fallback")).all():
        raise ValueError("Scores require district or zone_fallback evidence_kind")
    numeric = pd.to_numeric(scores.score, errors="coerce")
    if not (np.isfinite(numeric) & numeric.between(0, 100) & numeric.eq(numeric.round())).all():
        raise ValueError("Published crisis scores must be finite integers in [0,100]")
    scores["score"] = numeric
    # The project defaults are stated explicitly; changes require a new
    # diagnostic contract, never silent remapping of independent labels.
    expected = numeric.map(lambda value: "Safe" if value <= 30 else "Watch" if value <= 60 else "Warning" if value <= 80 else "Crisis")
    if not scores.tier.eq(expected).all():
        raise ValueError("Published score/tier disagrees with documented 30/60/80 project boundaries")
    matched = scores.merge(evidence, on=["district_id", "target_date"], how="inner", validate="one_to_one")
    report = {"status": "independent_agreement_diagnostics" if len(matched) else "no_exact_target_matches",
        "calibrated": False, "weights_changed": False, "score_is_probability": False,
        "as_of": str(cutoff.date()), "geography_version": geography_version,
        "input_score_cases": len(scores), "input_evidence_cases": len(evidence),
        "matched_cases": len(matched), "unmatched_score_cases": len(scores) - len(matched),
        "unmatched_evidence_cases": len(evidence) - len(matched),
        "unique_matched_districts": int(matched.district_id.nunique()),
        "overall": _metrics(matched),
        "by_evidence_kind": {str(kind): _metrics(group) for kind, group in matched.groupby("evidence_kind")},
        "limitations": [
            "Independence and mapping provenance are supplied declarations, not automatically verified scientific independence.",
            "These are supplied-case agreement diagnostics; no probability calibration or representative nationwide accuracy is established.",
            "Tier mapping validity, observation staleness, spatial comparability and label representativeness require independent review.",
            "No score threshold, weight, active model, configuration, source dataset or database is modified."]}
    return report


def _output(path, inputs):
    path = Path(path).resolve()
    if not path.is_relative_to((ROOT / "reports/candidates").resolve()):
        raise ValueError("Output must be inside reports/candidates")
    if path.exists() or path in {Path(item).resolve() for item in inputs}:
        raise ValueError("Choose a new candidate output; existing files and inputs are protected")
    return path


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scores", type=Path)
    parser.add_argument("--evidence", type=Path)
    parser.add_argument("--geography-version")
    parser.add_argument("--as-of", default=str(pd.Timestamp.today().date()))
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    if bool(args.scores) != bool(args.evidence):
        raise ValueError("Provide both scores and independent evidence, or neither for an offline readiness report")
    inputs = [path for path in (args.scores, args.evidence) if path]
    output = _output(args.output, inputs) if args.output else None
    report = (evaluate_scores(pd.read_csv(args.scores), pd.read_csv(args.evidence),
        as_of=args.as_of, geography_version=args.geography_version)
        if inputs else readiness_report())
    report["input_files"] = [{"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()} for path in inputs]
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, allow_nan=False))
    return 0 if report["status"] == "independent_agreement_diagnostics" else 2


if __name__ == "__main__":
    raise SystemExit(main())
