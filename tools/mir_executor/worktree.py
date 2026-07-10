"""Per-dispatch git worktree lifecycle for ADR-60 R4 structural isolation.

Each Codex subprocess dispatch runs in its own git worktree so a sub-agent works
on a separate checkout and cannot physically edit the main worktree cursor at
``tasks/plan.md``. The worktree carries its own ``.mir-dispatch/brief.md``,
``status.json``, and ``result.json`` artifacts, while ``CODEX_EVENTS_FILE`` is
wired back to the main repository log for ADR-59 monitoring.

Design reference:
``docs/decisions/adr-60-claude-orchestrator-codex-subagent-execution-2026-06-22.md``
§5.2 and §13 row ``adr60-worktree``.
"""

from __future__ import annotations

import json
import os
import pathlib
import shutil
import subprocess
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass


@dataclass(frozen=True)
class DispatchWorktree:
    """Resolved paths and branch metadata for one isolated dispatch worktree."""

    dispatch_id: str
    main_repo_root: pathlib.Path
    path: pathlib.Path
    branch: str
    base_commit: str
    brief_path: pathlib.Path
    status_path: pathlib.Path
    result_path: pathlib.Path


@dataclass(frozen=True)
class MergeOutcome:
    """Files merged back to main and files deliberately skipped."""

    merged_files: list[str]
    skipped: list[str]


_AUTO_TEMP_BASES: set[pathlib.Path] = set()
HARNESS_DENY_PREFIXES = (".claude/", ".ai-harness/", "config/", "docs/", "tasks/")
LIFTABLE_HARNESS_PREFIXES = (".claude/", ".ai-harness/", "config/", "docs/")


def _is_denied_harness_path(path: str, *, allow_harness_self_modify: bool = False) -> bool:
    """Return True when a merge-back path targets control-plane harness state."""
    if path == "tasks/tdd.json":
        return False
    if allow_harness_self_modify and any(path.startswith(p) for p in LIFTABLE_HARNESS_PREFIXES):
        return False
    return any(path.startswith(prefix) for prefix in HARNESS_DENY_PREFIXES)


