"""Create-only static receipts. No app/model imports, sockets, DB or .env reads."""
from datetime import datetime, timezone
import hashlib
from importlib import metadata
import json
from pathlib import Path
import re
import subprocess
import sys

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[1]
assert OUT == ROOT / "reports" / "visual_rehearsal_preservation_20261023_01"
TARGET = OUT / "provisioning_receipts.json"
if TARGET.exists():
    raise SystemExit("Refusing to replace an existing receipt")


def git(*args):
    return subprocess.run(["git", *args], cwd=ROOT, check=True, capture_output=True).stdout


def read_json(path):
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(value):
    return sha(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode())


tracked = set(git("ls-files", "-z").decode().split("\0"))
previous = read_json("reports/end_to_end_verification_20261022/api_source/source_asset_receipts.json")


def receipt(path, role, expected=None, prior=None):
    item = {"path": path, "role": role, "exists": (ROOT/path).is_file(), "tracked_in_index": path in tracked}
    in_head = subprocess.run(["git", "cat-file", "-e", "HEAD:"+path], cwd=ROOT, capture_output=True).returncode == 0
    item["tracked_in_head"] = in_head
    if item["exists"]:
        raw = (ROOT/path).read_bytes()
        item.update(bytes=len(raw), sha256=sha(raw))
        if in_head:
            blob = git("show", "HEAD:"+path)
            item.update(head_blob_sha256=sha(blob), working_bytes_equal_head=raw == blob,
                        matches_head_after_crlf_normalization=raw.replace(b"\r\n", b"\n") == blob.replace(b"\r\n", b"\n"))
        if expected is not None:
            item.update(expected_sha256=expected, matches_descriptor_sha256=sha(raw) == expected)
        if prior is not None:
            item.update(previous_receipt_sha256=prior, matches_previous_receipt_sha256=sha(raw) == prior)
    return item


sources = [receipt(p["path"], "source", prior=p.get("sha256")) for p in previous["sources"]]
additional = ["dashboard/src/App.jsx", "dashboard/src/App.css", "dashboard/src/index.css", "dashboard/src/main.jsx",
              "dashboard/src/components/MapComponent.jsx", "dashboard/src/pages/Alerts.jsx", "dashboard/src/districtMap.js",
              "dashboard/package-lock.json", "requirements.txt", "db/connection.py",
              "reports/end_to_end_verification_20261022/audit_server.py"]
sources.extend(receipt(p, "additional_source") for p in additional if p not in {s["path"] for s in sources})
assets = [receipt(p["path"], p["role"], p.get("expected_sha256"), p.get("sha256")) for p in previous["runtime_assets"]]

direct = read_json("research/twelve_month_app.json")
scenario = read_json("research/experimental_scenario_sources.json")
manifest = read_json(direct["manifest_path"])
card_path = str(Path(direct["manifest_path"]).parent / manifest["card_path"]).replace("\\", "/")
card = read_json(card_path)
descriptors = {
    "direct_contract_hash_matches": canonical(direct["contract"]) == direct["contract_sha256"],
    "direct_manifest_hash_matches": sha((ROOT/direct["manifest_path"]).read_bytes()) == direct["manifest_sha256"],
    "direct_manifest_contract_matches": manifest["contract_sha256"] == direct["contract_sha256"],
    "direct_scope": direct["contract"]["supported_district_ids"],
    "direct_generation": direct["contract"]["feature_generation_id"],
    "direct_allowed_use": direct["contract"]["allowed_use"],
    "scenario_canonical_config_hash": canonical(scenario),
    "scenario_hash_matches_source_pin": canonical(scenario) == "1f12ed7df01913dcd69fbe1a6a3369905fdad3c43a9d4385814e4efc775dd5a0",
    "scenario_generation": scenario["feature_generation_id"],
    "model_deserialization": False,
}
pointer_summaries = []
for path in ("models/checkpoints/aquaiq_xgb.json", "models/checkpoints/aquaiq_monthly_climate.json"):
    pointer = read_json(path)
    pointer_summaries.append({"pointer_path":path, **{key:pointer[key] for key in ("bundle_schema_version", "model_path", "card_path", "model_sha256", "card_sha256")}})

