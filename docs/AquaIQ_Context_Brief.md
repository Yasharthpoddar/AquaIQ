# AquaIQ — Project Context Brief

*Paste or upload this file at the start of any new chat, then say what you want to work on next. This document exists so you don't have to re-explain decisions that already took several rounds to nail down — treat everything below as settled unless the person explicitly asks to revisit it.*

*Last replanned: 10 Sep 2026 — see §3 and §8 for what changed from the original version.*

---

## 1. What this project is

**AquaIQ** — AI-powered groundwater depletion forecasting system for India's districts.

- **Who:** Yasharth (2024800092), Yash, Ayush — B.Tech CSE, Sardar Patel Institute of Technology (SPIT), Mumbai
- **What for:** TE Sem V Mini Project I, AY 2026–27 Odd Semester
- **Real-world hook:** Maps to Smart India Hackathon problem statement **SIH25068** (Ministry of Jal Shakti — Real-Time Groundwater Evaluation using DWLR Data)
- **Code:** [github.com/Yasharthpoddar/AquaIQ](https://github.com/Yasharthpoddar/AquaIQ)
- **One-line pitch:** Forecasts district-level groundwater depletion 6 months ahead using a two-layer ML system, outputs a 0–100 Crisis Score per district, served through a Flask API + React dashboard.

---

## 2. Already done — do not redo or re-litigate

| Artifact | Status |
|---|---|
| IEEE-format project proposal | ✅ Written and submitted |
| SRS (IEEE 830-1998 format) | ✅ Written and submitted |
| SPIT official title page | ✅ Filled and submitted |
| 14-week team project plan (HTML) | ✅ Built, verified, task-balanced, replanned 10 Sep |
| Phase I evaluation | ✅ Delivered (17 Aug) |
| Phase II evaluation | ✅ Delivered (02 Sep) |
| CGWB / IMD / ERA5 ingestion scripts | ✅ In the repo, working (`data_ingestion/`) |
| PostgreSQL schema + init script | ✅ In the repo, working (`db/`) |

Don't suggest rewriting the submitted documents unless explicitly asked. If the person wants changes to the plan/architecture, edit forward from what's below — don't propose starting over.

---

## 3. Non-negotiable technical decisions

These took real back-and-forth to settle. Don't reintroduce dropped scope or re-derive from scratch.

> **Scope change, 10 Sep 2026: LSTM and SHAP dropped.** The advanced/self-study layer is now **XGBoost only**. This wasn't a syllabus problem — it was a time/complexity call three weeks out from Phase III. Everything downstream has been updated to match (ensemble formula, targets, API endpoint count, DB schema) — see below and the project plan HTML.

> **Open item, not yet confirmed with the guide.** The SPIT title page template contains two constraints that don't fully agree:
> - The **student confirmation table** on the title page lists Sem I–V courses as acceptable, including CS301 and CS302.
> - The **faculty guide's certification line**, same document, says the project must align with "fundamental concepts covered during **Semesters I to IV only**."
> - **CS303** (used throughout the submitted SRS/proposal to justify Fuzzy Logic and Perceptron ANN as "core") doesn't appear in the title page's table at all — not a Sem I–IV issue, it's just never listed.
>
> This was flagged before Phase I as worth a two-minute check with the guide; whether it actually came up isn't confirmed either way in this brief. Worth asking directly if it hasn't been addressed. If "Sem I–IV only" is enforced strictly, the fallback is to fold Fuzzy Logic, Perceptron ANN, CS301, and CS302 into the self-study/advanced framing too, and let the guaranteed-core layer rest on just AS202 + CS204 + CS205.

**Two-layer architecture, and why:**
- **Core layer** — must map only to SPIT Sem I–V courses: `AS202` (Python for Data Science), `CS205` (Statistical Methods), `CS303` (AI & Soft Computing — Fuzzy Logic + Perceptron/ANN, *not* deep learning), `CS204` (DBMS), `CS301` (Distributed Computing / client-server), `CS302` (Software Engineering).
- **Advanced layer** — **XGBoost only** (500 trees). Framed as a **self-study extension** — verified against the SPIT syllabus PDF: XGBoost = CS307 (Sem VI). LSTM (CS321, Sem VI) and SHAP (CS424, Sem VII) were part of this layer originally; both are dropped as of 10 Sep 2026. With only one advanced model left, the ensemble design itself (see §4) and the walk-forward backtesting are the stronger self-study talking points at ESE — worth leaning on those in the demo/report rather than the model count.

**Data sources — exactly 3, nothing else:**
- CGWB (`india-wris.nrsc.gov.in`) — borewell groundwater level readings, ~15,000 wells. Actual usable range is 2013–2023 at quarterly cadence (needs interpolation); a merged historical set (1996–2017 + 2013–2023) gave ~1.2M clean rows after dedup. ~75 districts don't have enough direct coverage and fall back to a zone-level aggregate.
- IMD (`imdpune.gov.in`) — monthly district rainfall + 30-year climatological normal
- ERA5 (`cds.climate.copernicus.eu`) — temperature, evapotranspiration

**Explicitly dropped, do not bring back (unless the person asks to reopen this):** GRACE-FO, GLDAS, NDVI/MODIS (vegetation), irrigation_fraction, population_density, soil type, rainwater-harvesting infrastructure. These were in an earlier draft but nothing ever sourced them. If a guide asks why no satellite data: *CGWB gives direct ground truth at 15,000+ points, which is stronger evidence than an indirect satellite proxy for a district-level system.* The right home for these factors is a **Limitations & Future Work** section in the ESE report — name them explicitly, one line each on why they're excluded.

> **Known documentation mismatch:** the already-submitted SRS (FR-02) still lists the *old* 11-feature scope — `NDVI, irrigation_fraction, population_density, soil_moisture` — and still references the GRACE data gap, because that text was never touched when the pipeline was simplified (documentation was frozen, not editable). The actual build uses the clean 10-feature list below. This mismatch predates and is unrelated to the 10 Sep LSTM/SHAP scope change.

**The exact 10 features (memorize, don't reinvent):**
1. `GWL_current` — CGWB
2. `GWL_lag_3mo` — CGWB
3. `GWL_lag_6mo` — CGWB
4. `rainfall_current` — IMD
5. `rainfall_3mo_avg` — IMD
6. `monsoon_deficit_pct` — IMD current vs IMD 30-yr climatological normal
7. `temperature` — ERA5
8. `evapotranspiration` — ERA5
9. `water_balance_proxy` = rainfall − ET — derived, no new source
10. `crop_season_flag` — calendar rule (Kharif Jun–Oct / Rabi Nov–Mar / Zaid Apr–May), no new source

**Ensemble weight-fitting and walk-forward validation** — previously flagged as optional upgrades, now built directly into the Week 8 plan rather than left open: the Crisis Score weights get fit on the validation set against the 2015–16/2018–19 drought backtests (not eyeballed), and XGBoost is evaluated with walk-forward validation (rolling windows, not one fixed split) — this absorbs what was originally scoped as an LSTM validation task.

---

## 4. System architecture

```
Data (CGWB + IMD + ERA5, downloaded Week 1)
  → Preprocessing (interpolation + SARIMA gap-fill, MinMaxScaler, 10 features above)
  → Core ML: Linear Regression (trend) · Fuzzy Logic (Crisis Score) · Perceptron ANN (risk tier)
  → Advanced ML: XGBoost (500 trees, walk-forward validated)
  → Ensemble: AquaIQ Crisis Score = Linear Regression trend forecast + XGBoost risk + historical drought frequency
    (drought frequency = % of past months below district's 20th percentile GWL, computed
    entirely from CGWB's own history, no external drought dataset needed)
  → Crisis Score tiers: Safe 0–30 · Watch 31–60 · Warning 61–80 · Crisis 81–100
  → Flask REST API (5 endpoints) → React dashboard
```

**PostgreSQL tables (migrated from the originally-planned SQLite):** `raw_data`, `features`, `predictions`, `crisis_scores` — `shap_values` dropped along with SHAP.

**Flask API endpoints (5, down from 6):** `/predict/{district_id}` · `/district/{district_id}` · `/history/{district_id}` · `/alerts` · `/simulate` (POST) — `/shap/{district_id}` dropped along with SHAP.

**Frontend:** React + Leaflet.js (India choropleth map, GeoJSON from datameet.org) + Recharts (forecast timeline) + Tailwind

**Targets:** Linear Regression R² > 0.75 · Test coverage ≥ 70% · API response < 3s — the earlier LSTM target (Pearson r ≥ 0.85, RMSE < 2.5cm) no longer applies; Linear Regression's R² is now the accuracy bar for the forecast component.

---

## 5. Team division principle

**Explicitly equal — not divided by skill.** Earlier drafts split work by specialization (one person = ML, one = data, one = frontend); this was deliberately rejected and rebuilt so every workstream (data, core ML, advanced ML, API, dashboard, testing) rotates across all three people across the 14 weeks. Presentation duty at each evaluation also rotates three ways — every person presents a different section at every single evaluation, nobody is the permanent face of the project. If asked to modify task assignments, preserve this rotation principle unless explicitly told otherwise.

---

## 6. Timeline

| Phase | Date | Evaluator | Marks | Status |
|---|---|---|---|---|
| Phase I | 17 Aug 2026 | Guide only | 50 | ✅ Done |
| Phase II | 02 Sep 2026 | Guide only | 50 | ✅ Done |
| Phase III | 30 Sep 2026 | Guide only | 50 | Upcoming |
| Phase IV | 12 Oct 2026 | Guide only | 50 | Upcoming |
| ESE | 02 Nov 2026 | Industry expert / Alumni | 100 | Upcoming |

*(Dates and evaluator types are confirmed from the official SPIT department email. The specific mark sub-breakdown per phase — e.g. how the 50 splits across criteria — was inferred from typical structure, not verified against the actual attached rubric PDF. Worth double-checking with the guide if it matters.)*

**Important:** the 14-week plan's week boundaries are **not** clean 7-day blocks — they're sized to land evaluations on the right week (Week 2 runs 9 days, Week 5 is only 2 days, Week 11 is 4 days). Always check the actual date range printed on each week's card in the HTML plan rather than assuming `(today − 01 Aug) / 7`.

Full week-by-week task breakdown (14 weeks, ~3 tasks/person/week) lives in the companion HTML file — attach `AquaIQ_ProjectPlan.html` alongside this brief if you need that level of detail. Weeks 7–8 were restructured on 10 Sep to drop LSTM/SHAP work and fold in preprocessing/core-ML/skeleton tasks that hadn't landed in the repo yet (see §8).

**Budget:** ~₹3,949 (Colab Pro + poster printing; everything else free/open-source). Note: the repo's own README says no paid compute is actually needed for the current model stack (XGBoost, Fuzzy Logic, Perceptron, Linear Regression all run fine on a laptop CPU) — hasn't been reconciled with this budget line, worth a quick check if it matters.

---

## 7. Files that exist already

- `AquaIQ_IEEE_Proposal_v2.docx` — IEEE-format project proposal
- `AquaIQ_SRS_IEEE830.docx` — full SRS, 24 pages, IEEE 830-1998 format
- `AquaIQ_SPIT_MiniProject.docx` — filled SPIT official title page
- `AquaIQ_ProjectPlan.html` — interactive 14-week plan, filterable by person, presentation rotation table
- GitHub repo: [github.com/Yasharthpoddar/AquaIQ](https://github.com/Yasharthpoddar/AquaIQ) — `data_ingestion/`, `db/`, `preprocessing/` (partial), `models/`, `api/` (skeletons only), plus validation notebooks and the syllabus PDF used to verify course-code mappings

Attach whichever of these are relevant to what you're working on next — this brief is the index, not a replacement.

---

## 8. Where things stand right now

As of 10 Sep 2026 (Week 7 of 14, 09–15 Sep):

- **Phase I and Phase II are both done.** Phase III (LSTM/XGBoost/ensemble/Flask, now XGBoost/ensemble/Flask) is 30 Sep.
- **Built and working in the repo:** ingestion scripts for all three data sources, PostgreSQL schema + init, district/GeoJSON validation.
- **Not yet in the repo,** even though the original plan had it landing by Week 6: the full preprocessing pipeline (only correlation analysis exists so far), all core/advanced ML model code (Linear Regression, Fuzzy Logic, Perceptron, XGBoost), the Flask app, the React dashboard, and tests. This may be sitting in local notebooks that haven't been pushed — worth checking before assuming it's a from-scratch build.
- **Because of that gap, Weeks 7–8 in the plan now carry more than they originally did** — they fold in the Week 4–6 backlog (preprocessing, Fuzzy Logic, Linear Regression, Perceptron, React/Flask skeletons) alongside the XGBoost + ensemble work that Phase III actually needs. Check the plan's own date ranges (see §6) rather than assuming a clean week count from 01 Aug.

When you resume, check the current date against the plan's actual week boundaries and orient from there.

---

## 9. How to use this in a new chat

Paste this whole file as your first message (or upload it), then just say what you need — "help me write the preprocessing pipeline for Week 7," "I'm stuck on the Flask /predict endpoint," "review my XGBoost walk-forward results," whatever it is. No need to re-explain the architecture, the dropped scope, or the team structure — it's all above.
