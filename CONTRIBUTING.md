# Contributing to AquaIQ

This document outlines the Git branching strategy and commit conventions for the AquaIQ team (Yasharth, Yash, Ayush). This maps to the Phase III, P3 Evaluation Criteria (Branching & commit conventions).

## 1. Branching Strategy: GitFlow (Simplified)

We follow a simplified GitFlow model tailored for a 3-person team with weekly rotating task ownership:

- **`main`**: The stable source of truth. Code here should always be deployable and fully tested. We merge into `main` only at major milestones (e.g., End of Phase II, Phase III submission).
- **`develop`**: The integration branch. All completed features are merged here first. When we're ready for a milestone release, `develop` is merged into `main`.
- **`feature/*`**: Short-lived feature branches created off `develop`. Used for all new work (e.g., `feature/xgboost-walkforward`, `feature/api-integration`).
  
**Merge Convention:** 
When merging a `feature/*` branch into `develop` or `develop` into `main`, we use the `--no-ff` (no fast-forward) flag to preserve the explicit merge commit and historical context of the branch.

## 2. Commit Conventions

We strictly follow [Conventional Commits](https://www.conventionalcommits.org/). Every commit message should be structured as follows:

```
<type>[optional scope]: <description>
```

### Allowed Types:
- **`feat:`** A new feature (e.g., a new endpoint, a new model).
- **`fix:`** A bug fix (e.g., fixing ingestion crashes or missing data).
- **`docs:`** Documentation changes (e.g., updating README, adding SRS).
- **`test:`** Adding or modifying tests (e.g., PyTest coverage).
- **`chore:`** Routine tasks, dependency updates, or configuration changes (e.g., saving weights to config.yaml).
- **`refactor:`** Code changes that neither fix a bug nor add a feature.

### Examples:
- `feat(models): implement true walk-forward validation for XGBoost`
- `fix(ingestion): populate districts table with all 640+ GeoJSON districts`
- `test(api): add pytest coverage for all 6 API endpoints`
- `docs: completely rewrite README.md to reflect current 10-feature XGBoost scope`
