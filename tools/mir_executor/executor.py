"""
executor.py
-----------
MirExecutor: MCP-backed Codex runner + tdd.json ledger update.

Design inspiration: harness_framework (Hermes pattern) — no code copied.
P0-J MVP: blocking runner only. Async / Stop hook wiring deferred to P0-J.1.
"""

from __future__ import annotations

import asyncio
import json
import os
import pathlib
import shlex
import subprocess
import tempfile
import time
from collections.abc import Mapping
from dataclasses import dataclass

from mir.core.conductor.dispatch_brief import (
    codex_args_from_dispatch_brief,
    load_dispatch_brief,
)
from mir.core.contracts.dispatch_brief import DispatchBrief
from tools.mir_executor.codex_mcp_client import (
    CodexMcpClient,
    CodexMcpError,
    CodexMcpTimeoutError,
)
from tools.mir_executor.dispatch import _MCP_DISPATCH_BASE_INSTRUCTIONS

_CODEX_EXEC_FLAGS_WITH_VALUE = frozenset(
    {
        "--approval",
        "--approval-policy",
        "--add-dir",
        "--cd",
        "--color",
        "--config",
        "--config-profile",
        "--cwd",
        "--disable",
        "--enable",
        "--image",
        "--local-provider",
        "--model",
        "--output-last-message",
        "--output-schema",
        "--profile",
        "--reasoning-effort",
        "--sandbox",
        "-C",
        "-c",
        "-i",
        "-m",
        "-o",
        "-p",
        "-s",
    }
)
_CODEX_EXEC_BOOLEAN_FLAGS = frozenset(
    {
        "--dangerously-bypass-approvals-and-sandbox",
        "--dangerously-bypass-hook-trust",
        "--ephemeral",
        "--full-auto",
        "--help",
        "--ignore-rules",
        "--ignore-user-config",
        "--json",
        "--no-color",
        "--oss",
        "--skip-git-repo-check",
        "--strict-config",
        "--version",
        "-V",
        "-h",
    }
)


def _prompt_from_codex_args(codex_args: list[str]) -> str:
    """Extract the prompt positional from an exec-shaped Codex argv."""
    prompt_parts: list[str] = []
    index = 0
    while index < len(codex_args):
        token = codex_args[index]
        if token == "--":
            prompt_parts = codex_args[index + 1 :]
            break
        if token == "exec" and not prompt_parts:
            index += 1
            continue

        flag_name = token.split("=", 1)[0]
        if flag_name in _CODEX_EXEC_FLAGS_WITH_VALUE:
            index += 1 if "=" in token else 2
            continue
        if flag_name in _CODEX_EXEC_BOOLEAN_FLAGS:
            index += 1
            continue
        if token.startswith("-") and not prompt_parts:
            index += 1
            continue

        prompt_parts = codex_args[index:]
        break

    if len(prompt_parts) == 1:
        return prompt_parts[0]
    return " ".join(prompt_parts).strip()


def _codex_mcp_command(codex_bin: str, prompt: str) -> list[str]:
    """Return a representative command list for result/ledger reporting."""
    command = [codex_bin, "mcp-server", "codex"]
    if prompt:
        command.append(prompt)
    return command


def _codex_mcp_config(reasoning_effort: str | None = None) -> dict[str, object]:
    """Return the lightweight MCP config, optionally pinning reasoning effort."""
    config: dict[str, object] = {"project_doc_max_bytes": 0}
    if reasoning_effort is not None:
        config["model_reasoning_effort"] = reasoning_effort
    return config


def _is_linked_worktree(cwd: os.PathLike[str] | str) -> bool:
    """Return True when cwd is a git linked worktree."""
    cwd_path = pathlib.Path(cwd).resolve()
    try:
        completed = subprocess.run(
            ["git", "-C", str(cwd_path), "rev-parse", "--git-common-dir"],
            capture_output=True,
            text=True,
            check=True,
            shell=False,
        )
    except (OSError, subprocess.CalledProcessError):
        return False

    common_dir_text = completed.stdout.strip()
    if not common_dir_text:
        return False

    common_dir = pathlib.Path(common_dir_text)
    if not common_dir.is_absolute():
        common_dir = cwd_path / common_dir
    common_dir = common_dir.resolve()

    try:
        common_dir.relative_to(cwd_path)
    except ValueError:
        return True
    return False


