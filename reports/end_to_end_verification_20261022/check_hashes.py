"""Pre/post hash verification for protected artifacts."""
import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

EXPECTED = {
    "reports/candidates/twelve_month_horizon_finalization_20261020/artifact/manifest.json":
        "e390b0e78221560e66b50610d4ef37cb37225d34232589c4d52064713ef27165",
    "reports/candidates/twelve_month_horizon_finalization_20261020/artifact/xgb_fixed_2021.json":
        "f94911f5e1a6c3e8b4bbbb82d6a4c6ec87b5d601abbfd774801afc046aa5455f",
    "reports/candidates/twelve_month_horizon_finalization_20261020/artifact/xgb_fixed_2021_card.json":
        "c399ed9cfa5c1746c874659d89bd1d69d92ea841dc262b7d0dfab89bac9e0bd7",
    "reports/candidates/twelve_month_horizon_finalization_20261020/artifact/features.csv":
        "728677ebfbe103f0d38b53fd0bd02deb8a4d647f15f5bb199d392a29be33569e",
    "reports/candidates/twelve_month_horizon_finalization_20261020/artifact/provenance.json":
        "2e6b5e5d43db8df0b681b82ac4ec6fbf4d84ff359c1c006acd6b93da4f0322f1",
}

all_ok = True
for rel, expected in EXPECTED.items():
    actual = hashlib.sha256((ROOT / rel).read_bytes()).hexdigest()
    match = actual == expected
    name = rel.split("/")[-1]
    print(f"  {name:30s} {'MATCH' if match else 'MISMATCH'}")
    if not match:
        all_ok = False
        print(f"    expected: {expected}")
        print(f"    actual:   {actual}")

print(f"\nAll protected hashes: {'PASS' if all_ok else 'FAIL'}")
