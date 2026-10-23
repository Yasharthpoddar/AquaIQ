# AquaIQ — visual rehearsal and preservation investigation

23 October 2026. Verified local commit: `090626df28ad6414b355e2b1a4e24a4163693de5` on `main`. The [completed end-to-end audit](C:/Users/Yasharth/Downloads/AquaIQ/reports/end_to_end_verification_20261022/REPORT.md) remains the numerical source of truth; it was not changed or rerun.

| Decision | Verdict | Reason |
|---|---|---|
| Academic demonstration | **CONDITIONALLY READY** | Existing local provisioning works. A human must still verify the requested desktop/mobile views and scientific labels before presenting them as visually checked. |
| Production | **NO-GO** | No verified prospective skill or historical input availability; unresolved well/datum/geography issues and nonportable default provisioning remain. |
| Visual verification | **NOT VERIFIED** | Browser automation could not initialize, even after one supported reset. No chart, browser console or responsive viewport was inspected in this turn. |
| Preservation | **PARTIAL** | The known HTML difference is now fully explained as added carriage-return bytes; all eleven exception files match the previous final state. Their writer/launcher remains unresolved. |

No application source, datasets, historical predictions, model checkpoints, database contents, environment/configuration files or previous reports were intentionally edited. No build, backtest, training, ingestion, scheduled-job change, commit, push, cleanup or restoration was run. All new evidence is confined to this fresh directory. No existing service was started, stopped or reconfigured.

## Preservation: the exact HTML difference is now known

The original inventory recorded a 682-byte HTML file with SHA-256:

`273c2d6eec27ffa15c1daa1fed8e5100376cd3e63b583a3f94a87c869904c9ad`

The previous final receipt recorded 696 bytes with SHA-256:

`f21af1b46c1ed4d5ed506773dac8784e54d471b25288301e3464926d6129a336`

**New retained evidence:** `scratch/all-district-twelve-month-build-01/index.html` is exactly 682 bytes and matches the original hash. This supplies original bytes that were unavailable to the earlier report. It was read, not restored or rebuilt.

Comparing those bytes with the current `dashboard/dist/index.html` proves that the difference consists of **fourteen added carriage-return bytes (`0x0D`)**. Original: zero CR, fifteen LF. Current: fourteen CR, fifteen LF, including thirteen CRLF pairs, one CRCRLF sequence and two LF without a preceding CR. Dropping CR bytes **in memory only** produces the original bytes and original hash exactly. All non-CR bytes, including markup and asset references, are identical. No file was normalized or rewritten.

This narrows the content impact to line endings; it does not make the original byte-preservation assertion pass. Relative to the initial inventory, **1,114/1,115 files still match**, with this same HTML the only exception. All eleven exception files—the HTML plus ten unexpected untracked files—match their previous final hashes and lengths. The ten files are the empty `aquaiq.db` and nine files under the three previously reported audit directories; full paths and current UTC metadata are in the preservation evidence.

**Prior evidence is intact:** all 478 payload lengths/hashes in the old evidence manifest match; the independent 479-file prior-audit inventory also includes the manifest itself. Existing data/model/report hash checks remain consistent with the prior audit. The current task did not open the empty file as a SQLite database. Normal application serving uses PostgreSQL, not that file.

**Attribution remains unresolved.** Narrow, redacted inspection of available session and command histories did not find a direct target-window write/build record. Thirty-one AquaIQ session logs lacked the relevant time window; the overlapping desktop log supplied no timestamped build/DB receipt. PSReadLine contained seven bare build commands, but no timestamps or working directories, and its last-write date preceded the event. These cannot identify a writer. File times around 22 October 16:47–16:49 UTC are supporting metadata, not process attribution. The new original-byte match proves content identity, not who copied/generated it.

