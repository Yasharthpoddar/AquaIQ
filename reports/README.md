# Evidence index

## Authoritative current records

| Record | Scope and decision |
| --- | --- |
| [Final reliability release](final_release_20261026/REPORT.md) | Accepted official observations, V3 source/provenance, weather/boundary rejection decisions, independent supplied-asset replay and uncertainty limits. |
| [Enriched retraining](retraining_20261027/REPORT.md) | Retained experimental candidate, 145,494 observed pairs, chronological selection and retrospective baselines. Frozen production remains active. |
| [Accuracy experiments](accuracy_experiments_20261027/REPORT.md) | Sixteen supported recipes and two baselines; no robust improvement over the current recipe. Grouped horizons are a rejected replacement. |
| [Accuracy acceptance assessment](accuracy_experiments_20261027/acceptance_assessment.json) | Explicit failed development gates and absent untouched post-refit test. No promotion. |
| [Complete tiered generation](nationwide_20261025/REPORT.md) | Registry/output coverage, A–D evidence, fallback methods and historical validation; coverage is not skill. |
| [Source catalogue](../data_sources/catalog.yaml) | Accepted, rejected and access-limited sources, provenance and attribution. |

The detailed [accuracy evidence map](accuracy_experiments_20261027/README.md) identifies its active protocol, final machine results, figure data, model identities and correction trail. Case-level exports and raw inputs remain local where documented; a code-only clone is not a populated forecasting service.

## Historical scientific studies and verification

- [Six-month selection](candidates/six_month_selection_20261017/REPORT.md), [scientific audit](scientific_validation_audit_20261018/REPORT.md) and [issuance feasibility](provenance_issuance_20261019/REPORT.md): seasonal baselines, uncertain improvements, observed-only eligibility and no-go constraints.
- [Twelve-month study](candidates/twelve_month_horizon_20261020/REPORT.md) and [application finalization](candidates/twelve_month_horizon_finalization_20261020/REPORT.md): expanding historical versus fixed artifact results, limited Adilabad scope and negative sensitivities.
- [Actual forecast validation](actual_forecast_validation_20261019/) and [original enrichment](data_enrichment/REPORT.md): retained observations, panel diagnostics, benchmarks and original scope. Accepted/source evidence was not pruned.
- [Submission finalization](submission_finalization_20261019/FINALIZATION.md), [publication evidence](github_release_20261020/PUBLICATION.md), [end-to-end audit](end_to_end_verification_20261022/REPORT.md) and dated UI reports: historical software/preservation checks. Their manifests describe those historical checkouts.
- [Earlier conservative cleanup](repository_cleanup_20261027/REPORT.md) and [current simplification](repository_simplification_20261027/REPORT.md): distinct dated housekeeping decisions, preserved without rewriting history.

Historical reports retain their original conclusions and dates. Plans/presentations are not measured current-period accuracy. Test receipts do not establish prospective forecast skill or calibrated local probabilities.

## Layout and archival policy

The working tree keeps authoritative reports, protocols, acceptance decisions, unique machine evidence, source manifests and required research artifacts. Duplicate accuracy Markdown drafts/plots and captured pytest output files have been consolidated; their exact historical bytes remain in pinned Git history, with [recovery instructions](ARCHIVE.md). Negative experimental results remain prominent above.

Historical frontend build copies remain retained because current local use could not be ruled out. They are not production source or new forecast results. Installed dependencies, `dashboard/dist`, academic deliverables, current test source and raw/processed source datasets remain protected. Do not treat an old file-size/hash inventory as a runtime input manifest; archived payload recovery is required before rerunning a historical whole-workspace preservation check.
