"""Static audit receipts only: stdlib reads/hashes; no application imports or IO services."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[2]


def git(*args):
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, check=True).stdout


tracked = set(git("ls-files", "-z").decode().split("\0"))


def read_json(relative):
    return json.loads((ROOT / relative).read_text(encoding="utf-8"))


def receipt(relative, role):
    path = ROOT / relative
    exists = path.is_file()
    value = {"path": relative, "role": role, "exists_locally": exists,
             "tracked_in_head": relative in tracked}
    if exists:
        raw = path.read_bytes()
        value.update(bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())
        if relative in tracked:
            original = git("show", "HEAD:" + relative)
            value["working_bytes_match_head"] = raw == original
            value["content_matches_head_after_crlf_normalization"] = raw.replace(b"\r\n", b"\n") == original.replace(b"\r\n", b"\n")
            value["head_blob_sha256"] = hashlib.sha256(original).hexdigest()
    return value


sources = ["api/app.py", "api/contracts.py", "api/district_resolver.py",
           *["api/routes/" + n + ".py" for n in ("scores", "research", "predict", "district", "history", "alerts", "simulate", "health")],
           *["models/" + n + ".py" for n in ("research_forecast", "research_graph", "experimental_scenario", "scenario_sources", "monthly_projection", "climate_forecast", "climate_inputs", "ensemble", "research_horizon", "xgboost_model", "ann_classifier", "tiers")],
           "preprocessing/pipeline.py", "preprocessing/features.py", "config.yaml",
           "research/twelve_month_app.json", "research/experimental_scenario_sources.json",
           "dashboard/src/api.js", "dashboard/src/components/DistrictForecastGraph.jsx",
           "dashboard/src/components/experimentalScenarioContract.js", "dashboard/src/components/forecastGraph.js",
           "dashboard/src/components/researchForecastContract.js", "dashboard/src/pages/DistrictDetail.jsx",
           "dashboard/src/pages/Home.jsx", "dashboard/src/components/ExperimentalScenario.jsx",
           "dashboard/src/components/ForecastGraphPanel.jsx", "dashboard/src/pages/Simulate.jsx",
           "dashboard/vite.config.js", "dashboard/package.json", "deploy/Dockerfile.api",
           "deploy/Dockerfile.web", "deploy/compose.yaml", "deploy/serve.py", ".dockerignore", ".gitignore",
           "api_spec.md", "README.md", "deploy/README.md",
           "reports/candidates/twelve_month_graph_only_20261021/demo_server.py"]
source_receipts = [receipt(p, "audited_source") for p in sources]

assets = []
config = read_json("research/twelve_month_app.json")
manifest_path = config["manifest_path"]
assets.append(receipt(manifest_path, "direct_research_manifest"))
manifest = read_json(manifest_path)
base = Path(manifest_path).parent
for prefix in ("card", "snapshot", "input_provenance", "provenance"):
    relative = (base / manifest[prefix + "_path"]).as_posix()
    item = receipt(relative, "direct_research_" + prefix)
    item["expected_sha256"] = manifest[prefix + "_sha256"]
    item["hash_matches_descriptor"] = item.get("sha256") == item["expected_sha256"]
    assets.append(item)
card_path = (base / manifest["card_path"]).as_posix()
card = read_json(card_path)
item = receipt((base / card["model_path"]).as_posix(), "direct_research_model")
item["expected_sha256"] = card["model_sha256"]
item["hash_matches_descriptor"] = item.get("sha256") == item["expected_sha256"]
assets.append(item)
assets[0]["expected_sha256"] = config["manifest_sha256"]
assets[0]["hash_matches_descriptor"] = assets[0].get("sha256") == config["manifest_sha256"]

scenario = read_json("research/experimental_scenario_sources.json")
for key in ("feature_csv", "feature_manifest", "district_crosswalk"):
    item = receipt(scenario[key + "_path"], "national_scenario_" + key)
    item["expected_sha256"] = scenario[key + "_sha256"]
    item["hash_matches_descriptor"] = item.get("sha256") == item["expected_sha256"]
    assets.append(item)

summaries = {}
summary_keys = ("version", "family", "research_only", "allowed_use", "horizon_months", "horizons_months",
                "features", "feature_schema_sha256", "units", "feature_units", "feature_generation_id",
                "train_target_cutoff", "max_train_target_date", "max_train_origin", "supported_district_ids",
                "model_sha256", "shadow_artifact_approved", "validation_assessment")
summaries["direct_research"] = {k: card[k] for k in summary_keys if k in card}
for label, pointer_path in (("legacy_six_month", "models/checkpoints/aquaiq_xgb.json"),
                            ("monthly_climate", "models/checkpoints/aquaiq_monthly_climate.json")):
    assets.append(receipt(pointer_path, label + "_pointer"))
    pointer = read_json(pointer_path)
    for key in ("model", "card"):
        relative = (Path(pointer_path).parent / pointer[key + "_path"]).as_posix()
        item = receipt(relative, label + "_" + key)
        item["expected_sha256"] = pointer[key + "_sha256"]
        item["hash_matches_descriptor"] = item.get("sha256") == item["expected_sha256"]
        assets.append(item)
        if key == "card":
            loaded = read_json(relative)
            summaries[label] = {k: loaded[k] for k in summary_keys if k in loaded}

for relative, role in (("data/raw/india_districts.geojson", "legacy_raw_boundary"),
                       ("dashboard/public/india_districts.geojson", "frontend_map_boundary")):
    assets.append(receipt(relative, role))

result = {"audit_type": "static_read_only_source_and_asset_inventory", "collected_at_utc": datetime.now(timezone.utc).isoformat(),
          "head": git("rev-parse", "HEAD").decode().strip(), "branch": git("branch", "--show-current").decode().strip(),
          "activity": {"application_imports": False, "model_fit": False, "model_load": False,
                       "network": False, "database_connection": False, "source_modification": False,
                       "environment_or_cookie_contents_read": False},
          "sources": source_receipts, "runtime_assets": assets, "safe_model_card_summaries": summaries}
(OUT / "source_asset_receipts.json").write_text(json.dumps(result, indent=2, allow_nan=False) + "\n", encoding="utf-8")
print(json.dumps({"head": result["head"], "sources": len(source_receipts), "runtime_assets": len(assets),
                  "untracked_runtime_assets": sum(not p["tracked_in_head"] for p in assets),
                  "missing_local_runtime_assets": [p["path"] for p in assets if not p["exists_locally"]],
                  "source_content_mismatches_from_head": [p["path"] for p in source_receipts if p.get("content_matches_head_after_crlf_normalization") is False],
                  "receipt": str(OUT / "source_asset_receipts.json")}, indent=2))
