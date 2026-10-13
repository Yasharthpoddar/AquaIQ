"""
AquaIQ -- Unified Pipeline Orchestrator (run_pipeline.py)
-----------------------------------------------------------
Executes the end-to-end groundwater depth forecasting & crisis pipeline:
  1. Ingest: canonical districts & CGWB chunked data
  2. Preprocess: continuous timeline & causal LOCF (<=3 mo)
  3. Features: physical feature engineering & monsoon deficit
  4. Train: purged walk-forward CV XGBoost model training
  5. Backtest: causal historical backtest & model card evaluation
  6. Score All: batch scoring for all 725 canonical districts

Usage:
  python scripts/run_pipeline.py --step all
  python scripts/run_pipeline.py --step score_all --as-of 2026-10-12
  python scripts/run_pipeline.py --step train --dry-run
"""

import argparse
import logging
import os
import sys
import time
from datetime import date
from pathlib import Path
from dotenv import load_dotenv
import warnings

warnings.filterwarnings("ignore", message=".*pandas only supports SQLAlchemy.*")
warnings.filterwarnings("ignore", category=UserWarning)

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("AquaIQ.Pipeline")


def step_ingest(dry_run: bool = False) -> bool:
    """Step 1: Data ingestion (districts, CGWB observations, and weather)."""
    logger.info("=== STEP 1: INGESTION ===")
    if dry_run:
        logger.info("[Dry Run] Would ingest canonical districts and CGWB observations.")
        return True

    try:
        from data_ingestion.ingest_cgwb import main as ingest_cgwb_main
        logger.info("Running canonical district and CGWB observation ingestion...")
        ingest_cgwb_main()

        from data_ingestion.ingest_imd_era5 import main as ingest_weather_main
        logger.info("Running IMD & ERA5 weather data ingestion...")
        ingest_weather_main([])
        return True
    except Exception as e:
        logger.error(f"Ingestion failed: {e}", exc_info=True)
        return False


def step_preprocess(dry_run: bool = False) -> bool:
    """Step 2: Causal preprocessing (continuous timeline + LOCF <= 3 mo)."""
    logger.info("=== STEP 2: PREPROCESSING ===")
    if dry_run:
        logger.info("[Dry Run] Would run continuous timeline and causal imputation.")
        return True

    try:
        from preprocessing.pipeline import main as preprocess_main
        logger.info("Running causal preprocessing pipeline...")
        preprocess_main([])
        return True
    except Exception as e:
        logger.error(f"Preprocessing failed: {e}", exc_info=True)
        return False


def step_features(dry_run: bool = False) -> bool:
    """Step 3: Physical feature store construction."""
    logger.info("=== STEP 3: FEATURE ENGINEERING ===")
    if dry_run:
        logger.info("[Dry Run] Would compute physical features and populate feature store.")
        return True

    try:
        from preprocessing.features import main as features_main
        logger.info("Running feature engineering pipeline...")
        features_main([])
        return True
    except Exception as e:
        logger.error(f"Feature engineering failed: {e}", exc_info=True)
        return False


def step_train(dry_run: bool = False) -> bool:
    """Step 4: Historical endpoint and climate-conditioned monthly model training."""
    logger.info("=== STEP 4: MODEL TRAINING ===")
    if dry_run:
        logger.info("[Dry Run] Would train the historical endpoint and monthly climate XGBoost models.")
        return True

    try:
        from models.xgboost_model import main as train_main
        logger.info("Training XGBoost model on observed targets...")
        train_main([])
        from models.climate_forecast import main as climate_train_main
        logger.info("Training monthly climate-conditioned XGBoost on observed changes...")
        climate_train_main([])
        return True
    except Exception as e:
        logger.error(f"Model training failed: {e}", exc_info=True)
        return False


def step_backtest(dry_run: bool = False) -> bool:
    """Step 5: Causal walk-forward backtest."""
    logger.info("=== STEP 5: HISTORICAL BACKTEST ===")
    if dry_run:
        logger.info("[Dry Run] Would execute historical walk-forward backtest.")
        return True

    try:
        from models.backtest import main as backtest_main
        logger.info("Running walk-forward backtest...")
        backtest_main([])
        return True
    except Exception as e:
        logger.error(f"Backtest failed: {e}", exc_info=True)
        return False


def step_score_all(as_of_date: date, dry_run: bool = False) -> bool:
    """Step 6: Batch scoring of all 725 canonical districts."""
    logger.info(f"=== STEP 6: BATCH CRISIS SCORING (as-of {as_of_date}) ===")
    if dry_run:
        logger.info(f"[Dry Run] Would score all canonical districts as-of {as_of_date}.")
        return True

    try:
        from models.score_all import score_all_districts
        logger.info("Computing crisis scores and updating crisis_scores table...")
        n_scored = score_all_districts(as_of_date)
        logger.info(f"Successfully batch scored {n_scored} canonical districts.")
        return True
    except Exception as e:
        logger.error(f"Batch scoring failed: {e}", exc_info=True)
        return False


def main():
    parser = argparse.ArgumentParser(description="AquaIQ End-to-End Pipeline Orchestrator")
    parser.add_argument(
        "--step",
        choices=["all", "ingest", "preprocess", "features", "train", "backtest", "score_all"],
        default="all",
        help="Pipeline step to execute (default: all)",
    )
    parser.add_argument(
        "--as-of",
        type=str,
        default=None,
        help="As-of evaluation date for batch scoring (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simulate execution without modifying database or disk",
    )

    args = parser.parse_args()
    as_of = date.fromisoformat(args.as_of) if args.as_of else date.today()

    start_time = time.time()
    logger.info(f"Starting AquaIQ pipeline orchestrator (step={args.step}, as_of={as_of}, dry_run={args.dry_run})")

    steps_to_run = []
    if args.step == "all":
        steps_to_run = [
            ("ingest", lambda: step_ingest(args.dry_run)),
            ("preprocess", lambda: step_preprocess(args.dry_run)),
            ("features", lambda: step_features(args.dry_run)),
            ("train", lambda: step_train(args.dry_run)),
            ("backtest", lambda: step_backtest(args.dry_run)),
            ("score_all", lambda: step_score_all(as_of, args.dry_run)),
        ]
    elif args.step == "ingest":
        steps_to_run = [("ingest", lambda: step_ingest(args.dry_run))]
    elif args.step == "preprocess":
        steps_to_run = [("preprocess", lambda: step_preprocess(args.dry_run))]
    elif args.step == "features":
        steps_to_run = [("features", lambda: step_features(args.dry_run))]
    elif args.step == "train":
        steps_to_run = [("train", lambda: step_train(args.dry_run))]
    elif args.step == "backtest":
        steps_to_run = [("backtest", lambda: step_backtest(args.dry_run))]
    elif args.step == "score_all":
        steps_to_run = [("score_all", lambda: step_score_all(as_of, args.dry_run))]

    success = True
    for step_name, step_fn in steps_to_run:
        step_start = time.time()
        ok = step_fn()
        elapsed = time.time() - step_start
        if not ok:
            logger.error(f"Pipeline ABORTED at step '{step_name}' after {elapsed:.1f}s")
            success = False
            break
        logger.info(f"Completed step '{step_name}' in {elapsed:.1f}s")

    total_elapsed = time.time() - start_time
    if success:
        logger.info(f"AquaIQ pipeline run SUCCEEDED in {total_elapsed:.1f}s")
        sys.exit(0)
    else:
        logger.error(f"AquaIQ pipeline run FAILED in {total_elapsed:.1f}s")
        sys.exit(1)


if __name__ == "__main__":
    main()
