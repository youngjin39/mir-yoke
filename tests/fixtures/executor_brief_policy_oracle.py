"""DispatchBrief contract for execution-lane handoff and durable resume."""
from __future__ import annotations

import argparse
import dataclasses
import hashlib
import json
import os
import pathlib
from typing import ClassVar

from pydantic import BaseModel, ConfigDict, Field, model_validator

VERIFICATION_IDS = frozenset(
    {
        "python-tests",
        "project-verification",
        "ruff",
        "mypy",
        "spec-projections",
        "git-diff-check",
    }
)


class DispatchBriefSourceRefs(BaseModel):
    """Source references used to derive a dispatch brief."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    task_spec: str = Field(min_length=1)
    plan: str = Field(default="tasks/plan.md")
    phase: str = Field(min_length=1)


class DispatchBrief(BaseModel):
    """Execution-ready handoff artifact for one target agent and one slice."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    CURRENT_VERSION: ClassVar[int] = 2

    version: int = Field(default=CURRENT_VERSION)
    task_id: str = Field(min_length=1)
    phase_id: str | None = None
    slice_id: str = Field(min_length=1)
    target_agent: str = Field(min_length=1)
    user_intent: str = Field(min_length=1)
    expanded_goal: str = Field(min_length=1)
    owned_scope: tuple[str, ...] = Field(min_length=1)
    out_of_scope: tuple[str, ...] = ()
    verification_ids: tuple[str, ...] = ()
    verification_commands: tuple[str, ...] = ()
    stop_conditions: tuple[str, ...] = Field(min_length=1)
    handoff_refs: tuple[str, ...] = ()
    tdd_change_refs: tuple[str, ...] = ()
    resume_state_ref: str = Field(min_length=1)
    source_refs: DispatchBriefSourceRefs

    @model_validator(mode="after")
    def _validate_contract(self) -> DispatchBrief:
        if self.version == self.CURRENT_VERSION:
            if not self.verification_ids:
                raise ValueError("DispatchBrief v2 requires verification_ids")
            unknown = sorted(set(self.verification_ids) - VERIFICATION_IDS)
            if unknown:
                raise ValueError(f"DispatchBrief contains unknown verification_ids: {unknown}")
            if self.verification_commands:
                raise ValueError("DispatchBrief v2 forbids verification_commands")
        elif self.version == 1:
            if not self.verification_commands:
                raise ValueError("DispatchBrief v1 requires verification_commands")
            if self.verification_ids:
                raise ValueError("DispatchBrief v1 forbids verification_ids")
        else:
            raise ValueError("DispatchBrief.version must be 1 or 2")
        expected_resume_ref = f"tasks/dispatch/{self.task_id}/{self.slice_id}.json"
        if self.resume_state_ref != expected_resume_ref:
            raise ValueError(
                "DispatchBrief.resume_state_ref must match "
                f"{expected_resume_ref!r}"
            )
        if self.source_refs.plan != "tasks/plan.md":
            raise ValueError("DispatchBrief.source_refs.plan must be 'tasks/plan.md'")
        return self

    @property
    def automatic_finalization_allowed(self) -> bool:
        """Return whether this brief uses the non-executable v2 verifier contract."""
        return self.version == self.CURRENT_VERSION


# Generic oracle extracted from the reference brief controls and result hooks.


def load_dispatch_brief(path):
    return DispatchBrief(**json.loads(path.read_text(encoding="utf-8")))


# Briefs typed by pre_execute, keyed by path and content digest, for validate_brief to reuse.
_LOADED_BRIEFS: dict[tuple[pathlib.Path, str], object] = {}


def _brief_key(path: pathlib.Path) -> tuple[pathlib.Path, str]:
    resolved = path.resolve()
    return resolved, hashlib.sha256(resolved.read_bytes()).hexdigest()


def validate_brief(brief: pathlib.Path | str, repo_root: pathlib.Path):
    """Keep the typed DispatchBrief file schema; plain prompt text passes through."""
    if isinstance(brief, pathlib.Path):
        cached = _LOADED_BRIEFS.pop(_brief_key(brief), None)
        if cached is not None:
            return cached

        return load_dispatch_brief(brief)
    return None


def after_provider_call(result: object, metadata: dict) -> object | None:
    """Bound and redact dispatch output kept in memory, as the jobs DB does."""
    from tools.mir_executor.dispatch import CodexAttempt  # noqa: PLC0415
    from tools.mir_executor.jobs import sanitize_persisted_text  # noqa: PLC0415

    if not isinstance(result, CodexAttempt):
        return None
    stdout = sanitize_persisted_text(result.stdout) or ""
    stderr = sanitize_persisted_text(result.stderr) or ""
    if (stdout, stderr) == (result.stdout, result.stderr):
        return None
    return dataclasses.replace(result, stdout=stdout, stderr=stderr)


def after_run(worktree: object, attempt: int, result: object) -> None:
    """Keep each attempt's redacted result in result.json for the dispatch artifacts."""
    from tools.mir_executor.jobs import sanitize_persisted_text  # noqa: PLC0415

    payload = {
        "exit_code": result.exit_code,
        "error_sig": sanitize_persisted_text(result.error_sig) or "",
        "stdout": sanitize_persisted_text(result.stdout) or "",
        "stderr": sanitize_persisted_text(result.stderr) or "",
        "lane_unavailable": result.lane_unavailable,
        "retryable": result.retryable,
        "blocked_reason": sanitize_persisted_text(result.blocked_reason),
    }
    path = pathlib.Path(worktree.result_path)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.chmod(path, 0o600)


def _apply_dispatch_brief_controls(args: argparse.Namespace) -> None:
    """A v2 brief is the sole source of the prompt, merge allowlist and verifier IDs."""
    brief_path = getattr(args, "dispatch_brief", None)
    if not getattr(args, "dispatch", False) or brief_path is None:
        return

    key = _brief_key(pathlib.Path(brief_path))
    brief = load_dispatch_brief(pathlib.Path(brief_path))
    if brief.version != brief.CURRENT_VERSION:
        raise ValueError(
            "DispatchBrief v1 is diagnostic-only; CLI dispatch requires a v2 brief"
        )
    if getattr(args, "codex_args", None) is not None or getattr(
        args, "codex_args_file", None
    ) is not None:
        raise ValueError("--dispatch-brief cannot be combined with Codex prompt arguments")
    # Resume callers hash-check the persisted brief before restoring these lists.
    # Initial execute must reject even identical explicit CLI controls.
    resuming = bool(getattr(args, "resume_job_id", None))
    allow_paths = getattr(args, "allow_paths", None)
    verify_cmds = getattr(args, "verify_cmds", None)
    if (allow_paths or (resuming and allow_paths is not None)) and not (
        resuming and args.allow_paths == list(brief.owned_scope)
    ):
        raise ValueError("--dispatch-brief owns the merge allowlist; omit --allow-path")
    if (verify_cmds or (resuming and verify_cmds is not None)) and not (
        resuming and args.verify_cmds == list(brief.verification_ids)
    ):
        raise ValueError("--dispatch-brief owns verification IDs; omit --verify-cmd")
    args.allow_paths = list(brief.owned_scope)
    args.verify_cmds = list(brief.verification_ids)
    _LOADED_BRIEFS[key] = brief


def pre_execute(args, root):
    _apply_dispatch_brief_controls(args)
