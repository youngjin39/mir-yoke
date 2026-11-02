"""Capture E9b finalization on disposable real Git repositories; no providers.

E9B_SCRATCH must select external-volume scratch. The reference functions stay
unchanged; stdlib patches inject failures at their existing call boundaries.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from contextlib import ExitStack
from dataclasses import asdict
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
from tools.mir_executor import dispatch as reference  # noqa: E402
from tools.mir_executor.jobs import JobRecord, JobRegistry  # noqa: E402
from tools.mir_executor.worktree import create_dispatch_worktree  # noqa: E402

FILES = {
    "pkg/a.py": "a = 1\n", "pkg/b.py": "b = 1\n",
    "pkg/delete.py": "delete me\n", "pkg/rename-old.py": "rename me\n",
    "pkg/[ab].py": "literal\n", "wip/staged.txt": "staged base\n",
    "wip/unstaged.txt": "unstaged base\n",
}
CASES = [
    {"name": "merged"}, {"name": "preserved", "outcome": "blocked"},
    {"name": "empty-diff", "empty": True},
    {"name": "reviewed-empty", "empty": True, "expect_changes": False},
    {"name": "missing-verifiers", "verification_commands": []},
    {"name": "unknown-verifier", "verification_commands": ["missing"]},
    {"name": "secret", "secret": True},
    {"name": "review-missing", "require_review": True},
    {"name": "review-rejected", "review": "reject"},
    {"name": "main-moved", "drift": "main"},
    {"name": "dispatch-moved", "drift": "dispatch"},
    {"name": "dispatch-dirty", "drift": "dirty"},
    {"name": "main-unstaged", "collision": "unstaged"},
    {"name": "main-staged", "collision": "staged"},
    {"name": "untracked-collision", "collision": "untracked"},
    {"name": "ignored-collision", "collision": "ignored"},
    {"name": "parent-collision", "collision": "parent"},
    {"name": "deletion-rename-literal", "paths": True},
    {"name": "unrelated-wip", "wip": True},
    {"name": "partial-merge-error", "inject": "merge", "wip": True},
    {"name": "rollback-restore-failed", "inject": "restore", "wip": True},
    {"name": "rollback-skipped", "inject": "rollback", "wip": True},
    {"name": "cleanup-failed", "inject": "cleanup"},
    {"name": "persist-failed", "inject": "persist"},
    {"name": "reviewed-cleanup-failed", "inject": "cleanup", "empty": True,
     "expect_changes": False},
    {"name": "lock-timeout", "lock": True},
]


def git(repo, *args):
    return subprocess.check_output(["git", "-C", str(repo), *args], stderr=subprocess.PIPE).decode()


def write(root, name, content):
    target = root / name
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8", newline="")


def snapshot(repo):
    if not repo.exists():
        return None
    files = {}
    for prefix in ("pkg", "wip"):
        base = repo / prefix
        if base.is_file():
            files[prefix] = base.read_text()
        elif base.exists():
            for path in sorted(base.rglob("*")):
                if path.is_file():
                    files[path.relative_to(repo).as_posix()] = path.read_text()
    return dict(index=git(repo, "ls-files", "--stage"),
                status=git(repo, "status", "--porcelain=v1", "-z", "--untracked-files=all",
                           "--ignored=matching", "--", "pkg", "wip"), files=files)


def seed(repo):
    repo.mkdir()
    git(repo, "init", "-q")
    git(repo, "config", "user.name", "Fixture")
    git(repo, "config", "user.email", "fixture@example.invalid")
    git(repo, "config", "core.autocrlf", "false")
    write(repo, ".gitignore", ".mir/\n.mir-dispatch/\nconfig/\n*.ignored\n")
    for name, content in FILES.items():
        write(repo, name, content)
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "fixture")
    write(repo, "config/mir-executor.local.json", json.dumps({
        "verifiers": {"ok": [sys.executable, "-c", "pass"]}}))


def hold_lock(repo, ready):
    lock = repo / ".mir/dispatch-finalize.lock"
    lock.parent.mkdir(parents=True, exist_ok=True)
    with lock.open("a+b") as stream:
        if os.name == "nt":
            import msvcrt
            stream.write(b"0")
            stream.flush()
            stream.seek(0)
            msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
        ready.write_text("ready")
        sys.stdin.buffer.read(1)


def capture(case, scratch):
    home = scratch / case["name"]
    home.mkdir()
    repo = home / "repo"
    seed(repo)
    if case.get("secret"):
        write(repo, ".mir/repo-profile.toml", '[boundaries]\nsecrets = ["a.py"]\n')
    wt = create_dispatch_worktree(repo, "fixture", brief_text="Fixture brief",
                                  worktrees_root=home / "trees")
    if not case.get("empty"):
        write(wt.path, "pkg/a.py", "a = 2\n")
    if case.get("inject") in {"merge", "restore", "rollback"}:
        write(wt.path, "pkg/new.py", "new = 2\n")
    if case.get("paths"):
        (wt.path / "pkg/delete.py").unlink()
        (wt.path / "pkg/rename-old.py").rename(wt.path / "pkg/rename-new.py")
        write(wt.path, "pkg/[ab].py", "literal changed\n")
    collision = case.get("collision")
    if collision in {"untracked", "ignored", "parent"}:
        target = {"untracked": "pkg/new.py", "ignored": "pkg/new.ignored",
                  "parent": "pkg/parent/new.py"}[collision]
        write(wt.path, target, "dispatch new\n")
        write(repo, "pkg/parent" if collision == "parent" else target, "main collision\n")
        if collision == "ignored":
            git(wt.path, "add", "-f", target)
    if collision in {"staged", "unstaged"}:
        write(repo, "pkg/a.py", "main wip\n")
        if collision == "staged":
            git(repo, "add", "pkg/a.py")
    if case.get("wip"):
        write(repo, "wip/staged.txt", "staged wip\n")
        git(repo, "add", "wip/staged.txt")
        write(repo, "wip/unstaged.txt", "unstaged wip\n")
        write(repo, "wip/untracked.txt", "untracked wip\n")
        write(repo, "wip/cache.ignored", "ignored wip\n")
    before = {"main": snapshot(repo), "dispatch": snapshot(wt.path)}
    injected = []

    def review(_wt, _files):
        drift = case.get("drift")
        if drift == "main":
            write(repo, "pkg/b.py", "main moved\n")
            git(repo, "add", "pkg/b.py")
            git(repo, "commit", "-qm", "main drift")
        elif drift == "dispatch":
            write(wt.path, "pkg/b.py", "dispatch moved\n")
            git(wt.path, "add", "pkg/b.py")
            git(wt.path, "commit", "-qm", "dispatch drift")
        elif drift == "dirty":
            write(wt.path, "pkg/b.py", "dispatch dirty\n")
        if drift:
            injected.append({"main": snapshot(repo), "dispatch": snapshot(wt.path)})
        return reference.ReviewEvidence(case.get("review") != "reject", "fixture-rejected"
                                        if case.get("review") == "reject" else "approved",
                                        "fixture review", "fixture")

    real_git = reference._git

    def refuse_restore(root, args, *, check=True):
        if "restore" in args and args[-1] == "pkg/a.py":
            injected.append({"main": snapshot(repo), "dispatch": snapshot(wt.path)})
            return subprocess.CompletedProcess(args, 1, "", "restore refused")
        return real_git(root, args, check=check)

    def partial_merge(*_args, **_kwargs):
        write(repo, "pkg/a.py", "partial merge\n")
        write(repo, "pkg/new.py", "new = 2\n")
        git(repo, "add", "pkg/a.py", "pkg/new.py")
        injected.append({"main": snapshot(repo), "dispatch": snapshot(wt.path)})
        raise RuntimeError("boom")

    def refuse_rollback(*_args, **_kwargs):
        injected.append({"main": snapshot(repo), "dispatch": snapshot(wt.path)})
        return ["target-residue"]

    def refuse_cleanup(*_args, **_kwargs):
        injected.append({"main": snapshot(repo), "dispatch": snapshot(wt.path)})
        raise RuntimeError("cleanup offline")

    def refuse_persist(*_args, **_kwargs):
        injected.append({"main": snapshot(repo), "dispatch": snapshot(wt.path)})
        raise RuntimeError("persist offline")

    registry = JobRegistry(home / "jobs.db")
    registry.insert(JobRecord(job_id="fixture-job", change_id="fixture", category="unit",
                              family=None, repo_root=str(repo), codex_args=[],
                              timeout_seconds=60, status="running"))
    holder = None
    try:
        with ExitStack() as stack:
            inject = case.get("inject")
            if inject in {"merge", "restore", "rollback"}:
                stack.enter_context(patch.object(reference, "merge_result", partial_merge))
            if inject == "restore":
                stack.enter_context(patch.object(reference, "_git", refuse_restore))
            if inject == "rollback":
                stack.enter_context(patch.object(reference, "_rollback_targets",
                                                 side_effect=refuse_rollback))
            if inject == "cleanup":
                stack.enter_context(patch.object(reference, "cleanup_worktree",
                                                 side_effect=refuse_cleanup))
            if inject == "persist":
                stack.enter_context(patch.object(reference, "persist_dispatch_artifacts",
                                                 side_effect=refuse_persist))
            if case.get("lock"):
                ready = home / "ready"
                holder = subprocess.Popen([sys.executable, __file__, "--hold-lock", str(repo),
                                           str(ready)], stdin=subprocess.PIPE)
                import time
                deadline = time.monotonic() + 20
                while not ready.exists() and time.monotonic() < deadline:
                    time.sleep(0.02)
                if not ready.exists():
                    raise RuntimeError("lock holder failed")
            outcome = reference.DispatchOutcome(case.get("outcome", "completed"), 1, False,
                                                 "fixture-blocked" if case.get("outcome") else None,
                                                 wt, exit_code=0)
            final = reference.finalize_dispatch(wt, repo, outcome, allowlist=["pkg/"],
                verification_commands=case.get("verification_commands", ["ok"]),
                expect_changes=case.get("expect_changes", True),
                artifacts_root=home / "artifacts", finalize_lock_timeout=0,
                require_review=case.get("require_review"),
                reviewer=review if case.get("review") or case.get("drift") else None)
        success = final.action in {"merged", "reviewed", "merged-but-cleanup-failed",
                                   "reviewed-but-cleanup-failed"}
        # Exact E3 registry API, mirroring cli.py's terminal mapping.
        registry.update_status("fixture-job", "completed" if success else "failed",
                               exit_code=0 if success else 1)
        job = registry.get("fixture-job")
        expected = dict(result=asdict(final), before=before, injected=injected,
                        after={"main": snapshot(repo), "dispatch": snapshot(wt.path)},
                        artifacts=sorted(p.name for p in (home / "artifacts/fixture").glob("*")),
                        registry={"status": job.status, "exit_code": job.exit_code})
        artifact_dir = home / "artifacts/fixture"
        expected["artifact_content"] = {
            name: json.loads((artifact_dir / name).read_text()) if name.endswith(".json")
            else (artifact_dir / name).read_text()
            for name in ("brief.md", "reviewer.json") if (artifact_dir / name).exists()
        }
    finally:
        registry.close()
        if holder:
            try:
                holder.communicate(b"x", timeout=20)
            except subprocess.TimeoutExpired:
                holder.kill()
                holder.communicate()
                raise
    return dict(case, expected=expected)


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "--hold-lock":
        hold_lock(Path(sys.argv[2]), Path(sys.argv[3]))
        return
    scratch = Path(os.environ["E9B_SCRATCH"])
    scratch.mkdir(parents=True, exist_ok=True)
    run = Path(tempfile.mkdtemp(prefix="oracle-", dir=scratch))
    tempfile.tempdir = str(run)
    try:
        cases = [capture(case, run) for case in CASES]
        target = Path(__file__).with_name("executor_finalize.json")
        target.write_text(json.dumps({"oracle": "tools/mir_executor/dispatch.py:finalize_dispatch",
                                     "files": FILES, "cases": cases}, indent=2) + "\n")
        print(f"captured {len(cases)} Python finalize cases")
    finally:
        shutil.rmtree(run)


if __name__ == "__main__":
    main()