reference = git("rev-parse", "98c7056^{commit}").decode().strip()
continuity = []
for path in ("dashboard/src/App.css", "dashboard/src/index.css", "dashboard/src/components/MapComponent.jsx",
             "dashboard/src/districtMap.js", "dashboard/src/App.jsx", "dashboard/src/pages/Home.jsx",
             "dashboard/src/pages/Alerts.jsx", "dashboard/src/pages/Simulate.jsx", "dashboard/src/pages/DistrictDetail.jsx"):
    current = git("show", "HEAD:"+path)
    old = git("show", reference+":"+path)
    entry = {"path":path, "head_blob_sha256":sha(current), "reference_blob_sha256":sha(old), "head_equals_reference":current == old}
    if path.endswith("App.jsx"):
        nav = lambda raw: re.search(rb"<nav\b.*?</nav>", raw, re.DOTALL).group(0)
        entry["nav_markup_equal_reference"] = nav(current) == nav(old)
    if path.endswith("Home.jsx"):
        cards = lambda raw: re.search(rb'\{Object\.entries\(tierCounts\).*?\{\/\* Stats bar \*\/\}', raw, re.DOTALL).group(0)
        entry["tier_summary_card_markup_equal_reference"] = cards(current) == cards(old)
    continuity.append(entry)

python_dependencies = []
for line in (ROOT/"requirements.txt").read_text(encoding="utf-8").splitlines():
    line = line.strip()
    if not line or line.startswith("#"):
        continue
    requirement = line.split(";", 1)[0].strip()
    name, expected = requirement.split("==", 1)
    applies = not (name == "gunicorn" and sys.platform == "win32")
    try:
        actual = metadata.version(name)
    except metadata.PackageNotFoundError:
        actual = None
    python_dependencies.append({"name":name, "expected":expected, "installed":actual, "applies_to_this_platform":applies,
                                "installed_matches_requirement":actual == expected if applies else None})

package = read_json("dashboard/package.json")
node_dependencies = []
for group in ("dependencies", "devDependencies"):
    for name, constraint in package[group].items():
        path = ROOT/"dashboard/node_modules"/name/"package.json"
        info = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
        node_dependencies.append({"name":name, "group":group, "declared_constraint":constraint,
                                  "package_metadata_exists":path.is_file(), "installed_version":info.get("version")})
node_exe = Path("C:/Program Files/nodejs/node.exe")
node_version = subprocess.run([str(node_exe), "--version"], capture_output=True, check=True).stdout.decode().strip() if node_exe.is_file() else None

result = {
    "type":"static_read_only_provisioning_review", "collected_at_utc":datetime.now(timezone.utc).isoformat(),
    "head":git("rev-parse", "HEAD").decode().strip(), "branch":git("branch", "--show-current").decode().strip(),
    "tracked_status_porcelain":git("status", "--porcelain=v1", "--untracked-files=no").decode(),
    "activity":{"app_imports":False,"model_deserialization":False,"model_fitting":False,"http_requests":False,"db_connections":False,
                "network":False,"source_or_environment_modification":False,"env_contents_read":False,"docker_or_build":False},
    "sources":sources, "runtime_assets":assets, "descriptor_checks":descriptors, "model_pointers":pointer_summaries,
    "reference_commit":reference, "source_continuity":continuity,
    "runtime":{"python_executable":sys.executable,"python_version":sys.version,"python_dependencies":python_dependencies,
               "node_executable_exists":node_exe.is_file(),"node_version":node_version,"node_dependencies":node_dependencies,
               "vite_entry_exists":(ROOT/"dashboard/node_modules/vite/bin/vite.js").is_file(),
               "env_file_exists":(ROOT/".env").is_file(),"env_values_and_credentials_verified":False,
               "database_reachability_and_contents_verified":False},
    "limits":["Dependency distributions inspected as metadata only; DLL/import/runtime compatibility not exercised.",
              "Source continuity does not prove rendered appearance, browser interactions or responsive layout.",
              "Hashes prove local bytes and descriptor agreement, not predictive skill, source availability or scientific validity.",
              "External PostgreSQL role, permissions, data generation and complete score publication remain a serving prerequisite."]
}
with TARGET.open("x", encoding="utf-8", newline="\n") as handle:
    json.dump(result, handle, indent=2, allow_nan=False)
    handle.write("\n")
print(json.dumps({"receipt":str(TARGET), "head":result["head"], "tracked_clean":not result["tracked_status_porcelain"],
                  "sources":len(sources), "assets":len(assets), "assets_missing":[p["path"] for p in assets if not p["exists"]],
                  "assets_changed_from_previous":[p["path"] for p in assets if p.get("matches_previous_receipt_sha256") is False],
                  "asset_descriptor_mismatches":[p["path"] for p in assets if p.get("matches_descriptor_sha256") is False],
                  "source_head_mismatches":[p["path"] for p in sources if p.get("matches_head_after_crlf_normalization") is False],
                  "python_dependency_mismatches":[p for p in python_dependencies if p["installed_matches_requirement"] is False],
                  "source_continuity":continuity}, indent=2))
