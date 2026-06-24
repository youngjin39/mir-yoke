"""ADR-60 dispatch helper for isolated Codex subprocess execution.

The helper owns the per-task attempt policy: create an isolated dispatch
worktree, run Codex for a finite number of attempts, then either surface a
single fallback opportunity or block the lane for human orchestration.
"""

from __future__ import annotations

import json
import os
import pathlib
import shlex
import shutil
import subprocess
from collections.abc import Callable
from dataclasses import dataclass

from tools.mir_executor.jobs import JobRegistry
from tools.mir_executor.worktree import (
    DispatchWorktree,
    _is_denied_harness_path,
    cleanup_worktree,
    create_dispatch_worktree,
    dispatch_env,
    merge_result,
    read_result,
    write_status,
)

MAX_CODEX_ATTEMPTS = 3
OUTAGE_THRESHOLD = 3


def reap_node_repl() -> int:
    """Clear stale node_repl IPC the next codex attempt would otherwise hang connecting to.

    node_repl hang mitigation 2026-06-25; root cause is closed-source Codex.app.
    """
    try:
        completed = subprocess.run(
            ["pkill", "-9", "-f", "Codex.app/Contents/Resources/node_repl"],
            capture_output=True,
            timeout=10,
        )
    except Exception:  # noqa: BLE001
        return -1
    return completed.returncode


def force_full_access_sandbox(codex_args: list[str]) -> list[str]:
    """Force dispatch writes out of the macOS workspace-write Seatbelt sandbox.

    codex apply_patch file writes hang under the workspace-write Seatbelt sandbox
    on this macOS. Dispatch safety relies on the R4 worktree plus the merge gate,
    and danger-full-access is the user global codex default
    (codex-dispatch-danger-sandbox 2026-06-25).
    """
    forced_args = list(codex_args)
    sandbox_flags = {"--sandbox", "-s"}
    for index, token in enumerate(forced_args[1:], start=1):
        if token == "workspace-write" and forced_args[index - 1] in sandbox_flags:
            forced_args[index] = "danger-full-access"
    return forced_args


@dataclass(frozen=True)
class CodexAttempt:
    """Result of one Codex or fallback execution attempt."""

    exit_code: int
    error_sig: str = ""
    stdout: str = ""
    stderr: str = ""


@dataclass(frozen=True)
class DispatchOutcome:
    """Terminal dispatch status plus the retained inspection worktree."""

    status: str
    attempts: int
    fell_back: bool
    blocked_reason: str | None
    worktree: DispatchWorktree | None
    result: dict | None = None


@dataclass(frozen=True)
class MergeGate:
    """Deterministic merge-gate decision for a completed dispatch."""

    approved: bool
    reason: str
    changed_files: list[str]


@dataclass(frozen=True)
class FinalizeResult:
    """Final action taken for a completed or blocked dispatch worktree."""

    action: str
    reason: str
    merged_files: list[str]


def _append_event(events_path: pathlib.Path, event: dict[str, object]) -> None:
    """Append one JSONL event to the dispatch event log."""
    events_path.parent.mkdir(parents=True, exist_ok=True)
    with events_path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(event, ensure_ascii=False) + "\n")


