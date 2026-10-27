# Historical accuracy experiments

The candidate-only workflow audits the already inspected serving diagnostic,
then compares seventeen prespecified recipes and two simple baselines using
nested chronological development folds. It does not promote models, write
database forecasts, alter serving dispatch, or recalibrate intervals.

The executed findings and limitations are in
[`reports/accuracy_experiments_20261027/REPORT.md`](../reports/accuracy_experiments_20261027/REPORT.md).
The exact ignored V3 data and original baseline assets are required, as described
in [the release reproduction guide](FINAL_RELEASE_REPRODUCTION.md).

Use fresh output paths for each replay. From the repository root:

```powershell
.\venv\Scripts\python.exe -u -B -m scripts.audit_accuracy_baselines --output reports/accuracy_experiments_replay/audit
.\venv\Scripts\python.exe -u -B -m scripts.run_accuracy_experiments prepare --audit reports/accuracy_experiments_replay/audit --protocol reports/accuracy_experiments_replay/protocol.json
.\venv\Scripts\python.exe -u -B -m scripts.run_accuracy_experiments run --protocol reports/accuracy_experiments_replay/protocol.json --output reports/accuracy_experiments_replay/run_replay
.\venv\Scripts\python.exe -B -m pytest --integration --basetemp scratch/pytest-accuracy-replay -q
npm.cmd --prefix dashboard test
npm.cmd --prefix dashboard run lint
npm.cmd --prefix dashboard run build
```

`prepare` requires a successful audit and seals the training source, candidate
recipes, dependencies, fold rules, data fingerprint and ranking rule before any
new fitting. `run` refuses changed code, changed inputs or an existing output
directory. A stopped run remains an incomplete record; use a new run path.
Per-fold models, cards, traces and predictions remain local under the report
directory. A new final learner, when selected strictly from the inner folds, is
stored under a new `models/artifacts/accuracy_experiments_20261027_*/` directory.

Use the explicit isolated loader for these research artifacts:

```python
from models.accuracy_challengers import load
model, card = load("path/to/new/checkpoint.json")
# pairs must contain the seventeen ordered serving features and observed anchors.
predicted_depths_m_bgl = model.depth(pairs)
```

The loader checks hashes, feature order and exact horizon coverage. Ridge stores
train-fitted transforms as JSON, without executable pickle artifacts. A trend
artifact requires its source frame explicitly because inference consumes the
observed origin history. These checkpoints intentionally use a separate format
and cannot replace the active production pointer.

The primary statistic averages district-macro MAE across inner folds on a common
seasonal-eligible population. Full-population case and macro MAE, RMSE, signed
error and coverage are also published. A district with one eligible case is
included in the macro average, consistent with the prior protocol; it does not
become a supported district-level finding. Subgroup interpretation requires at
least thirty cases across ten districts.

Each validation origin can contribute all twelve horizons through the following
December. Thus the last outer origin cohorts are 2020 and 2021, with complete
target windows ending before 2023. Inner target windows must end before their
outer training cutoff. All new development targets precede 2023. The frozen artifact was trained through
2019 and is a valid temporal reference only on later origins. The current
experimental artifact was trained through January 2025; its predictions on the
new historical folds are contaminated and are never selection evidence. Refitted
production/current recipes provide comparable chronological controls.

Outer folds evaluate a selection procedure. Showing every recipe on outer folds
is a secondary exploratory comparison and must not be used to pick another
winner. January 2026 labels and the old 2023/2024 folds remain historical
references. Historical publication times are unknown, and the controlled
observed-origin experiment does not validate stale estimated serving anchors.
Fresh prospective observations and complete original promotion gates remain
necessary before any production change.
