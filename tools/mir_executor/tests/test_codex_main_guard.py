from __future__ import annotations

import json
import pathlib
import shutil
import subprocess

import pytest

from tools.mir_executor.codex_mcp_client import CodexMcpResult
from tools.mir_executor.executor import MirExecutor

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]


def _write_codex_shim(tmp_path: pathlib.Path) -> pathlib.Path:
    shim = tmp_path / "codex-shim.sh"
    shim.write_text('#!/bin/sh\nprintf "%s\\n" "$@"\n', encoding="utf-8")
    shim.chmod(0o755)
    return shim


def _install_fake_codex_mcp_client(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, object]]:
    calls: list[dict[str, object]] = []

    class FakeCodexMcpClient:
        def __init__(self, **_kwargs: object) -> None:
            pass

        def __enter__(self) -> FakeCodexMcpClient:
            return self

        def __exit__(self, *_exc_info: object) -> None:
            return None

        def call_codex(self, **kwargs: object) -> CodexMcpResult:
            calls.append(kwargs)
            return CodexMcpResult(content_text="ok", thread_id="thread-test", raw_result={})

    monkeypatch.setattr(
        "tools.mir_executor.executor.CodexMcpClient",
        FakeCodexMcpClient,
    )
    return calls


def _main_worktree_root() -> pathlib.Path:
    completed = subprocess.run(
        ["git", "-C", str(_REPO_ROOT), "rev-parse", "--git-common-dir"],
        capture_output=True,
        text=True,
        check=True,
    )
    common_dir = pathlib.Path(completed.stdout.strip())
    if not common_dir.is_absolute():
        common_dir = _REPO_ROOT / common_dir
    common_dir = common_dir.resolve()
    if common_dir.name == ".git":
        return common_dir.parent

    completed = subprocess.run(
        ["git", "-C", str(_REPO_ROOT), "rev-parse", "--show-toplevel"],
        capture_output=True,
        text=True,
        check=True,
    )
    return pathlib.Path(completed.stdout.strip()).resolve()


def _make_ledger(tmp_path: pathlib.Path) -> pathlib.Path:
    tasks_dir = tmp_path / "tasks"
    tasks_dir.mkdir()
    ledger_path = tasks_dir / "tdd.json"
    ledger_path.write_text(
        json.dumps(
            {
                "version": 1,
                "changes": [
                    {
                        "id": "test-change-id",
                        "scope": "synthetic guard test entry",
                        "targets": ["tools/mir_executor/executor.py"],
                        "categories": {"unit": {"status": "planned"}},
                    }
                ],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return ledger_path


def _clone_current_repo(tmp_path: pathlib.Path) -> pathlib.Path:
    clone_path = tmp_path / "repo-clone"
    subprocess.run(
        ["git", "clone", "--quiet", "--no-hardlinks", str(_REPO_ROOT), str(clone_path)],
        capture_output=True,
        text=True,
        check=True,
    )
    return clone_path


def _remove_worktree(repo_root: pathlib.Path, worktree_path: pathlib.Path) -> None:
    subprocess.run(
        ["git", "-C", str(repo_root), "worktree", "remove", "--force", str(worktree_path)],
        capture_output=True,
        text=True,
        check=False,
    )
    if worktree_path.exists():
        shutil.rmtree(worktree_path)


def test_run_codex_allows_linked_worktree_cwd(tmp_path, monkeypatch):
    shim = _write_codex_shim(tmp_path)
    calls = _install_fake_codex_mcp_client(monkeypatch)
    monkeypatch.setenv("CODEX_BIN", str(shim))
    monkeypatch.delenv("MIR_CODEX_MAIN", raising=False)

    repo_clone = _clone_current_repo(tmp_path)
    worktree_path = tmp_path / "linked-worktree"
    try:
        subprocess.run(
            [
                "git",
                "-C",
                str(repo_clone),
                "worktree",
                "add",
                "--detach",
                str(worktree_path),
                "HEAD",
            ],
            capture_output=True,
            text=True,
            check=True,
        )

        codex_args = ["exec", "echo", "ok"]
        result = MirExecutor(repo_root=worktree_path).run_codex(
            codex_args,
            cwd=worktree_path,
        )

        assert result.exit_code == 0
        assert result.command == [str(shim), "mcp-server", "codex", "echo ok"]
        assert calls[0]["cwd"] == worktree_path.resolve()
    finally:
        _remove_worktree(repo_clone, worktree_path)


def test_run_codex_allows_main_worktree_with_main_marker(tmp_path, monkeypatch):
    shim = _write_codex_shim(tmp_path)
    main_root = _main_worktree_root()
    _install_fake_codex_mcp_client(monkeypatch)
    monkeypatch.setenv("CODEX_BIN", str(shim))
    monkeypatch.setenv("MIR_CODEX_MAIN", "1")

    result = MirExecutor(repo_root=main_root).run_codex(
        ["exec", "echo", "main"],
        cwd=main_root,
    )

    assert result.exit_code == 0


def test_run_codex_refuses_main_worktree_without_main_marker(tmp_path, monkeypatch):
    shim = _write_codex_shim(tmp_path)
    main_root = _main_worktree_root()
    monkeypatch.setenv("CODEX_BIN", str(shim))
    monkeypatch.delenv("MIR_CODEX_MAIN", raising=False)

    with pytest.raises(RuntimeError, match="ADR-60 section 16 D3"):
        MirExecutor(repo_root=main_root).run_codex(
            ["exec", "echo", "refuse"],
            cwd=main_root,
        )


def test_execute_refuses_main_worktree_without_main_marker(tmp_path, monkeypatch):
    shim = _write_codex_shim(tmp_path)
    ledger_path = _make_ledger(tmp_path)
    main_root = _main_worktree_root()
    monkeypatch.setenv("CODEX_BIN", str(shim))
    monkeypatch.delenv("MIR_CODEX_MAIN", raising=False)
    monkeypatch.chdir(main_root)

    executor = MirExecutor(repo_root=main_root, ledger_path=ledger_path)

    with pytest.raises(RuntimeError, match="ADR-60 section 16 D3"):
        executor.execute("test-change-id", "unit", ["exec", "echo", "resume"])
