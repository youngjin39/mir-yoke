"""
executor.py
-----------
MirExecutor: app-server-backed Codex runner + tdd.json ledger update.

Design inspiration: harness_framework (Hermes pattern) — no code copied.
P0-J lineage: blocking executor MVP; ADR-69 bans raw exec delegation, so Codex
runs through codex_mcp_client.py.
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
from contextlib import nullcontext
from dataclasses import dataclass

from tools.mir_executor.codex_mcp_client import (
    CodexMcpClient,
    CodexMcpError,
    CodexMcpTimeoutError,
)
from tools.mir_executor.dispatch import (
    _MCP_DISPATCH_BASE_INSTRUCTIONS,
    AgentRoute,
    resolve_agent_route,
)
from tools.mir_executor.local_hooks import (
    after_provider_call,
    invoke_hook,
    local_config,
    validate_timeout,
    writer_scope,
)
from tools.mir_executor.worktree import child_env

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


def _codex_mcp_command(codex_bin: str) -> list[str]:
    """Return a representative command list for result/ledger reporting."""
    return [codex_bin, "app-server"]


def _codex_mcp_config(reasoning_effort: str | None = None) -> dict[str, object]:
    """Return the lightweight app-server config, optionally pinning reasoning effort."""
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


async def _drain_worker(task: asyncio.Task) -> None:
    """Keep inherited leases held until cleanup finishes, even on repeated cancel."""
    while not task.done():
        try:
            await asyncio.shield(task)
        except asyncio.CancelledError:
            continue
        except BaseException:
            break
    try:
        task.result()
    except BaseException:
        pass


class MirExecutor:
    def __init__(
        self,
        repo_root: pathlib.Path,
        ledger_path: pathlib.Path | None = None,
        dispatch_brief_path: pathlib.Path | None = None,
        target_agent: str | None = None,
        agent_route: AgentRoute | None = None,
    ) -> None:
        """ledger_path defaults to repo_root / 'tasks' / 'tdd.json'."""
        self._repo_root = repo_root
        self._ledger_path = (
            ledger_path if ledger_path is not None else repo_root / "tasks" / "tdd.json"
        )
        self._dispatch_brief_path = dispatch_brief_path
        self._target_agent = target_agent
        if (
            agent_route is not None
            and target_agent is not None
            and agent_route.target_agent != target_agent
        ):
            raise ValueError("agent_route and target_agent must identify the same agent")
        self._agent_route = agent_route

    @property
    def repo_root(self) -> pathlib.Path:
        """Repository whose mutations share a writer lease."""
        return self._repo_root

    def resolve_agent_route(self) -> AgentRoute | None:
        """Resolve only an explicitly selected agent through the common route seam."""
        if self._agent_route is not None:
            return self._agent_route
        if self._target_agent is None:
            return None
        return resolve_agent_route(self._repo_root, self._target_agent)

    def _writer_scope(self, route: AgentRoute | None):
        return (
            nullcontext()
            if route is not None and route.sandbox == "read-only"
            else writer_scope(self._repo_root)
        )

    def load_dispatch_brief(self) -> object | None:
        if self._dispatch_brief_path is None:
            return None
        if not self._dispatch_brief_path.exists():
            raise FileNotFoundError(
                f"DispatchBrief not found: {self._dispatch_brief_path}. "
                "Persist the handoff artifact before invoking the executor lane."
            )
        validated = invoke_hook(
            self._repo_root, "validate_brief", self._dispatch_brief_path, self._repo_root
        )
        if validated is not None:
            return validated
        payload = json.loads(self._dispatch_brief_path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("Dispatch brief must contain a JSON object")
        return payload

    def resolve_codex_args(self, codex_args: list[str]) -> list[str]:
        if codex_args:
            return list(codex_args)
        brief = self.load_dispatch_brief()
        if brief is None:
            return []
        goal = (
            brief.get("expanded_goal")
            if isinstance(brief, Mapping)
            else getattr(brief, "expanded_goal", None)
        )
        if not isinstance(goal, str) or not goal.strip():
            raise ValueError("Dispatch brief must contain a non-empty expanded_goal")
        return ["exec", goal]

    def run_codex(
        self,
        codex_args: list[str],
        timeout_seconds: int | None = None,
        *,
        cwd: os.PathLike[str] | str | None = None,
        model: str | None = None,
        reasoning_effort: str | None = None,
        stall_timeout: float | None = None,
    ) -> SubprocessResult:
        """Run Codex through the app-server backend (blocking).

        Maps the app-server result into the existing SubprocessResult contract.
        Raises FileNotFoundError with clear message if binary missing.
        Raises subprocess.TimeoutExpired on timeout (not swallowed).
        """
        if "timeout_seconds_range" in local_config(self._repo_root):
            validate_timeout(self._repo_root, timeout_seconds)
            validate_timeout(self._repo_root, stall_timeout)
        resolved_cwd = (pathlib.Path.cwd() if cwd is None else pathlib.Path(cwd)).resolve()
        _guard_codex_main_worktree(resolved_cwd, os.environ)
        try:
            return self._run_codex_mcp_for_async(
                codex_args,
                timeout_seconds,
                resolved_cwd,
                model,
                reasoning_effort,
                stall_timeout,
            )
        except CodexMcpTimeoutError as exc:
            raise subprocess.TimeoutExpired(
                cmd=_codex_mcp_command(os.environ.get("CODEX_BIN", "codex")),
                timeout=timeout_seconds,
                output="",
                stderr=str(exc),
            ) from exc

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
        with writer_scope(self._repo_root):
            # Re-validate after Codex returns (idempotent — re-reads from disk).
            self._validate_ledger_entry(change_id, category)

            ledger = json.loads(self._ledger_path.read_text(encoding="utf-8"))
            entry = _ledger_entry_for(ledger, change_id)

            categories: dict = entry.get("categories", {})

            previous_status: str | None = categories[category].get("status")
            new_status = "pass" if result.exit_code == 0 else "fail"
            command_str = " ".join(shlex.quote(p) for p in result.command)
            notes = (
                f"P0-J auto: rc={result.exit_code}, stderr first 200 chars: {result.stderr[:200]!r}"
            )

            categories[category].update(
                {
                    "status": new_status,
                    "command": command_str,
                    "notes": notes,
                }
            )

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
        timeout_seconds: int | None = None,
        *,
        model: str | None = None,
        reasoning_effort: str | None = None,
        stall_timeout: float | None = None,
    ) -> tuple[SubprocessResult, LedgerUpdate]:
        """Convenience: run_codex + update_ledger together.

        Validates change_id + category BEFORE invoking Codex so a typo'd id
        fails within seconds instead of after a multi-minute Codex run (W3).
        """
        with writer_scope(self._repo_root):
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
        timeout_seconds: int | None = None,
        *,
        cwd: os.PathLike[str] | str | None = None,
        model: str | None = None,
        reasoning_effort: str | None = None,
        stall_timeout: float | None = None,
    ) -> SubprocessResult:
        """Async variant of run_codex using the app-server backend in a worker thread.

        Single call: prefer sync run_codex. Multi-call or long-running: use this.
        On timeout: TimeoutError (caller catches both sync and async timeout classes
        when mixing sync and async paths).
        Raises FileNotFoundError with clear message if binary missing.
        """
        if "timeout_seconds_range" in local_config(self._repo_root):
            validate_timeout(self._repo_root, timeout_seconds)
            validate_timeout(self._repo_root, stall_timeout)
        resolved_cwd = pathlib.Path.cwd() if cwd is None else pathlib.Path(cwd)
        resolved_cwd = resolved_cwd.resolve()
        _guard_codex_main_worktree(resolved_cwd, os.environ)
        task = asyncio.create_task(
            asyncio.to_thread(
                self._run_codex_mcp_for_async,
                codex_args,
                timeout_seconds,
                resolved_cwd,
                model,
                reasoning_effort,
                stall_timeout,
            )
        )
        try:
            return await asyncio.shield(task)
        except asyncio.CancelledError:
            await _drain_worker(task)
            raise

    async def run_agent_async(
        self,
        codex_args: list[str],
        timeout_seconds: float | None = None,
    ) -> SubprocessResult:
        """Run the explicitly selected agent through its native provider."""
        if "timeout_seconds_range" in local_config(self._repo_root):
            validate_timeout(self._repo_root, timeout_seconds)
        route = self.resolve_agent_route()
        if route is None or route.execution_backend == "codex":
            kwargs: dict[str, object] = {"timeout_seconds": timeout_seconds}
            if route is not None and route.model is not None:
                kwargs["model"] = route.model
            if route is not None and route.reasoning_effort is not None:
                kwargs["reasoning_effort"] = route.reasoning_effort
            return await self.run_codex_async(codex_args, **kwargs)
        if route.execution_backend != "claude":
            raise ValueError(f"Unsupported agent backend: {route.execution_backend!r}")
        state: dict[str, object] = {}

        async def call():
            state["loop"] = asyncio.get_running_loop()
            state["task"] = asyncio.current_task()
            if state.get("cancelled"):
                raise asyncio.CancelledError
            return await self._run_claude_agent_async(codex_args, timeout_seconds, route)

        task = asyncio.create_task(asyncio.to_thread(lambda: asyncio.run(call())))
        try:
            return await asyncio.shield(task)
        except asyncio.CancelledError:
            state["cancelled"] = True
            loop, child = state.get("loop"), state.get("task")
            if loop is not None and child is not None and not child.done():
                try:
                    loop.call_soon_threadsafe(child.cancel)
                except RuntimeError:
                    # The worker may have finished and closed its loop meanwhile.
                    pass
            await _drain_worker(task)
            raise

    async def _run_claude_agent_async(
        self,
        codex_args: list[str],
        timeout_seconds: float | None,
        route: AgentRoute,
    ) -> SubprocessResult:
        if "timeout_seconds_range" in local_config(self._repo_root):
            validate_timeout(self._repo_root, timeout_seconds)
        prompt = _prompt_from_codex_args(self.resolve_codex_args(codex_args))
        command = [os.environ.get("CLAUDE_BIN", "claude"), "--agent", route.target_agent, "-p"]
        start = time.monotonic()
        with self._writer_scope(route):
            process = await asyncio.create_subprocess_exec(
                *command,
                cwd=str(self._repo_root),
                env=child_env(self._repo_root),
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(prompt.encode("utf-8")),
                    timeout=timeout_seconds,
                )
            except (TimeoutError, asyncio.CancelledError):
                await self._terminate_async_process(process)
                raise
            mapped = SubprocessResult(
                process.returncode or 0,
                stdout.decode("utf-8", errors="replace"),
                stderr.decode("utf-8", errors="replace"),
                time.monotonic() - start,
                command,
            )
            return after_provider_call(
                self._repo_root,
                mapped,
                prompt=prompt,
                model=route.model,
                reasoning_effort=route.reasoning_effort,
                attempt=1,
                elapsed_seconds=mapped.duration_seconds,
            )

    @staticmethod
    async def _terminate_async_process(process: asyncio.subprocess.Process) -> None:
        if process.returncode is not None:
            return
        process.terminate()
        try:
            await asyncio.wait_for(process.wait(), timeout=2.0)
        except TimeoutError:
            process.kill()
            await process.wait()

    def _run_codex_mcp_for_async(
        self,
        codex_args: list[str],
        timeout_seconds: int | None,
        resolved_cwd: pathlib.Path,
        model: str | None,
        reasoning_effort: str | None,
        stall_timeout: float | None,
    ) -> SubprocessResult:
        """Run the shared app-server call for the async wrapper without timeout remapping."""
        if "timeout_seconds_range" in local_config(self._repo_root):
            validate_timeout(self._repo_root, timeout_seconds)
            validate_timeout(self._repo_root, stall_timeout)
        codex_bin = os.environ.get("CODEX_BIN", "codex")
        prompt = _prompt_from_codex_args(self.resolve_codex_args(codex_args))
        command = _codex_mcp_command(codex_bin)
        route = self.resolve_agent_route()
        start = time.monotonic()
        raw_result = None
        with self._writer_scope(route):
            try:
                with CodexMcpClient(
                    codex_bin=codex_bin,
                    env=child_env(self._repo_root),
                    call_timeout=timeout_seconds,
                ) as client:
                    call_kwargs: dict[str, object] = {
                        "prompt": prompt,
                        "cwd": resolved_cwd,
                        "sandbox": (
                            route.sandbox
                            if route is not None and route.sandbox is not None
                            else local_config(self._repo_root).get(
                                "codex_sandbox_default", "workspace-write"
                            )
                        ),
                        "approval_policy": "never",
                        "base_instructions": route.base_instructions
                        if route is not None
                        else _MCP_DISPATCH_BASE_INSTRUCTIONS,
                        "config": _codex_mcp_config(reasoning_effort),
                        "timeout": timeout_seconds,
                    }
                    if model is not None:
                        call_kwargs["model"] = model
                    if stall_timeout is not None:
                        call_kwargs["stall_timeout"] = stall_timeout
                    raw_result = client.call_codex(**call_kwargs)
            except CodexMcpTimeoutError as exc:
                if timeout_seconds is not None:
                    raise
                mapped = SubprocessResult(1, "", str(exc), time.monotonic() - start, command)
            except FileNotFoundError as exc:
                raise FileNotFoundError(
                    f"Codex binary not found: {codex_bin!r}. "
                    "Set CODEX_BIN to the full path of the codex executable."
                ) from exc
            except CodexMcpError as exc:
                mapped = SubprocessResult(1, "", str(exc), time.monotonic() - start, command)
            else:
                mapped = SubprocessResult(
                    0, raw_result.content_text, "", time.monotonic() - start, command
                )
            return after_provider_call(
                self._repo_root,
                mapped,
                prompt=prompt,
                model=model,
                reasoning_effort=reasoning_effort,
                attempt=1,
                elapsed_seconds=mapped.duration_seconds,
                raw_result=raw_result,
            )

    async def execute_async(
        self,
        change_id: str,
        category: str,
        codex_args: list[str],
        timeout_seconds: int | None = None,
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
