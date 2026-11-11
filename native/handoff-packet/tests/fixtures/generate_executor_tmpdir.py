"""Freeze D02 observations from the two pinned Python references only.

Run with the repository Python and set MIR_EXECUTOR_TMPDIR_CAPTURE to a fresh directory.
"""

import io
import json
import os
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

WORKTREE_PIN = "99e71083f419b9732ff5779e0245c920f03f5979"
RESULT_PIN = "520739783e546bf9e1051fef584dfb0d89b32548"
ROOT = Path(__file__).resolve().parents[4]


def capture(scratch, shape):
    # Each shape gets a fresh interpreter: tempfile caches its selected directory.
    code = r"""
import importlib.util, json, os, pathlib, subprocess, sys, tempfile, types

root = pathlib.Path(sys.argv[1])
shape = sys.argv[2]
sys.path.insert(0, str(root / "worktree-reference"))
from tools.mir_executor.worktree import create_dispatch_worktree, cleanup_worktree

spec = importlib.util.spec_from_file_location(
    "result_oracle", root / "result-reference/tests/fixtures/executor_brief_policy_oracle.py"
)
oracle = importlib.util.module_from_spec(spec)
spec.loader.exec_module(oracle)
base = root / shape
base.mkdir()
real = base / "real"
real.mkdir()
alias = base / "alias"
alias.symlink_to(real, target_is_directory=True)
(real / "child").mkdir()
tmp = {"plain": real, "ancestor": alias / "child", "terminal": alias}[shape]
os.environ["TMPDIR"] = str(tmp)
tempfile.tempdir = None
repo = base / "repo"
repo.mkdir()


def git(*args):
    return subprocess.run(
        ["git", "-C", str(repo), *args], check=True, capture_output=True, text=True
    ).stdout.strip()


for args in [
    ("init", "-q"),
    ("config", "user.name", "Fixture"),
    ("config", "user.email", "fixture@example.invalid"),
]:
    git(*args)
(repo / "code").write_text("initial")
git("add", "-A")
git("commit", "-qm", "fixture")
wt = create_dispatch_worktree(repo, "auto", brief_text="brief")
auto_root = wt.path.parent
cleanup_worktree(wt, delete_branch=False)
result = {
    "automatic_removed": not auto_root.exists(),
    "branch_kept": bool(git("branch", "--list", wt.branch)),
}
path = tmp / "result.json"
attempt = types.SimpleNamespace(
    exit_code=1,
    error_sig="token=signature",
    stdout="\ud55c\uae00",
    stderr="password=hidden",
    lane_unavailable=False,
    retryable=True,
    blocked_reason=None,
)
oracle.after_run(types.SimpleNamespace(result_path=path), 1, attempt)
result["artifact"] = path.read_text()
result["mode"] = path.stat().st_mode & 0o777
wt = create_dispatch_worktree(repo, "selected", worktrees_root=alias)
result["selected_terminal_accepted"] = wt.brief_path.read_text() == ""
cleanup_worktree(wt)
(real / "outside").mkdir()
(real / "outside/keep").write_text("keep")
(real / "descendant").symlink_to(real / "outside", target_is_directory=True)
try:
    create_dispatch_worktree(repo, "descendant", worktrees_root=real)
except subprocess.CalledProcessError as exc:
    result["descendant"] = {
        "exception": type(exc).__name__,
        "code": exc.returncode,
        "target_preserved": (real / "outside/keep").read_text() == "keep",
    }
print(json.dumps(result, ensure_ascii=True))

"""
    return json.loads(
        subprocess.check_output(
            [sys.executable, "-c", code, str(scratch), shape],
            cwd=scratch,
            env={**os.environ, "HOME": str(scratch / "home")},
            text=True,
        )
    )


def main():
    destination = os.environ.get("MIR_EXECUTOR_TMPDIR_CAPTURE")
    scratch = Path(destination or tempfile.mkdtemp(prefix="executor-tmpdir-")).resolve()
    scratch.mkdir(parents=True, exist_ok=True)
    (scratch / "home").mkdir(exist_ok=True)
    for name, pin in [("worktree-reference", WORKTREE_PIN), ("result-reference", RESULT_PIN)]:
        dest = scratch / name
        dest.mkdir()
        archive = subprocess.check_output(["git", "archive", pin], cwd=ROOT)
        with tarfile.open(fileobj=io.BytesIO(archive)) as source:
            source.extractall(dest, filter="data")
    data = {
        "worktree_pin": WORKTREE_PIN,
        "result_pin": RESULT_PIN,
        "cases": {shape: capture(scratch, shape) for shape in ["plain", "ancestor", "terminal"]},
    }
    Path(__file__).with_name("executor_tmpdir.json").write_text(
        json.dumps(data, indent=2, ensure_ascii=True) + "\n"
    )


if __name__ == "__main__":
    main()