def run_dispatch(
    main_repo_root: pathlib.Path,
    dispatch_id: str,
    *,
    brief_text: str = "",
    base_commit: str = "HEAD",
    codex_runner: Callable[[DispatchWorktree, int], CodexAttempt],
    claude_fallback: Callable[[DispatchWorktree], CodexAttempt] | None = None,
    dispatch_events_path: pathlib.Path | None = None,
    max_codex_attempts: int = MAX_CODEX_ATTEMPTS,
    outage_threshold: int = OUTAGE_THRESHOLD,
    prior_consecutive_codex_failures: int = 0,
    worktrees_root: pathlib.Path | None = None,
) -> DispatchOutcome:
    """Run one isolated dispatch with finite Codex attempts and fallback policy."""
    main_repo_root = pathlib.Path(main_repo_root)
    wt = create_dispatch_worktree(
        main_repo_root,
        dispatch_id,
        base_commit=base_commit,
        brief_text=brief_text,
        worktrees_root=worktrees_root,
    )
    events_path = dispatch_events_path or wt.path / ".mir-dispatch" / "dispatch-events.jsonl"

    attempts = 0
    error_sigs: list[str] = []
    for attempt in range(1, max_codex_attempts + 1):
        result = codex_runner(wt, attempt)
        attempts = attempt
        if result.exit_code == 0:
            write_status(wt, "codex_completed", attempt=attempt)
            structured_result = read_result(wt)
            _append_event(
                events_path,
                {"kind": "codex_success", "dispatch_id": dispatch_id, "attempt": attempt},
            )
            return DispatchOutcome("completed", attempt, False, None, wt, structured_result)

        error_sigs.append(result.error_sig)
        _append_event(
            events_path,
            {
                "kind": "codex_failure",
                "dispatch_id": dispatch_id,
                "attempt": attempt,
                "exit_code": result.exit_code,
                "error_sig": result.error_sig,
            },
        )
        if result.error_sig and error_sigs.count(result.error_sig) >= 3:
            write_status(wt, "spinning", attempt=attempt, error_sig=result.error_sig)
            _append_event(
                events_path,
                {
                    "kind": "spinning",
                    "dispatch_id": dispatch_id,
                    "error_sig": result.error_sig,
                },
            )
            break

    write_status(wt, "codex_failed", attempts=attempts)

    consecutive = prior_consecutive_codex_failures + 1
    if consecutive >= outage_threshold:
        _append_event(
            events_path,
            {
                "kind": "codex_outage_halt",
                "dispatch_id": dispatch_id,
                "consecutive_failures": consecutive,
                "threshold": outage_threshold,
            },
        )
        write_status(wt, "blocked", reason="codex-outage")
        return DispatchOutcome("blocked", attempts, False, "codex-outage", wt)

    if claude_fallback is None:
        _append_event(
            events_path,
            {"kind": "fallback_required", "dispatch_id": dispatch_id, "attempts": attempts},
        )
        write_status(wt, "blocked", reason="fallback-required")
        return DispatchOutcome("blocked", attempts, False, "fallback-required", wt)

    _append_event(
        events_path,
        {"kind": "fallback", "dispatch_id": dispatch_id, "after_attempts": attempts},
    )
    fallback_result = claude_fallback(wt)
    if fallback_result.exit_code == 0:
        write_status(wt, "fallback_completed")
        _append_event(events_path, {"kind": "fallback_success", "dispatch_id": dispatch_id})
        return DispatchOutcome("fallback_completed", attempts, True, None, wt)

    _append_event(
        events_path,
        {
            "kind": "fallback_failed",
            "dispatch_id": dispatch_id,
            "exit_code": fallback_result.exit_code,
        },
    )
    write_status(wt, "blocked", reason="fallback-failed")
    return DispatchOutcome("blocked", attempts, True, "fallback-failed", wt)


def _last_json_line(path: pathlib.Path) -> dict[str, object]:
    """Read the last parseable JSON object from a JSONL file."""
    if not path.exists():
        return {}
    for line in reversed(path.read_text(encoding="utf-8").splitlines()):
        if not line.strip():
            continue
        try:
            data = json.loads(line)
        except (json.JSONDecodeError, ValueError):
            continue
        if isinstance(data, dict):
            return data
    return {}


