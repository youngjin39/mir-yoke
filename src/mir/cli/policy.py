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
    usage = ("usage: mir policy resolve --category CATEGORY "
             "[--repo-root PATH] [--format json|text]")
    if argv in (["--help"], ["-h"]):
        print(usage)
        return 0
    print(usage, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
