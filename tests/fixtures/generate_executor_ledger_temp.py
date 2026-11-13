"""Capture only pinned ledger methods with synthetic files; never run a provider."""
from __future__ import annotations

import argparse
import ast
import contextlib
import hashlib
import json
import os
import subprocess
import tempfile
from pathlib import Path
from types import SimpleNamespace

PIN = "99a8c865d6977b97d32c42beb330206f6b3f10a3"


def capture(scratch: Path) -> dict:
    source = subprocess.check_output(["git", "show", f"{PIN}:tools/mir_executor/executor.py"])
    tree = ast.parse(source)
    executor = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "MirExecutor")
    nodes = [n for n in executor.body if isinstance(n, ast.FunctionDef)
             and n.name in {"update_ledger", "_validate_ledger_entry"}]
    nodes += [n for n in tree.body if isinstance(n, ast.FunctionDef)
              and n.name == "_ledger_entry_for"]
    namespace = dict(json=json, os=os, tempfile=tempfile,
                     writer_scope=lambda _: contextlib.nullcontext(),
                     LedgerUpdate=lambda **kw: kw)
    module = ast.unparse(ast.Module(body=nodes, type_ignores=[]))
    exec("from __future__ import annotations\n" + module, namespace)
    original_names, original_limit = tempfile._get_candidate_names, tempfile.TMP_MAX
    records = {}
    try:
        # A reduced, identical bound makes every attempted collision observable.
        tempfile.TMP_MAX = 3
        for case in ("collision", "exhaustion"):
            with tempfile.TemporaryDirectory(dir=scratch) as directory:
                root = Path(directory)
                ledger = root / "tdd.json"
                ledger.write_text('{"c":{"categories":{"unit":{"status":"pending"}}}}')
                candidates = ["one", "two", "three"]
                existing = candidates if case == "exhaustion" else candidates[:1]
                for name in existing:
                    (root / f"tmp{name}.tmp").write_text(f"owner-{name}")
                attempts = []

                def names(candidates=candidates, attempts=attempts):
                    for name in candidates:
                        attempts.append(name)
                        yield name

                tempfile._get_candidate_names = names
                executor = SimpleNamespace(_repo_root=root, _ledger_path=ledger)
                executor._validate_ledger_entry = lambda *args, executor=executor: namespace[
                    "_validate_ledger_entry"](executor, *args)
                error = None
                try:
                    namespace["update_ledger"](executor, "c", "unit", SimpleNamespace(
                        exit_code=0, stderr="", command=["fake"]))
                except OSError as caught:
                    error = f"{type(caught).__name__}: {caught}"
                records[case] = dict(error=error, attempts=attempts,
                                     preserved={name: (root / f"tmp{name}.tmp").read_text()
                                                for name in existing},
                                     status=json.loads(ledger.read_text())["c"]["categories"]["unit"]["status"])
                tempfile._get_candidate_names = original_names
    finally:
        tempfile._get_candidate_names, tempfile.TMP_MAX = original_names, original_limit
    return dict(pin=PIN, source_sha256=hashlib.sha256(source).hexdigest(),
                retry_source="CPython 3.12 Lib/tempfile.py TMP_MAX and _mkstemp_inner",
                test_retry_bound=3, records=records)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scratch", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    args.output.write_text(json.dumps(capture(args.scratch), indent=2) + "\n")
