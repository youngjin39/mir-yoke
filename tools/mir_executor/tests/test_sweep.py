"""Tests for deterministic stale-job and orphan-worktree sweeping."""

from __future__ import annotations

import datetime
import hashlib
import json
import pathlib
import subprocess

import pytest

from tools.mir_executor import sweep as sweep_module
from tools.mir_executor.cli import main
from tools.mir_executor.jobs import JobRecord, JobRegistry
from tools.mir_executor.sweep import sweep_run_state

UTC = datetime.UTC
STARTED = datetime.datetime(2026, 7, 11, 0, 0, tzinfo=UTC)


def _job(
    job_id: str,
    repo_root: pathlib.Path,
    *,
    status: str = "running",
    started_at: str = STARTED.isoformat(),
    timeout_seconds: int = 60,
) -> JobRecord:
    return JobRecord(
        job_id=job_id,
        change_id="runstate-sweep-test",
        category="transaction_locking",
        family=None,
        repo_root=str(repo_root),
        codex_args=[],
        timeout_seconds=timeout_seconds,
        status=status,
        started_at=started_at,
    )


def _git(repo: pathlib.Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout


def _repo(tmp_path: pathlib.Path) -> pathlib.Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Test User")
    (repo / "tracked.txt").write_text("initial\n", encoding="utf-8")
    _git(repo, "add", "tracked.txt")
    _git(repo, "commit", "-m", "initial")
    return repo


def _worktree(repo: pathlib.Path, tmp_path: pathlib.Path, job_id: str) -> pathlib.Path:
    path = tmp_path / f"worktree-{job_id}"
    _git(repo, "worktree", "add", "-b", f"mir-dispatch/{job_id}", str(path), "HEAD")
    return path.resolve()


def _digest(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_find_stale_uses_strict_timeout_boundary(tmp_path: pathlib.Path) -> None:
    repo = _repo(tmp_path)
    registry = JobRegistry(tmp_path / "jobs.db")
    registry.insert(_job("boundary", repo))

    assert registry.find_stale(STARTED + datetime.timedelta(seconds=179), 120) == []
    assert [
        job.job_id
        for job in registry.find_stale(STARTED + datetime.timedelta(seconds=181), 120)
    ] == ["boundary"]
    registry.close()


def test_dry_run_detects_orphan_and_mutates_nothing(tmp_path: pathlib.Path) -> None:
    repo = _repo(tmp_path)
    orphan = _worktree(repo, tmp_path, "missing-job")
    jobs_db = tmp_path / "jobs.db"
    registry = JobRegistry(jobs_db)
    registry.insert(_job("stale-job", repo))
    registry.close()
    db_before = _digest(jobs_db)
    worktrees_before = _git(repo, "worktree", "list", "--porcelain")

    result = sweep_run_state(
        repo,
        jobs_db,
        now=STARTED + datetime.timedelta(seconds=181),
        grace_seconds=120,
        apply=False,
    )

    assert result["stale_jobs"] == ["stale-job"]
    assert result["orphan_worktrees"] == [str(orphan)]
    assert result["reaped_jobs"] == []
    assert result["removed_worktrees"] == []
    assert _digest(jobs_db) == db_before
    assert _git(repo, "worktree", "list", "--porcelain") == worktrees_before
    registry = JobRegistry(jobs_db)
    assert registry.get("stale-job").status == "running"  # type: ignore[union-attr]
    registry.close()


def test_apply_reaps_stale_job_removes_orphan_and_second_apply_is_noop(
    tmp_path: pathlib.Path,
) -> None:
    repo = _repo(tmp_path)
    orphan = _worktree(repo, tmp_path, "finished-job")
    jobs_db = tmp_path / "jobs.db"
    registry = JobRegistry(jobs_db)
    registry.insert(_job("stale-job", repo))
    registry.insert(_job("finished-job", repo, status="completed"))
    registry.close()

    result = sweep_run_state(
        repo,
        jobs_db,
        now=STARTED + datetime.timedelta(seconds=181),
        grace_seconds=120,
        apply=True,
    )

    assert result["reaped_jobs"] == ["stale-job"]
    assert result["removed_worktrees"] == [str(orphan)]
    assert result["errors"] == []
    assert not orphan.exists()
    registry = JobRegistry(jobs_db)
    stale = registry.get("stale-job")
    assert stale is not None
    assert stale.status == "failed"
    assert stale.stderr == "stale-reaped"
    registry.close()

    second = sweep_run_state(
        repo,
        jobs_db,
        now=STARTED + datetime.timedelta(seconds=181),
        grace_seconds=120,
        apply=True,
    )
    assert second["stale_jobs"] == []
    assert second["orphan_worktrees"] == []
    assert second["reaped_jobs"] == []
    assert second["removed_worktrees"] == []


def test_apply_preserves_orphan_with_unique_commit(tmp_path: pathlib.Path) -> None:
    repo = _repo(tmp_path)
    orphan = _worktree(repo, tmp_path, "unique-commit")
    (orphan / "tracked.txt").write_text("unique\n", encoding="utf-8")
    _git(orphan, "add", "tracked.txt")
    _git(orphan, "commit", "-m", "unique work")

    result = sweep_run_state(repo, tmp_path / "jobs.db", apply=True)

    assert result["removed_worktrees"] == []
    assert result["preserved_worktrees"] == [
        {"path": str(orphan), "reasons": ["unique-commit"]}
    ]
    assert orphan.exists()
    assert _git(repo, "show-ref", "--verify", "refs/heads/mir-dispatch/unique-commit")


@pytest.mark.parametrize(
    "dirty_kind",
    ["tracked", "staged", "untracked", "ignored"],
)
def test_apply_preserves_orphan_with_non_runtime_dirt(
    tmp_path: pathlib.Path,
    dirty_kind: str,
) -> None:
    repo = _repo(tmp_path)
    orphan = _worktree(repo, tmp_path, f"dirty-{dirty_kind}")
    if dirty_kind == "tracked":
        (orphan / "tracked.txt").write_text("dirty\n", encoding="utf-8")
    elif dirty_kind == "staged":
        (orphan / "staged.txt").write_text("staged\n", encoding="utf-8")
        _git(orphan, "add", "staged.txt")
    elif dirty_kind == "untracked":
        (orphan / "untracked.txt").write_text("untracked\n", encoding="utf-8")
    else:
        (repo / ".git" / "info" / "exclude").write_text("*.ignored\n", encoding="utf-8")
        (orphan / "cache.ignored").write_text("ignored\n", encoding="utf-8")

    result = sweep_run_state(repo, tmp_path / "jobs.db", apply=True)

    assert result["removed_worktrees"] == []
    assert result["preserved_worktrees"] == [
        {"path": str(orphan), "reasons": ["worktree-dirty"]}
    ]
    assert orphan.exists()


def test_apply_reinspection_preserves_toctou_dirty_worktree(
    tmp_path: pathlib.Path,
    monkeypatch,
) -> None:
    repo = _repo(tmp_path)
    orphan = _worktree(repo, tmp_path, "toctou")
    real_inspect = sweep_module._inspect_removal_candidate
    calls = 0

    def mutate_before_second_inspection(repo_root, listed):
        nonlocal calls
        calls += 1
        if calls == 2:
            (orphan / "late.txt").write_text("late dirt\n", encoding="utf-8")
        return real_inspect(repo_root, listed)

    monkeypatch.setattr(sweep_module, "_inspect_removal_candidate", mutate_before_second_inspection)

    result = sweep_run_state(repo, tmp_path / "jobs.db", apply=True)

    assert result["removed_worktrees"] == []
    assert result["preserved_worktrees"] == [
        {"path": str(orphan), "reasons": ["apply-time-drift", "worktree-dirty"]}
    ]
    assert orphan.exists()


def test_eligible_apply_uses_only_non_force_removal(
    tmp_path: pathlib.Path,
    monkeypatch,
) -> None:
    repo = _repo(tmp_path)
    orphan = _worktree(repo, tmp_path, "safe-remove")
    real_run = subprocess.run
    commands: list[list[str]] = []

    def record_run(command, **kwargs):
        commands.append(list(command))
        return real_run(command, **kwargs)

    monkeypatch.setattr(sweep_module.subprocess, "run", record_run)

    result = sweep_run_state(repo, tmp_path / "jobs.db", apply=True)

    assert result["removed_worktrees"] == [str(orphan)]
    removal = next(command for command in commands if command[-3:-1] == ["worktree", "remove"])
    branch_delete = next(command for command in commands if command[-3:-1] == ["branch", "-d"])
    assert "--force" not in removal
    assert "-D" not in branch_delete


def test_apply_preserves_candidate_when_inspection_fails(
    tmp_path: pathlib.Path,
    monkeypatch,
) -> None:
    repo = _repo(tmp_path)
    orphan = _worktree(repo, tmp_path, "inspection-failure")
    real_run = subprocess.run

    def fail_branch_inspection(command, **kwargs):
        if "rev-parse" in command and "mir-dispatch/inspection-failure" in command:
            raise OSError("inspection unavailable")
        return real_run(command, **kwargs)

    monkeypatch.setattr(sweep_module.subprocess, "run", fail_branch_inspection)

    result = sweep_run_state(repo, tmp_path / "jobs.db", apply=True)

    assert result["removed_worktrees"] == []
    assert result["preserved_worktrees"] == [
        {"path": str(orphan), "reasons": ["inspection-failed:branch-tip"]}
    ]
    assert orphan.exists()


def test_runtime_evidence_is_preserved_byte_identically(
    tmp_path: pathlib.Path,
) -> None:
    repo = _repo(tmp_path)
    orphan = _worktree(repo, tmp_path, "runtime-evidence")
    runtime = orphan / ".mir-dispatch"
    runtime.mkdir()
    (runtime / "status.json").write_bytes(b'{"state":"complete"}\n')
    before = _digest(runtime / "status.json")

    result = sweep_run_state(repo, tmp_path / "jobs.db", apply=True)

    assert result["removed_worktrees"] == []
    assert result["removable_worktrees"] == []
    assert result["preserved_worktrees"] == [
        {"path": str(orphan), "reasons": ["runtime-evidence-present"]}
    ]
    assert _digest(runtime / "status.json") == before
    assert orphan.exists()


def test_remove_refusal_preserves_clean_candidate(
    tmp_path: pathlib.Path,
    monkeypatch,
) -> None:
    repo = _repo(tmp_path)
    orphan = _worktree(repo, tmp_path, "remove-refused")
    real_run = subprocess.run

    def refuse_remove(command, **kwargs):
        if "worktree" in command and "remove" in command:
            raise OSError("remove unavailable")
        return real_run(command, **kwargs)

    monkeypatch.setattr(sweep_module.subprocess, "run", refuse_remove)
    result = sweep_run_state(repo, tmp_path / "jobs.db", apply=True)

    assert result["removed_worktrees"] == []
    assert result["removable_worktrees"] == []
    assert result["preserved_worktrees"] == [
        {
            "path": str(orphan),
            "reasons": ["apply-time-drift:remove-inspection-failed"],
        }
    ]
    assert orphan.exists()


def test_live_running_job_and_its_worktree_are_preserved(tmp_path: pathlib.Path) -> None:
    repo = _repo(tmp_path)
    live_worktree = _worktree(repo, tmp_path, "live-job")
    jobs_db = tmp_path / "jobs.db"
    registry = JobRegistry(jobs_db)
    registry.insert(_job("live-job", repo))
    registry.close()

    result = sweep_run_state(
        repo,
        jobs_db,
        now=STARTED + datetime.timedelta(seconds=179),
        grace_seconds=120,
        apply=True,
    )

    assert result["stale_jobs"] == []
    assert result["orphan_worktrees"] == []
    assert live_worktree.exists()


def test_unparseable_started_at_is_skipped(tmp_path: pathlib.Path) -> None:
    repo = _repo(tmp_path)
    jobs_db = tmp_path / "jobs.db"
    registry = JobRegistry(jobs_db)
    registry.insert(_job("bad-time", repo, started_at="not-a-time"))
    registry.close()

    result = sweep_run_state(repo, jobs_db, now=STARTED, apply=True)

    assert result["stale_jobs"] == []
    registry = JobRegistry(jobs_db)
    assert registry.get("bad-time").status == "running"  # type: ignore[union-attr]
    registry.close()


def test_cli_prints_one_json_line_and_defaults_to_dry_run(
    tmp_path: pathlib.Path, capsys
) -> None:
    repo = _repo(tmp_path)
    orphan = _worktree(repo, tmp_path, "missing-job")
    jobs_db = tmp_path / "jobs.db"
    registry = JobRegistry(jobs_db)
    registry.close()

    assert main(
        [
            "sweep",
            "--repo-root",
            str(repo),
            "--jobs-db",
            str(jobs_db),
            "--grace-seconds",
            "120",
        ]
    ) == 0

    lines = capsys.readouterr().out.splitlines()
    assert len(lines) == 1
    payload = json.loads(lines[0])
    assert payload["apply"] is False
    assert payload["orphan_worktrees"] == [str(orphan)]
    assert orphan.exists()
