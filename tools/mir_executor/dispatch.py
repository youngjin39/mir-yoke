"""ADR-60 dispatch helper for isolated Codex execution.

The helper owns the per-task attempt policy: create an isolated dispatch
worktree, run Codex for a finite number of attempts, then either surface a
single fallback opportunity or block the lane for human orchestration.
"""

from __future__ import annotations

import hashlib
import json
import os
import pathlib
import shlex
import shutil
import subprocess
import tempfile
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass

try:
    import fcntl as _fcntl
except ImportError:  # pragma: no cover - Windows is not a target
    _fcntl = None  # type: ignore[assignment]

from tools.mir_executor.codex_mcp_client import (
    CodexMcpClient,
    CodexMcpError,
    CodexMcpTimeoutError,
)
from tools.mir_executor.jobs import JobRegistry
from tools.mir_executor.worktree import (
    DispatchWorktree,
    _is_denied_harness_path,
    cleanup_worktree,
    create_dispatch_worktree,
    dispatch_env,
    merge_result,
    write_status,
)

MAX_CODEX_ATTEMPTS = 1
OUTAGE_THRESHOLD = 3


@dataclass(frozen=True)
class CodexAttempt:
    """Result of one Codex or fallback execution attempt."""

    exit_code: int
    error_sig: str = ""
    stdout: str = ""
    stderr: str = ""
    lane_unavailable: bool = False


@dataclass(frozen=True)
class DispatchOutcome:
    """Terminal dispatch status plus the retained inspection worktree."""

    status: str
    attempts: int
    fell_back: bool
    blocked_reason: str | None
    worktree: DispatchWorktree | None


@dataclass(frozen=True)
class MergeGate:
    """Deterministic merge-gate decision for a completed dispatch."""

    approved: bool
    reason: str
    changed_files: list[str]


@dataclass(frozen=True)
class FinalizeResult:
    """Final action taken for a completed or blocked dispatch worktree.

    ``merged`` means allowlisted changes were checked out and staged in the
    main working tree; the control-plane main is responsible for committing them.
    """

    action: str
    reason: str
    merged_files: list[str]


class _VerificationCleanupError(RuntimeError):
    """Raised when an isolated verification worktree cannot be deregistered."""


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
    """Run one isolated dispatch; retries require an explicit non-default attempt count."""
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
            _append_event(
                events_path,
                {"kind": "codex_success", "dispatch_id": dispatch_id, "attempt": attempt},
            )
            return DispatchOutcome("completed", attempt, False, None, wt)

        error_sigs.append(result.error_sig)
        _append_event(
            events_path,
            {
                "kind": "codex_failure",
                "dispatch_id": dispatch_id,
                "attempt": attempt,
                "exit_code": result.exit_code,
                "error_sig": result.error_sig,
                "lane_unavailable": result.lane_unavailable,
            },
        )
        if result.lane_unavailable:
            _append_event(
                events_path,
                {"kind": "lane_unavailable", "dispatch_id": dispatch_id, "attempt": attempt},
            )
            write_status(wt, "blocked", reason="lane-unavailable", attempt=attempt)
            return DispatchOutcome("blocked", attempt, False, "lane-unavailable", wt)
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


def _error_sig_from_text(text: str) -> str:
    """Return the 12-char error signature shape used by the codex shim."""
    if not text:
        return ""
    tail = "\n".join(text.splitlines()[-20:])
    return hashlib.sha256(tail.encode("utf-8")).hexdigest()[:12]


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
    timeout_seconds: int | None,
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


