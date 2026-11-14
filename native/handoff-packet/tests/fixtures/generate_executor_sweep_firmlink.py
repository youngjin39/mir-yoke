"""Capture pinned sweep path spelling using isolated, disposable Git repositories.

macOS only. Pass a fresh --scratch directory and an explicit --output file.
The Data spelling simulates the default TMPDIR spelling without writing in /private.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

PIN = "f10edf21f5a94db1254eacabfdb06b517f9daeca"
ROOT = Path(__file__).resolve().parents[4]
HELPER = "native/handoff-packet/tests/fixtures/generate_executor_sweep.py"
SOURCES = [
    "tools/mir_executor/" + name
    for name in ("__init__.py", "sweep.py", "jobs.py", "redaction.py", "local_hooks.py")
] + [HELPER]

CHILD = r"""
import datetime, importlib.util, json, os, pathlib, shutil, subprocess, sys
from unittest.mock import patch

reference, scratch = map(pathlib.Path, sys.argv[1:])
sys.path[:] = [str(reference), *[p for p in sys.path if p and pathlib.Path(p).is_absolute()]]
from tools.mir_executor import sweep

spec = importlib.util.spec_from_file_location(
    "fixture_reference",
    reference / "native/handoff-packet/tests/fixtures/generate_executor_sweep.py",
)
fixture = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = fixture
spec.loader.exec_module(fixture)
loaded = {}
for name, module in list(sys.modules.items()):
    if name == "tools" or name.startswith("tools.") or name == spec.name:
        file = getattr(module, "__file__", None)
        if file:
            path = pathlib.Path(file).resolve()
            assert path.is_relative_to(reference.resolve()), (name, str(path))
            loaded[name] = str(path.relative_to(reference))
        else:
            assert all(
                pathlib.Path(p).resolve().is_relative_to(reference.resolve())
                for p in module.__path__
            )
assert "tools.mir_executor.sweep" in loaded
# The private-root probe substitutes only Git output and never writes there.
private_root = pathlib.Path("/private/var/folders")
private_registered = pathlib.Path("/System/Volumes/Data/private/var/folders")
listing = (
    "worktree "
    + str(private_registered / "oracle-wt")
    + chr(0)
    + "branch refs/heads/mir-dispatch/probe"
    + chr(0) * 2
)
with patch.object(
    sweep.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, stdout=listing)
):
    probe = sweep._list_dispatch_worktrees(private_root / "oracle-repo")
assert str(probe[0].path) == str(private_registered / "oracle-wt")
private_probe = {
    "listed_path": str(probe[0].path),
    "ordinary_resolve": str(private_root.resolve()),
    "registered_resolve": str(private_registered.resolve()),
    "evidence_type": "derived",
    "excluded": "No sweep or Git command ran under /private",
}
cases = {}
for spelling in ("ordinary", "data"):
    for route in ("registered-firmlink", "registered-retarget"):
        ordinary = scratch / (spelling + "-" + route)
        ordinary.mkdir()
        data = pathlib.Path("/System/Volumes/Data") / str(ordinary).lstrip("/")
        assert data.is_dir() and os.path.samefile(data, ordinary)
        home = data if spelling == "data" else ordinary
        registered = data
        fixture.setup(registered if route == "registered-firmlink" else home, "run-mixed")
        if route == "registered-retarget":
            alias = home / "registered"
            alias.symlink_to(home, target_is_directory=True)
            for root, name in ((alias, "wt-clean"), (registered, "wt-finished")):
                (home / "repo/.git/worktrees" / name / "gitdir").write_text(
                    str(root / name / ".git") + "\n"
                )
            outside = home / "outside"
            (outside / "wt-clean").mkdir(parents=True)
            for name in ("tracked.txt", ".gitignore", ".git"):
                shutil.copyfile(home / "wt-clean" / name, outside / "wt-clean" / name)
        listed = [str(item.path) for item in sweep._list_dispatch_worktrees(home / "repo")]
        assert len(listed) == 11 and any(p.endswith("/wt-clean") for p in listed)
        real_remove = sweep._remove_worktree_safely

        def remove(repo, listed):
            if route == "registered-retarget" and listed.job_id == "clean":
                alias.unlink()
                alias.symlink_to(outside, target_is_directory=True)
            return real_remove(repo, listed)

        with patch.object(sweep, "_remove_worktree_safely", remove):
            result = sweep.sweep_run_state(
                home / "repo",
                home / "jobs.db",
                now=datetime.datetime.fromisoformat(fixture.NOW),
                grace_seconds=120,
                apply=True,
            )
        assert result["stale_jobs"] == ["stale"]
        expected_removed = [str(data / "wt-finished")]
        if route == "registered-firmlink":
            expected_removed.insert(0, str(data / "wt-clean"))
        else:
            assert {
                "path": str((home / "wt-clean").resolve()),
                "reasons": ["apply-time-drift:remove-refused"],
            } in result["preserved_worktrees"]
            assert (outside / "wt-clean/tracked.txt").read_text() == "initial\n"
        assert result["removed_worktrees"] == expected_removed
        assert not (home / "wt-finished").exists()

        def norm(value):
            if isinstance(value, str):
                # Keep the Data prefix observable; only the physical scratch root is normalized.
                return value.replace(str(ordinary), "$ROOT")
            if isinstance(value, list):
                return [norm(v) for v in value]
            if isinstance(value, dict):
                return {k: norm(v) for k, v in value.items()}
            return value

        cases[spelling + "|" + route] = norm(
            {
                "fixture_root": str(home),
                "registered_root": str(registered),
                "pathlib_resolve_registered": str(registered.resolve()),
                "listed_paths": listed,
                "result": result,
                "clean_exists": (home / "wt-clean").exists(),
                "finished_exists": (home / "wt-finished").exists(),
            }
        )
print(
    json.dumps(
        {"loaded_modules": loaded, "private_path_listing_probe": private_probe, "cases": cases},
        indent=2,
    )
)
"""


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scratch", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    scratch = args.scratch.absolute()
    scratch.mkdir(parents=True, exist_ok=True)
    reference = scratch / "reference"
    reference.mkdir()  # A reused capture directory is an error.
    digests = {}
    for name in SOURCES:
        source = subprocess.check_output(["git", "-C", str(ROOT), "show", f"{PIN}:{name}"])
        target = reference / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(source)
        digests[name] = hashlib.sha256(source).hexdigest()
    old = json.loads((ROOT / "native/handoff-packet/tests/fixtures/g6/sweep.json").read_text())
    assert digests["tools/mir_executor/sweep.py"] == old["provenance"]["source_sha256"]
    home = scratch / "home"
    home.mkdir()
    env = dict(
        os.environ,
        HOME=str(home),
        PYTHONDONTWRITEBYTECODE="1",
        GIT_CONFIG_NOSYSTEM="1",
        GIT_CONFIG_GLOBAL=os.devnull,
    )
    result = subprocess.run(
        [sys.executable, "-I", "-c", CHILD, str(reference), str(scratch)],
        cwd=scratch,
        env=env,
        check=True,
        text=True,
        capture_output=True,
    )
    captured = json.loads(result.stdout)
    record = {
        "provenance": {
            "reference_pin": PIN,
            "source_sha256": digests,
            "isolation": "python -I; synthetic project imports; origins checked before execution",
            "simulation": "T7 ordinary and Data spellings; no /private fixture created",
            "python": sys.version,
        },
        **captured,
    }
    args.output.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "output": str(args.output),
                "cases": {k: v["result"]["removed_worktrees"] for k, v in record["cases"].items()},
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
