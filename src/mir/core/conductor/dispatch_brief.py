"""DispatchBrief builder + persistence for conductor bridge handoff."""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

from mir.core.contracts.dispatch_brief import DispatchBrief, DispatchBriefSourceRefs
from mir.core.contracts.task_spec import TaskSpec

_ROLE_TO_TARGET_AGENT: dict[str, str] = {
    "executor": "executor-agent",
    "reviewer": "codex-final-reviewer",
    "planner": "main-orchestrator",
    "tester": "quality-agent",
}


def build_dispatch_brief(
    task_spec: TaskSpec,
    *,
    family_slug: str,
    change_id: str | None = None,
    verification_commands: tuple[str, ...] = (),
    phase_ref: str = "tasks/phase.json",
) -> DispatchBrief:
    """Build the persisted execution-lane handoff artifact."""
    del family_slug  # Reserved for future family-specific routing expansion.

    task_id = _derive_task_id(task_spec)
    slice_id = _derive_slice_id(task_spec, change_id=change_id)
    owned_scope = tuple(task_spec.scope)
    verification = verification_commands or ("uv run pytest -q",)

    return DispatchBrief(
        version=1,
        task_id=task_id,
        phase_id=task_spec.phase_tag,
        slice_id=slice_id,
        target_agent=_ROLE_TO_TARGET_AGENT.get(task_spec.role_binding, "executor-agent"),
        user_intent=task_spec.intent.strip(),
        expanded_goal=_expanded_goal(task_spec),
        owned_scope=owned_scope,
        out_of_scope=("Do not edit paths outside owned_scope without orchestration approval.",),
        verification_commands=verification,
        stop_conditions=_stop_conditions(owned_scope),
        handoff_refs=(),
        tdd_change_refs=(f"tasks/tdd.json#{change_id}",) if change_id else (),
        resume_state_ref=f"tasks/dispatch/{task_id}/{slice_id}.json",
        source_refs=DispatchBriefSourceRefs(
            task_spec=f"runtime://task-spec/{task_id}",
            plan="tasks/plan.md",
            phase=phase_ref,
        ),
    )


def persist_dispatch_brief(
    brief: DispatchBrief,
    *,
    repo_root: Path,
    dispatch_root: Path | None = None,
) -> Path:
    """Atomically persist DispatchBrief JSON and return the filesystem path."""
    if dispatch_root is None:
        target_path = repo_root / brief.resume_state_ref
    else:
        target_path = dispatch_root / brief.task_id / f"{brief.slice_id}.json"

    target_path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(brief.model_dump(mode="json"), indent=2, ensure_ascii=False) + "\n"

    fd, tmp_path = tempfile.mkstemp(dir=target_path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(payload)
        os.replace(tmp_path, target_path)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise

    return target_path


def load_dispatch_brief(path: Path) -> DispatchBrief:
    """Load and validate a persisted DispatchBrief JSON file."""
    payload: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return DispatchBrief(**payload)


def verification_commands_from_tdd_entry(entry: Any) -> tuple[str, ...]:
    """Extract command-bearing category commands from a TDD entry."""
    categories = getattr(entry, "categories", {}) or {}
    commands: list[str] = []
    for payload in categories.values():
        if not isinstance(payload, dict):
            continue
        command = payload.get("command")
        if isinstance(command, str) and command and command not in commands:
            commands.append(command)
    return tuple(commands)


def codex_args_from_dispatch_brief(brief: DispatchBrief) -> tuple[str, ...]:
    """Return the deterministic Codex argv used for brief-driven execution."""
    return ("exec", brief.expanded_goal)


def _derive_task_id(task_spec: TaskSpec) -> str:
    return task_spec.fingerprint or _slugify(task_spec.intent) or "dispatch-task"


def _derive_slice_id(task_spec: TaskSpec, *, change_id: str | None) -> str:
    if change_id:
        return _slugify(change_id) or "dispatch-slice"
    phase_part = task_spec.phase_tag or "task"
    return _slugify(f"{phase_part}-{task_spec.role_binding}") or "dispatch-slice"


def _expanded_goal(task_spec: TaskSpec) -> str:
    return (
        f"{task_spec.intent.strip()} "
        f"[role={task_spec.role_binding}, stack={task_spec.stack or 'default'}]"
    )


def _stop_conditions(owned_scope: tuple[str, ...]) -> tuple[str, ...]:
    if "<unspecified>" in owned_scope:
        return (
            "Stop and hand control back if concrete file or module ownership remains unresolved.",
            "Stop if the requested work expands beyond the current slice intent.",
        )
    return (
        "Stop if the change requires files outside owned_scope.",
        "Stop if verification_commands no longer match the edited surface.",
    )


def _slugify(value: str) -> str:
    lowered = value.lower()
    chars = [ch if ch.isalnum() else "-" for ch in lowered]
    slug = "".join(chars).strip("-")
    while "--" in slug:
        slug = slug.replace("--", "-")
    return slug[:80]


__all__ = (
    "build_dispatch_brief",
    "codex_args_from_dispatch_brief",
    "load_dispatch_brief",
    "persist_dispatch_brief",
    "verification_commands_from_tdd_entry",
)