Preserve the current files, original-byte evidence, exact diff and history-scan receipt. Do not normalize the HTML, delete the empty database filename, restore the old file, or regenerate output to conceal the exception. Further attribution requires a direct historical command/process/file-write record or reliable session-owner confirmation. [Preservation investigation](C:/Users/Yasharth/Downloads/AquaIQ/reports/visual_rehearsal_preservation_20261023_01/PRESERVATION.md).

## Services and communication

The first unprivileged listener query failed because CIM access was unavailable. An approved read-only query then established these existing listeners:

| Listener | Owning PID at inspection | Identity / use |
|---|---:|---|
| `127.0.0.1:5183` | 15196 | Existing Vite frontend. |
| `127.0.0.1:5053` | 26088 | Existing normal API using the reviewed audit helper. |
| `127.0.0.1:5051` | 8176 | Existing restricted historical demo helper; unsuitable for the complete dashboard. |

No port was freed and no process was restarted. The reviewed normal helper enforces read-only PostgreSQL sessions, blocks listed saved-ML fitting methods, disables debug/reload, and allows the exact frontend origin `http://127.0.0.1:5183`. Existing scenario serving can calculate its documented transient seasonal/trend fit in memory; no scenario or model pipeline was executed by this new HTTP probe.

Six read-only localhost GETs passed: frontend Home shell, Kurukshetra deep-link shell, frontend API module, normal config, health and published scores. The served module explicitly uses `http://127.0.0.1:5053`; API replies allow the expected 5183 origin. Health reports healthy and the published score totals remain Safe300, Watch365, Warning50, Crisis6, Unknown4: 725 records, of which 721 have scores. Estimate types remain 427 district, 294 zone fallback and four insufficient.

**This establishes configuration and HTTP reachability, not actual browser communication or rendering.** Vite's relative proxy still targets port5000; the existing explicit client API URL avoids it. The older5051 helper intentionally403s legacy routes and the scenario route. Its guard was not weakened. [Port/process receipt](C:/Users/Yasharth/Downloads/AquaIQ/reports/visual_rehearsal_preservation_20261023_01/port_occupancy.json), [safe HTTP receipt](C:/Users/Yasharth/Downloads/AquaIQ/reports/visual_rehearsal_preservation_20261023_01/local_http_provisioning.json).

## Why the visual rehearsal could not be completed

The current computer-use skill and its guidance/reference/confirmation rules were read. Both browser initialization attempts returned:

```text
failed to write kernel assets: The system cannot find the path specified. (os error 3)
```

One supported JavaScript-kernel reset succeeded between attempts; the subsequent retry failed identically. Failure occurred before a browser window or page was inspected. No unsupported helper, browser security bypass, package installation or alternative policy workaround was attempted. This differs from the earlier audit's browser-URL-confidence stop and does not supersede that earlier evidence.

No screenshot was captured or reused, and no browser console error was observed. The error above belongs to the automation runtime, not to AquaIQ. Consequently no application route is marked visually failed merely because the automation could not inspect it. [Attempt receipt](C:/Users/Yasharth/Downloads/AquaIQ/reports/visual_rehearsal_preservation_20261023_01/browser_attempts.json).

## Desktop rehearsal status

Every row is **NOT VERIFIED** visually. Visible behaviour in this turn is **not observed** for every row; the shared blocker is browser initialization. Expectations below come from the retained numerical audit and current source, and must not be reported as a successful walkthrough. Exact manual actions, acceptance criteria, safe error/retry cases and screenshot guidance are in the [manual rehearsal](C:/Users/Yasharth/Downloads/AquaIQ/reports/visual_rehearsal_preservation_20261023_01/MANUAL_REHEARSAL.md).