def persist_dispatch_artifacts(
    wt: DispatchWorktree,
    main_repo_root: pathlib.Path,
) -> pathlib.Path:
    """Copy durable per-dispatch artifacts into the main repository state."""
    artifact_dir = pathlib.Path(main_repo_root) / "tasks" / "dispatch" / wt.dispatch_id
    artifact_dir.mkdir(parents=True, exist_ok=True)
    dispatch_dir = wt.path / ".mir-dispatch"
    for filename in (
        "brief.md",
        "status.json",
        "result.json",
        "events.jsonl",
        "dispatch-events.jsonl",
    ):
        source = dispatch_dir / filename
        if source.exists():
            shutil.copy2(source, artifact_dir / filename)
    return artifact_dir


def _run_guarded(
    command: list[str],
    cwd: pathlib.Path,
    env: dict[str, str],
    timeout_seconds: int,
) -> subprocess.CompletedProcess[str]:
    """Run a guarded headless subprocess with closed stdin and captured output."""
    return subprocess.run(
        command,
        cwd=str(cwd),
        env=env,
        capture_output=True,
        text=True,
        timeout=timeout_seconds,
        stdin=subprocess.DEVNULL,
    )


def build_codex_runner(
    main_repo_root: pathlib.Path,
    codex_args: list[str],
    *,
    timeout_seconds: int = 600,
) -> Callable[[DispatchWorktree, int], CodexAttempt]:
    """Build the real Codex runner used by ``execute --background --dispatch``."""

    def _runner(wt: DispatchWorktree, attempt: int) -> CodexAttempt:
        env = dispatch_env(main_repo_root, session_id=wt.dispatch_id)
        events_file = wt.path / ".mir-dispatch" / "events.jsonl"
        events_file.parent.mkdir(parents=True, exist_ok=True)
        env["CODEX_EVENTS_FILE"] = str(events_file)
        codex_bin = env.get("CODEX_BIN", os.environ.get("CODEX_BIN", "codex"))
        command = [codex_bin, *force_full_access_sandbox(codex_args)]
        try:
            if attempt > 1:
                reap_node_repl()
            completed = subprocess.run(
                command,
                cwd=str(wt.path),
                env=env,
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
                stdin=subprocess.DEVNULL,
            )
        except subprocess.TimeoutExpired as exc:
            stdout = exc.stdout if isinstance(exc.stdout, str) else ""
            stderr = exc.stderr if isinstance(exc.stderr, str) else str(exc)
            return CodexAttempt(exit_code=124, stdout=stdout, stderr=stderr)

        event = _last_json_line(events_file)
        error_sig = event.get("error_sig")
        return CodexAttempt(
            exit_code=completed.returncode,
            error_sig=error_sig if isinstance(error_sig, str) else "",
            stdout=completed.stdout,
            stderr=completed.stderr,
        )

    return _runner


_CLAUDE_DISPATCH_PROMPT = (
    "Read the task brief at .mir-dispatch/brief.md and implement it fully "
    "in this worktree. Do not edit tasks/plan.md."
)


def _run_claude_adapter(
    main_repo_root: pathlib.Path,
    wt: DispatchWorktree,
    *,
    timeout_seconds: int,
    mark_fallback_depth: bool,
) -> CodexAttempt:
    """Run headless ``claude -p`` in a dispatch worktree."""
    env = dispatch_env(main_repo_root, session_id=wt.dispatch_id)
    env["CLAUDE_PROJECT_DIR"] = str(wt.path)
    if mark_fallback_depth:
        env["MIR_DISPATCH_FALLBACK_DEPTH"] = "1"
    claude_bin = os.environ.get("CLAUDE_BIN", "claude")
    command = [claude_bin, "-p", _CLAUDE_DISPATCH_PROMPT]
    try:
        completed = _run_guarded(command, wt.path, env, timeout_seconds)
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout if isinstance(exc.stdout, str) else ""
        stderr = exc.stderr if isinstance(exc.stderr, str) else str(exc)
        return CodexAttempt(exit_code=124, stdout=stdout, stderr=stderr)

    return CodexAttempt(
        exit_code=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
    )


