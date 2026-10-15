"""Check explicit repository roots with this checkout's checker (read-only).

Usage: python3 scripts/check_ontology_fleet.py REPO_ROOT [REPO_ROOT ...]
Exit zero only when every requested mapping has zero errors.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

CHECKER = (Path(__file__).resolve().parents[1]
           / "plugins/mir-core/skills/ontology/scripts/ontology_check.py")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("roots", type=Path, nargs="+")
    args = parser.parse_args()
    failed = False
    for root in args.roots:
        root = root.resolve()
        result = subprocess.run(
            [sys.executable, str(CHECKER), "mapping", "--repo", str(root), "--json"],
            capture_output=True, text=True, check=False,
        )
        if result.returncode not in (0, 1):
            print(f"{root.name}: checker failed (exit {result.returncode})")
            print(result.stderr or result.stdout)
            failed = True
            continue
        report = json.loads(result.stdout)
        errors, warnings = report["errors"], report["warnings"]
        print(f"{root.name}: {len(errors)} errors, {len(warnings)} warnings")
        for finding in errors + warnings:
            print(f"  {finding['pointer']}: {finding['message']}")
        failed |= result.returncode != 0 or bool(errors)
    return int(failed)


if __name__ == "__main__":
    raise SystemExit(main())