def build_codex_mcp_runner(
    main_repo_root: pathlib.Path,
    prompt: str,
    *,
    timeout_seconds: int | None = None,
    model: str | None = None,
    reasoning_effort: str | None = None,
    stall_timeout: float | None = None,
    client_factory: Callable[..., CodexMcpClient] = CodexMcpClient,
) -> Callable[[DispatchWorktree, int], CodexAttempt]:
    """Build an ADR-66 MCP-backed Codex runner without ``codex exec`` argv."""
    config: dict[str, object] = {"project_doc_max_bytes": 0}
    if reasoning_effort is not None:
        config["model_reasoning_effort"] = reasoning_effort

    def _runner(wt: DispatchWorktree, attempt: int) -> CodexAttempt:
        _ = attempt
        env = dispatch_env(main_repo_root, session_id=wt.dispatch_id)
        events_file = wt.path / ".mir-dispatch" / "events.jsonl"
        events_file.parent.mkdir(parents=True, exist_ok=True)
        env["CODEX_EVENTS_FILE"] = str(events_file)
        started_at = time.monotonic()
        thread_id: str | None = None

        def append_progress(method: str, _params: object) -> None:
            _append_event(
                events_file,
                {
                    "transport": "mcp",
                    "event": "progress",
                    "duration_s": time.monotonic() - started_at,
                    "method": method,
                },
            )

        try:
            try:
                client = client_factory(env=env, call_timeout=timeout_seconds)
                client.__enter__()
            except Exception as exc:  # startup and handshake failures mean no usable lane
                stderr = str(exc)
                error_sig = _error_sig_from_text(stderr)
                _append_event(
                    events_file,
                    {
                        "exit_code": 1,
                        "duration_s": time.monotonic() - started_at,
                        "error_sig": error_sig,
                        "transport": "mcp",
                        "lane_unavailable": True,
                    },
                )
                return CodexAttempt(
                    exit_code=1,
                    stderr=stderr,
                    error_sig=error_sig,
                    lane_unavailable=True,
                )
            try:
                call_kwargs: dict[str, object] = {
                    "prompt": prompt,
                    "cwd": str(wt.path),
                    "sandbox": "danger-full-access",
                    "approval_policy": "never",
                    "base_instructions": _MCP_DISPATCH_BASE_INSTRUCTIONS,
                    "config": config,
                    "timeout": timeout_seconds,
                    "progress_callback": append_progress,
                }
                if model is not None:
                    call_kwargs["model"] = model
                if stall_timeout is not None:
                    call_kwargs["stall_timeout"] = stall_timeout
                result = client.call_codex(**call_kwargs)  # type: ignore[arg-type]
            finally:
                client.__exit__(None, None, None)
            thread_id = result.thread_id
            duration_s = time.monotonic() - started_at
            _append_event(
                events_file,
                {
                    "exit_code": 0,
                    "duration_s": duration_s,
                    "error_sig": "",
                    "transport": "mcp",
                    "threadId": thread_id,
                    "lane_unavailable": False,
                },
            )
            return CodexAttempt(exit_code=0, stdout=result.content_text)
        except CodexMcpTimeoutError as exc:
            stderr = str(exc)
            exit_code = 124
        except (CodexMcpError, FileNotFoundError, OSError) as exc:
            stderr = str(exc)
            exit_code = 1

        duration_s = time.monotonic() - started_at
        error_sig = _error_sig_from_text(stderr)
        _append_event(
            events_file,
            {
                "exit_code": exit_code,
                "duration_s": duration_s,
                "error_sig": error_sig,
                "transport": "mcp",
                "threadId": thread_id,
                "lane_unavailable": False,
            },
        )
        return CodexAttempt(
            exit_code=exit_code,
            stderr=stderr,
            error_sig=error_sig,
            lane_unavailable=False,
        )

    return _runner


_CLAUDE_DISPATCH_PROMPT = (
    "Read the task brief at .mir-dispatch/brief.md and implement it fully "
    "in this worktree. Do not edit tasks/plan.md."
)

_MCP_DISPATCH_BASE_INSTRUCTIONS = (
    "You are a code-implementation sub-agent in an isolated git worktree for the Mir "
    "harness. Read .mir-dispatch/brief.md and implement the task fully. Rules: modify "
    "only files inside this worktree, never edit tasks/plan.md, follow existing code "
    "style and structure, keep changes minimal and scoped to the brief, when tests are "
    "specified make them pass. Report a concise summary of what you changed."
)


