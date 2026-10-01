"""Stop hooks must use a randomised mktemp template (owner Discord 1555187641522331731)."""

from __future__ import annotations

import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[1]


def test_stop_hooks_use_a_randomised_mktemp_template() -> None:
    """BSD mktemp leaves `XXXXXX.py` literal, so one leftover file broke every later Stop hook."""
    for name in ("mir-stop.sh", "stop-failure-audit.sh"):
        body = (ROOT / ".claude" / "hooks" / name).read_text(encoding="utf-8")
        templates = re.findall(r"mktemp\s+(\S+?)\)", body)
        assert templates, name
        for template in templates:
            assert template.endswith("XXXXXX"), f"{name}: {template}"
