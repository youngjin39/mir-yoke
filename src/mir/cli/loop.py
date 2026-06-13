"""File-backed continuation loop cursor CLI for ``tasks/plan.md``."""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_HARNESS_ROOT = Path(__file__).resolve().parents[3]
if str(_HARNESS_ROOT) not in sys.path:
    sys.path.insert(0, str(_HARNESS_ROOT))

from tools.autonomous_loop.loop import (  # noqa: E402
    trigger_circuit_breaker,
    trigger_retry_budget,
)
from tools.plan_archive.archiver import (  # noqa: E402
    _BODY_STEP_STATUS_RE,
    STEP_STATUS_VOCAB,
    Section,
    parse_sections,
)

PLAN_PATH = Path("tasks/plan.md")
MARK_STATUSES = STEP_STATUS_VOCAB
DONE_STATUSES = {"DONE", "CLOSED"}
STEP_ATTEMPT_BLOCK_THRESHOLD = 3


class LoopError(RuntimeError):
    """Raised for invalid cursor mutations."""


@dataclass(frozen=True)
class PlanStep:
    step_id: int
    status: str
    line: str
    fields: dict[str, str]

    @property
    def attempts(self) -> int:
        raw = self.fields.get("attempts")
        if raw is None:
            return 0
        try:
            return int(raw)
        except ValueError:
            return 0

    @property
    def brief(self) -> str | None:
        return self.fields.get("brief")

    @property
    def tdd_change_id(self) -> str | None:
        raw = self.fields.get("tdd")
        if not raw or "#" not in raw:
            return None
        return raw.rsplit("#", 1)[0] or None

    @property
    def tdd_category(self) -> str | None:
        raw = self.fields.get("tdd")
        if not raw or "#" not in raw:
            return None
        return raw.rsplit("#", 1)[1] or None


@dataclass(frozen=True)
class NextResult:
    status: str
    step_id: int | None = None
    brief: str | None = None
    tdd_change_id: str | None = None
    tdd_category: str | None = None
    reason: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "step_id": self.step_id,
            "brief": self.brief,
            "tdd_change_id": self.tdd_change_id,
            "tdd_category": self.tdd_category,
            "reason": self.reason,
        }


def _active_task_section(text: str) -> Section | None:
    for section in parse_sections(text):
        if not section.heading:
            continue
        if "Pinned Tracker Policies" in section.heading:
            continue
        return section
    return None


