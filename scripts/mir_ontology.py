"""Yoke checkout entrypoint; consumers copy the canonical installed runner (Python 3.9+)."""

import os
import subprocess
import sys
from pathlib import Path


def main():
    root = Path(__file__).resolve().parents[1]
    args = sys.argv[1:]
    if not args or args[0] not in {"mapping", "impact", "lookup", "mk"}:
        print("usage: mir_ontology.py {mapping|impact|lookup|mk} ...", file=sys.stderr)
        return 2
    checker = Path(os.environ.get(
        "MIR_ONTOLOGY_CHECKER",
        root / "plugins/mir-core/skills/ontology/scripts/ontology_check.py",
    ))
    command, *rest = args
    script = checker.with_name("mk_query.py") if command == "mk" else checker
    if not script.is_file():
        print(f"ontology distribution is missing: {script}", file=sys.stderr)
        return 2
    if command == "mk":
        # The client owns --soft as a global option; accept it after query too.
        soft = ["--soft"] if "--soft" in rest else []
        forwarded = ["--repo", str(root), *soft,
                     *(arg for arg in rest if arg != "--soft")]
    else:
        forwarded = [command, "--repo", str(root), *rest]
    return subprocess.call([sys.executable, str(script), *forwarded])


if __name__ == "__main__":
    raise SystemExit(main())