| Check | Exact route / surface | Human confirmation still required |
|---|---|---|
| Home layout, cards, labels/errors | `/` | Four tier cards, 721 scored plus four unavailable, total725; prototype and uncalibrated-index banner; no visible error/clipping. |
| Map and navigation | `/` map/search/zoom/district click | Boundary layer, tooltips, controls, canonical district navigation, Back and actual loading state. Base tiles depend separately on OpenStreetMap. |
| District identity/freshness | `/district/HR-Kaithal` and `/district/HR-Kurukshetra` | Correct name/state/ID; historical score/source month separate from current estimate and scenario date. |
| Experimental monthly scenarios | Both district routes with `?view=scenario#forecast-graph` | Twelve explicit November2026–October2027 values for the current October date; expanded table/curve agree; January2026 staleness and estimated current depth visible; experimental/unvalidated label. |
| Historical M+12 | `/district/TS-Adilabad?origin_month=2024-01#forecast-graph` | January2024→January2025; February2024–January2025 domain; no M+1…M+11 values/line; final ML≈7.57m and separate annual baseline≈6.84m. |
| Latest unavailable ML | `/district/TS-Adilabad?view=historical#forecast-graph`, Latest observed origin | May2026→May2027; null ML with reasons; no silent old forecast. A separate baseline≈6.55m is permitted. |
| Recorded history | District pages, Recorded groundwater history | Observed and forward-filled traces, absent months and estimated values distinguished; no claim of fresh current observations. See source concern below. |
| Alerts | `/alerts` filters/district links | All/Crisis/Warning/Watch/Safe, count changes, source labels and navigation. Source requests up to1000 and displays “Showing…of…”; there is no implemented load-more/page control for the current725-record list. |
| Sensitivity simulator | `/simulate`, select Kaithal, 0/0 then rainfall0/extraction+10% | Baseline parity and labelled heuristic scenario; prior retained examples79→79 and79→81 are references, not fresh visual results. |
| Empty/error/retry/navigation | Nicobars scenario; Adilabad `origin_month=2024-13`; valid origin Apply; page links/reload | No borrowed curve, explicit invalid-origin/no-fallback error, retry without invented recovery, valid-origin recovery and reachable loading/error states. |

**Source-derived presentation concern, not a new visual finding:** the history chart filters out missing-depth rows at `DistrictDetail.jsx:44`, then configures the observed trace with `connectNulls` at line79. Thus its input/connection rules do not preserve explicit missing-month gaps. This can visually imply continuity across absent/filled intervals; it does not fabricate measured values. This applies to recorded history, **not** the separate direct M+12 graph. Smallest proposed follow-up: retain the calendar rows, use null values for missing observations and avoid joining across them; verify the existing observed/fill values remain unchanged. No such change was implemented. During the demonstration, do not present that line as a complete monthly observation record. [Source location](C:/Users/Yasharth/Downloads/AquaIQ/dashboard/src/pages/DistrictDetail.jsx:44).

Other source continuity checks confirm unchanged CSS/map/alerts/simulator files and unchanged navigation/tier-card markup relative to the academic six-month reference. This is not pixel or responsive confirmation. The district page defaults to the separate seasonal/trend scenario; API metadata still names direct M+12 as primary. Explain the two products explicitly.

## Mobile / responsive status

All items below are **NOT VERIFIED**, with no actual viewport or visible behaviour observed:

| Page / viewport | Required observation |
|---|---|
| Home,390×844 and360×800 | Navigation usable, cards/text wrap, unavailable count visible, no clipped disclosures or horizontal overflow. |
| Map at the same widths | Usable sizing, zoom/search controls, district selection/tooltips; base-tile failure distinguished from local boundary failure. |
| Scenario/historical/latest graphs | Legible dates/legends, final red/blue marks, tooltips, expanded12-row table, provenance hashes and warnings without overlap; historical gaps retained. |
| Alerts and simulator | Filters and long names fit; form controls, labels, focus and results accessible by keyboard/touch; no clipped result/warning. |

Use browser device emulation. A separate phone cannot reach these loopback-only services without a separately approved networking change; do not change bind addresses, CORS or firewall settings for this rehearsal. Source use of `ResponsiveContainer` or `overflow-x:hidden` alone cannot certify accessibility.

## Provisioning and deployment distinction