def _run_claude_adapter(
    main_repo_root: pathlib.Path,
    wt: DispatchWorktree,
    *,
    timeout_seconds: int | None,
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
    timeout_seconds: int | None = None,
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
    verify_timeout: int | None = None,
    allow_harness_self_modify: bool = False,
    expect_changes: bool = True,
    source_commit: str | None = None,
) -> MergeGate:
    """Evaluate the deterministic ADR-60 P2 merge gate for one dispatch."""
    if source_commit is None:
        source_commit = _git(wt.path, ["rev-parse", "HEAD"]).stdout.strip()
    changed_text = _git(
        wt.path,
        ["diff", "--no-renames", "--name-only", "-z", wt.base_commit, source_commit],
    ).stdout
    changed = [path for path in changed_text.split("\0") if path]

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

    if _dispatch_nonruntime_status(wt.path):
        return MergeGate(False, "dispatch-dirty", changed)
    try:
        with _isolated_verification_worktree(wt, source_commit) as verification_root:
            for cmd in verification_commands:
                try:
                    completed = subprocess.run(
                        shlex.split(cmd),
                        cwd=str(verification_root),
                        capture_output=True,
                        text=True,
                        stdin=subprocess.DEVNULL,
                        timeout=verify_timeout,
                    )
                except subprocess.TimeoutExpired:
                    return MergeGate(False, "verification-timeout", changed)
                if completed.returncode != 0:
                    return MergeGate(False, f"verification-failed:{cmd}", changed)
    except _VerificationCleanupError:
        return MergeGate(False, "verification-cleanup-failed", changed)
    if _dispatch_nonruntime_status(wt.path):
        return MergeGate(False, "dispatch-dirty", changed)

    return MergeGate(True, "approved", changed)


def _commit_worktree_if_needed(wt: DispatchWorktree) -> None:
    """Commit staged dispatch changes while excluding internal dispatch artifacts."""
    _git(wt.path, ["add", "-A"])
    _git(wt.path, ["reset", "--", ".mir-dispatch"], check=False)
    staged = _git(wt.path, ["diff", "--cached", "--quiet"], check=False)
    if staged.returncode == 1:
        _git(wt.path, ["commit", "-m", f"mir-dispatch {wt.dispatch_id}"])


def _dispatch_nonruntime_status(worktree_root: pathlib.Path) -> str:
    return _git(
        worktree_root,
        [
            "status",
            "--porcelain=v2",
            "-z",
            "--untracked-files=all",
            "--",
            ".",
            ":(exclude).mir-dispatch",
            ":(exclude).mir-dispatch/**",
        ],
    ).stdout


@contextmanager
def _isolated_verification_worktree(
    wt: DispatchWorktree,
    source_commit: str,
) -> Iterator[pathlib.Path]:
    temp_base = pathlib.Path(tempfile.mkdtemp(prefix="mir-verify-"))
    verification_root = temp_base / "worktree"
    added = False
    try:
        _git(
            wt.main_repo_root,
            ["worktree", "add", "--detach", str(verification_root), source_commit],
        )
        added = True
        profile = wt.path / ".mir" / "repo-profile.toml"
        if profile.is_file():
            target = verification_root / ".mir" / "repo-profile.toml"
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(profile, target)
        yield verification_root
    finally:
        if not added:
            shutil.rmtree(temp_base, ignore_errors=True)
        else:
            try:
                remove = _git(
                    wt.main_repo_root,
                    ["worktree", "remove", "--force", str(verification_root)],
                    check=False,
                )
            except OSError:
                remove = None
            if remove is None or remove.returncode != 0:
                try:
                    _git(wt.main_repo_root, ["worktree", "prune"], check=False)
                except OSError:
                    pass
                if not verification_root.exists():
                    shutil.rmtree(temp_base, ignore_errors=True)
                raise _VerificationCleanupError("verification-cleanup-failed")
            shutil.rmtree(temp_base, ignore_errors=True)


