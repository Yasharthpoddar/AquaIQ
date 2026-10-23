# AquaIQ preservation and attribution continuation — 23 October 2026

**Current rehearsal preservation: PASS within the recorded file scope. Historical preservation: PARTIAL, with the same disclosed exception. Writer attribution: UNRESOLVED.**

The final read-only recheck completed at **2026-10-23 13:39:26 UTC**. All **1,115/1,115** protected files match this rehearsal's starting hashes and lengths. Against the original 22 October `before.json`, **1,114/1,115** match; the only difference remains `dashboard/dist/index.html`. All **11/11** previously disclosed exception files match the prior final receipt. All **479/479** files in the prior end-to-end audit directory match the rehearsal's starting inventory, and all **478/478** payloads match that audit's retained evidence manifest. No new discrepancy was found in these scopes.

The historical HTML bytes are now located in a retained build directory. Their comparison establishes that the HTML difference consists of **14 added carriage-return bytes and no other byte changes**. This refines the prior report's statement that original HTML bytes were unavailable. The prior report and its evidence were retained unchanged.

## Evidence and boundaries

Read references:

- `reports/end_to_end_verification_20261022/REPORT.md`
- `reports/end_to_end_verification_20261022/before.json`
- `reports/end_to_end_verification_20261022/final_preservation_20261023.json`
- `reports/end_to_end_verification_20261022/EVIDENCE_MANIFEST.json`

All evidence created by this preservation investigation is confined to this new rehearsal directory. Existing source, data, model, configuration, database and environment files were not modified. No build, test suite, pipeline, training, ingestion, migration, cleanup, restore, revert, commit or push was run. No application/server process was launched, no existing service was stopped, and no network or database connection was made by this investigation. The empty SQLite-named file was inspected through file metadata and SHA-256 only.

The file inventory authenticates retained bytes. It is not a production database content checksum, complete process audit, whole-machine history audit or visual verification.

## Eleven retained exception files

Each row below matches the prior final receipt's byte length and SHA-256. Exact current SHA-256 values and UTC creation/write timestamps for every row are retained in [exception_files_current.json](exception_files_current.json) and repeated in the final recheck's `exception_files` array.

| Path | Bytes | Current versus prior final |
|---|---:|---|
| `dashboard/dist/index.html` | 696 | Identical |
| `aquaiq.db` | 0 | Identical |
| `reports/final_research_readiness_20261022_audit/final_research_readiness_report.md` | 35,596 | Identical |
| `reports/final_research_readiness_20261022_audit/reproducible_checks.py` | 23,476 | Identical |
| `reports/final_research_readiness_20261022_audit/results.json` | 6,949 | Identical |
| `reports/statistical_audit_correction_20261022/AquaIQ_Statistical_Audit_Correction_Report.md` | 22,171 | Identical |
| `reports/statistical_audit_correction_20261022/audit_correction_analysis.py` | 18,756 | Identical |
| `reports/statistical_audit_correction_20261022/audit_correction_output.txt` | 8,828 | Identical |
| `reports/statistical_inference_review_20261022/AquaIQ_Statistical_Inference_Review_Addendum.md` | 13,103 | Identical |
| `reports/statistical_inference_review_20261022/inference_results.json` | 2,354 | Identical |
| `reports/statistical_inference_review_20261022/inference_review.py` | 18,607 | Identical |

The HTML's current creation/write metadata is 22 October **16:49:41 UTC**. The empty `aquaiq.db` has creation/write metadata of **16:47:38 UTC** and SHA-256 `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`. These timestamps support the incident timeline; they do not identify a writer or launcher. The ten outside-audit additions remain preserved. None was removed or reconstructed.

## Retained original HTML and exact byte comparison

The narrowly scoped search inspected current `dashboard/dist/index.html`, existing `scratch/*/index.html` build outputs, and the two prior audit build indexes. It found:

| Artifact | Bytes | SHA-256 |
|---|---:|---|
| Original dist HTML, recorded by `before.json` | 682 | `273c2d6eec27ffa15c1daa1fed8e5100376cd3e63b583a3f94a87c869904c9ad` |
| Retained `scratch/all-district-twelve-month-build-01/index.html` | 682 | `273c2d6eec27ffa15c1daa1fed8e5100376cd3e63b583a3f94a87c869904c9ad` |
| Current `dashboard/dist/index.html` | 696 | `f21af1b46c1ed4d5ed506773dac8784e54d471b25288301e3464926d6129a336` |
| Current HTML with all `0x0D` bytes omitted **in memory** | 682 | `273c2d6eec27ffa15c1daa1fed8e5100376cd3e63b583a3f94a87c869904c9ad` |