Current static checks found all17 inventoried runtime assets present and unchanged,13 linked checksums matching,60 tracked source/configuration files matching HEAD, a clean tracked tree/index, and24 applicable Python requirement versions matching installed metadata. Existing Node22.18.0/Vite8.3.0 are available. No new dependencies were installed or models deserialized by this review.

| Product / surface | Local prerequisites |
|---|---|
| Frontend/map | Existing dashboard dependencies/source, tracked public boundary, correct dashboard working directory and explicit API URL. External base-tile access is separate. |
| Direct historical M+12 / special Adilabad scenario | Frozen manifest, model/card, feature snapshot, input provenance and source provenance under the descriptor's immutable report-artifact path. |
| Other district scenarios | Exact pinned national feature CSV/manifest and canonical crosswalk; sufficient own observed history. |
| Full legacy dashboard, history, alerts, simulator | Matching XGB/climate pointers plus immutable model/card pairs and an existing compatible PostgreSQL database with canonical features/provenance and a completed matching score publication. |

Fifteen of the17 inventoried runtime assets are absent from Git tracking. A clean checkout alone does not reproduce this locally provisioned demonstration. The default Docker context excludes reports; Compose mounts data/checkpoints but not the frozen direct bundle. Thus even those supplied mounts do not supply Adilabad's default report bundle. Docker was not run or changed. Current legacy health does not prove research-bundle/container readiness.

Proposed later fixes, **not implemented**: a reviewed read-only packaging/mount for the immutable research bundle; separate research/scenario readiness checks; a complete pinned release inventory and accurate UI-default product documentation. [Provisioning detail and receipts](C:/Users/Yasharth/Downloads/AquaIQ/reports/visual_rehearsal_preservation_20261023_01/PROVISIONING.md).

## Safe next steps and production blockers

Keep the existing local machine and normal5053/5183 setup for the demonstration. Do not switch to5051 to hide a failure. Preserve the raw/data/model/report assets and explain unavailable cases. Do not rerun numerical experiments: the prior audit already separates the792-case expanding study from the24-case fixed artifact and the unvalidated monthly scenario. The fixed artifact loses to its annual baseline; broad XGB superiority is uncertain; HGB remains abstained.

Production staysNO-GO because historical publication/acquisition/receipt/revision timing is uncertified, stable physical-well/datum/panel identity remains unresolved, source district/coordinate conflicts are substantial, inputs are stale/incomplete and prospective skill has not been demonstrated. The index remains project-defined/uncalibrated and extraction simulation remains a sensitivity heuristic. No preservation or visual result repairs those scientific limitations. Real shadow issuance remains outside scope.

## Exact manual actions remaining

1. Open [the existing local app](http://127.0.0.1:5183/) in a real browser. Confirm requests use5053 and complete D1–D4: Home/map/identity plus Kaithal and Kurukshetra scenarios with the12-row tables expanded.
2. Complete D5–D7: January2024 Adilabad M+12 markers/gaps, latest unavailable ML and observed/fill/missing history. Flag any apparent history continuity rather than claiming complete observations.
3. Complete D8–D10: Alerts filters/counts/navigation, Kaithal zero-change and+10%extraction sensitivity, unsupported/invalid-origin and recovery/retry states. Keep heuristic and historical labels visible.
4. Use device emulation at390×844 and360×800 for M1–M4; check navigation, map, charts, text overflow, alerts and simulator keyboard/touch usability.
5. Record actual PASS/FAIL/NOT VERIFIED results, viewport/date, redacted console errors and uniquely named local screenshots in a new note. Do not overwrite this checklist or prior evidence. A route returning200 is not sign-off.
6. Before calling the demoREADY, resolve or explicitly accommodate material visual failures through a separately approved follow-up. If attribution matters for release, obtain a direct historical write/command record; do not infer a writer from line endings or timestamps.

No manual model training, build, migration, data acquisition, restoration, commit/push or shadow forecast is required or authorized by this checklist.