def _head_tracks_path(repo_root: pathlib.Path, path: str) -> bool:
    result = _git(
        repo_root,
        ["--literal-pathspecs", "ls-tree", "-z", "--name-only", "HEAD", "--", path],
    )
    return bool(result.stdout)


def _head_absent_path_collision(repo_root: pathlib.Path, path: str) -> bool:
    if _head_tracks_path(repo_root, path):
        return False

    candidate = repo_root / pathlib.PurePosixPath(path)
    if os.path.lexists(candidate):
        return True

    current = repo_root
    for part in pathlib.PurePosixPath(path).parts[:-1]:
        current /= part
        if os.path.lexists(current) and (current.is_symlink() or not current.is_dir()):
            return True
    return False


def _target_status(repo_root: pathlib.Path, paths: list[str]) -> str:
    if not paths:
        return ""
    return _git(
        repo_root,
        [
            "--literal-pathspecs",
            "status",
            "--porcelain=v2",
            "-z",
            "--untracked-files=all",
            "--ignored=matching",
            "--",
            *paths,
        ],
    ).stdout


def _targets_dirty(repo_root: pathlib.Path, paths: list[str]) -> bool:
    return any(_head_absent_path_collision(repo_root, path) for path in paths) or bool(
        _target_status(repo_root, paths)
    )


def _rollback_targets(
    repo_root: pathlib.Path,
    paths: list[str],
    tracked_at_head: set[str],
) -> list[str]:
    failures: list[str] = []
    for path in paths:
        reset = _git(
            repo_root,
            ["--literal-pathspecs", "reset", "--", path],
            check=False,
        )
        if reset.returncode != 0:
            failures.append(f"reset:{path}")
        if path in tracked_at_head:
            restored = _git(
                repo_root,
                [
                    "--literal-pathspecs",
                    "restore",
                    "--source=HEAD",
                    "--staged",
                    "--worktree",
                    "--",
                    path,
                ],
                check=False,
            )
            if restored.returncode != 0:
                failures.append(f"restore:{path}")
        else:
            cleaned = _git(
                repo_root,
                ["--literal-pathspecs", "clean", "-fdx", "--", path],
                check=False,
            )
            if cleaned.returncode != 0:
                failures.append(f"clean:{path}")
    try:
        if _targets_dirty(repo_root, paths):
            failures.append("target-residue")
    except Exception as exc:  # noqa: BLE001
        failures.append(f"status:{exc}")
    return failures


@contextmanager
def _finalize_lock(
    main_repo_root: pathlib.Path,
    timeout: int,
) -> Iterator[bool]:
    """Acquire the per-repository finalize lock within a bounded wait."""
    lock_path = pathlib.Path(main_repo_root) / ".mir" / "dispatch-finalize.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    if _fcntl is None:
        yield True
        return

    acquired = False
    deadline = time.monotonic() + max(timeout, 0)
    with lock_path.open("a+") as lock_file:
        while True:
            try:
                _fcntl.flock(
                    lock_file.fileno(),
                    _fcntl.LOCK_EX | _fcntl.LOCK_NB,
                )
                acquired = True
                break
            except BlockingIOError:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                time.sleep(min(0.05, remaining))
        try:
            yield acquired
        finally:
            if acquired:
                _fcntl.flock(lock_file.fileno(), _fcntl.LOCK_UN)


