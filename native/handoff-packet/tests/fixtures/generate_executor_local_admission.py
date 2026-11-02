"""Capture Python execute preparation outcomes for target-local hook fixtures."""

from __future__ import annotations

import contextlib
import io
import json
import os
import pathlib
import subprocess
import sys
import tempfile
from unittest.mock import patch

ROOT = pathlib.Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
from tools.mir_executor import cli, cli_parser, local_hooks  # noqa: E402

CASES = [
    ("empty", "", ""),
    (
        "mutate",
        "def pre_execute(args, root):\n args.family = 'changed'\n args.dispatch = True\n",
        "",
    ),
    (
        "redirect",
        "def pre_execute(args, root):\n"
        " args.repo_root = root.parent / 'home'\n args.family = 'redirected'\n",
        "",
    ),
    (
        "redirect_refused",
        "def pre_execute(args, root):\n args.repo_root = root.parent / 'redirected'\n",
        "def authorize_target(home, target, args):\n"
        " if target.name == 'redirected': raise RuntimeError('redirect denied')\n",
    ),
    ("value_error", "def pre_execute(args, root):\n raise ValueError('hook rejected')\n", ""),
    ("os_error", "def pre_execute(args, root):\n raise PermissionError('hook denied')\n", ""),
]
base = pathlib.Path(os.environ.get("MIR_NATIVE_TEST_SCRATCH", tempfile.gettempdir()))
base.mkdir(parents=True, exist_ok=True)
with tempfile.TemporaryDirectory(dir=base) as directory:
    scratch = pathlib.Path(directory).resolve()
    for name in ("home", "target", "redirected"):
        root = scratch / name
        (root / "tools/mir_executor").mkdir(parents=True)
        subprocess.run(["git", "init", "-q", str(root)], check=True)
    rows = []
    for name, source, home_source in CASES:
        local_hooks._MODULES.clear()
        (scratch / "target/tools/mir_executor/local.py").write_text(source)
        (scratch / "home/tools/mir_executor/local.py").write_text(home_source)
        args = cli_parser._build_parser(scratch / "target").parse_args(
            ["execute", "--repo-root", str(scratch / "target")]
        )
        stderr = io.StringIO()
        with patch.object(
            local_hooks, "__file__", str(scratch / "home/tools/mir_executor/local_hooks.py")
        ):
            with contextlib.redirect_stderr(stderr):
                try:
                    root = cli._prepare_execute_root(args)
                except ValueError as exc:
                    print(f"[mir_executor] argument parse error: {exc}", file=sys.stderr)
                    expected = {"code": 1}
                except OSError as exc:
                    print(f"[mir_executor] {type(exc).__name__}: {exc}", file=sys.stderr)
                    expected = {"code": 1}
                else:
                    expected = {"root": str(root), "family": args.family, "dispatch": args.dispatch}
        expected["stderr"] = stderr.getvalue()
        rows.append(
            {"name": name, "source": source, "home_source": home_source, "expected": expected}
        )
    serialized = json.dumps(rows, ensure_ascii=True, indent=2).replace(str(scratch), "$scratch")
    pathlib.Path(__file__).with_name("executor_local_admission.json").write_text(serialized + "\n")
print(f"captured {len(rows)} Python local admission cases")
