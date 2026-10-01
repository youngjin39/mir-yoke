"""Deterministic stale-job and orphan dispatch-worktree sweeping."""

from __future__ import annotations

import datetime
import pathlib
import re
import shutil
import subprocess
from dataclasses import dataclass

from tools.mir_executor.jobs import JobRecord, JobRegistry
from tools.mir_executor.local_hooks import local_config

_DISPATCH_BRANCH_PREFIX = "refs/heads/mir-dispatch/"


@dataclass(frozen=True)
class _ListedWorktree:
    path: pathlib.Path
    branch: str
    job_id: str


@dataclass(frozen=True)
class _RemovalInspection:
    tip: str | None
    status: str | None
    reasons: tuple[str, ...]

    @property
    def removable(self) -> bool:
        return not self.reasons


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
        values = {
            key: value for key, _, value in (field.partition(" ") for field in fields)
        }
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


def _inspect_removal_candidate(
    repo_root: pathlib.Path,
    listed: _ListedWorktree,
) -> _RemovalInspection:
    reasons: list[str] = []
    runtime_dir = listed.path / ".mir-dispatch"
    runtime_present = runtime_dir.exists() or runtime_dir.is_symlink()
    try:
        tip_result = subprocess.run(
            ["git", "-C", str(repo_root), "rev-parse", listed.branch],
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError:
        return _RemovalInspection(None, None, ("inspection-failed:branch-tip",))
    tip = tip_result.stdout.strip() if tip_result.returncode == 0 else None
    if tip is None:
        reasons.append("inspection-failed:branch-tip")
    else:
        try:
            ancestry = subprocess.run(
                [
                    "git",
                    "-C",
                    str(repo_root),
                    "merge-base",
                    "--is-ancestor",
                    tip,
                    "HEAD",
                ],
                check=False,
                capture_output=True,
                text=True,
            )
        except OSError:
            ancestry = None
        if ancestry is None:
            reasons.append("inspection-failed:ancestry")
        elif ancestry.returncode == 1:
            reasons.append("unique-commit")
        elif ancestry.returncode != 0:
            reasons.append("inspection-failed:ancestry")

    def read_status(pathspecs: list[str]) -> str | None:
        try:
            result = subprocess.run(
                [
                    "git",
                    "-C",
                    str(listed.path),
                    "status",
                    "--porcelain=v2",
                    "-z",
                    "--untracked-files=all",
                    "--ignored=matching",
                    "--",
                    *pathspecs,
                ],
                check=False,
                capture_output=True,
                text=True,
            )
        except OSError:
            return None
        return result.stdout if result.returncode == 0 else None

    status = read_status(["."])
    nonruntime_status = read_status(
        [
            ".",
            ":(exclude).mir-dispatch",
            ":(exclude).mir-dispatch/**",
        ]
    )
    if status is None or nonruntime_status is None:
        reasons.append("inspection-failed:status")
    else:
        if runtime_present:
            reasons.append("runtime-evidence-present")
        if nonruntime_status:
            reasons.append("worktree-dirty")
    return _RemovalInspection(tip, status, tuple(reasons))


def _remove_worktree_safely(
    repo_root: pathlib.Path,
    listed: _ListedWorktree,
) -> tuple[bool, str | None]:
    try:
        remove = subprocess.run(
            ["git", "-C", str(repo_root), "worktree", "remove", str(listed.path)],
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError:
        return False, "apply-time-drift:remove-inspection-failed"
    if remove.returncode != 0:
        return False, "apply-time-drift:remove-refused"

    try:
        branch_delete = subprocess.run(
            ["git", "-C", str(repo_root), "branch", "-d", listed.branch],
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError:
        return True, "branch-delete-inspection-failed"
    if branch_delete.returncode != 0:
        return True, "branch-delete-refused"
    return True, None


def _load_jobs(
    jobs_db: pathlib.Path, *, read_only: bool
) -> tuple[JobRegistry | None, list[JobRecord]]:
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
    """Report stale running jobs and reap only independently orphaned worktrees."""
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
        projected_failed: set[str] = set()

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
        inspections = {
            worktree.path: _inspect_removal_candidate(repo_root, worktree)
            for worktree in orphans
        }
        removable_worktrees = [
            str(worktree.path)
            for worktree in orphans
            if inspections[worktree.path].removable
        ]
        preserved_worktrees = [
            {
                "path": str(worktree.path),
                "reasons": list(inspections[worktree.path].reasons),
            }
            for worktree in orphans
            if not inspections[worktree.path].removable
        ]
        removed_worktrees: list[str] = []
        if apply:
            for worktree in orphans:
                initial = inspections[worktree.path]
                if not initial.removable:
                    continue
                repeated = _inspect_removal_candidate(repo_root, worktree)
                if not repeated.removable or repeated != initial:
                    preserved_worktrees.append(
                        {
                            "path": str(worktree.path),
                            "reasons": [
                                "apply-time-drift",
                                *repeated.reasons,
                            ],
                        }
                    )
                    continue
                removed, remove_reason = _remove_worktree_safely(repo_root, worktree)
                if removed:
                    removed_worktrees.append(str(worktree.path))
                    if remove_reason is not None:
                        errors.append(f"worktree {worktree.path}: {remove_reason}")
                else:
                    preserved_worktrees.append(
                        {
                            "path": str(worktree.path),
                            "reasons": [
                                remove_reason or "apply-time-drift:remove-refused"
                            ],
                        }
                    )
            preserved_paths = {item["path"] for item in preserved_worktrees}
            removable_worktrees = [
                path for path in removable_worktrees if path not in preserved_paths
            ]
    finally:
        if registry is not None:
            registry.close()

    return {
        "stale_jobs": stale_ids,
        "orphan_worktrees": orphan_paths,
        "removable_worktrees": removable_worktrees,
        "preserved_worktrees": preserved_worktrees,
        "reaped_jobs": reaped_jobs,
        "removed_worktrees": removed_worktrees,
        "errors": errors,
        "apply": apply,
    }


ARTIFACT_RETENTION_DAYS = 30
_JOB_ARTIFACT_ID = re.compile(r"^[0-9a-f]{32}$")


def sweep_terminal_artifacts(
    repo_root: pathlib.Path,
    jobs_db: pathlib.Path,
    *,
    now: datetime.datetime | None = None,
    retention_days: int | None = None,
    apply: bool = False,
) -> dict[str, object]:
    """Sweep expired terminal-job artifact directories, never silently.

    Ledger-driven: only a directory named exactly by a terminal job's
    validated hex identity or recorded attempt identity under ``tasks/dispatch``
    is ever a candidate, so
    an owner file or foreign name in that directory can never be matched.
    A running job, a missing ``completed_at``, or a directory symlink is
    skipped. On ``apply`` each removal writes one ``artifact_sweeps``
    evidence row (files, bytes, timestamp) in the jobs ledger.
    """
    repo_root = pathlib.Path(repo_root).resolve()
    jobs_db = pathlib.Path(jobs_db).resolve()
    now = now or datetime.datetime.now(datetime.UTC)
    if now.tzinfo is None:
        now = now.replace(tzinfo=datetime.UTC)
    else:
        now = now.astimezone(datetime.UTC)
    if retention_days is None:
        retention_days = local_config(repo_root).get(
            "artifact_retention_days", ARTIFACT_RETENTION_DAYS
        )
    if (
        isinstance(retention_days, bool)
        or not isinstance(retention_days, int)
        or retention_days < 0
    ):
        raise ValueError("artifact_retention_days must be a non-negative integer")
    floor = now - datetime.timedelta(days=retention_days)
    dispatch_root = repo_root / "tasks" / "dispatch"
    if (repo_root / "tasks").is_symlink() or dispatch_root.is_symlink():
        return {
            "retention_days": retention_days,
            "expired": [],
            "removed": [],
            "errors": ["artifact root is a symlink"],
        }

    expired: list[str] = []
    removed: list[str] = []
    errors: list[str] = []
    registry, jobs = _load_jobs(jobs_db, read_only=not apply)
    try:
        for job in jobs:
            if job.status == "running" or not job.completed_at:
                continue
            if _JOB_ARTIFACT_ID.fullmatch(job.job_id) is None:
                continue
            try:
                completed = datetime.datetime.fromisoformat(job.completed_at)
            except ValueError:
                errors.append(f"unparseable completed_at for {job.job_id}")
                continue
            if completed.tzinfo is None:
                completed = completed.replace(tzinfo=datetime.UTC)
            if completed >= floor:
                continue
            dispatch_ids = {job.job_id}
            metadata = job.ai_run_metadata or {}
            history = metadata.get("dispatch_ids", [])
            if isinstance(history, list):
                dispatch_ids.update(
                    item
                    for item in history
                    if isinstance(item, str) and _JOB_ARTIFACT_ID.fullmatch(item)
                )
            current = metadata.get("dispatch_id")
            if isinstance(current, str) and _JOB_ARTIFACT_ID.fullmatch(current):
                dispatch_ids.add(current)
            for dispatch_id in sorted(dispatch_ids):
                artifact_dir = dispatch_root / dispatch_id
                if artifact_dir.is_symlink() or not artifact_dir.is_dir():
                    continue
                expired.append(dispatch_id)
                if not apply:
                    continue
                files = 0
                size_bytes = 0
                for entry in artifact_dir.rglob("*"):
                    if entry.is_file() and not entry.is_symlink():
                        files += 1
                        size_bytes += entry.stat().st_size
                assert registry is not None
                # Record intent before deleting: an interruption between
                # the two steps must leave a recorded intent and a still-present
                # directory -- never a silently vanished one. A rerun after such
                # a crash reuses the existing row instead of stacking duplicates.
                already_recorded = registry.has_artifact_sweep(
                    job.job_id, path=str(artifact_dir)
                )
                if not already_recorded:
                    registry.record_artifact_sweep(
                        job.job_id,
                        str(artifact_dir),
                        files,
                        size_bytes,
                        now.isoformat(),
                    )
                # Re-check the shape immediately before removal to shrink the
                # check-to-use window.
                if artifact_dir.is_symlink() or not artifact_dir.is_dir():
                    errors.append(f"remove {dispatch_id}: shape changed before removal")
                    continue
                try:
                    shutil.rmtree(artifact_dir)
                except OSError as exc:
                    errors.append(f"remove {dispatch_id}: {exc}")
                    continue
                removed.append(dispatch_id)
    finally:
        if registry is not None:
            registry.close()
    return {
        "retention_days": retention_days,
        "expired": sorted(expired),
        "removed": sorted(removed),
        "errors": errors,
    }
