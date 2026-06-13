"""
executor.py
-----------
MirExecutor: Codex CLI subprocess wrapper + tdd.json ledger update.

Design inspiration: an internal harness executor pattern — no code copied.
P0-J MVP: blocking subprocess only. Async / Stop hook wiring deferred to P0-J.1.
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
from dataclasses import dataclass

from mir.core.conductor.dispatch_brief import (
    codex_args_from_dispatch_brief,
    load_dispatch_brief,
)
from mir.core.contracts.dispatch_brief import DispatchBrief


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
    ) -> SubprocessResult:
        """Run ``${CODEX_BIN:-codex} *codex_args`` via subprocess.run (blocking).

        Captures stdout/stderr (text mode). Returns SubprocessResult.
        Raises FileNotFoundError with clear message if binary missing.
        Raises subprocess.TimeoutExpired on timeout (not swallowed).
        """
        codex_bin = os.environ.get("CODEX_BIN", "codex")
        command = [codex_bin, *self.resolve_codex_args(codex_args)]

        start = time.monotonic()
        try:
            completed = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
                shell=False,
            )
        except FileNotFoundError as exc:
            raise FileNotFoundError(
                f"Codex binary not found: {codex_bin!r}. "
                "Set CODEX_BIN to the full path of the codex executable."
            ) from exc
        duration = time.monotonic() - start

        return SubprocessResult(
            exit_code=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
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
        changes: list[dict] = ledger.get("changes", [])

        entry: dict | None = None
        for ch in changes:
            if ch.get("id") == change_id:
                entry = ch
                break

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
        changes: list[dict] = ledger.get("changes", [])

        entry: dict | None = None
        for ch in changes:
            if ch.get("id") == change_id:
                entry = ch
                break

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
    ) -> tuple[SubprocessResult, LedgerUpdate]:
        """Convenience: run_codex + update_ledger together.

        Validates change_id + category BEFORE invoking Codex so a typo'd id
        fails within seconds instead of after a multi-minute Codex run (W3).
        """
        # Fast-fail: validate before the expensive Codex subprocess.
        self._validate_ledger_entry(change_id, category)
        result = self.run_codex(codex_args, timeout_seconds=timeout_seconds)
        update = self.update_ledger(change_id, category, result)
        return result, update

    async def run_codex_async(
        self,
        codex_args: list[str],
        timeout_seconds: int = 600,
    ) -> SubprocessResult:
        """Async variant of run_codex using asyncio.create_subprocess_exec.

        Single call: prefer sync run_codex. Multi-call or long-running: use this.
        On timeout: asyncio.TimeoutError (not subprocess.TimeoutExpired — caller catches both
        when mixing sync and async paths).
        Raises FileNotFoundError with clear message if binary missing.
        """
        codex_bin = os.environ.get("CODEX_BIN", "codex")
        resolved_args = self.resolve_codex_args(codex_args)
        command = [codex_bin, *resolved_args]

        start = time.monotonic()
        try:
            proc = await asyncio.create_subprocess_exec(
                codex_bin,
                *resolved_args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except FileNotFoundError as exc:
            raise FileNotFoundError(
                f"Codex binary not found: {codex_bin!r}. "
                "Set CODEX_BIN to the full path of the codex executable."
            ) from exc

        try:
            raw_stdout, raw_stderr = await asyncio.wait_for(
                proc.communicate(), timeout=timeout_seconds
            )
        except TimeoutError:
            try:
                proc.kill()
            except ProcessLookupError:
                pass
            try:
                await asyncio.wait_for(proc.communicate(), timeout=5.0)
            except Exception:
                pass  # best-effort pipe/transport drain before the event loop closes
            try:
                await asyncio.wait_for(proc.wait(), timeout=5.0)
            except Exception:
                pass  # best-effort cleanup; do not mask the original timeout
            raise

        duration = time.monotonic() - start

        return SubprocessResult(
            exit_code=proc.returncode,
            stdout=raw_stdout.decode("utf-8", errors="replace"),
            stderr=raw_stderr.decode("utf-8", errors="replace"),
            duration_seconds=duration,
            command=command,
        )

    async def execute_async(
        self,
        change_id: str,
        category: str,
        codex_args: list[str],
        timeout_seconds: int = 600,
    ) -> tuple[SubprocessResult, LedgerUpdate]:
        """Async variant of execute: validate + run_codex_async + update_ledger.

        _validate_ledger_entry is sync (file IO; async benefit minimal).
        update_ledger is sync (atomic write via tempfile + os.replace).
        """
        # Fast-fail: validate before the expensive async Codex subprocess.
        self._validate_ledger_entry(change_id, category)
        result = await self.run_codex_async(codex_args, timeout_seconds=timeout_seconds)
        update = self.update_ledger(change_id, category, result)
        return result, update
