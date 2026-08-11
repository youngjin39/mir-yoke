"""Retained CLI modules without a public 0.9 module entrypoint."""
from __future__ import annotations

import sys


def main(argv: list[str] | None = None) -> int:
    del argv
    print(
        "Mir Yoke 0.9 exposes no public CLI; retained modules are reference corpus.",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
