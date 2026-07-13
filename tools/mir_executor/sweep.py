"""Deterministic stale-job and orphan dispatch-worktree sweeping."""

from __future__ import annotations

import datetime
import pathlib
import subprocess
from dataclasses import dataclass

from tools.mir_executor.jobs import JobRecord, JobRegistry

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
            preserved_paths = {
                item["path"]
                for item in preserved_worktrees
            }
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
