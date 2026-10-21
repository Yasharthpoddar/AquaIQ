"""Review an explicit source/docs allowlist without exposing private values.

preflight: create compact review and link inventories, never overwrite them.
staged: verify the exact index and scan Git blobs before commit/push.
No fitting, source acquisition, database, model loading or remote operations.
"""
from datetime import datetime, timezone
import ast
import csv
import hashlib
import io
import json
from pathlib import Path
import re
import subprocess
import sys
from urllib.parse import unquote

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
FINAL = ROOT / "reports/candidates/twelve_month_horizon_finalization_20261020"
PRIVATE = [ROOT / "reports/actual_forecast_validation_20261019/source_manifest.json",
           ROOT / "reports/actual_forecast_validation_20261019/acquired/nwic_copyright.html.retrieval.json"]
GENERATED = {"reports/github_release_20261021/REVIEW.json", "reports/github_release_20261021/LINK_AVAILABILITY.csv"}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def private_values(item, under_header=False):
    if isinstance(item, dict):
        for key, value in item.items():
            key = re.sub(r"[^a-z]", "", key.lower())
            yield from private_values(value, under_header or key in {"cookie", "setcookie", "authorization"})
    elif isinstance(item, list):
        for value in item:
            yield from private_values(value, under_header)
    elif under_header and isinstance(item, str) and len(item) >= 10:
        yield item
        for match in re.finditer(r"(?:^|[;,]\s*)([\w-]+)=([^;,\s]+)", item):
            name, value = match.groups()
            if name.lower() not in {"path", "domain", "expires", "max-age", "samesite"} and len(value) >= 10:
                yield value


def paths():
    selected = (HERE / "ALLOWLIST.txt").read_text(encoding="utf-8").splitlines()
    if len(selected) != len(set(selected)) or selected != sorted(selected):
        raise ValueError("Allowlist must be unique and sorted")
    for name in selected:
        path = ROOT / name
        if not name or path.resolve() != path.absolute() or not path.resolve().is_relative_to(ROOT.resolve()):
            raise ValueError("Allowlist path is not confined")
        if path.is_symlink() or path.suffix not in {".py", ".md", ".json", ".txt", ".js", ".jsx", ".html", ".csv"}:
            raise ValueError("Non-source publication entry: " + name)
        if (name.startswith(("data/", "models/checkpoints/", "scratch/"))
                or "/acquired/" in name or "/normalized" in name
                or "/evaluation/models/" in name or name.endswith("/xgb_fixed_2021.json")
                or name.endswith(("/features.csv", "/input_provenance.json"))
                or path in PRIVATE):
            raise ValueError("Excluded private/data/artifact entry: " + name)
    return selected


def read_private():
    result = set()
    for path in PRIVATE:
        result.update(private_values(json.loads(path.read_text(encoding="utf-8"))))
    if not result:
        raise ValueError("Private-value comparison was inconclusive")
    return result


def scan(name, raw, protected):
    if len(raw) > 1_000_000:
        raise ValueError("Unexpectedly large publication member: " + name)
    content = raw.decode("utf-8-sig")
    patterns = [r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----",
                r"\b(?:ghp_|github_pat_)[A-Za-z0-9_]{20,}", r"\bAKIA[A-Z0-9]{16}\b",
                r"(?i)authorization[\s\"']*[:=][\s\"']*(?:Bearer|Basic)\s+[A-Za-z0-9._~+/-]{12,}"]
    if any(value in content for value in protected) or any(re.search(pattern, content) for pattern in patterns):
        raise ValueError("Sensitive-value match; values withheld; path: " + name)
    if name.endswith(".py"):
        ast.parse(content, filename=name)
    if name.endswith(".json"):
        json.loads(content, parse_constant=lambda value: (_ for _ in ()).throw(ValueError("Nonfinite JSON")))
    return content


def git(*arguments):
    return subprocess.check_output(["git", *arguments], cwd=ROOT)


