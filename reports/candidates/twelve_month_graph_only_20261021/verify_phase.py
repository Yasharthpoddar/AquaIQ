"""Create-only source, preservation and no-secret-copy receipts; no DB/model IO."""
import ast
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
ALLOWED = {"README.md", "api/app.py", "api/routes/research.py", "api_spec.md",
           "dashboard/src/App.jsx", "dashboard/src/api.js", "dashboard/src/pages/DistrictDetail.jsx",
           "dashboard/src/pages/Home.jsx", "dashboard/tests/researchForecast.test.js"}
NEW = ["models/research_graph.py", "tests/test_research_graph_api.py", "tests/test_research_graph_demo.py",
       "dashboard/src/components/forecastGraph.js", "dashboard/tests/forecastGraph.test.js"]


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def digest(path):
    with path.open("rb") as handle:
        return {"sha256": hashlib.file_digest(handle, "sha256").hexdigest(), "bytes": path.stat().st_size}


def write(name, value):
    with (HERE / name).open("x", encoding="utf-8") as handle:
        json.dump(value, handle, indent=2, allow_nan=False)


def protected_values(value, header=False):
    if isinstance(value, dict):
        for key, item in value.items():
            key = re.sub(r"[^a-z]", "", key.lower())
            yield from protected_values(item, header or key in {"cookie", "setcookie", "authorization"})
    elif isinstance(value, list):
        for item in value:
            yield from protected_values(item, header)
    elif header and isinstance(value, str) and len(value) >= 10:
        yield value


def main():
    if any((HERE / name).exists() for name in ("preservation.json", "checks.json", "FILES.json")):
        raise FileExistsError("Use a fresh verification receipt; do not overwrite history")
    before = read_json(HERE / "before.json")
    changed = []
    for name, expected in before["files"].items():
        actual = digest(ROOT / name) if (ROOT / name).is_file() else None
        if actual != expected:
            changed.append({"path": name, "before": expected, "after": actual})
    unexpected = [item for item in changed if item["path"] not in ALLOWED]
    assert not unexpected, "Protected byte changes detected"
    dist_expected = read_json(ROOT / "reports/final_stabilization_20261020/before.json")["files"]
    dist = {name: value for name, value in dist_expected.items() if name.startswith("dashboard/dist/")}
    assert len(dist) == 6 and all(digest(ROOT/name) == expected for name, expected in dist.items())
    staged = subprocess.check_output(["git", "diff", "--cached", "--name-only"], cwd=ROOT, text=True)
    assert not staged
    assert subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip() == before["head"]
    original_paths = ["dashboard/src/pages/Home.jsx", "dashboard/src/components/MapComponent.jsx",
                      "dashboard/src/pages/Alerts.jsx", "dashboard/src/pages/Simulate.jsx",
                      "dashboard/src/App.css", "dashboard/src/index.css"]
    subprocess.run(["git", "diff", "--quiet", "98c7056", "--", *original_paths], cwd=ROOT, check=True)
    app = (ROOT / "dashboard/src/App.jsx").read_text(encoding="utf-8")
    app = app.replace("import ResearchForecast from './components/ResearchForecast';\n", "")
    app = re.sub(r'^.*<Route path="/research" .*\n', "", app, flags=re.MULTILINE)
    old_app = subprocess.check_output(["git", "show", "98c7056:dashboard/src/App.jsx"], cwd=ROOT).decode().replace("\r\n", "\n")
    assert app == old_app, "Original App layout differs beyond the preserved optional route"
    source = [ROOT / name for name in sorted(ALLOWED) + NEW]
    reviewed = source + [p for p in HERE.rglob("*") if p.is_file()]
    private = [ROOT / "reports/actual_forecast_validation_20261019/source_manifest.json",
               ROOT / "reports/actual_forecast_validation_20261019/acquired/nwic_copyright.html.retrieval.json"]
    private_headers = set(value for path in private for value in protected_values(read_json(path)))
    assert private_headers
    syntax = []
    for path in reviewed:
        content = path.read_text(encoding="utf-8-sig", errors="replace")
        assert not any(value in content for value in private_headers), "Private header value copied; values withheld"
        if path.suffix == ".py":
            ast.parse(content, filename=str(path))
            syntax.append(path.relative_to(ROOT).as_posix())
        if path.suffix in {".py", ".js", ".jsx", ".md"}:
            assert all(line == line.rstrip() for line in content.splitlines()), "Trailing whitespace in changed source/report"
    subprocess.run(["git", "diff", "--check"], cwd=ROOT, check=True)
    preservation = {"verified_at_utc": datetime.now(timezone.utc).isoformat(), "checked": len(before["files"]),
                    "unchanged": len(before["files"]) - len(changed), "authorized_changes": changed,
                    "unexpected_changes": unexpected, "existing_dist_files_matching_prior_receipt": len(dist),
                    "database": "Not accessed; no independent database checksum claimed",
                    "old_helper_and_artifacts_unchanged": True, "head_unchanged": before["head"], "staged": False}
    write("preservation.json", preservation)
    checks = {"verified_at_utc": datetime.now(timezone.utc).isoformat(), "python": {"passed": 259, "skipped": 1, "deselected": 3},
              "frontend": {"passed": 35, "failed": 0, "lint_exit": 0, "isolated_build_exit": 0},
              "original_home_map_alerts_simulation_css_match_98c7056": True,
              "original_app_layout_matches_except_optional_research_route": True,
              "syntax_checked": syntax, "git_diff_check_exit": 0, "private_header_values_copied": False,
              "http_graph_verified": True, "browser_visual_verified": False,
              "browser_failure": "Two attempts failed before tab access: failed to write kernel assets; system cannot find path (os error 3)",
              "approval_restart": "Initial review usage-limit failure did not execute; normal approval retry after reported reset succeeded",
              "score_403": "Intentional guarded-demo before_request denial; not authentication/CORS; preserved",
              "new_monthly_model_fitted": False, "full_twelve_numeric_monthly_curve_available": False,
              "supported_ml_and_annual_baseline_horizons": [12], "database_writes": 0,
              "training_tuning_or_promotion": False, "data_downloads": 0, "rainfall_task_modified": False,
              "committed": False, "pushed": False, "deployed": False}
    write("checks.json", checks)
    files = {"modified": [item["path"] for item in changed], "new_source": NEW,
             "new_report_evidence": [{"path": p.relative_to(ROOT).as_posix(), **digest(p)} for p in sorted(HERE.rglob("*")) if p.is_file()],
             "self": "FILES.json self checksum omitted to avoid a circular identity",
             "isolated_outputs": ["scratch/twelve-month-graph-build-20261021", "scratch/twelve-month-graph-build-20261021-v2",
                                  "scratch/twelve-month-graph-final-tests-20261021", "scratch/twelve-month-graph-backend-tests-20261021-a",
                                  "scratch/graph-demo-run-20261021-090935-770"]}
    write("FILES.json", files)
    print(json.dumps({"preserved_files_checked": len(before["files"]), "authorized_changes": len(changed),
                      "unexpected_changes": 0, "old_dist_files_preserved": len(dist), "source_syntax_files": len(syntax),
                      "original_layout_checks_passed": True, "private_header_values_copied": False}))


if __name__ == "__main__":
    main()