def _guard_codex_main_worktree(
    cwd: os.PathLike[str] | str,
    env: Mapping[str, str],
) -> None:
    """Refuse delegated Codex in the main worktree unless explicitly marked main."""
    if env.get("MIR_CODEX_MAIN") == "1":
        return
    if _is_linked_worktree(cwd):
        return
    raise RuntimeError(
        "Delegated Codex refused in the main worktree per ADR-60 section 16 D3. "
        "Delegated execution must go through `mir_executor execute --background --dispatch`, "
        "which uses an R4 worktree, or set MIR_CODEX_MAIN=1 for the main process "
        "itself, such as loop_driver."
    )


def _ledger_entry_for(ledger: dict, change_id: str) -> dict | None:
    changes = ledger.get("changes")
    if isinstance(changes, list):
        for item in changes:
            if item.get("id") == change_id:
                return item

    entry = ledger.get(change_id)
    if isinstance(entry, dict):
        return entry
    return None


@dataclass
class SubprocessResult:
    exit_code: int
    stdout: str
    stderr: str
    duration_seconds: float
    command: list[str]


@dataclass
class LedgerUpdate:
    change_id: str
    category: str
    previous_status: str | None
    new_status: str
    notes: str


class MirExecutor:
    def __init__(
        self,
        repo_root: pathlib.Path,
        ledger_path: pathlib.Path | None = None,
        dispatch_brief_path: pathlib.Path | None = None,
    ) -> None:
        """ledger_path defaults to repo_root / 'tasks' / 'tdd.json'."""
        self._repo_root = repo_root
        self._ledger_path = (
            ledger_path if ledger_path is not None else repo_root / "tasks" / "tdd.json"
        )
        self._dispatch_brief_path = dispatch_brief_path

    def load_dispatch_brief(self) -> DispatchBrief | None:
        if self._dispatch_brief_path is None:
            return None
        if not self._dispatch_brief_path.exists():
            raise FileNotFoundError(
                f"DispatchBrief not found: {self._dispatch_brief_path}. "
                "Persist the handoff artifact before invoking the executor lane."
            )
        return load_dispatch_brief(self._dispatch_brief_path)

    def resolve_codex_args(self, codex_args: list[str]) -> list[str]:
        if codex_args:
            return list(codex_args)
        brief = self.load_dispatch_brief()
        if brief is None:
            return []
        return list(codex_args_from_dispatch_brief(brief))

    def run_codex(
        self,
        codex_args: list[str],
        timeout_seconds: int = 600,
        *,
        cwd: os.PathLike[str] | str | None = None,
        model: str | None = None,
        reasoning_effort: str | None = None,
        stall_timeout: float | None = None,
    ) -> SubprocessResult:
        """Run Codex through the MCP backend (blocking).

        Maps the MCP response into the existing SubprocessResult contract.
        Raises FileNotFoundError with clear message if binary missing.
        Raises subprocess.TimeoutExpired on timeout (not swallowed).
        """
        resolved_cwd = pathlib.Path.cwd() if cwd is None else pathlib.Path(cwd)
        resolved_cwd = resolved_cwd.resolve()
        _guard_codex_main_worktree(resolved_cwd, os.environ)
        codex_bin = os.environ.get("CODEX_BIN", "codex")
        prompt = _prompt_from_codex_args(self.resolve_codex_args(codex_args))
        command = _codex_mcp_command(codex_bin, prompt)

        start = time.monotonic()
        try:
            with CodexMcpClient(
                codex_bin=codex_bin,
                call_timeout=float(timeout_seconds),
            ) as client:
                call_kwargs: dict[str, object] = {
                    "prompt": prompt,
                    "cwd": resolved_cwd,
                    "sandbox": "danger-full-access",
                    "approval_policy": "never",
                    "base_instructions": _MCP_DISPATCH_BASE_INSTRUCTIONS,
                    "config": _codex_mcp_config(reasoning_effort),
                    "timeout": float(timeout_seconds),
                }
                if model is not None:
                    call_kwargs["model"] = model
                if stall_timeout is not None:
                    call_kwargs["stall_timeout"] = stall_timeout
                result = client.call_codex(**call_kwargs)
        except CodexMcpTimeoutError as exc:
            raise subprocess.TimeoutExpired(
                cmd=command,
                timeout=timeout_seconds,
                output="",
                stderr=str(exc),
            ) from exc
        except FileNotFoundError as exc:
            raise FileNotFoundError(
                f"Codex binary not found: {codex_bin!r}. "
                "Set CODEX_BIN to the full path of the codex executable."
            ) from exc
        except CodexMcpError as exc:
            duration = time.monotonic() - start
            return SubprocessResult(
                exit_code=1,
                stdout="",
                stderr=str(exc),
                duration_seconds=duration,
                command=command,
            )
        duration = time.monotonic() - start

        return SubprocessResult(
            exit_code=0,
            stdout=result.content_text,
            stderr="",
            duration_seconds=duration,
            command=command,
        )

    def _validate_ledger_entry(self, change_id: str, category: str) -> dict:
        """Read ledger and validate change_id + category exist.

        Returns the matching entry dict so callers can reuse it.
        Raises FileNotFoundError if ledger file is missing.
        Raises KeyError if change_id not in changes[].
        Raises KeyError if category not in entry's categories dict.
        Raises ValueError if category status is 'not_applicable'.
        """
        if not self._ledger_path.exists():
            raise FileNotFoundError(
                f"Ledger not found: {self._ledger_path}. "
                "Create tasks/tdd.json with a planned entry before calling execute."
            )

        ledger = json.loads(self._ledger_path.read_text(encoding="utf-8"))
        entry = _ledger_entry_for(ledger, change_id)

        if entry is None:
            raise KeyError(
                f"unknown change_id {change_id!r} in {self._ledger_path}. "
                "Add a TDD entry for this id before executing."
            )

        categories: dict = entry.get("categories", {})
        if category not in categories:
            raise KeyError(
                f"category {category!r} not in entry {change_id!r}. "
                "Declare the category in tdd.json before updating it (do not silently add)."
            )

        if categories[category].get("status") == "not_applicable":
            raise ValueError(
                f"category {category!r} is marked not_applicable; cannot run executor on it. "
                "Edit tdd.json manually if you intend to reclassify."
            )

        return entry

    def update_ledger(
        self,
        change_id: str,
        category: str,
        result: SubprocessResult,
    ) -> LedgerUpdate:
        """Find entry by id in tdd.json. Update categories[category] with status/command/notes.

        Atomic write: write to temp file in same dir, then os.replace().
        Raises FileNotFoundError if ledger_path missing.
        Raises KeyError if change_id not found in changes[].
        Raises KeyError if category not in entry's categories dict.
        Raises ValueError if category status is 'not_applicable'.
        Returns LedgerUpdate with previous_status snapshot.
        """
        # Re-validate after Codex returns (idempotent — re-reads from disk).
        self._validate_ledger_entry(change_id, category)

        ledger = json.loads(self._ledger_path.read_text(encoding="utf-8"))
        entry = _ledger_entry_for(ledger, change_id)

        categories: dict = entry.get("categories", {})

        previous_status: str | None = categories[category].get("status")
        new_status = "pass" if result.exit_code == 0 else "fail"
        command_str = " ".join(shlex.quote(p) for p in result.command)
        notes = (
            f"P0-J auto: rc={result.exit_code}, "
            f"stderr first 200 chars: {result.stderr[:200]!r}"
        )

        categories[category] = {
            "status": new_status,
            "command": command_str,
            "notes": notes,
        }

        updated_text = json.dumps(ledger, indent=2, ensure_ascii=False) + "\n"

        ledger_dir = self._ledger_path.parent
        fd, tmp_path = tempfile.mkstemp(dir=ledger_dir, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(updated_text)
            os.replace(tmp_path, self._ledger_path)
        except Exception:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise

        return LedgerUpdate(
            change_id=change_id,
            category=category,
            previous_status=previous_status,
            new_status=new_status,
            notes=notes,
        )

    def execute(
        self,
        change_id: str,
        category: str,
        codex_args: list[str],
        timeout_seconds: int = 600,
        *,
        model: str | None = None,
        reasoning_effort: str | None = None,
        stall_timeout: float | None = None,
    ) -> tuple[SubprocessResult, LedgerUpdate]:
        """Convenience: run_codex + update_ledger together.

        Validates change_id + category BEFORE invoking Codex so a typo'd id
        fails within seconds instead of after a multi-minute Codex run (W3).
        """
        # Fast-fail: validate before the expensive Codex subprocess.
        self._validate_ledger_entry(change_id, category)
        run_kwargs: dict[str, object] = {"timeout_seconds": timeout_seconds}
        if model is not None:
            run_kwargs["model"] = model
        if reasoning_effort is not None:
            run_kwargs["reasoning_effort"] = reasoning_effort
        if stall_timeout is not None:
            run_kwargs["stall_timeout"] = stall_timeout
        result = self.run_codex(codex_args, **run_kwargs)
        update = self.update_ledger(change_id, category, result)
        return result, update

    async def run_codex_async(
        self,
        codex_args: list[str],
        timeout_seconds: int = 600,
        *,
        cwd: os.PathLike[str] | str | None = None,
        model: str | None = None,
        reasoning_effort: str | None = None,
        stall_timeout: float | None = None,
    ) -> SubprocessResult:
        """Async variant of run_codex using the MCP backend in a worker thread.

        Single call: prefer sync run_codex. Multi-call or long-running: use this.
        On timeout: TimeoutError (caller catches both sync and async timeout classes
        when mixing sync and async paths).
        Raises FileNotFoundError with clear message if binary missing.
        """
        resolved_cwd = pathlib.Path.cwd() if cwd is None else pathlib.Path(cwd)
        resolved_cwd = resolved_cwd.resolve()
        _guard_codex_main_worktree(resolved_cwd, os.environ)
        return await asyncio.to_thread(
            self._run_codex_mcp_for_async,
            codex_args,
            timeout_seconds,
            resolved_cwd,
            model,
            reasoning_effort,
            stall_timeout,
        )

    def _run_codex_mcp_for_async(
        self,
        codex_args: list[str],
        timeout_seconds: int,
        resolved_cwd: pathlib.Path,
        model: str | None,
        reasoning_effort: str | None,
        stall_timeout: float | None,
    ) -> SubprocessResult:
        """Run the shared MCP call for the async wrapper without timeout remapping."""
        codex_bin = os.environ.get("CODEX_BIN", "codex")
        prompt = _prompt_from_codex_args(self.resolve_codex_args(codex_args))
        command = _codex_mcp_command(codex_bin, prompt)
        start = time.monotonic()
        try:
            with CodexMcpClient(
                codex_bin=codex_bin,
                call_timeout=float(timeout_seconds),
            ) as client:
                call_kwargs: dict[str, object] = {
                    "prompt": prompt,
                    "cwd": resolved_cwd,
                    "sandbox": "danger-full-access",
                    "approval_policy": "never",
                    "base_instructions": _MCP_DISPATCH_BASE_INSTRUCTIONS,
                    "config": _codex_mcp_config(reasoning_effort),
                    "timeout": float(timeout_seconds),
                }
                if model is not None:
                    call_kwargs["model"] = model
                if stall_timeout is not None:
                    call_kwargs["stall_timeout"] = stall_timeout
                result = client.call_codex(**call_kwargs)
        except CodexMcpTimeoutError:
            raise
        except FileNotFoundError as exc:
            raise FileNotFoundError(
                f"Codex binary not found: {codex_bin!r}. "
                "Set CODEX_BIN to the full path of the codex executable."
            ) from exc
        except CodexMcpError as exc:
            duration = time.monotonic() - start
            return SubprocessResult(
                exit_code=1,
                stdout="",
                stderr=str(exc),
                duration_seconds=duration,
                command=command,
            )

        duration = time.monotonic() - start

        return SubprocessResult(
            exit_code=0,
            stdout=result.content_text,
            stderr="",
            duration_seconds=duration,
            command=command,
        )

    async def execute_async(
        self,
        change_id: str,
        category: str,
        codex_args: list[str],
        timeout_seconds: int = 600,
        *,
        model: str | None = None,
        reasoning_effort: str | None = None,
        stall_timeout: float | None = None,
    ) -> tuple[SubprocessResult, LedgerUpdate]:
        """Async variant of execute: validate + run_codex_async + update_ledger.

        _validate_ledger_entry is sync (file IO; async benefit minimal).
        update_ledger is sync (atomic write via tempfile + os.replace).
        """
        # Fast-fail: validate before the expensive async Codex subprocess.
        self._validate_ledger_entry(change_id, category)
        run_kwargs: dict[str, object] = {"timeout_seconds": timeout_seconds}
        if model is not None:
            run_kwargs["model"] = model
        if reasoning_effort is not None:
            run_kwargs["reasoning_effort"] = reasoning_effort
        if stall_timeout is not None:
            run_kwargs["stall_timeout"] = stall_timeout
        result = await self.run_codex_async(codex_args, **run_kwargs)
        update = self.update_ledger(change_id, category, result)
        return result, update