An independent byte-for-byte comparison also confirms that the retained original equals the filtered current byte array, including byte order. The original has **0 CR and 15 LF bytes**. Current HTML has **14 CR and 15 LF bytes**, comprising **13 CRLF pairs**, **one CRCRLF sequence** (one additional CR preceding a CRLF), and **two LF bytes without a preceding CR**. This explains why replacing only CRLF with LF leaves 683 bytes: one additional CR remains.

The exact difference is therefore 14 inserted carriage-return bytes. There is no other byte change after removing those CR bytes. The other five protected dist assets match their original baseline hashes. This is a content-preservation finding; it does not identify the command that rewrote the file or certify browser rendering. No HTML was normalized, copied over another file or restored. Full candidate metadata and newline counts are in [html_comparison.json](html_comparison.json).

## Available command/session histories

The search targeted **22 October 16:40–17:00 UTC**, covering the empty-file and HTML timestamps. History evidence is allowlisted in [history_investigation.json](history_investigation.json):

- **31 AquaIQ session logs** from the 21/22 October session directories and the matching archived 22 October session were checked. They contain **zero records in the target window**. Their safe retained metadata does not provide the missing command receipt.
- PSReadLine's retained text history contains seven whole-line bare `npm run build` entries. It preserves **neither per-command timestamps nor execution directories**. Its file write metadata is 18 October, and it contains no SQLite/AquaIQ database command reference. Those entries cannot be assigned to either 22 October event.
- The desktop diagnostic log spanning 16:05–17:23 UTC contains target-window diagnostic entries, but **zero literal build-command receipts, zero `AquaIQ` references and zero `aquaiq.db` references**. Generic `build`, `vite` and `sqlite` labels in diagnostics do not establish an AquaIQ execution.
- The three retained Codex prompt-history entries contain no target-window record. The older TUI/sandbox log files have last-write metadata in May and do not supply a contemporaneous receipt.

Only safe file metadata, record timestamps, counts and strictly allowlisted bare build commands were exported. No complete history lines, session messages, private cookies, request headers, credentials, environment values or unrelated personal history were copied. Browser caches, broad Downloads content, authentication stores and local application databases were not searched.

**Attribution remains unresolved for both the 16:49 UTC HTML rewrite and the 16:47 UTC empty database-file creation.** No direct safe retained record found in this scope establishes a launcher, actor, parent process or exact command. The absence of such a receipt is a limit of available evidence, not proof that an execution did not occur. Filesystem timestamps alone are not used for attribution.

## Preservation matrices and reproducibility

- [protected_matrix_current.json](protected_matrix_current.json): all 1,115 original protected paths, original/current sizes and hashes, plus current UTC metadata.
- [prior_audit_report_matrix_start.json](prior_audit_report_matrix_start.json): the 479-file starting baseline for the complete prior audit directory.
- [prior_evidence_manifest_validation.json](prior_evidence_manifest_validation.json): 478/478 payload lengths and hashes match the prior manifest. The manifest's own SHA-256 is `f288a9f7343e025cff8e1156b603d3aa7e99f44cb9784f3fba811ad869c566cf`.
- [preservation_final_recheck.json](preservation_final_recheck.json): 1,115/1,115 match this rehearsal start, 1,114/1,115 match the original baseline, 479/479 prior audit files remain unchanged, and 11/11 exceptions match both this rehearsal start and the prior final receipt.

The collector, history/HTML comparison, manifest validator and final recheck scripts are retained beside these receipts. Their evidence writers use `FileMode.CreateNew`; existing output files are refused. A later final recheck can write a fresh basename without replacing this receipt:

```powershell
& 'reports/visual_rehearsal_preservation_20261023_01/recheck_preservation.ps1' -OutputName 'preservation_root_final_recheck.json'
```

The historical byte-preservation exception remains openly recorded. Its content impact is now established as carriage-return insertion only. Release attribution is still unresolved; this investigation performed no corrective or release action.