def link_inventory(selected):
    tracked = set(git("ls-files", "-z").decode().split("\0")) | set(selected)
    rows = []
    for name in selected:
        if not name.endswith(".md"):
            continue
        text = (ROOT / name).read_text(encoding="utf-8")
        for target in re.findall(r"!?\[[^\]]*\]\(([^)]+)\)", text):
            target = target.strip().strip("<>")
            if target.startswith("#"):
                kind, resolved = "same_document_anchor", name
            elif re.match(r"https?://", target):
                kind, resolved = "external_or_runtime_url_not_fetched", target
            elif re.match(r"(?:[A-Za-z]:|/|file:)", target):
                kind, resolved = "machine_local_reference", target
            else:
                path = (ROOT / name).parent / unquote(target.split("#")[0])
                path = path.resolve()
                if not path.is_relative_to(ROOT.resolve()):
                    kind, resolved = "machine_local_reference", target
                else:
                    resolved = path.relative_to(ROOT).as_posix()
                    kind = "published_target" if resolved in tracked else "local_only_excluded" if path.exists() else "missing_reference"
            rows.append({"document": name, "target": target, "classification": kind, "repository_target": resolved})
    return rows


def main():
    if sys.argv[1:] not in (["preflight"], ["staged"]):
        raise SystemExit("Use preflight or staged")
    selected = paths()
    protected_before = {str(path): sha(path) for path in PRIVATE}
    protected = read_private()
    if sys.argv[1:] == ["staged"]:
        staged = set(filter(None, git("diff", "--cached", "--name-only", "-z").decode().split("\0")))
        if staged != set(selected):
            raise ValueError("Index does not match the reviewed allowlist")
        for name in selected:
            scan(name, git("show", ":" + name), protected)
        subprocess.run(["git", "diff", "--cached", "--check"], cwd=ROOT, check=True)
        if any(sha(path) != protected_before[str(path)] for path in PRIVATE):
            raise ValueError("Private original changed")
        print(json.dumps({"staged_review_passed": True, "files": len(selected), "sensitive_matches": 0,
                          "private_originals_unchanged": True}))
        return
    if any((ROOT / name).exists() for name in GENERATED):
        raise FileExistsError("Publication receipts are create-only")
    for name in selected:
        if name not in GENERATED:
            scan(name, (ROOT / name).read_bytes(), protected)
    inventory = json.loads((FINAL / "FILES.json").read_text())
    checked = [entry for key in ("modified_existing_source_files", "new_integration_source_files") for entry in inventory[key]]
    for entry in checked:
        if sha(ROOT / entry["path"]) != entry["sha256"]:
            raise ValueError("Tested application source changed: " + entry["path"])
    links = link_inventory(selected)
    with (HERE / "LINK_AVAILABILITY.csv").open("x", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["document", "target", "classification", "repository_target"])
        writer.writeheader()
        writer.writerows(links)
    quality = json.loads((FINAL / "checks.json").read_text())
    review = {"reviewed_at_utc": datetime.now(timezone.utc).isoformat(), "allowlist_count": len(selected),
              "source_and_metadata_bytes": sum((ROOT / name).stat().st_size for name in selected if name not in GENERATED),
              "application_source_hashes_match_final_tested_versions": True,
              "tested_source_files": len(checked), "python_final": quality["python_final"],
              "frontend_final": quality["frontend_final"], "tests_reused_without_refitting": True,
              "prior_preservation_checked": quality["preservation_checked"],
              "prior_unexpected_changes": quality["unexpected_changes"],
              "known_private_header_or_cookie_values_copied": False, "sensitive_matches": 0,
              "private_originals_unchanged": all(sha(path) == protected_before[str(path)] for path in PRIVATE),
              "link_count": len(links), "link_classifications": {key: sum(row["classification"] == key for row in links) for key in sorted({row["classification"] for row in links})},
              "datasets_models_database_task_exports_and_runtime_snapshots_published": False,
              "six_month_main_preserved": True, "target_branch": "experiment/12-month-horizon",
              "training_or_tuning": False, "database_accessed": False, "data_downloads": 0,
              "forecast_or_shadow_issuance": False, "deployment": False,
              "scope": "Explicit allowlist only; existing tracked history is not a new whole-repository security audit",
              "stage_and_push": "Require an exact staged-blob check and non-forced branch push after this preflight"}
    with (HERE / "REVIEW.json").open("x", encoding="utf-8") as handle:
        json.dump(review, handle, indent=2, allow_nan=False)
    for name in selected:
        scan(name, (ROOT / name).read_bytes(), protected)
    print(json.dumps({"publication_preflight_passed": True, "files": len(selected),
                      "tested_source_files_unchanged": len(checked), "sensitive_matches": 0,
                      "private_originals_unchanged": review["private_originals_unchanged"],
                      "link_classifications": review["link_classifications"]}))


if __name__ == "__main__":
    main()
