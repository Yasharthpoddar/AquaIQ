"""
AquaIQ — Perceptron ANN Classifier (Week 5, Yasharth)
-------------------------------------------------------
MLPClassifier that predicts crisis tier (Safe/Watch/Warning/Crisis)
directly from the 10-feature vector.

Architecture (from project plan):
  Input layer:  10 features
  Hidden layer: 64 neurons, ReLU activation
  Output layer: 4 classes (Safe/Watch/Warning/Crisis), softmax

Training labels come from the Fuzzy Logic FIS output (fuzzy_logic.py).
This is a contemporaneous FIS imitation exercise, not independently validated
crisis ground truth or a future groundwater forecast.

Course mapping: CS303 — AI & Soft Computing (ANN module).

Metrics: accuracy, precision, recall, F1-score per class, confusion matrix.

Run:
    python models/ann_classifier.py
    python models/ann_classifier.py --epochs 500
"""

import argparse
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import yaml
from dotenv import load_dotenv
from sklearn.neural_network import MLPClassifier
from sklearn.metrics import (
    accuracy_score,
    classification_report,
    confusion_matrix,
)
from sklearn.preprocessing import LabelEncoder, StandardScaler

ROOT = Path(__file__).parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from models import xgboost_model as forecast
load_dotenv(ROOT / ".env")

with open(ROOT / "config.yaml") as f:
    CONFIG = yaml.safe_load(f)

PROCESSED_DIR = ROOT / CONFIG["paths"]["data_processed"]
TRAIN_END = pd.Timestamp(CONFIG["date_range"]["train_end"])
TEST_START = pd.Timestamp(CONFIG["date_range"]["test_start"])

TIER_ORDER = ["Safe", "Watch", "Warning", "Crisis"]


def load_features() -> pd.DataFrame:
    """Use verified units, calendar lags and explicit observation provenance."""
    return forecast.load_feature_matrix()


def generate_fuzzy_labels(df: pd.DataFrame) -> pd.Series:
    """
    Generate crisis tier labels using the Fuzzy Logic FIS.
    Uses monsoon_deficit_pct as rainfall_deficit proxy and
    GWL depletion rate as the depletion_rate input.
    """
    from models.fuzzy_logic import build_fuzzy_system, compute_crisis_score

    sim, *_ = build_fuzzy_system()

    labels = []
    for _, row in df.iterrows():
        # Map features to FIS inputs
        # rainfall_deficit: use monsoon_deficit_pct if available, else estimate
        if "monsoon_deficit_pct" in df.columns and pd.notna(row.get("monsoon_deficit_pct")):
            # Convert: positive deficit = bad, so negate
            rd = max(0, min(100, -row["monsoon_deficit_pct"]))
        else:
            labels.append(None)
            continue

        # depletion_rate: GWL change rate. Higher GWL_current = deeper = worse.
        if pd.notna(row.get("gwl_lag_6mo")) and pd.notna(row.get("gwl_current")):
            # FIS accepts centimetres/year: six-month metres * 2 * 100.
            depl = min(15, max(0, row["gwl_current"] - row["gwl_lag_6mo"]) * 200)
        else:
            labels.append(None)
            continue

        score, tier = compute_crisis_score(sim, rd, depl)
        labels.append(tier)

    return pd.Series(labels, index=df.index)


