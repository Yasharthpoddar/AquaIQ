# AquaIQ — Project Context Brief

*Paste or upload this file at the start of any new chat, then say what you want to work on next. This document exists so you don't have to re-explain decisions that already took several rounds to nail down — treat everything below as settled unless the person explicitly asks to revisit it.*

---

## 1. What this project is

**AquaIQ** — AI-powered groundwater depletion forecasting system for India's districts.

- **Who:** Yasharth (2024800092), Yash, Ayush — B.Tech CSE, Sardar Patel Institute of Technology (SPIT), Mumbai
- **What for:** TE Sem V Mini Project I, AY 2026–27 Odd Semester
- **Real-world hook:** Maps to Smart India Hackathon problem statement **SIH25068** (Ministry of Jal Shakti — Real-Time Groundwater Evaluation using DWLR Data)
- **One-line pitch:** Forecasts district-level groundwater depletion 6 months ahead using a two-layer ML system, outputs a 0–100 Crisis Score per district, served through a Flask API + React dashboard.

---

## 2. Already done — do not redo or re-litigate

| Artifact | Status |
|---|---|
| IEEE-format project proposal | ✅ Written and submitted |
| SRS (IEEE 830-1998 format) | ✅ Written and submitted |
| SPIT official title page | ✅ Filled and submitted |
| 14-week team project plan (HTML) | ✅ Built, verified, task-balanced |

Don't suggest rewriting these unless explicitly asked. If the person wants changes to the plan/architecture, edit forward from what's below — don't propose starting over.

---

## 3. Non-negotiable technical decisions

These took real back-and-forth to settle. Don't reintroduce dropped scope or re-derive from scratch.

> **⚠️ Open question — worth 2 minutes with the guide before 17 Aug.** The actual SPIT title page template (checked directly, not from memory) contains two constraints that don't fully agree:
> - The **student confirmation table** on the title page lists Sem I–V courses as acceptable, including CS301 and CS302.
> - The **faculty guide's certification line**, same document, says the project must align with "fundamental concepts covered during **Semesters I to IV only**."
> - **CS303** (used throughout the already-submitted SRS/proposal to justify Fuzzy Logic and Perceptron ANN as "core") doesn't appear in the title page's table at all — not a Sem I–IV issue, it's just never listed.
>
> This means the already-submitted SRS/proposal currently justify part of the "core, syllabus-safe" layer using a course (CS303) that isn't on SPIT's own printed list, and lean on CS301/CS302 which may or may not count depending on which of the two constraints above actually gets enforced. Worth asking the guide directly which reading is correct. If "Sem I–IV only" is enforced strictly, the safest fallback is to fold Fuzzy Logic, Perceptron ANN, CS301, and CS302 into the self-study/advanced framing too, and let the guaranteed-core layer rest on just AS202 + CS204 + CS205.

**Two-layer architecture, and why:**
- **Core layer** — must map only to SPIT Sem I–V courses: `AS202` (Python for Data Science), `CS205` (Statistical Methods), `CS303` (AI & Soft Computing — Fuzzy Logic + Perceptron/ANN, *not* deep learning), `CS204` (DBMS), `CS301` (Distributed Computing / client-server), `CS302` (Software Engineering).
- **Advanced layer** — LSTM, XGBoost, SHAP, PyTorch. Framed explicitly as a **self-study extension**, because these are genuinely Sem VI/VII content — verified against the actual SPIT syllabus PDF: XGBoost = CS307 (Sem VI), SHAP = CS424 (Sem VII), LSTM = CS321 (Sem VI). This split is what makes the project both syllabus-compliant *and* impressive at ESE.

**Data sources — exactly 3, nothing else:**
- CGWB (`india-wris.nrsc.gov.in`) — borewell groundwater level readings, ~15,000 wells
- IMD (`imdpune.gov.in`) — monthly district rainfall + 30-year climatological normal
- ERA5 (`cds.climate.copernicus.eu`) — temperature, evapotranspiration

**Explicitly dropped, do not bring back (unless the person asks to reopen this):** GRACE-FO, GLDAS, NDVI/MODIS (vegetation), irrigation_fraction, population_density. These were in an earlier draft but nothing ever sourced them — every downstream task depended on data nobody was tasked with downloading. CGWB direct well readings beat an indirect satellite proxy — *but only where CGWB has coverage*. Coverage isn't uniform across all 640+ districts (some remote/hilly districts have thin or zero well history). The fix for that is a **zone-level fallback** (below), not GRACE — GRACE's own resolution (~300km) wouldn't give real district-level signal there either, so reintroducing it wouldn't actually solve the gap.

**Zone-level fallback for thin-data districts** (built Week 8, schema already supports it): below `data_readiness_min_pct` (60%) in `config.yaml`, aggregate CGWB data across every district in the same `agro_climatic_zone` (from the Week 2 district master table) instead of training on that one district alone — same smoothing effect as a coarse regional estimate, zero new external source. If even the zone lacks enough history, show "insufficient data" honestly rather than fabricating a score. `crisis_scores.estimate_type` tracks which of the three (`district_level` / `zone_fallback` / `insufficient_data`) applies, so the dashboard can label it.

