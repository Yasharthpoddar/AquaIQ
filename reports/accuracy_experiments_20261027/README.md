# Accuracy experiment evidence map

- **Authoritative narrative:** [REPORT.md](REPORT.md).
- **Decision:** [acceptance_assessment.json](acceptance_assessment.json); retain the enriched candidate and frozen production model. Grouped horizons are rejected as a replacement.
- **Active protocol:** [protocol_v2.json](protocol_v2.json); original attempt [protocol.json](protocol.json) remains as history.
- **Final fold evidence:** [run_v2/results.json](run_v2/results.json), [fold inputs/support](run_v2/fold_inputs.json), [selection lock](run_v2/final_selection_lock.json) and [final research artifact decision](run_v2/decision.json).
- **Corrected comparisons/figures:** [analysis_v2/comparison.json](analysis_v2/comparison.json), [development figure](analysis_v2/development_comparison.png), [historical figure](analysis_v2/historical_diagnostics.png), [checksums](analysis_v2/figure_checksums.json).
- **Baseline reproduction:** [audit_v2/baseline_audit.json](audit_v2/baseline_audit.json), [serving replay](audit_v2/serving_replay.json), [old-fold reproduction](audit_v2/historical_validation_reproduction.json).
- **Verification:** [verification_v3.json](verification_v3.json), [artifact verification](artifact_verification.json), [JUnit](pytest.xml) and before/after public fingerprints.

The earlier [analysis_v1/comparison.json](analysis_v1/comparison.json) is retained solely to audit the reporting correction: a metric dictionary overwrote a reference name and hid a failed subgroup gate. Training, predictions and raw fold gates did not change. Corrected analysis_v2 and the acceptance assessment are authoritative. Verification v1/v2 and failed-run/protection records retain chronology, not an alternate winning model.

Four obsolete Markdown drafts, three byte-identical old figure/checksum copies and the completed progress snapshot were pruned. Final `results.json` is byte-identical to that progress snapshot, and the retained analysis_v2 figures are byte-identical to the deleted copies. [Pinned Git recovery](../ARCHIVE.md) preserves all historical text/bytes without keeping duplicate working copies. Case exports, detailed diagnostics and fold learners remain local and unchanged under the existing ignore policy.
