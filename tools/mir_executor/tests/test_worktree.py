"""Tests for ADR-60 dispatch worktree isolation helpers."""

from __future__ import annotations

import json
import pathlib
import subprocess

import pytest

from tools.mir_executor.worktree import (
    HARNESS_DENY_PREFIXES,
    LIFTABLE_HARNESS_PREFIXES,
    _is_denied_harness_path,
    cleanup_worktree,
    create_dispatch_worktree,
    dispatch_env,
    merge_result,
    read_result,
    write_result,
)


def _git(repo_root: pathlib.Path, *args: str) -> subprocess.CompletedProcess[str]:
    """Run git in a temp test repository."""
    return subprocess.run(
        ["git", "-C", str(repo_root), *args],
        check=True,
        capture_output=True,
        text=True,
    )


def _make_repo(tmp_path: pathlib.Path) -> pathlib.Path:
    """Build a real temp git repo with a plan cursor and one code file."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init")
    _git(repo, "config", "user.email", "t@e")
    _git(repo, "config", "user.name", "t")

    (repo / "tasks").mkdir()
    (repo / "pkg").mkdir()
    (repo / "tasks" / "plan.md").write_text("MAIN-PLAN-V1\n", encoding="utf-8")
    (repo / "pkg" / "mod.py").write_text("x = 1\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", "init")
    return repo


def _write_repo_file(repo_root: pathlib.Path, path: str, text: str) -> None:
    target = repo_root / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")


def test_create_makes_isolated_checkout(tmp_path: pathlib.Path) -> None:
    repo = _make_repo(tmp_path)
    wt = create_dispatch_worktree(repo, "create", brief_text="brief text")
    try:
        assert wt.path.is_dir()
        assert str(wt.path) in _git(repo, "worktree", "list").stdout
        assert wt.brief_path.read_text(encoding="utf-8") == "brief text"
        status = json.loads(wt.status_path.read_text(encoding="utf-8"))
        assert status["state"] == "created"
    finally:
        cleanup_worktree(wt)


def test_create_copies_gitignored_repo_profile(tmp_path: pathlib.Path) -> None:
    repo = _make_repo(tmp_path)
    (repo / ".gitignore").write_text(".mir/\n", encoding="utf-8")
    _git(repo, "add", ".gitignore")
    _git(repo, "commit", "-m", "ignore mir")

    profile_text = '[repo]\nrepository_type = "meta_harness"\n'
    profile_path = repo / ".mir" / "repo-profile.toml"
    profile_path.parent.mkdir(parents=True)
    profile_path.write_text(profile_text, encoding="utf-8")
    (profile_path.parent / "memory.db").write_bytes(b"do-not-copy")

    assert not _git(repo, "ls-files", ".mir/repo-profile.toml").stdout.strip()

    wt = create_dispatch_worktree(repo, "copy-profile")
    try:
        worktree_profile = wt.path / ".mir" / "repo-profile.toml"
        assert worktree_profile.is_file()
        assert not worktree_profile.is_symlink()
        assert worktree_profile.read_text(encoding="utf-8") == profile_text
        assert not (wt.path / ".mir" / "memory.db").exists()
    finally:
        cleanup_worktree(wt)


def test_structural_isolation_plan_edit_does_not_touch_main(tmp_path: pathlib.Path) -> None:
    repo = _make_repo(tmp_path)
    original = (repo / "tasks" / "plan.md").read_bytes()
    wt = create_dispatch_worktree(repo, "isolation")
    try:
        (wt.path / "tasks" / "plan.md").write_text(
            "WORKTREE-PLAN-DIFFERENT\n",
            encoding="utf-8",
        )
        assert (repo / "tasks" / "plan.md").read_bytes() == original
    finally:
        cleanup_worktree(wt)


def test_read_result_roundtrip_and_absent(tmp_path: pathlib.Path) -> None:
    repo = _make_repo(tmp_path)
    wt = create_dispatch_worktree(repo, "result")
    try:
        assert read_result(wt) is None
        write_result(wt, {"status": "ok", "n": 3})
        assert read_result(wt) == {"status": "ok", "n": 3}
    finally:
        cleanup_worktree(wt)


def test_merge_brings_code_excludes_plan_md(tmp_path: pathlib.Path) -> None:
    repo = _make_repo(tmp_path)
    wt = create_dispatch_worktree(repo, "merge")
    try:
        (wt.path / "pkg" / "mod.py").write_text("x = 2\n", encoding="utf-8")
        (wt.path / "tasks" / "plan.md").write_text(
            "WORKTREE-PLAN-DIFFERENT\n",
            encoding="utf-8",
        )
        _git(wt.path, "add", "-A")
        _git(wt.path, "commit", "-m", "change")

        outcome = merge_result(wt)

        assert (repo / "pkg" / "mod.py").read_text(encoding="utf-8") == "x = 2\n"
        assert (repo / "tasks" / "plan.md").read_text(encoding="utf-8") == "MAIN-PLAN-V1\n"
        assert "tasks/plan.md" in outcome.skipped
        assert "pkg/mod.py" in outcome.merged_files
    finally:
        cleanup_worktree(wt)


def test_harness_deny_prefixes_are_pinned() -> None:
    assert HARNESS_DENY_PREFIXES == (".claude/", ".ai-harness/", "config/", "docs/", "tasks/")
    assert _is_denied_harness_path(".ai-harness/development-ai-rules.md")
    assert _is_denied_harness_path("tasks/other.json")
    assert not _is_denied_harness_path("tasks/tdd.json")
    assert not _is_denied_harness_path("tools/mir_executor/worktree.py")


@pytest.mark.parametrize(
    "path",
    [
        ".claude/x",
        "config/x",
        "docs/y",
        ".ai-harness/z",
    ],
)
def test_is_denied_harness_source_lifted_for_meta_harness(path: str) -> None:
    assert _is_denied_harness_path(path)
    assert not _is_denied_harness_path(path, allow_harness_self_modify=True)


def test_is_denied_control_plane_state_never_lifted() -> None:
    for path in (
        "tasks/plan.md",
        "tasks/checklist.md",
        "tasks/lessons.md",
        "tasks/dispatch/abc/result.json",
    ):
        assert _is_denied_harness_path(path, allow_harness_self_modify=True)

    assert not _is_denied_harness_path("tasks/tdd.json", allow_harness_self_modify=True)
    assert not _is_denied_harness_path("tasks/tdd.json")


def test_liftable_prefixes_are_pinned() -> None:
    assert LIFTABLE_HARNESS_PREFIXES == (".claude/", ".ai-harness/", "config/", "docs/")
    assert "tasks/" not in LIFTABLE_HARNESS_PREFIXES


@pytest.mark.parametrize(
    "denied_path",
    [
        ".claude/agents/executor-agent.md",
        "config/repo-agent-management.json",
        "docs/decisions/example.md",
    ],
)
def test_merge_excludes_denied_harness_paths(tmp_path: pathlib.Path, denied_path: str) -> None:
    repo = _make_repo(tmp_path)
    _write_repo_file(repo, denied_path, "MAIN\n")
    _git(repo, "add", denied_path)
    _git(repo, "commit", "-m", "seed denied path")

    wt = create_dispatch_worktree(repo, f"merge-denied-{denied_path.split('/')[0].strip('.')}")
    try:
        _write_repo_file(wt.path, denied_path, "WORKTREE\n")
        (wt.path / "pkg" / "mod.py").write_text("x = 11\n", encoding="utf-8")
        _git(wt.path, "add", "-A")
        _git(wt.path, "commit", "-m", "change denied and code")

        outcome = merge_result(wt)

        assert (repo / denied_path).read_text(encoding="utf-8") == "MAIN\n"
        assert (repo / "pkg" / "mod.py").read_text(encoding="utf-8") == "x = 11\n"
        assert denied_path in outcome.skipped
        assert "pkg/mod.py" in outcome.merged_files
    finally:
        cleanup_worktree(wt)


def test_merge_result_meta_harness_merges_source_but_skips_plan(tmp_path: pathlib.Path) -> None:
    repo = _make_repo(tmp_path)
    wt = create_dispatch_worktree(repo, "merge-meta-harness-source")
    source_path = ".claude/agents/example.md"
    try:
        _write_repo_file(wt.path, source_path, "WORKTREE\n")
        (wt.path / "tasks" / "plan.md").write_text(
            "WORKTREE-PLAN-DIFFERENT\n",
            encoding="utf-8",
        )
        _git(wt.path, "add", "-A")
        _git(wt.path, "commit", "-m", "change harness source and plan")

        default_outcome = merge_result(wt)

        assert source_path in default_outcome.skipped
        assert "tasks/plan.md" in default_outcome.skipped
        assert source_path not in default_outcome.merged_files
        assert not (repo / source_path).exists()

        meta_outcome = merge_result(wt, allow_harness_self_modify=True)

        assert source_path in meta_outcome.merged_files
        assert "tasks/plan.md" in meta_outcome.skipped
        assert (repo / source_path).read_text(encoding="utf-8") == "WORKTREE\n"
        assert (repo / "tasks" / "plan.md").read_text(encoding="utf-8") == "MAIN-PLAN-V1\n"
    finally:
        cleanup_worktree(wt)


def test_merge_allows_tasks_tdd_json(tmp_path: pathlib.Path) -> None:
    repo = _make_repo(tmp_path)
    wt = create_dispatch_worktree(repo, "merge-tdd")
    try:
        (wt.path / "tasks" / "tdd.json").write_text('{"version": 1}\n', encoding="utf-8")
        _git(wt.path, "add", "tasks/tdd.json")
        _git(wt.path, "commit", "-m", "change tdd ledger")

        outcome = merge_result(wt)

        assert (repo / "tasks" / "tdd.json").read_text(encoding="utf-8") == '{"version": 1}\n'
        assert "tasks/tdd.json" in outcome.merged_files
        assert "tasks/tdd.json" not in outcome.skipped
    finally:
        cleanup_worktree(wt)


def test_cleanup_removes_worktree(tmp_path: pathlib.Path) -> None:
    repo = _make_repo(tmp_path)
    wt = create_dispatch_worktree(repo, "cleanup")

    cleanup_worktree(wt)

    assert not wt.path.exists()
    assert str(wt.path) not in _git(repo, "worktree", "list").stdout


def test_cleanup_idempotent(tmp_path: pathlib.Path) -> None:
    repo = _make_repo(tmp_path)
    wt = create_dispatch_worktree(repo, "idempotent")

    cleanup_worktree(wt)
    cleanup_worktree(wt)


def test_dispatch_env_points_events_file_at_main_log(tmp_path: pathlib.Path) -> None:
    repo = _make_repo(tmp_path)

    assert dispatch_env(repo)["CODEX_EVENTS_FILE"] == str(
        (repo / "tasks" / "codex-exec-events.jsonl").resolve()
    )
