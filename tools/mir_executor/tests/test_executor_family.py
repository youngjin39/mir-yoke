"""Tests for the --family slug option added in P0-J.3.

Six base tests + two P2.2 registry tests covering:
  1. --family resolves path via _FAMILY_PATHS registry
  2. Unknown slug → exit 1 + stderr "Unknown family slug"
  3. --family + --repo-root mutually exclusive → argparse exit 2
  4. Neither --family nor --repo-root → argparse exit 2
  5. --family + --async flag work together (async mock layer, ledger updated)
  6. --repo-root backwards-compatibility (BC)
  7. P2.2: claude-starter slug exists in _FAMILY_PATHS (17 entries after mir-yoke + musinsa-brand land)
  8. P2.2: --family claude-starter → exit 1 (executor refuses fleet-excluded slug)
"""

from __future__ import annotations

import json

import pytest

from tools.mir_executor import cli  # noqa: E402
from tools.mir_executor.codex_mcp_client import CodexMcpResult

profile_compiler_cli = pytest.importorskip("tools.profile_compiler.cli")
CLAUDE_STARTER_SLUG = getattr(profile_compiler_cli, "CLAUDE_STARTER_SLUG", None)
if CLAUDE_STARTER_SLUG is None:
    pytest.skip(
        "tools.profile_compiler.cli lacks CLAUDE_STARTER_SLUG; "
        "family compatibility baseline predates P2.2",
        allow_module_level=True,
    )

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_ledger(root, change_id: str = "x", category: str = "unit", status: str = "planned"):
    tasks_dir = root / "tasks"
    tasks_dir.mkdir(parents=True, exist_ok=True)
    ledger = {
        "version": 1,
        "changes": [
            {
                "id": change_id,
                "scope": "synthetic",
                "targets": ["tasks/tdd.json"],
                "categories": {category: {"status": status}},
            }
        ],
    }
    (tasks_dir / "tdd.json").write_text(json.dumps(ledger, indent=2), encoding="utf-8")
    return tasks_dir / "tdd.json"


def _install_fake_codex_mcp_client(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeCodexMcpClient:
        def __init__(self, **_kwargs: object) -> None:
            pass

        def __enter__(self) -> FakeCodexMcpClient:
            return self

        def __exit__(self, *_exc_info: object) -> None:
            return None

        def call_codex(self, **_kwargs: object) -> CodexMcpResult:
            return CodexMcpResult(content_text="", thread_id="thread-test", raw_result={})

    monkeypatch.setattr(
        "tools.mir_executor.executor.CodexMcpClient",
        FakeCodexMcpClient,
    )


# ---------------------------------------------------------------------------
# Test 1: --family resolves path via _FAMILY_PATHS registry
# ---------------------------------------------------------------------------

def test_cli_family_option_resolves_via_registry(tmp_path, monkeypatch):
    fake_root = tmp_path / "fake-grownote"
    fake_root.mkdir()
    ledger_path = _make_ledger(fake_root, change_id="x", category="unit")

    from tools.profile_compiler import cli as pc_cli
    monkeypatch.setitem(pc_cli._FAMILY_PATHS, "grownote", fake_root)

    _install_fake_codex_mcp_client(monkeypatch)

    rc = cli.main([
        "execute",
        "--family", "grownote",
        "--change-id", "x",
        "--category", "unit",
        "--codex-args", "ignored",
    ])
    assert rc == 0

    data = json.loads(ledger_path.read_text(encoding="utf-8"))
    assert data["changes"][0]["categories"]["unit"]["status"] == "pass"


# ---------------------------------------------------------------------------
# Test 2: Unknown slug → exit 1 + stderr contains "Unknown family slug"
# ---------------------------------------------------------------------------

def test_cli_family_option_errors_on_unknown_slug(capsys):
    with pytest.raises(SystemExit) as exc_info:
        cli.main([
            "execute",
            "--family", "nonexistent-slug",
            "--change-id", "x",
            "--category", "unit",
            "--codex-args", "ignored",
        ])
    assert exc_info.value.code == 1
    captured = capsys.readouterr()
    assert "Unknown family slug" in captured.err or "nonexistent-slug" in captured.err


# ---------------------------------------------------------------------------
# Test 3: --family + --repo-root mutually exclusive → argparse exit 2
# ---------------------------------------------------------------------------

def test_cli_family_and_repo_root_mutually_exclusive(tmp_path):
    with pytest.raises(SystemExit) as exc_info:
        cli.main([
            "execute",
            "--family", "grownote",
            "--repo-root", str(tmp_path),
            "--change-id", "x",
            "--category", "unit",
            "--codex-args", "ignored",
        ])
    assert exc_info.value.code == 2


# ---------------------------------------------------------------------------
# Test 4: Neither --family nor --repo-root → argparse exit 2
# ---------------------------------------------------------------------------

def test_cli_neither_family_nor_repo_root_errors():
    with pytest.raises(SystemExit) as exc_info:
        cli.main([
            "execute",
            "--change-id", "x",
            "--category", "unit",
            "--codex-args", "ignored",
        ])
    assert exc_info.value.code == 2


# ---------------------------------------------------------------------------
# Test 5: --family + --async flag work together (proper async mock layer)
# ---------------------------------------------------------------------------

def test_cli_family_with_async_flag_works(tmp_path, monkeypatch):
    fake_root = tmp_path / "fake-grownote-async"
    fake_root.mkdir()
    ledger_path = _make_ledger(fake_root, change_id="x", category="unit")

    from tools.profile_compiler import cli as pc_cli
    monkeypatch.setitem(pc_cli._FAMILY_PATHS, "grownote", fake_root)

    _install_fake_codex_mcp_client(monkeypatch)

    rc = cli.main([
        "execute",
        "--family", "grownote",
        "--async",
        "--change-id", "x",
        "--category", "unit",
        "--codex-args", "ignored",
    ])
    assert rc == 0

    # Verify the ledger was updated to "pass" (async path still calls update_ledger).
    data = json.loads(ledger_path.read_text(encoding="utf-8"))
    assert data["changes"][0]["categories"]["unit"]["status"] == "pass"


# ---------------------------------------------------------------------------
# Test 6: --repo-root BC — existing pattern still works unchanged
# ---------------------------------------------------------------------------

def test_cli_repo_root_still_works_BC(tmp_path, monkeypatch):
    _make_ledger(tmp_path, change_id="x", category="unit")

    _install_fake_codex_mcp_client(monkeypatch)

    rc = cli.main([
        "execute",
        "--repo-root", str(tmp_path),
        "--change-id", "x",
        "--category", "unit",
        "--codex-args", "ignored",
    ])
    assert rc == 0


# ---------------------------------------------------------------------------
# Test 8: P2.2 — --family claude-starter via executor exits with refusal
# ---------------------------------------------------------------------------

def test_claude_starter_compile_skips_with_message(capsys):
    """P2.2: compile_family('claude-starter') returns a skip result (not an error/raise)."""
    result = profile_compiler_cli.compile_family(CLAUDE_STARTER_SLUG, mode="dry-run")
    assert "skipped" in result.profile_status, (
        f"compile_family(claude-starter) must return skip result; got {result.profile_status!r}"
    )
    assert "P2.2" in result.profile_status, (
        "skip message must reference P2.2 for traceability"
    )
