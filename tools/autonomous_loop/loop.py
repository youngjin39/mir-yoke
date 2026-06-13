"""Autonomous loop 6-trigger detectors (R27-T03)."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

from scripts.verify_self_stop import verify_self_stop

RETRY_BUDGET_THRESHOLD = 5

SE_META_FAMILIES = {"your-harness"}


@dataclass
class TriggerResult:
    trigger_id: str
    reason: str
    should_request_approval: bool


def trigger_retry_budget(task_state: dict) -> TriggerResult | None:
    """Fire when retry_count.total >= RETRY_BUDGET_THRESHOLD."""
    retry = task_state.get("retry_count")
    if not isinstance(retry, dict):
        return None
    total = retry.get("total")
    if total is None:
        return None
    if total >= RETRY_BUDGET_THRESHOLD:
        return TriggerResult(
            trigger_id="retry_budget",
            reason=f"retry_count.total={total} >= threshold={RETRY_BUDGET_THRESHOLD}",
            should_request_approval=True,
        )
    return None


def trigger_se_meta_self_stop(family: str, fleet_state_path: Path) -> TriggerResult | None:
    """Fire when SE-meta family self-stop check returns BLOCK."""
    if family not in SE_META_FAMILIES:
        return None
    result = verify_self_stop(
        source_family=family,
        phase=None,
        ledger_path=fleet_state_path,
        catalog_path=fleet_state_path,
        override=False,
    )
    if result.decision.value == "BLOCK":
        return TriggerResult(
            trigger_id="se_meta_self_stop",
            reason=f"verify_self_stop returned BLOCK for family={family}",
            should_request_approval=True,
        )
    return None


def trigger_circuit_breaker(state: dict) -> TriggerResult | None:
    """Fire when circuit breaker state is 'open'."""
    if state.get("state") == "open":
        return TriggerResult(
            trigger_id="circuit_breaker",
            reason="circuit breaker state=open",
            should_request_approval=True,
        )
    return None


def trigger_interrupt(flag_path: Path) -> TriggerResult | None:
    """Fire when interrupt flag file exists."""
    if flag_path.exists():
        return TriggerResult(
            trigger_id="interrupt",
            reason=f"interrupt flag present at {flag_path}",
            should_request_approval=True,
        )
    return None


def trigger_external_side_effect(
    tool_name: str, side_effects_yaml: Path
) -> TriggerResult | None:
    """Fire when tool_name is in the always_require_approval list."""
    if not side_effects_yaml.exists():
        return None
    data = yaml.safe_load(side_effects_yaml.read_text())
    if not isinstance(data, dict):
        return None
    blocked = data.get("always_require_approval", [])
    if tool_name in blocked:
        return TriggerResult(
            trigger_id="external_side_effect",
            reason=f"tool={tool_name} requires approval per external_side_effects.yaml",
            should_request_approval=True,
        )
    return None


def detect_all(
    task_state: dict,
    run_state: dict,
    family: str = "your-harness",
    interrupt_flag: Path | None = None,
    fleet_state_path: Path | None = None,
    circuit_state: dict | None = None,
    tool_name: str | None = None,
    side_effects_yaml: Path | None = None,
) -> list[TriggerResult]:
    """Run all 6 trigger detectors and return list of fired TriggerResults."""
    results: list[TriggerResult] = []

    t1 = trigger_retry_budget(task_state)
    if t1:
        results.append(t1)

    if fleet_state_path is not None:
        t2 = trigger_se_meta_self_stop(family, fleet_state_path)
        if t2:
            results.append(t2)

    if circuit_state is not None:
        t4 = trigger_circuit_breaker(circuit_state)
        if t4:
            results.append(t4)

    if interrupt_flag is not None:
        t5 = trigger_interrupt(interrupt_flag)
        if t5:
            results.append(t5)

    if tool_name is not None and side_effects_yaml is not None:
        t6 = trigger_external_side_effect(tool_name, side_effects_yaml)
        if t6:
            results.append(t6)

    return results


def main() -> int:
    import argparse
    import json
    import sys as _sys

    parser = argparse.ArgumentParser(description="Autonomous loop 6-trigger detector CLI.")
    parser.add_argument("--detect", action="store_true")
    parser.add_argument(
        # active_task.json retired (ADR-44 R21); retry_count now lives in run_state,
        # matching orchestrator.detect_all(run_state, run_state).
        "--task-state",
        type=Path,
        default=Path("tasks/run_state.json"),
    )
    parser.add_argument("--run-state", type=Path, default=Path("tasks/run_state.json"))
    parser.add_argument("--family", default="your-harness")
    args = parser.parse_args()

    if not args.detect:
        parser.print_help()
        return 0

    task_state = json.loads(args.task_state.read_text()) if args.task_state.exists() else {}
    run_state = json.loads(args.run_state.read_text()) if args.run_state.exists() else {}

    results = detect_all(task_state, run_state, family=args.family)
    for r in results:
        print(
            f"[intervention-trigger WARN] trigger={r.trigger_id} reason={r.reason}",
            file=_sys.stderr,
        )
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