def _git(repo_root: pathlib.Path, args: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    """Run git with list arguments and captured text output."""
    return subprocess.run(
        ["git", "-C", str(repo_root), *args],
        check=check,
        capture_output=True,
        text=True,
    )


def _write_json(path: pathlib.Path, payload: dict) -> None:
    """Write a pretty JSON object with a trailing newline."""
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _read_json_object(path: pathlib.Path) -> dict:
    """Read a JSON object, treating absent or empty files as an empty object."""
    if not path.exists():
        return {}
    text = path.read_text(encoding="utf-8")
    if not text.strip():
        return {}
    data = json.loads(text)
    if not isinstance(data, dict):
        raise TypeError(f"expected JSON object in {path}")
    return data


def create_dispatch_worktree(
    main_repo_root: pathlib.Path,
    dispatch_id: str,
    *,
    base_commit: str = "HEAD",
    brief_text: str = "",
    worktrees_root: pathlib.Path | None = None,
) -> DispatchWorktree:
    """Create an isolated dispatch worktree and seed its dispatch artifacts."""
    main_repo_root = pathlib.Path(main_repo_root)
    base_sha = _git(main_repo_root, ["rev-parse", base_commit]).stdout.strip()

    auto_temp_base: pathlib.Path | None = None
    if worktrees_root is None:
        auto_temp_base = pathlib.Path(tempfile.mkdtemp(prefix="mir-wt-")).resolve()
        worktree_path = auto_temp_base / dispatch_id
        _AUTO_TEMP_BASES.add(auto_temp_base)
    else:
        root = pathlib.Path(worktrees_root)
        root.mkdir(parents=True, exist_ok=True)
        worktree_path = root / dispatch_id

    branch = f"mir-dispatch/{dispatch_id}"
    try:
        _git(
            main_repo_root,
            ["worktree", "add", "-b", branch, str(worktree_path), base_sha],
        )
    except Exception:
        if auto_temp_base is not None:
            _AUTO_TEMP_BASES.discard(auto_temp_base)
            shutil.rmtree(auto_temp_base, ignore_errors=True)
        raise

    profile_path = main_repo_root / ".mir" / "repo-profile.toml"
    if profile_path.is_file():
        worktree_profile_path = worktree_path / ".mir" / "repo-profile.toml"
        worktree_profile_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(profile_path, worktree_profile_path)

    dispatch_dir = worktree_path / ".mir-dispatch"
    dispatch_dir.mkdir(parents=True, exist_ok=True)
    brief_path = dispatch_dir / "brief.md"
    status_path = dispatch_dir / "status.json"
    result_path = dispatch_dir / "result.json"

    brief_path.write_text(brief_text, encoding="utf-8", errors="surrogatepass")
    _write_json(
        status_path,
        {
            "dispatch_id": dispatch_id,
            "state": "created",
            "base_commit": base_sha,
        },
    )

    return DispatchWorktree(
        dispatch_id=dispatch_id,
        main_repo_root=main_repo_root,
        path=worktree_path,
        branch=branch,
        base_commit=base_sha,
        brief_path=brief_path,
        status_path=status_path,
        result_path=result_path,
    )


def write_status(worktree: DispatchWorktree, state: str, **fields: object) -> None:
    """Merge a state update into the worktree-local status.json."""
    status = _read_json_object(worktree.status_path)
    status.update({"state": state, **fields})
    _write_json(worktree.status_path, status)


def merge_result(
    worktree: DispatchWorktree,
    *,
    commit_message: str | None = None,
    allow_harness_self_modify: bool = False,
) -> MergeOutcome:
    """Merge committed worktree branch changes into main, excluding harness state."""
    _ = commit_message
    changed_text = _git(
        worktree.main_repo_root,
        ["diff", "--name-only", worktree.base_commit, worktree.branch],
    ).stdout
    changed = [line for line in changed_text.splitlines() if line]

    merged_files: list[str] = []
    skipped: list[str] = []
    for path in changed:
        if path == "tasks/plan.md" or _is_denied_harness_path(
            path,
            allow_harness_self_modify=allow_harness_self_modify,
        ):
            skipped.append(path)
            continue
        _git(worktree.main_repo_root, ["checkout", worktree.branch, "--", path])
        merged_files.append(path)

    return MergeOutcome(merged_files=merged_files, skipped=skipped)


def cleanup_worktree(worktree: DispatchWorktree, *, delete_branch: bool = True) -> None:
    """Remove the dispatch worktree, prune metadata, and optionally delete its branch."""
    remove = _git(
        worktree.main_repo_root,
        ["worktree", "remove", "--force", str(worktree.path)],
        check=False,
    )
    if remove.returncode != 0 and worktree.path.exists():
        raise subprocess.CalledProcessError(
            remove.returncode,
            remove.args,
            output=remove.stdout,
            stderr=remove.stderr,
        )

    _git(worktree.main_repo_root, ["worktree", "prune"], check=False)

    if delete_branch:
        branch_delete = _git(
            worktree.main_repo_root,
            ["branch", "-D", worktree.branch],
            check=False,
        )
        if branch_delete.returncode != 0 and "not found" not in branch_delete.stderr:
            raise subprocess.CalledProcessError(
                branch_delete.returncode,
                branch_delete.args,
                output=branch_delete.stdout,
                stderr=branch_delete.stderr,
            )

    temp_base = worktree.path.parent
    if temp_base in _AUTO_TEMP_BASES:
        try:
            temp_base.rmdir()
        except OSError:
            pass
        else:
            _AUTO_TEMP_BASES.discard(temp_base)


def dispatch_env(
    main_repo_root: pathlib.Path,
    base_env: Mapping[str, str] | None = None,
    *,
    session_id: str | None = None,
) -> dict[str, str]:
    """Return an environment that points Codex shim events at the main repo log."""
    env = dict(os.environ if base_env is None else base_env)
    events_file = pathlib.Path(main_repo_root) / "tasks" / "codex-exec-events.jsonl"
    env["CODEX_EVENTS_FILE"] = str(events_file.resolve())
    if session_id is not None:
        env["MIR_CODEX_SESSION_ID"] = str(session_id)
    return env
