"""Dynamic E11 oracle on disposable Git repositories and private job ledgers."""

from __future__ import annotations

import datetime
import hashlib
import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
from tools.mir_executor import sweep  # noqa: E402
from tools.mir_executor.jobs import JobRecord, JobRegistry  # noqa: E402

NOW = "2026-07-11T00:03:01+00:00"
OLD = "2026-01-01T00:00:00+00:00"
IDS = [str(i) * 32 for i in range(1, 9)]


def git(repo, *args):
    env = dict(os.environ, GIT_AUTHOR_DATE=OLD, GIT_COMMITTER_DATE=OLD, GIT_OPTIONAL_LOCKS="0")
    return subprocess.check_output(
        ["git", "-C", str(repo), *args], stderr=subprocess.PIPE, env=env
    ).decode()


def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="")


def directory_link(target, outside):
    """Use a real junction when Windows does not grant symlink privilege."""
    try:
        target.symlink_to(outside, target_is_directory=True)
        return False
    except OSError:
        if os.name != "nt":
            raise
        subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(target), str(outside)],
            check=True,
            capture_output=True,
        )
        return True


def setup(home, case):
    home.mkdir(parents=True, exist_ok=True)
    repo = home / "repo"
    repo.mkdir()
    git(repo, "init", "-q")
    git(repo, "config", "user.name", "Fixture")
    git(repo, "config", "user.email", "fixture@example.invalid")
    git(repo, "config", "core.autocrlf", "false")
    write(repo / "tracked.txt", "initial\n")
    write(repo / ".gitignore", ".mir-dispatch/\n*.ignored\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "fixture")
    db = home / "jobs.db"
    if case == "missing-db":
        return
    registry = JobRegistry(db)

    def job(
        identity,
        status="running",
        started="2026-07-11T00:00:00+00:00",
        completed=None,
        metadata=None,
    ):
        registry.insert(
            JobRecord(
                job_id=identity,
                change_id="fixture",
                category="unit",
                family=None,
                repo_root=str(repo),
                codex_args=[],
                timeout_seconds=60,
                status=status,
                started_at=started,
                completed_at=completed,
                ai_run_metadata=metadata,
            )
        )

    if case.startswith("run"):
        job("stale")
        job("live", started="2026-07-11T00:02:00+00:00")
        job("bad-time", started="invalid")
        job("boundary", started="2026-07-11T00:00:01+00:00")
        job("finished", status="completed")
        for name in [
            "stale",
            "live",
            "finished",
            "clean",
            "tracked",
            "staged",
            "untracked",
            "ignored",
            "runtime",
            "unique",
            "locked",
        ]:
            wt = home / ("wt-" + name)
            git(repo, "worktree", "add", "-q", "-b", "mir-dispatch/" + name, str(wt), "HEAD")
            if name == "tracked":
                write(wt / "tracked.txt", "dirty\n")
            elif name == "staged":
                write(wt / "staged.txt", "staged\n")
                git(wt, "add", "staged.txt")
            elif name in {"untracked", "ignored"}:
                write(wt / ("cache.ignored" if name == "ignored" else "new.txt"), "dirt\n")
            elif name == "runtime":
                write(wt / ".mir-dispatch/status.json", '{"state":"done"}\n')
            elif name == "unique":
                write(wt / "tracked.txt", "unique\n")
                git(wt, "commit", "-qam", "unique")
            elif name == "locked":
                git(repo, "worktree", "lock", str(wt))
    else:
        job(
            IDS[0],
            status="completed",
            completed=OLD,
            metadata={"dispatch_ids": [IDS[1], "../foreign", 7], "dispatch_id": IDS[2]},
        )
        job(IDS[3], status="running", completed=OLD)
        job(IDS[4], status="failed", completed=NOW)
        job(IDS[5], status="cancelled", completed=None)
        job(IDS[6], status="failed", completed="invalid")
        job("invalid-id", status="completed", completed=OLD)
        for identity in [*IDS, "invalid-id", "owner-file"]:
            write(repo / "tasks/dispatch" / identity / "nested/data.txt", "hello\n")
        if case == "artifact-receipt":
            registry.record_artifact_sweep(IDS[0], str(repo / "tasks/dispatch" / IDS[0]), 1, 6, OLD)
        if case in {"artifact-link", "artifact-root-link"}:
            outside = home / "outside"
            write(outside / "sentinel", "preserve\n")
            target = repo / (
                "tasks/dispatch" if case.endswith("root-link") else "tasks/dispatch/" + IDS[1]
            )
            import shutil

            shutil.rmtree(target)
            if directory_link(target, outside):
                # The Python reference checks is_symlink, not Windows junctions.
                # Native tests assert the stricter reparse-point safety contract.
                write(home / "fixture-junction.json", json.dumps(case))
    registry.close()


def normalize(value, home):
    if isinstance(value, str):
        return value.replace(str(home), "$ROOT").replace(str(home).replace("\\", "/"), "$ROOT")
    if isinstance(value, list):
        return [normalize(v, home) for v in value]
    if isinstance(value, dict):
        return {k: normalize(v, home) for k, v in value.items()}
    return value


def snapshot(home, raw=False):
    tree = {}
    for base, dirs, files in os.walk(home, followlinks=False):
        base = Path(base)
        if not raw and ".git" in dirs:
            dirs.remove(".git")
        for name in sorted(dirs + files):
            path = base / name
            rel = path.relative_to(home).as_posix()
            if path.is_symlink():
                tree[rel] = {"link": normalize(os.readlink(path), home)}
            elif path.is_file():
                if not raw and (name == ".git" or name.startswith("jobs.db")):
                    continue
                content = path.read_bytes()
                tree[rel] = hashlib.sha256(content).hexdigest() if raw else content.hex()
            else:
                tree[rel] = {"dir": True}
    if raw:
        return tree
    rows = {}
    db = home / "jobs.db"
    if db.exists():
        conn = sqlite3.connect(f"{db.as_uri()}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        try:
            for table in ["jobs", "artifact_sweeps"]:
                rows[table] = [
                    dict(row) for row in conn.execute(f"SELECT * FROM {table} ORDER BY rowid")
                ]
        finally:
            conn.close()
    refs = git(home / "repo", "for-each-ref", "--format=%(refname) %(objectname)")
    return normalize({"tree": tree, "rows": rows, "refs": refs}, home)


def oracle(home, case, apply, seam, now_text=NOW):
    repo, db = home / "repo", home / "jobs.db"
    now = datetime.datetime.fromisoformat(now_text)
    if case.startswith("run") or case == "missing-db":
        real = sweep._inspect_removal_candidate
        calls = {}

        def inspect(root, listed):
            calls[listed.job_id] = calls.get(listed.job_id, 0) + 1
            if seam == "drift" and listed.job_id == "clean" and calls[listed.job_id] == 2:
                write(listed.path / "late.txt", "late\n")
            return real(root, listed)

        with patch.object(sweep, "_inspect_removal_candidate", inspect):
            return sweep.sweep_run_state(repo, db, now=now, grace_seconds=120, apply=apply)
    real = sweep.shutil.rmtree

    def remove(path, *args, **kwargs):
        if seam == "crash":
            raise RuntimeError("injected crash")
        return real(path, *args, **kwargs)

    with patch.object(sweep.shutil, "rmtree", remove):
        return sweep.sweep_terminal_artifacts(repo, db, now=now, retention_days=30, apply=apply)


if __name__ == "__main__":
    mode, root, case = sys.argv[1:4]
    home = Path(root).resolve()
    if mode == "link":
        directory_link(home, Path(case).resolve())
        print("null")
    elif mode == "setup":
        setup(home, case)
        print("null")
    elif mode == "snapshot":
        print(json.dumps(snapshot(home, raw=len(sys.argv) > 4)))
    else:
        apply = sys.argv[4] == "true"
        seam = sys.argv[5] if len(sys.argv) > 5 else ""
        try:
            result = oracle(home, case, apply, seam, sys.argv[6] if len(sys.argv) > 6 else NOW)
        except RuntimeError as exc:
            result = {"crash": str(exc)}
        print(json.dumps(normalize(result, home)))
