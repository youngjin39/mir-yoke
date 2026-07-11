"""Tests for deterministic stale-job and orphan-worktree sweeping."""

from __future__ import annotations

import datetime
import hashlib
import json
import pathlib
import subprocess

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