def finalize_dispatch(
    wt: DispatchWorktree,
    main_repo_root: pathlib.Path,
    outcome: DispatchOutcome,
    *,
    allowlist: list[str],
    verification_commands: list[str],
    verify_timeout: int | None = None,
    finalize_lock_timeout: int = 600,
    expect_changes: bool = True,
    allow_harness_self_modify: bool = False,
) -> FinalizeResult:
    """Gate and finalize a dispatch fail-closed.

    A ``merged`` result means allowlisted changes were checked out and staged in
    the main working tree; the control-plane main must commit them afterward.
    """
    main_repo_root = pathlib.Path(main_repo_root)
    allow_harness = allow_harness_self_modify or _resolve_harness_self_modify(main_repo_root)
    if outcome.status not in {"completed", "fallback_completed"}:
        persist_dispatch_artifacts(wt, main_repo_root)
        return FinalizeResult(
            "preserved",
            outcome.blocked_reason or "failed",
            [],
        )

    try:
        _commit_worktree_if_needed(wt)
        source_commit = _git(wt.path, ["rev-parse", "HEAD"]).stdout.strip()
        gate = evaluate_merge_gate(
            wt,
            allowlist=allowlist,
            verification_commands=verification_commands,
            verify_timeout=verify_timeout,
            allow_harness_self_modify=allow_harness,
            expect_changes=expect_changes,
            source_commit=source_commit,
        )
        if not gate.approved:
            persist_dispatch_artifacts(wt, main_repo_root)
            return FinalizeResult("blocked", gate.reason, [])

        with _finalize_lock(main_repo_root, finalize_lock_timeout) as lock_acquired:
            if not lock_acquired:
                persist_dispatch_artifacts(wt, main_repo_root)
                return FinalizeResult("blocked", "finalize-lock-timeout", [])

            try:
                main_head = _git(main_repo_root, ["rev-parse", "HEAD"]).stdout.strip()
                if main_head != wt.base_commit:
                    persist_dispatch_artifacts(wt, main_repo_root)
                    return FinalizeResult("blocked", "main-moved", [])

                current_dispatch_head = _git(
                    wt.path,
                    ["rev-parse", "HEAD"],
                ).stdout.strip()
                if current_dispatch_head != source_commit:
                    persist_dispatch_artifacts(wt, main_repo_root)
                    return FinalizeResult("blocked", "dispatch-moved", [])

                if _dispatch_nonruntime_status(wt.path):
                    persist_dispatch_artifacts(wt, main_repo_root)
                    return FinalizeResult("blocked", "dispatch-dirty", [])

                if _targets_dirty(main_repo_root, gate.changed_files):
                    persist_dispatch_artifacts(wt, main_repo_root)
                    return FinalizeResult("blocked", "main-dirty", [])

                tracked_at_head = {
                    path
                    for path in gate.changed_files
                    if _head_tracks_path(main_repo_root, path)
                }
                try:
                    merge_outcome = merge_result(
                        wt,
                        source_commit=source_commit,
                        approved_files=gate.changed_files,
                        allow_harness_self_modify=allow_harness,
                    )
                except Exception as exc:  # noqa: BLE001
                    rollback_failures = _rollback_targets(
                        main_repo_root,
                        gate.changed_files,
                        tracked_at_head,
                    )
                    try:
                        persist_dispatch_artifacts(wt, main_repo_root)
                    except Exception:  # noqa: BLE001
                        pass
                    if rollback_failures:
                        return FinalizeResult(
                            "blocked",
                            "rollback-failed:"
                            f"merge-error:{exc}; failures={rollback_failures}",
                            [],
                        )
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
    except Exception as exc:  # noqa: BLE001
        try:
            persist_dispatch_artifacts(wt, main_repo_root)
        except Exception:  # noqa: BLE001
            pass
        return FinalizeResult("blocked", f"error:{exc}", [])


def build_claude_fallback(
    main_repo_root: pathlib.Path,
    *,
    timeout_seconds: int | None = None,
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
            dispatch_status = _diagnostic_token(job.stderr, "dispatch_status")
            if dispatch_status in {"completed", "fallback_completed"}:
                break
            count += 1
        return count
    finally:
        registry.close()


def _diagnostic_token(payload: str | None, key: str) -> str | None:
    prefix = f"{key}="
    for token in (payload or "").split():
        if token.startswith(prefix):
            return token.removeprefix(prefix)
    return None
