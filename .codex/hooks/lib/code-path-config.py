"""ADR-23 dogfooding-aware code-path config emitter.

Output (stdout): one path per line, the configured MIR_FAMILY_CODE_PATHS
for the given family slug. Defaults to ['tools/', 'src/'] if family is
unknown or has no override.

ADR-23 dogfooding exemption: if family is in the "active 10 dogfooding"
set, the calling hook should skip block (advisory only).
"""

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]


def get_family_config(family_slug: str) -> dict:
    """Load config/repos/<family>.json if exists."""
    path = PROJECT_ROOT / "config" / "repos" / f"{family_slug}.json"
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def get_code_paths(family_slug: str) -> list[str]:
    """Return MIR_FAMILY_CODE_PATHS for family. Default ['tools/', 'src/']."""
    config = get_family_config(family_slug)
    paths = config.get("code_paths") or config.get("mir_family_code_paths")
    if paths:
        return list(paths)
    return ["tools/", "src/"]


def is_dogfooding_exempt(family_slug: str) -> bool:
    """ADR-23 dogfooding exemption check.

    Returns True if family is in the "active dogfooding" set
    (advisory mode, no BLOCK on direct edits).
    """
    config = get_family_config(family_slug)
    return bool(config.get("dogfooding_exempt", False))


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Emit configured MIR_FAMILY_CODE_PATHS or dogfooding-exempt status."
    )
    parser.add_argument("--family", required=True, help="Family slug (e.g. mir-harness)")
    parser.add_argument(
        "--check",
        choices=["code-paths", "dogfooding-exempt"],
        default="code-paths",
        help="What to check (default: code-paths)",
    )
    args = parser.parse_args()

    if args.check == "code-paths":
        for p in get_code_paths(args.family):
            print(p)
    elif args.check == "dogfooding-exempt":
        print("yes" if is_dogfooding_exempt(args.family) else "no")
    return 0


if __name__ == "__main__":
    sys.exit(main())
