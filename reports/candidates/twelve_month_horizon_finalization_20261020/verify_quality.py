"""Read-only review of this change set; create-only check receipt, no data output."""
import ast
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
SOURCE = ["README.md", "api_spec.md", "deploy/README.md", "api/app.py", "api/routes/scores.py",
          "api/routes/research.py", "models/research_forecast.py", "tests/test_research_forecast_api.py",
          "dashboard/index.html", "dashboard/src/App.jsx", "dashboard/src/api.js",
          "dashboard/src/pages/Home.jsx", "dashboard/src/pages/DistrictDetail.jsx",
          "dashboard/src/components/ResearchForecast.jsx", "dashboard/src/components/researchForecastContract.js",
          "dashboard/tests/researchForecast.test.js", "research/twelve_month_app.json"]


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8-sig"),
                      parse_constant=lambda value: (_ for _ in ()).throw(ValueError("Nonfinite JSON")))


def sensitive_values(value, under_header=False):
    if isinstance(value, dict):
        for key, item in value.items():
            normalized = re.sub(r"[^a-z]", "", key.lower())
            yield from sensitive_values(item, under_header or normalized in {"cookie", "setcookie", "authorization"})
    elif isinstance(value, list):
        for item in value:
            yield from sensitive_values(item, under_header)
    elif under_header and isinstance(value, str) and len(value) >= 10:
        yield value


def main():
    destination = HERE / "quality-and-security.json"
    if destination.exists():
        raise FileExistsError("Use a fresh receipt; never overwrite completed evidence")
    paths = sorted(set([ROOT / name for name in SOURCE] + [p for p in HERE.rglob("*") if p.is_file()]))
    syntax = []
    json_files = []
    whitespace = []
    for path in paths:
        if path.suffix == ".py":
            ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
            syntax.append(path.relative_to(ROOT).as_posix())
        if path.suffix == ".json":
            read_json(path)
            json_files.append(path.relative_to(ROOT).as_posix())
        if path.suffix in {".py", ".js", ".jsx", ".md", ".html"}:
            for number, line in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), 1):
                if line.rstrip() != line:
                    whitespace.append({"path": path.relative_to(ROOT).as_posix(), "line": number})
    assert not whitespace, "Trailing whitespace found; receipt would contain locations only"
    private = [ROOT / "reports/actual_forecast_validation_20261019/source_manifest.json",
               ROOT / "reports/actual_forecast_validation_20261019/acquired/nwic_copyright.html.retrieval.json"]
    # Values are held only in memory for equality checks, never printed or saved.
    protected_values = set()
    for path in private:
        protected_values.update(sensitive_values(read_json(path)))
    assert protected_values, "Private header extraction was inconclusive; do not claim a completed check"
    patterns = [re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
                re.compile(r"\b(?:ghp_|github_pat_)[A-Za-z0-9_]{20,}"),
                re.compile(r"\bAKIA[A-Z0-9]{16}\b")]
    matches = []
    for path in paths:
        content = path.read_text(encoding="utf-8-sig", errors="replace")
        if any(value in content for value in protected_values) or any(pattern.search(content) for pattern in patterns):
            matches.append(path.relative_to(ROOT).as_posix())
    assert not matches, "Sensitive-value match; do not echo values"
    diff = subprocess.run(["git", "diff", "--check"], cwd=ROOT, text=True, capture_output=True)
    assert diff.returncode == 0, "Tracked whitespace check failed"
    versions = {"python": subprocess.check_output([str(ROOT / "venv/Scripts/python.exe"), "--version"], text=True).strip(),
                "node": subprocess.check_output(["node", "--version"], text=True).strip()}
    result = {"verified_at_utc": datetime.now(timezone.utc).isoformat(), "syntax_checked": syntax,
              "strict_json_checked": json_files, "trailing_whitespace": whitespace,
              "git_diff_check_exit_code": diff.returncode, "git_diff_check_stderr": diff.stderr,
              "reviewed_files": [p.relative_to(ROOT).as_posix() for p in paths],
              "reviewed_file_count": len(paths), "known_private_header_values_found": len(protected_values),
              "known_private_header_values_copied": False, "secret_pattern_matches": matches,
              "security_scope": "Only the explicitly reviewed finalization/source files; not a publication approval or scan of the entire private working tree",
              "versions": versions,
              "source_sha256": {name: hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in SOURCE}}
    with destination.open("x", encoding="utf-8") as handle:
        json.dump(result, handle, indent=2)
    print(json.dumps({"passed": True, "syntax_files": len(syntax), "json_files": len(json_files),
                      "reviewed_files": len(paths), "private_header_values_copied": False}))


if __name__ == "__main__":
    main()
