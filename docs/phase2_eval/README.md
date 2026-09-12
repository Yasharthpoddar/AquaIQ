# Phase II Mini Project Evaluation — AquaIQ

**Date:** 10 September 2026  
**Marks:** 25  
**Team:** Yasharth (2024800092), Yash, Ayush

---

## Evaluation Components

| # | Component | Marks | Document |
|---|-----------|-------|----------|
| P1 | Software Requirements Specification | 10 | [SRS_AquaIQ.md](SRS_AquaIQ.md) |
| P2 | UML Diagrams | 5 | [UML_Diagrams.md](UML_Diagrams.md) |
| P3 | Design of Algorithm / Prototype | 5 | [Algorithm_Design.md](Algorithm_Design.md) |
| P4 | Presentation | 5 | Slides (live demo of working prototype) |

---

## Quick Reference for Evaluators

### P1 — SRS Highlights
- IEEE 830-1998 format
- 14 functional requirements (FR-01 to FR-14) with input/processing/output
- 6 non-functional requirement categories (Performance, Accuracy, Availability, Security, Reproducibility, Testability)
- Full feature traceability matrix (10 features → 3 data sources)
- Course subject mapping (6 courses)

### P2 — UML Diagrams (7 diagrams)
1. **Use Case Diagram** — 3 actors, 9 use cases
2. **Class Diagram** — 5 entity classes + 6 service classes
3. **Sequence Diagram: Prediction** — User → React → Flask → DB → XGBoost → FIS
4. **Sequence Diagram: Simulation** — Policy maker → sliders → FIS re-computation
5. **Activity Diagram** — Full data pipeline flow (download → ingest → preprocess → train → score)
6. **Component Diagram** — 5-layer architecture (Data → Processing → Model → API → Presentation)
7. **ER Diagram** — 5 PostgreSQL tables with relationships

### P3 — Algorithm Design Highlights
- Pseudocode for all 7 algorithms with complexity analysis
- Preprocessing: 3-stage pipeline (interpolation → SARIMA → MinMaxScaler)
- Fuzzy Logic: 9-rule Mamdani FIS with membership function definitions
- XGBoost: Walk-forward temporal validation (no data leakage)
- Ensemble: Weighted combination (LR 25% + XGBoost 50% + Drought 25%)
- Prototype status: 15/15 components working, 17/17 unit tests passing

### P4 — Presentation / Demo Points
- **Live demo of Flask API** — `python -m api.app` → hit all 5 endpoints
- **Fuzzy Logic demo** — `python models/fuzzy_logic.py --demo` → shows Safe→Crisis mapping
- **Unit tests** — `pytest tests/test_preprocessing.py -v` → 17/17 pass
- **React dashboard build** — `cd dashboard && npm run build` → builds in ~2s
- **Policy recommendations** — `python models/policy_recommendations.py` → 4-tier alert table

---

## Repository Structure (relevant files)

```
AquaIQ/
├── api/                          # Flask API (Week 6)
│   ├── app.py                    # App factory + blueprint registration
│   └── routes/                   # 5 endpoint blueprints
│       ├── predict.py
│       ├── history.py
│       ├── alerts.py
│       ├── simulate.py
│       └── health.py
├── dashboard/                    # React + Vite (Week 4-5)
│   └── src/
│       ├── components/MapComponent.jsx   # Leaflet choropleth
│       └── pages/                        # 4 pages
├── data_ingestion/               # Data loading scripts
│   ├── ingest_cgwb.py
│   ├── ingest_imd_era5.py
│   ├── enrich_districts.py
│   └── data_completeness.py
├── preprocessing/                # Pipeline + features
│   ├── pipeline.py               # 3-stage preprocessing
│   └── features.py               # 10-feature engineering
├── models/                       # ML models
│   ├── linear_regression.py
│   ├── ann_classifier.py
│   ├── xgboost_model.py
│   ├── xgboost_gridsearch.py
│   ├── fuzzy_logic.py
│   ├── statistical_tests.py
│   ├── policy_recommendations.py
│   └── plot_predictions.py
├── db/                           # PostgreSQL
│   ├── schema.sql
│   └── init_db.py
├── tests/                        # pytest
│   ├── smoke_test_data.py
│   └── test_preprocessing.py
├── docs/
│   └── phase2_eval/              # ← YOU ARE HERE
│       ├── README.md
│       ├── SRS_AquaIQ.md
│       ├── UML_Diagrams.md
│       └── Algorithm_Design.md
├── config.yaml
├── requirements.txt
└── README.md
```
