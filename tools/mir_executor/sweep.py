"""Deterministic stale-job and orphan dispatch-worktree sweeping."""

from __future__ import annotations

import datetime
import pathlib
import subprocess
from dataclasses import dataclass

from tools.mir_executor.jobs import JobRecord, JobRegistry
from tools.mir_executor.worktree import DispatchWorktree, cleanup_worktree

_DISPATCH_BRANCH_PREFIX = "refs/heads/mir-dispatch/"


@dataclass(frozen=True)
class _ListedWorktree:
    path: pathlib.Path
    branch: str
    job_id: str


def _list_dispatch_worktrees(repo_root: pathlib.Path) -> list[_ListedWorktree]:
    result = subprocess.run(
        ["git", "-C", str(repo_root), "worktree", "list", "--porcelain", "-z"],
        check=True,
        capture_output=True,
        text=True,
    )
    main_path = repo_root.resolve()
    worktrees: list[_ListedWorktree] = []
    for record in result.stdout.split("\0\0"):
        fields = record.strip("\0").split("\0")
        values = {key: value for key, _, value in (field.partition(" ") for field in fields)}
        path_text = values.get("worktree")
        branch_ref = values.get("branch", "")
        if path_text is None or not branch_ref.startswith(_DISPATCH_BRANCH_PREFIX):
            continue
        path = pathlib.Path(path_text).resolve()
        if path == main_path:
            continue
        worktrees.append(
            _ListedWorktree(
                path=path,
                branch=branch_ref.removeprefix("refs/heads/"),
                job_id=branch_ref.removeprefix(_DISPATCH_BRANCH_PREFIX),
            )
        )
    return sorted(worktrees, key=lambda item: str(item.path))


def _cleanup_record(repo_root: pathlib.Path, listed: _ListedWorktree) -> DispatchWorktree:
    dispatch_dir = listed.path / ".mir-dispatch"
    return DispatchWorktree(
        dispatch_id=listed.job_id,
        main_repo_root=repo_root,
        path=listed.path,
        branch=listed.branch,
        base_commit="",
        brief_path=dispatch_dir / "brief.md",
        status_path=dispatch_dir / "status.json",
        result_path=dispatch_dir / "result.json",
    )


def _load_jobs(jobs_db: pathlib.Path, *, read_only: bool) -> tuple[JobRegistry | None, list[JobRecord]]:
    if read_only and not jobs_db.exists():
        return None, []
    registry = JobRegistry(jobs_db, read_only=read_only)
    return registry, registry.list_jobs()


def sweep_run_state(
    repo_root: pathlib.Path,
    jobs_db: pathlib.Path,
    *,
    now: datetime.datetime | None = None,
    grace_seconds: int = 120,
    apply: bool = False,
) -> dict[str, object]:
    """Report or reap stale running jobs and orphan dispatch worktrees."""
    repo_root = pathlib.Path(repo_root).resolve()
    jobs_db = pathlib.Path(jobs_db).resolve()
    now = now or datetime.datetime.now(datetime.UTC)
    if now.tzinfo is None:
        now = now.replace(tzinfo=datetime.UTC)
    else:
        now = now.astimezone(datetime.UTC)
    errors: list[str] = []

    registry, jobs = _load_jobs(jobs_db, read_only=not apply)
    try:
        stale = registry.find_stale(now, grace_seconds) if registry is not None else []
        stale_ids = sorted(job.job_id for job in stale)
        reaped_jobs: list[str] = []
        projected_failed = set(stale_ids) if not apply else set()
        if apply and registry is not None:
            for job_id in stale_ids:
                try:
                    registry.update_status(
                        job_id,
                        "failed",
                        stderr="stale-reaped",
                        completed_at=now.isoformat(),
                    )
                    reaped_jobs.append(job_id)
                    projected_failed.add(job_id)
                except Exception as exc:  # noqa: BLE001
                    errors.append(f"stale job {job_id}: {exc}")

        jobs_by_id = {job.job_id: job for job in jobs}
        try:
            listed_worktrees = _list_dispatch_worktrees(repo_root)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"list worktrees: {exc}")
            listed_worktrees = []
        orphans = [
            worktree
            for worktree in listed_worktrees
            if worktree.job_id not in jobs_by_id
            or jobs_by_id[worktree.job_id].status != "running"
            or worktree.job_id in projected_failed
        ]
        orphan_paths = [str(worktree.path) for worktree in orphans]
        removed_worktrees: list[str] = []
        if apply:
            for worktree in orphans:
                try:
                    cleanup_worktree(_cleanup_record(repo_root, worktree))
                    removed_worktrees.append(str(worktree.path))
                except Exception as exc:  # noqa: BLE001
                    errors.append(f"worktree {worktree.path}: {exc}")
    finally:
        if registry is not None:
            registry.close()

    return {
        "stale_jobs": stale_ids,
        "orphan_worktrees": orphan_paths,
        "reaped_jobs": reaped_jobs,
        "removed_worktrees": removed_worktrees,
        "errors": errors,
        "apply": apply,
    }