def _parse_fields(line: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    for part in line.rstrip("\r\n").split("|")[1:]:
        item = part.strip()
        if "=" not in item:
            continue
        key, value = item.split("=", 1)
        fields[key.strip()] = value.strip()
    return fields


def _parse_step_line(line: str) -> PlanStep | None:
    match = _BODY_STEP_STATUS_RE.match(line)
    if not match:
        return None
    return PlanStep(
        step_id=int(match.group("step_id")),
        status=match.group("status"),
        line=line,
        fields=_parse_fields(line),
    )


def _section_steps(section: Section) -> list[PlanStep]:
    steps: list[PlanStep] = []
    for line in section.content.splitlines():
        step = _parse_step_line(line)
        if step is not None:
            steps.append(step)
    return steps


def _blocked_result(step: PlanStep, reason: str) -> NextResult:
    return NextResult(
        status="BLOCKED",
        step_id=step.step_id,
        brief=step.brief,
        tdd_change_id=step.tdd_change_id,
        tdd_category=step.tdd_category,
        reason=reason,
    )


def _step_result(step: PlanStep) -> NextResult:
    return NextResult(
        status="STEP",
        step_id=step.step_id,
        brief=step.brief,
        tdd_change_id=step.tdd_change_id,
        tdd_category=step.tdd_category,
    )


def next_step(plan_path: Path = PLAN_PATH) -> NextResult:
    section = _active_task_section(plan_path.read_text(encoding="utf-8"))
    if section is None:
        return NextResult(status="BLOCKED", reason="no_active_section")

    steps = _section_steps(section)
    if not steps:
        return NextResult(status="BLOCKED", reason="no_machine_steps")

    for step in steps:
        if step.status in DONE_STATUSES:
            continue
        if step.status == "BLOCKED":
            trigger = trigger_circuit_breaker({"state": "open"})
            reason = trigger.reason if trigger else "step_blocked"
            return _blocked_result(step, reason)
        if step.status == "FAILED":
            retry_trigger = trigger_retry_budget(
                {"retry_count": {"total": step.attempts}}
            )
            if retry_trigger is not None:
                return _blocked_result(step, retry_trigger.reason)
            if step.attempts >= STEP_ATTEMPT_BLOCK_THRESHOLD:
                return _blocked_result(
                    step,
                    (
                        f"attempts={step.attempts} >= "
                        f"threshold={STEP_ATTEMPT_BLOCK_THRESHOLD}"
                    ),
                )
        return _step_result(step)

    return NextResult(status="COMPLETE")


def _set_field(line: str, key: str, value: str) -> str:
    newline = ""
    body = line
    if body.endswith("\r\n"):
        body = body[:-2]
        newline = "\r\n"
    elif body.endswith("\n"):
        body = body[:-1]
        newline = "\n"

    parts = body.split(" | ")
    replacement = f"{key}={value}"
    for index in range(1, len(parts)):
        if parts[index].startswith(f"{key}="):
            parts[index] = replacement
            break
    else:
        parts.append(replacement)
    return " | ".join(parts) + newline


def _replace_status(line: str, status: str) -> str:
    match = _BODY_STEP_STATUS_RE.match(line)
    if not match:
        raise LoopError("line is not a machine step")
    return line[: match.start("status")] + status + line[match.end("status") :]


def _rewrite_step_line(line: str, status: str, reason: str | None) -> tuple[str, bool]:
    step = _parse_step_line(line)
    if step is None:
        raise LoopError("line is not a machine step")

    if status == "IN_PROGRESS":
        if step.status == "IN_PROGRESS":
            return line, False
        if step.status != "TODO":
            raise LoopError(
                "IN_PROGRESS compare-and-set requires current status TODO "
                f"(got {step.status})"
            )
    elif step.status in DONE_STATUSES and status != step.status:
        raise LoopError(f"refusing to rewrite completed step {step.step_id}")

    updated = _replace_status(line, status)
    if status == "FAILED":
        updated = _set_field(updated, "attempts", str(step.attempts + 1))
    if reason:
        updated = _set_field(updated, "reason", reason)
    return updated, updated != line


def _atomic_write(path: Path, content: str) -> None:
    fd, tmp_path = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(content)
        os.replace(tmp_path, path)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def mark_step(
    step_id: int,
    status: str,
    reason: str | None = None,
    plan_path: Path = PLAN_PATH,
) -> dict[str, Any]:
    if status not in MARK_STATUSES:
        raise LoopError(f"unsupported status: {status}")

    lines = plan_path.read_text(encoding="utf-8").splitlines(keepends=True)
    for index, line in enumerate(lines):
        step = _parse_step_line(line)
        if step is None or step.step_id != step_id:
            continue
        updated, changed = _rewrite_step_line(line, status, reason)
        if changed:
            lines[index] = updated
            _atomic_write(plan_path, "".join(lines))
        return {
            "status": "OK",
            "step_id": step_id,
            "previous_status": step.status,
            "new_status": status,
            "changed": changed,
        }

    raise LoopError(f"step not found: {step_id}")


def _print_next(result: NextResult, as_json: bool) -> None:
    payload = result.as_dict()
    if as_json:
        print(json.dumps(payload, sort_keys=True))
        return
    detail = payload["reason"] or payload["brief"] or ""
    print(f"{payload['status']} step_id={payload['step_id']} {detail}".rstrip())


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="mir loop")
    sub = parser.add_subparsers(dest="command", required=True)

    next_parser = sub.add_parser("next", help="read the next plan cursor step")
    next_parser.add_argument("--json", action="store_true", dest="as_json")

    mark_parser = sub.add_parser("mark", help="update one plan cursor step")
    mark_parser.add_argument("--step", type=int, required=True)
    mark_parser.add_argument("--status", choices=MARK_STATUSES, required=True)
    mark_parser.add_argument("--reason")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "next":
            _print_next(next_step(), args.as_json)
            return 0
        if args.command == "mark":
            result = mark_step(args.step, args.status, args.reason)
            print(json.dumps(result, sort_keys=True))
            return 0
    except LoopError as exc:
        print(f"[mir loop] {exc}", file=sys.stderr)
        return 1
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
