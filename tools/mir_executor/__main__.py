"""Entry point for ``python -m tools.mir_executor``."""

from __future__ import annotations

import sys
from pathlib import Path

_HARNESS_ROOT = Path(__file__).resolve().parents[2]
_SRC_ROOT = _HARNESS_ROOT / "src"
for _path in (_HARNESS_ROOT, _SRC_ROOT):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from tools.mir_executor.cli import main

if __name__ == "__main__":
    main()