def build_claude_runner(
    main_repo_root: pathlib.Path,
    *,
    timeout_seconds: int = 600,
) -> Callable[[DispatchWorktree, int], CodexAttempt]:
    """Build the primary headless ``claude -p`` dispatch runner."""

    def _runner(wt: DispatchWorktree, attempt: int) -> CodexAttempt:
        _ = attempt
        return _run_claude_adapter(
            main_repo_root,
            wt,
            timeout_seconds=timeout_seconds,
            mark_fallback_depth=False,
        )

    return _runner


def _git(
    repo_root: pathlib.Path,
    args: list[str],
    *,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    """Run git with list arguments and captured text output."""
    return subprocess.run(
        ["git", "-C", str(repo_root), *args],
        check=check,
        capture_output=True,
        text=True,
    )


def _path_allowed(path: str, allowlist: list[str]) -> bool:
    """Return True when a repository path is covered by the declared allowlist."""
    for allowed in allowlist:
        prefix = allowed.rstrip("/")
        if path == allowed or path.startswith(prefix + "/"):
            return True
    return False


def _resolve_harness_self_modify(main_repo_root: pathlib.Path) -> bool:
    """Return True iff the dispatch repo declares repository_type == 'meta_harness'.

    Reads the per-repo self-identifying profile. Fail-closed: any missing/unreadable/
    malformed profile, or a non-meta type, yields False (DENY).
    """
    import tomllib

    try:
        profile_path = pathlib.Path(main_repo_root) / ".mir" / "repo-profile.toml"
        with profile_path.open("rb") as fh:
            data = tomllib.load(fh)
        return data.get("repo", {}).get("repository_type") == "meta_harness"
    except Exception:  # noqa: BLE001
        return False


def evaluate_merge_gate(
    wt: DispatchWorktree,
    *,
    allowlist: list[str],
    verification_commands: list[str],
    verify_timeout: int = 600,
    allow_harness_self_modify: bool = False,
    expect_changes: bool = True,
) -> MergeGate:
    """Evaluate the deterministic ADR-60 P2 merge gate for one dispatch."""
    changed_text = _git(wt.path, ["diff", "--name-only", wt.base_commit, "HEAD"]).stdout
    changed = [line for line in changed_text.splitlines() if line]

    if expect_changes and not changed:
        return MergeGate(False, "empty-diff fail-closed", [])

    for path in changed:
        if _is_denied_harness_path(
            path,
            allow_harness_self_modify=allow_harness_self_modify,
        ):
            return MergeGate(False, f"denied-harness:{path}; changed={changed}", changed)

    for path in changed:
        if not _path_allowed(path, allowlist):
            return MergeGate(False, f"out-of-allowlist:{path}", changed)

    if not verification_commands:
        return MergeGate(False, "no-verification-commands (fail-closed)", changed)

    for cmd in verification_commands:
        try:
            completed = subprocess.run(
                shlex.split(cmd),
                cwd=str(wt.path),
                capture_output=True,
                text=True,
                stdin=subprocess.DEVNULL,
                timeout=verify_timeout,
            )
        except subprocess.TimeoutExpired:
            return MergeGate(False, "verification-timeout", changed)
        if completed.returncode != 0:
            return MergeGate(False, f"verification-failed:{cmd}", changed)

    return MergeGate(True, "approved", changed)


def _commit_worktree_if_needed(wt: DispatchWorktree) -> None:
    """Commit staged dispatch changes while excluding internal dispatch artifacts."""
    _git(wt.path, ["add", "-A"])
    _git(wt.path, ["reset", "--", ".mir-dispatch"], check=False)
    staged = _git(wt.path, ["diff", "--cached", "--quiet"], check=False)
    if staged.returncode == 1:
        _git(wt.path, ["commit", "-m", f"mir-dispatch {wt.dispatch_id}"])


def finalize_dispatch(
    wt: DispatchWorktree,
    main_repo_root: pathlib.Path,
    outcome: DispatchOutcome,
    *,
    allowlist: list[str],
    verification_commands: list[str],
    verify_timeout: int = 600,
    expect_changes: bool = True,
) -> FinalizeResult:
    """Commit, gate, merge, and clean up a completed dispatch fail-closed."""
    main_repo_root = pathlib.Path(main_repo_root)
    allow_harness = _resolve_harness_self_modify(main_repo_root)
    if outcome.status not in {"completed", "fallback_completed"}:
        persist_dispatch_artifacts(wt, main_repo_root)
        return FinalizeResult(
            "preserved",
            outcome.blocked_reason or "failed",
            [],
        )

    try:
        _commit_worktree_if_needed(wt)
        gate = evaluate_merge_gate(
            wt,
            allowlist=allowlist,
            verification_commands=verification_commands,
            verify_timeout=verify_timeout,
            allow_harness_self_modify=allow_harness,
            expect_changes=expect_changes,
        )
        if not gate.approved:
            persist_dispatch_artifacts(wt, main_repo_root)
            return FinalizeResult("blocked", gate.reason, [])

        main_head = _git(main_repo_root, ["rev-parse", "HEAD"]).stdout.strip()
        if main_head != wt.base_commit:
            persist_dispatch_artifacts(wt, main_repo_root)
            return FinalizeResult("blocked", "main-moved", [])

        dirty = _git(main_repo_root, ["status", "--porcelain"]).stdout.strip()
        if dirty:
            persist_dispatch_artifacts(wt, main_repo_root)
            return FinalizeResult("blocked", "main-dirty", [])

        try:
            merge_outcome = merge_result(wt, allow_harness_self_modify=allow_harness)
        except Exception as exc:  # noqa: BLE001
            _git(
                main_repo_root,
                ["restore", "--source=HEAD", "--staged", "--worktree", "--", "."],
                check=False,
            )
            try:
                persist_dispatch_artifacts(wt, main_repo_root)
            except Exception:  # noqa: BLE001
                pass
            return FinalizeResult("blocked", f"merge-error:{exc}", [])

        try:
            persist_dispatch_artifacts(wt, main_repo_root)
            cleanup_worktree(wt)
        except Exception as exc:  # noqa: BLE001
            return FinalizeResult(
                "merged-but-cleanup-failed",
                f"post-merge-error:{exc}",
                merge_outcome.merged_files,
            )
        return FinalizeResult("merged", "approved", merge_outcome.merged_files)
    except Exception as exc:  # noqa: BLE001
        try:
            persist_dispatch_artifacts(wt, main_repo_root)
        except Exception:  # noqa: BLE001
            pass
        return FinalizeResult("blocked", f"error:{exc}", [])


def build_claude_fallback(
    main_repo_root: pathlib.Path,
    *,
    timeout_seconds: int = 600,
) -> Callable[[DispatchWorktree], CodexAttempt]:
    """Build the headless ``claude -p`` fallback runner for ADR-60 R3."""

    def _fallback(wt: DispatchWorktree) -> CodexAttempt:
        if os.environ.get("MIR_DISPATCH_FALLBACK_DEPTH"):
            return CodexAttempt(exit_code=70, stderr="fallback-depth-exceeded")

        return _run_claude_adapter(
            main_repo_root,
            wt,
            timeout_seconds=timeout_seconds,
            mark_fallback_depth=True,
        )

    return _fallback


def count_consecutive_codex_failures(
    jobs_db_path: pathlib.Path,
    *,
    change_id_prefix: str = "",
) -> int:
    """Count newest-leading failed jobs, optionally scoped by change-id prefix."""
    registry = JobRegistry(pathlib.Path(jobs_db_path))
    try:
        jobs = registry.list_jobs()
        if change_id_prefix:
            jobs = [job for job in jobs if job.change_id.startswith(change_id_prefix)]

        count = 0
        for job in jobs:
            if job.status != "failed":
                break
            count += 1
        return count
    finally:
        registry.close()
