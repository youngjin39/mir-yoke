"""mir policy: thin adapter to the pinned native resolver."""
from __future__ import annotations

import sys

from tools.mir_executor.entrypoint import _native_query


def main(argv: list[str]) -> int:
    if argv and argv[0] == "resolve":
        result = _native_query(["policy-resolve", *argv[1:]])
        if result is not None:
            return result
        print("[mir policy] pinned native policy resolver unavailable or incompatible; "
              "no routing result", file=sys.stderr)
        return 2
    print("usage: mir policy resolve --category CATEGORY "
          "[--repo-root PATH] [--format json|text]", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