def train_ann(df: pd.DataFrame, max_iter: int = 300):
    """
    Train the Perceptron ANN classifier.
    Architecture: [10, 64, 4] — Input(10) → Hidden(64, ReLU) → Output(4)
    """
    print("  Generating crisis tier labels from Fuzzy Logic FIS...")
    df = forecast.encode_crop_season(df)
    df["tier"] = generate_fuzzy_labels(df)
    df = df.dropna(subset=["tier"])

    # Feature columns
    feature_cols = forecast.get_feature_columns(df)

    print(f"  Features ({len(feature_cols)}): {feature_cols}")
    print(f"  Class distribution:")
    for tier in TIER_ORDER:
        count = (df["tier"] == tier).sum()
        print(f"    {tier}: {count} ({count/len(df)*100:.1f}%)")

    # Encode labels
    le = LabelEncoder()
    le.fit(TIER_ORDER)
    df["label"] = le.transform(df["tier"])

    # Temporal split
    df["date"] = pd.to_datetime(df["date"])
    train = df[df["date"] <= TRAIN_END].copy()
    test = df[df["date"] >= TEST_START].copy()

    if len(test) < 10 or len(train) < 50:
        raise ValueError("Insufficient train/final-test samples for the FIS imitation evaluation.")

    print(f"\n  Train: {len(train):,} samples | Test: {len(test):,} samples")

    if len(train) < 50:
        print("WARNING: Very small training set. Results may be unreliable.")

    # Scale features
    scaler = StandardScaler()
    # Missing signals do not mean zero rainfall/depth. Restrict this auxiliary
    # classifier to complete rows; the primary XGBoost handles missing values.
    train = train.dropna(subset=feature_cols)
    test = test.dropna(subset=feature_cols)
    if len(test) < 10 or len(train) < 50:
        raise ValueError("Insufficient complete samples for the FIS imitation evaluation.")
    X_train = scaler.fit_transform(train[feature_cols])
    X_test = scaler.transform(test[feature_cols])
    y_train = train["label"].values
    y_test = test["label"].values

    # Train MLP
    # Architecture: input (n_features) → 64 (ReLU) → 4 (softmax/output)
    mlp = MLPClassifier(
        hidden_layer_sizes=(64,),
        activation="relu",
        solver="adam",
        max_iter=max_iter,
        random_state=42,
        # sklearn's early_stopping=True reserves a random validation subset.
        # This auxiliary imitation model uses a fixed iteration budget and its
        # existing chronological final test, without a random time-series split.
        early_stopping=False,
        n_iter_no_change=20,
        verbose=False,
    )

    print(f"\n  Training MLPClassifier (hidden=[64], ReLU, Adam, max_iter={max_iter})...")
    mlp.fit(X_train, y_train)
    print(f"  Converged in {mlp.n_iter_} iterations")

    # Predict
    y_pred = mlp.predict(X_test)

    # Metrics
    acc = accuracy_score(y_test, y_pred)
    print(f"\n  Accuracy: {acc:.4f} ({acc*100:.1f}%)")

    # Classification report
    target_names = le.inverse_transform(sorted(np.unique(np.concatenate([y_test, y_pred]))))
    print(f"\n  Classification Report:")
    report = classification_report(y_test, y_pred, target_names=target_names, zero_division=0)
    print(report)

    # Confusion matrix
    cm = confusion_matrix(y_test, y_pred)
    print(f"  Confusion Matrix:")
    print(f"  {'':>10s}", end="")
    for name in target_names:
        print(f"  {name:>8s}", end="")
    print()
    for i, name in enumerate(target_names):
        print(f"  {name:>10s}", end="")
        for j in range(len(target_names)):
            print(f"  {cm[i][j]:>8d}", end="")
        print()

    return mlp, scaler, le, acc


def save_results(acc: float, report_path: Path):
    """Save ANN evaluation results."""
    os.makedirs(report_path.parent, exist_ok=True)
    with open(report_path, "w") as f:
        f.write(f"ANN FIS imitation agreement (not observed crisis accuracy): {acc:.4f}\n")
    print(f"\n  Results saved to {report_path}")


def main(argv=None):
    parser = argparse.ArgumentParser(description="AquaIQ Perceptron ANN Classifier")
    parser.add_argument("--epochs", type=int, default=300, help="Max training iterations")
    args = parser.parse_args(argv)

    print("AquaIQ -- Perceptron ANN Classifier\n")

    print("[1/3] Loading features...")
    df = load_features()
    print(f"  Loaded {len(df):,} rows, {df['district_id'].nunique()} districts")

    print("\n[2/3] Training ANN...")
    mlp, scaler, le, acc = train_ann(df, max_iter=args.epochs)

    print("\n[3/3] Saving...")
    save_results(acc, PROCESSED_DIR / "ann_results.txt")

    print("\nDone.")


if __name__ == "__main__":
    main()