> **Known documentation mismatch:** the already-submitted SRS (FR-02) still lists the *old* 11-feature scope — `NDVI, irrigation_fraction, population_density, soil_moisture` — and still references the GRACE data gap, because that text was never touched when the pipeline was simplified (documentation was frozen, not editable). The actual build uses the clean 10-feature list below.
>
> **Decided:** vegetation, irrigation, soil type, population density, and rainwater-harvesting infrastructure are deliberately out of scope — not oversights. Adding any of them back means a new data source + new sourcing task + retrained LSTM/XGBoost with a changed input shape, which reopens exactly the fragility that was just fixed. The call was made explicitly: lean and fully working beats broad and half-finished for a 3-person Sem V project on a hard deadline. Don't reopen this unless the person explicitly asks to. The right home for these factors is a **Limitations & Future Work** section in the ESE report — name them explicitly, one line each on why they're excluded. That's a documentation task, not a build task, and it's actually a stronger engineering story than silently omitting them.
>
> **Two concrete quality upgrades worth doing within current scope** (both low-risk, no new data source):
> 1. The ensemble Crisis Score formula (LSTM + XGBoost + drought frequency) currently has unspecified weights — fit them on the validation set against the 2015–16/2018–19 drought backtests instead of eyeballing them. This is the softest part of the design and the most likely thing a sharp evaluator probes.
> 2. Use walk-forward validation for the LSTM instead of a single train/val/test split — cheap given the 2002–2024 span already downloaded, meaningfully strengthens the accuracy claims.

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

---

## 4. System architecture

```
Data (CGWB + IMD + ERA5, downloaded Week 1)
  → Preprocessing (interpolation + SARIMA gap-fill, MinMaxScaler, 10 features above)
  → Core ML: Linear Regression (trend) · Fuzzy Logic (Crisis Score) · Perceptron ANN (risk tier)
  → Advanced ML: PyTorch LSTM (3-layer, hidden=128, 4-head attention) · XGBoost (500 trees) + SHAP
  → Ensemble: AquaIQ Crisis Score = LSTM forecast + XGBoost risk + historical drought frequency
    (drought frequency = % of past months below district's 20th percentile GWL — computed
    entirely from CGWB's own history, no external drought dataset needed)
  → Crisis Score tiers: Safe 0–30 · Watch 31–60 · Warning 61–80 · Crisis 81–100
  → Flask REST API (6 endpoints) → React dashboard
```

**SQLite tables:** `districts` (with `agro_climatic_zone`, used for fallback), `raw_data`, `features`, `predictions`, `shap_values`, `crisis_scores` (carries `estimate_type`: district_level / zone_fallback / insufficient_data)

**Flask API endpoints:** `/predict/{district_id}` · `/district/{district_id}` · `/shap/{district_id}` · `/history/{district_id}` · `/alerts` · `/simulate` (POST)

**Frontend:** React + Leaflet.js (India choropleth map, GeoJSON from datameet.org) + Recharts (forecast timeline) + Tailwind

**Targets:** LSTM Pearson r ≥ 0.85, RMSE < 2.5cm · Linear Regression R² > 0.75 · Test coverage ≥ 70% · API response < 3s

---

## 5. Team division principle

**Explicitly equal — not divided by skill.** Earlier drafts split work by specialization (one person = ML, one = data, one = frontend); this was deliberately rejected and rebuilt so every workstream (data, core ML, advanced ML, API, dashboard, testing) rotates across all three people across the 14 weeks. Presentation duty at each evaluation also rotates three ways — every person presents a different section at every single evaluation, nobody is the permanent face of the project. If asked to modify task assignments, preserve this rotation principle unless explicitly told otherwise.

---

## 6. Timeline

| Phase | Date | Evaluator | Marks |
|---|---|---|---|
| Phase I | 17 Aug 2026 | Guide only | 50 |
| Phase II | 02 Sep 2026 | Guide only | 50 |
| Phase III | 30 Sep 2026 | Guide only | 50 |
| Phase IV | 12 Oct 2026 | Guide only | 50 |
| ESE | 02 Nov 2026 | Industry expert / Alumni | 100 |

*(Dates and evaluator types are confirmed from the official SPIT department email. The specific mark sub-breakdown per phase — e.g. how the 50 splits across criteria — was inferred from typical structure, not verified against the actual attached rubric PDF. Worth double-checking with the guide if it matters.)*

Full week-by-week task breakdown (14 weeks, 3 tasks/person/week, 42 tasks each) lives in the companion HTML file — attach `AquaIQ_ProjectPlan.html` alongside this brief if you need that level of detail.

**Budget:** ~₹850 (poster printing + misc; everything else free/open-source — including compute. LSTM is small enough (~500K params) to train on a normal laptop CPU in under an hour; no Colab Pro or paid GPU needed. The already-submitted proposal's budget table assumed Colab Pro (₹3,099) — turned out unnecessary, actual spend is lower, not a problem worth raising with the guide.

---

## 7. Files that exist already

- `AquaIQ_IEEE_Proposal_v2.docx` — IEEE-format project proposal
- `AquaIQ_SRS_IEEE830.docx` — full SRS, 24 pages, IEEE 830-1998 format
- `AquaIQ_SPIT_MiniProject.docx` — filled SPIT official title page
- `AquaIQ_ProjectPlan.html` — interactive 14-week plan, filterable by person, presentation rotation table

Attach whichever of these are relevant to what you're working on next — this brief is the index, not a replacement.

---

## 8. Where things stand right now

Today's date context: plan starts **01 Aug 2026**, Phase I evaluation is **17 Aug 2026**. Check the current date when you resume and orient to whichever week that falls in — Week 1 is dataset downloads + environment setup, Week 3 is Phase I eval.

---

## 9. How to use this in a new chat

Paste this whole file as your first message (or upload it), then just say what you need — "help me write the LSTM training code for Week 7," "I'm stuck on the Flask /predict endpoint," "review my SHAP output," whatever it is. No need to re-explain the architecture, the dropped scope, or the team structure — it's all above.
