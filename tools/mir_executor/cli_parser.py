"""Independent argument parser for common executor commands."""

from __future__ import annotations

import argparse
import pathlib

from tools.mir_executor.dispatch import (
    DEFAULT_FINALIZE_LOCK_TIMEOUT,
    MAX_CODEX_ATTEMPTS,
)
from tools.mir_executor.local_hooks import invoke_hook

_DISPATCH_BACKENDS = frozenset({"codex", "claude"})

_STANDARD_CATEGORIES = [
    "unit",
    "integration",
    "e2e",
    "browser",
    "edge",
    "architecture",
    "availability",
    "load",
    "soak",
    "security",
    "compatibility",
    "transaction_locking",
]


def _positive_int(value: str) -> int:
    """Parse a strictly positive integer for explicit retry budgets."""
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return parsed


def _nonnegative_int(value: str) -> int:
    """Parse a non-negative integer for bounded lock waits."""
    parsed = int(value)
    if parsed < 0:
        raise argparse.ArgumentTypeError("must be a non-negative integer")
    return parsed


def _build_parser(repo_root: pathlib.Path | None = None) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m tools.mir_executor",
        description="Mir Executor — isolated delegated execution with optional TDD ledger update.",
    )
    # Global --jobs-db option available for all subcommands
    parser.add_argument(
        "--jobs-db",
        metavar="PATH",
        default=None,
        help="Override path to jobs.db (default: <repo_root>/tasks/jobs.db).",
    )
    sub = parser.add_subparsers(dest="subcommand")

    # ------------------------------------------------------------------
    # execute subcommand
    # ------------------------------------------------------------------
    exec_p = sub.add_parser(
        "execute",
        help="Run a delegated command; ledger identity is optional in dispatch mode.",
    )
    exec_p.add_argument(
        "--change-id",
        required=False,
        metavar="ID",
        help="Optional tdd.json change entry id; required outside --dispatch.",
    )
    exec_p.add_argument(
        "--category",
        required=False,
        choices=_STANDARD_CATEGORIES,
        metavar="NAME",
        help=(
            "Optional tdd.json category; required outside --dispatch. One of: "
            + ", ".join(_STANDARD_CATEGORIES)
            + "."
        ),
    )
    codex_args_group = exec_p.add_mutually_exclusive_group(required=False)
    codex_args_group.add_argument(
        "--codex-args",
        metavar="QUOTED_STRING",
        help=(
            "Arguments for legacy Codex invocation. In --dispatch mode, "
            "exec-shaped flags are dropped and the positional prompt is sent "
            "to the MCP Codex backend."
        ),
    )
    codex_args_group.add_argument(
        "--codex-args-file",
        type=pathlib.Path,
        metavar="PATH",
        help=(
            "Read UTF-8 file content and use it as one raw positional prompt "
            "argument, without shlex tokenization."
        ),
    )
    exec_p.add_argument(
        "--timeout",
        type=int,
        default=None,
        metavar="SECONDS",
        help="Optional hard subprocess timeout in seconds.",
    )
    exec_p.add_argument(
        "--model",
        default=None,
        metavar="MODEL",
        help=(
            "Optional Codex model name (e.g. a codex model id); omit to inherit "
            "Codex defaults."
        ),
    )
    exec_p.add_argument(
        "--reasoning-effort",
        default=None,
        metavar="EFFORT",
        help=(
            "Optional Codex model_reasoning_effort (free string); omit to inherit "
            "Codex defaults."
        ),
    )
    exec_p.add_argument(
        "--stall-timeout",
        type=float,
        default=None,
        metavar="SECONDS",
        help=("Optional no-progress MCP stall timeout in seconds."),
    )
    exec_p.add_argument(
        "--jobs-db",
        metavar="PATH",
        default=argparse.SUPPRESS,
        help="Override path to jobs.db (default: <repo_root>/tasks/jobs.db).",
    )
    exec_p.add_argument(
        "--repo-root",
        type=pathlib.Path,
        metavar="PATH",
        default=pathlib.Path.cwd(),
        help="Repository root path. Used to locate tasks/tdd.json.",
    )
    exec_p.add_argument("--family", default=None, help="Optional job family.")
    exec_p.add_argument("--artifacts-dir", type=pathlib.Path, default=None)
    invoke_hook(repo_root or pathlib.Path.cwd(), "register_execute_options", exec_p)
    exec_p.add_argument(
        "--async",
        "-a",
        action="store_true",
        default=False,
        dest="use_async",
        help="Use asyncio-based async subprocess (asyncio.TimeoutError on timeout).",
    )
    exec_p.add_argument(
        "--background",
        "-b",
        action="store_true",
        default=False,
        dest="background",
        help=(
            "Background mode: print job_id immediately, then run Codex and update "
            "job status on completion. MVP: runs in same process (true daemon is OOS)."
        ),
    )
    exec_p.add_argument(
        "--dispatch",
        action="store_true",
        default=False,
        dest="dispatch",
        help=(
            "Run the delegated dispatch helper with an isolated worktree, one "
            "attempt by default, and the outage guard."
        ),
    )
    exec_p.add_argument(
        "--max-codex-attempts",
        type=_positive_int,
        default=MAX_CODEX_ATTEMPTS,
        dest="max_codex_attempts",
        metavar="N",
        help=(
            "Explicit dispatch attempt budget (default: 1). Values above one opt "
            "into retrying the same dispatch."
        ),
    )
    exec_p.add_argument(
        "--finalize-lock-timeout",
        type=_nonnegative_int,
        default=DEFAULT_FINALIZE_LOCK_TIMEOUT,
        dest="finalize_lock_timeout",
        metavar="SECONDS",
        help=(
            "Maximum wait for the short merge-finalize lock (default: 30). "
            "This never stops a running delegated agent."
        ),
    )
    exec_p.add_argument(
        "--execution-backend",
        choices=sorted(_DISPATCH_BACKENDS),
        default=None,
        dest="execution_backend",
        metavar="BACKEND",
        help=(
            "ADR-61 dispatch-only backend request. Used only when the sub-agent "
            "policy permits selection; omitted requests retain the Codex preference."
        ),
    )
    exec_p.add_argument(
        "--expect-changes",
        action=argparse.BooleanOptionalAction,
        default=True,
        dest="expect_changes",
        help=(
            "Require a dispatch to produce a git diff before merge (default: true). "
            "Use --no-expect-changes for legitimate no-op or verify-only dispatches."
        ),
    )
    exec_p.add_argument(
        "--allow-harness-self-modify",
        action="store_true",
        default=False,
        dest="allow_harness_self_modify",
        help=(
            "Allow dispatch merge-back for liftable harness prefixes "
            "(.claude/, .ai-harness/, config/, docs/) when also allowlisted. "
            "tasks/ remains denied."
        ),
    )
    exec_p.add_argument(
        "--allow-path",
        action="append",
        dest="allow_paths",
        default=argparse.SUPPRESS,
        metavar="PATH",
        help="Repeatable ADR-60 dispatch merge allowlist path.",
    )
    exec_p.add_argument(
        "--verify-cmd",
        action="append",
        dest="verify_cmds",
        default=argparse.SUPPRESS,
        metavar="COMMAND",
        help="Repeatable ADR-60 dispatch verification command to re-run before merge.",
    )
    exec_p.add_argument(
        "--dispatch-brief",
        type=pathlib.Path,
        default=None,
        dest="dispatch_brief",
        metavar="PATH",
        help=(
            "Persisted DispatchBrief JSON. In --dispatch mode, expanded_goal "
            "is used as the MCP prompt when --codex-args contains no prompt positional."
        ),
    )

    # ------------------------------------------------------------------
    # status subcommand
    # ------------------------------------------------------------------
    status_p = sub.add_parser(
        "status",
        help="Print job status from the JobRegistry.",
    )
    status_p.add_argument(
        "--job-id",
        required=True,
        metavar="JOB_ID",
        help="UUID job_id returned by execute --background.",
    )
    status_p.add_argument(
        "--repo-root",
        type=pathlib.Path,
        metavar="PATH",
        default=None,
        help="Repository root path (for default jobs.db location).",
    )

    # ------------------------------------------------------------------
    # result subcommand
    # ------------------------------------------------------------------
    result_p = sub.add_parser(
        "result",
        help="Print job result (exit_code, stdout, stderr, duration) from the JobRegistry.",
    )
    result_p.add_argument(
        "--job-id",
        required=True,
        metavar="JOB_ID",
        help="UUID job_id returned by execute --background.",
    )
    result_p.add_argument(
        "--repo-root",
        type=pathlib.Path,
        metavar="PATH",
        default=None,
        help="Repository root path (for default jobs.db location).",
    )

    # ------------------------------------------------------------------
    # cancel subcommand
    # ------------------------------------------------------------------
    cancel_p = sub.add_parser(
        "cancel",
        help="Request cancellation of a background job.",
    )
    cancel_p.add_argument(
        "--job-id",
        required=True,
        metavar="JOB_ID",
        help="UUID job_id returned by execute --background.",
    )
    cancel_p.add_argument(
        "--repo-root",
        type=pathlib.Path,
        metavar="PATH",
        default=None,
        help="Repository root path (for default jobs.db location).",
    )

    # ------------------------------------------------------------------
    # resume subcommand
    # ------------------------------------------------------------------
    resume_p = sub.add_parser(
        "resume",
        help="Resume a job from its persisted DispatchBrief and stored registry state.",
    )
    resume_p.add_argument(
        "--job-id",
        required=True,
        metavar="JOB_ID",
        help="UUID job_id returned by execute --background or conductor bridge dispatch.",
    )
    resume_p.add_argument(
        "--timeout",
        type=int,
        default=None,
        metavar="SECONDS",
        help="Optional hard subprocess timeout in seconds.",
    )
    resume_p.add_argument(
        "--async",
        "-a",
        action="store_true",
        default=False,
        dest="use_async",
        help="Use asyncio-based async subprocess for resume.",
    )
    resume_p.add_argument(
        "--repo-root",
        type=pathlib.Path,
        metavar="PATH",
        default=None,
        help="Repository root path (for default jobs.db location).",
    )

    # ------------------------------------------------------------------
    # list-jobs subcommand
    # ------------------------------------------------------------------
    list_p = sub.add_parser(
        "list-jobs",
        help="List background jobs, optionally filtered by status.",
    )
    list_p.add_argument(
        "--status",
        metavar="STATUS",
        default=None,
        choices=["running", "completed", "cancelled", "failed"],
        help="Filter by status: running / completed / cancelled / failed.",
    )
    list_p.add_argument(
        "--repo-root",
        type=pathlib.Path,
        metavar="PATH",
        default=None,
        help="Repository root path (for default jobs.db location).",
    )

    sweep_p = sub.add_parser(
        "sweep",
        help="Report advisory-overdue jobs and orphan dispatch worktrees.",
    )
    sweep_p.add_argument(
        "--apply",
        action="store_true",
        default=False,
        help="Apply the reported cleanup (default: dry-run).",
    )
    sweep_p.add_argument(
        "--repo-root",
        type=pathlib.Path,
        default=pathlib.Path.cwd(),
        metavar="PATH",
        help="Main repository root (default: current directory).",
    )
    sweep_p.add_argument(
        "--jobs-db",
        metavar="PATH",
        default=argparse.SUPPRESS,
        help="Override path to jobs.db (default: <repo-root>/tasks/jobs.db).",
    )
    sweep_p.add_argument(
        "--grace-seconds",
        type=int,
        default=120,
        metavar="N",
        help="Grace after each advisory elapsed threshold (default: 120).",
    )

    return parser


# ---------------------------------------------------------------------------
# Background job runner (async)
# ---------------------------------------------------------------------------
