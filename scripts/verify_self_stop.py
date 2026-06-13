#!/usr/bin/env python3
"""ADR-41 SE-meta self-stop runtime gate.

tier: block — SE-meta self-stop obligation enforcement (R27-T02 / Choice 5=A).

Verifies that a share recommendation sourced from your-harness
is only forwarded to the fleet when the corresponding phase in
the mir-self rollout ledger has been adopted.

Exit codes:
  0 — PASS or WARN (WARN + --strict → 1)
  1 — BLOCK, or WARN with --strict
  2 — environment error (file not found, parse failure)
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import re
import sys
import tempfile
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path

# ---------------------------------------------------------------------------
# Decision types
# ---------------------------------------------------------------------------


class Decision(StrEnum):
    PASS = "PASS"
    WARN = "WARN"
    BLOCK = "BLOCK"


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class OverrideConfig:
    applied: bool
    reason: str = ""


@dataclass
class VerifyResult:
    decision: Decision
    reason: str
    source_family: str
    phase: str
    ledger_status: str
    catalog_status: str
    drift_detected: bool
    auto_reconciled: bool
    dogfooding_exemption: bool
    override_applied: bool
    advisory_log: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        ts = datetime.datetime.now(datetime.timezone.utc).strftime(  # noqa: UP017
            "%Y-%m-%dT%H:%M:%SZ"
        )
        return {
            "timestamp": ts,
            "source_family": self.source_family,
            "phase": self.phase,
            "ledger_status": self.ledger_status,
            "catalog_status": self.catalog_status,
            "drift_detected": self.drift_detected,
            "auto_reconciled": self.auto_reconciled,
            "dogfooding_exemption": self.dogfooding_exemption,
            "decision": self.decision.value,
            "reason": self.reason,
            "override": {
                "applied": self.override_applied,
                "reason": self._override_reason,
            },
            "advisory_log": self.advisory_log,
        }

    # Injected post-init by verify_self_stop()
    _override_reason: str = field(default="", repr=False)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Historical design-land-only exemption set.
# R11+ runtime tooling for phase-9..12 has landed, so the exemption is now empty.
_DESIGN_LAND_ONLY_PHASES = frozenset()

# Ledger status → fleet-harness-state.json status mapping
_LEDGER_TO_JSON_STATUS: dict[str, str] = {
    "pending": "not_adopted",
    "in_progress": "opt_in_pending",
    "partial": "opt_in_pending",
    "done": "adopted",
    "blocked": "not_adopted",
    "reverted": "declined",
}

# Statuses that result in BLOCK (absent dogfooding exemption)
_BLOCK_STATUSES = frozenset({"pending", "in_progress", "partial", "blocked", "reverted"})

# Unknown status sentinel
_UNKNOWN = "unknown"


# ---------------------------------------------------------------------------
# Ledger helpers — test-visible
# ---------------------------------------------------------------------------


def _build_mir_self_ledger_md(rows: dict[str, str]) -> str:
    """Build a minimal mir-self README.md ledger markdown for testing."""
    lines = [
        "# your-harness Self-Dogfooding — 9-Phase Rollout Ledger\n",
        "## 2. Rollout Ledger\n",
        "| Phase | Applied Design | Status | Exit Criterion | self-stop | Completion Date |",
        "|---|---|---|---|---|---|",
    ]
    for phase_key, status in rows.items():
        # Extract phase number
        m = re.match(r"phase-(\d+)", phase_key)
        n = m.group(1) if m else "?"
        lines.append(f"| {n} | [phase-{n}-application](phase-{n}-application.md)"
                     f" | {status} | – | – | – |")
    return "\n".join(lines) + "\n"


def _build_fleet_state_json(phase_statuses: dict[str, str]) -> dict:
    """Build a minimal fleet-harness-state.json for testing."""
    adoption = {}
    for phase_key, status in phase_statuses.items():
        adoption[phase_key] = {
            "status": status,
            "last_sync": "2026-05-23",
        }
    return {
        "version": "1.0",
        "last_updated": "2026-05-23T00:00:00Z",
        "families": {
            "your-harness": {
                "family_type": "SE-meta",
                "repo_path": "/path/to/your-harness",
                "adoption": adoption,
                "innovations": [],
                "recommendations_received": [],
            }
        },
    }


# ---------------------------------------------------------------------------
# Ledger parser
# ---------------------------------------------------------------------------


def parse_mir_self_ledger(ledger_path: Path, phase_ref: str) -> str:
    """Parse mir-self/README.md ledger table and return status for phase_ref.

    Returns the status string (e.g. "pending", "done") or _UNKNOWN on failure.
    Robust to varying whitespace in table cells.
    """
    try:
        content = ledger_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return _UNKNOWN

    # Extract phase number from "phase-N"
    m = re.match(r"phase-(\d+)$", phase_ref)
    if not m:
        return _UNKNOWN
    phase_num = m.group(1)

    # Match table rows: | N[optional extra] | ... | <status> | ...
    # The table has 6 columns; status is column 3 (0-indexed: cols 0-5).
    # Pattern: row starting with | <phase_num> followed by optional text (e.g. "(R9 added (newly))") |
    pattern = re.compile(
        r"^\|\s*" + re.escape(phase_num) + r"[^|]*\|[^|]*\|\s*([a-z_]+)\s*\|",
        re.MULTILINE,
    )
    match = pattern.search(content)
    if match:
        return match.group(1).strip()
    return _UNKNOWN


# ---------------------------------------------------------------------------
# Catalog (fleet-harness-state.json) helpers
# ---------------------------------------------------------------------------


def read_json_adoption_status(
    catalog_path: Path, family: str, phase_ref: str
) -> str:
    """Read adoption status for (family, phase_ref) from fleet-harness-state.json."""
    try:
        data = json.loads(catalog_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return _UNKNOWN

    try:
        return data["families"][family]["adoption"][phase_ref]["status"]
    except (KeyError, TypeError):
        return _UNKNOWN


def _atomic_write_json(path: Path, data: dict) -> None:
    """Atomic write via tempfile + os.replace (no partial-write risk)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
            f.write("\n")
        os.replace(tmp, path)
    except Exception:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def write_json_adoption_status(
    catalog_path: Path, family: str, phase_ref: str, new_status: str
) -> None:
    """Update adoption status for (family, phase_ref) in fleet-harness-state.json.

    Single direction only: ledger → JSON. Structural changes are prohibited.
    Uses atomic write (tempfile + os.replace) to avoid partial-write corruption.
    """
    try:
        data = json.loads(catalog_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return

    try:
        adoption = data["families"][family]["adoption"]
    except (KeyError, TypeError):
        return

    if phase_ref not in adoption:
        adoption[phase_ref] = {}

    adoption[phase_ref]["status"] = new_status

    try:
        _atomic_write_json(catalog_path, data)
    except OSError:
        pass


# ---------------------------------------------------------------------------
# Runtime-implemented heuristic
# ---------------------------------------------------------------------------


def is_runtime_implemented(phase_ref: str) -> bool:
    """Return True when the phase is no longer gated as design-land-only."""
    return phase_ref not in _DESIGN_LAND_ONLY_PHASES


# ---------------------------------------------------------------------------
# Core verification logic
# ---------------------------------------------------------------------------


def verify_self_stop(  # noqa: PLR0912 (acceptable complexity for gate logic)
    *,
    source_family: str,
    phase: str,
    ledger_path: Path,
    catalog_path: Path,
    override: OverrideConfig,
    auto_reconcile: bool = False,
    strict: bool = False,
    self_stop_acknowledged: bool | None = None,
    strictness: str = "doc-strict",
) -> VerifyResult:
    """Execute the 6-step SE-meta self-stop verification (ADR-41 Detection Logic).

    Returns a VerifyResult. Does not call sys.exit() — callers decide exit behavior.
    """
    advisory_log: list[str] = []
    drift_detected = False
    auto_reconciled = False
    dogfooding_exemption = False

    # ------------------------------------------------------------------
    # Step 1: Source family check
    # ------------------------------------------------------------------
    if source_family != "your-harness":
        return VerifyResult(
            decision=Decision.PASS,
            reason=f"source_family={source_family!r} is not your-harness; self-stop not applicable.",
            source_family=source_family,
            phase=phase,
            ledger_status="n/a",
            catalog_status="n/a",
            drift_detected=False,
            auto_reconciled=False,
            dogfooding_exemption=False,
            override_applied=False,
            advisory_log=[],
        )

    if strictness == "enforced" and self_stop_acknowledged is not True:
        return VerifyResult(
            decision=Decision.BLOCK,
            reason=(
                "self_stop_not_acknowledged: strictness=enforced requires "
                "self_stop_acknowledged=True"
            ),
            source_family=source_family,
            phase=phase,
            ledger_status="n/a",
            catalog_status="n/a",
            drift_detected=False,
            auto_reconciled=False,
            dogfooding_exemption=False,
            override_applied=False,
            advisory_log=[],
        )

    # ------------------------------------------------------------------
    # Step 2: Ledger status lookup
    # ------------------------------------------------------------------
    ledger_status = parse_mir_self_ledger(ledger_path, phase)
    if ledger_status == _UNKNOWN:
        advisory_log.append(
            f"WARNING: could not parse ledger status for {phase} from {ledger_path}"
        )

    # ------------------------------------------------------------------
    # Step 3: Catalog status lookup
    # ------------------------------------------------------------------
    catalog_status = read_json_adoption_status(catalog_path, "your-harness", phase)

    # ------------------------------------------------------------------
    # Step 4: Drift reconciliation
    # ------------------------------------------------------------------
    expected_json_status = _LEDGER_TO_JSON_STATUS.get(ledger_status, _UNKNOWN)
    if ledger_status != _UNKNOWN and catalog_status != _UNKNOWN:
        if catalog_status != expected_json_status:
            drift_detected = True
            advisory_log.append(
                f"SoT drift detected: ledger={ledger_status!r} "
                f"(expected json={expected_json_status!r}), "
                f"actual json={catalog_status!r}. "
                "Ledger takes precedence per mir-roles.md §6."
            )
            if auto_reconcile:
                write_json_adoption_status(
                    catalog_path, "your-harness", phase, expected_json_status
                )
                auto_reconciled = True
                advisory_log.append(
                    f"Auto-reconciled: catalog updated from {catalog_status!r} "
                    f"to {expected_json_status!r}."
                )

    # ------------------------------------------------------------------
    # Step 5 + 6: Decision based on ledger status + ADR-23 dogfooding check
    # ------------------------------------------------------------------

    # Historical design-land-only phases used a WARN-only exemption.
    # That set is now empty because the runtime surfaces landed in R11+.
    is_design_land = phase in _DESIGN_LAND_ONLY_PHASES

    if is_design_land and ledger_status in ("done", "partial"):
        # ADR-23 dogfooding exemption: design-land phases may share with WARN
        dogfooding_exemption = True
        decision = Decision.WARN
        reason = (
            f"{phase} is a design-land-only phase (ADR-23 dogfooding exception). "
            "Share allowed but flag as 'design-level only'. "
            "Runtime code will land in R11+."
        )
    elif ledger_status in _BLOCK_STATUSES:
        decision = Decision.BLOCK
        reason = (
            f"SE-meta self-stop: your-harness-self {phase} status={ledger_status!r}, "
            "cannot recommend to fleet until adopted. "
            "See mir-roles.md §6 + ADR-23 dogfooding exception."
        )
    elif ledger_status == "done":
        decision = Decision.PASS
        reason = f"your-harness-self {phase} is done; share is permitted."
    else:
        # unknown / unexpected
        decision = Decision.BLOCK
        reason = (
            f"SE-meta self-stop: your-harness-self {phase} status={ledger_status!r} "
            "(unknown or parse error); defaulting to BLOCK for safety."
        )

    # ------------------------------------------------------------------
    # Override logic (post-decision)
    # ------------------------------------------------------------------
    override_applied = False
    override_reason_stored = ""
    if override.applied and decision == Decision.BLOCK:
        # Unconditional stderr audit emit — fires regardless of stdout/file output mode.
        # Caller may redirect stdout (--format json --report ...) but stderr is always fd 2.
        sys.stderr.write(
            f"[verify_self_stop OVERRIDE] source={source_family} phase={phase} "
            f"original_decision=BLOCK override_reason={override.reason!r} "
            f"timestamp={datetime.datetime.now(datetime.UTC).isoformat()}\n"
        )
        sys.stderr.flush()
        override_applied = True
        override_reason_stored = override.reason
        advisory_log.append(
            f"OVERRIDE applied by user: decision upgraded from BLOCK to PASS. "
            f"Reason: {override.reason!r}. "
            "This override is subject to audit trail requirements (ADR-41)."
        )
        decision = Decision.PASS
        reason = f"Override applied (was: BLOCK). Reason: {override.reason!r}."

    result = VerifyResult(
        decision=decision,
        reason=reason,
        source_family=source_family,
        phase=phase,
        ledger_status=ledger_status,
        catalog_status=catalog_status,
        drift_detected=drift_detected,
        auto_reconciled=auto_reconciled,
        dogfooding_exemption=dogfooding_exemption,
        override_applied=override_applied,
        advisory_log=advisory_log,
    )
    result._override_reason = override_reason_stored
    return result


# ---------------------------------------------------------------------------
# Output formatters
# ---------------------------------------------------------------------------

_PASS_MARK = "[PASS]"
_WARN_MARK = "[WARN]"
_BLOCK_MARK = "[BLOCK]"
_CHECK_MARK = "  v"
_CROSS_MARK = "  x"


def _fmt_console(result: VerifyResult, *, source_family: str, phase: str,
                 ledger_path: Path, catalog_path: Path) -> str:
    lines = [
        "=== your-harness Self-Stop Verification ===",
        f"source_family: {source_family}",
        f"phase: {phase}",
        f"ledger_path: {ledger_path}",
        f"catalog_path: {catalog_path}",
        "",
        "Step 1/6 — Source Family Check",
    ]

    if source_family == "your-harness":
        lines.append("  v your-harness — self-stop applicable")
    else:
        lines.append(f"  v {source_family!r} — self-stop NOT applicable (PASS early)")
        lines += ["", "=== Summary ===", "  Decision: PASS", ""]
        return "\n".join(lines)

    lines += [
        "",
        "Step 2/6 — Ledger Status Lookup",
    ]
    ledger_mark = _CHECK_MARK if result.ledger_status == "done" else _CROSS_MARK
    lines.append(f"{ledger_mark} {phase}: status={result.ledger_status}")

    lines += [
        "",
        "Step 3/6 — Catalog Status Lookup",
    ]
    expected = _LEDGER_TO_JSON_STATUS.get(result.ledger_status, _UNKNOWN)
    catalog_mark = _CHECK_MARK if result.catalog_status == expected else _CROSS_MARK
    lines.append(
        f"{catalog_mark} {phase}: catalog status={result.catalog_status} "
        f"({'consistent' if not result.drift_detected else 'DRIFT vs'} "
        f"ledger={result.ledger_status})"
    )

    lines += [
        "",
        "Step 4/6 — Drift Reconciliation",
    ]
    if result.drift_detected:
        lines.append(
            f"  x drift detected (ledger={result.ledger_status!r}, "
            f"catalog={result.catalog_status!r})"
        )
        if result.auto_reconciled:
            lines.append(f"  v auto-reconciled catalog to {expected!r}")
    else:
        lines.append("  v no drift (skipped)")

    lines += [
        "",
        "Step 5/6 — ADR-23 Dogfooding Check",
    ]
    if result.dogfooding_exemption:
        lines.append(f"  v {phase} is design-land-only (ADR-23 exemption applies)")
    else:
        lines.append(f"  v {phase} not in design-land-only set")

    lines += [
        "",
        "Step 6/6 — Final Decision",
    ]
    dec_mark = _CHECK_MARK if result.decision == Decision.PASS else _CROSS_MARK
    lines.append(f"{dec_mark} {result.decision.value} — {result.reason}")
    if result.override_applied:
        lines.append("    See mir-roles.md §6 + ADR-23 dogfooding exception.")

    lines += [
        "",
        "=== Summary ===",
        f"  Decision: {result.decision.value}",
        f"  Override: {'applied' if result.override_applied else 'not applied'}",
        f"  Audit log: {result.advisory_log[0][:80] if result.advisory_log else '<none>'}",
        "",
    ]
    return "\n".join(lines)


def _fmt_json(result: VerifyResult) -> str:
    return json.dumps(result.to_dict(), indent=2)


def _fmt_markdown(result: VerifyResult) -> str:
    d = result.to_dict()
    lines = [
        "# your-harness Self-Stop Verification Report",
        "",
        "| Field | Value |",
        "|---|---|",
    ]
    for k, v in d.items():
        if isinstance(v, list):
            v = "; ".join(v) if v else "(none)"
        elif isinstance(v, dict):
            v = json.dumps(v)
        lines.append(f"| {k} | {v} |")
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="verify_self_stop",
        description="ADR-41 SE-meta self-stop runtime gate.",
    )
    p.add_argument("--source-family", required=True,
                   help='Share source family (e.g. "your-harness").')
    p.add_argument("--phase", required=True,
                   help='Phase reference (e.g. "phase-4").')
    p.add_argument(
        "--ledger",
        default="docs/harness-engineering/applications/mir-self/README.md",
        help="Path to mir-self rollout ledger (default: docs/harness-engineering/applications/mir-self/README.md).",  # noqa: E501
    )
    p.add_argument(
        "--catalog",
        default="config/fleet-harness-state.json",
        help="Path to fleet-harness-state.json (default: config/fleet-harness-state.json).",
    )
    p.add_argument(
        "--override",
        action="store_true",
        default=False,
        help="Skip BLOCK decision (requires --override-reason).",
    )
    p.add_argument(
        "--override-reason",
        default="",
        help="Required with --override. Reason text for audit log.",
    )
    p.add_argument(
        "--strict",
        action="store_true",
        default=False,
        help="Treat WARN as exit 1.",
    )
    p.add_argument(
        "--format",
        choices=["console", "json", "markdown"],
        default="console",
        dest="output_format",
        help="Output format (default: console).",
    )
    p.add_argument(
        "--report",
        default=None,
        help="Write output to file path (else stdout).",
    )
    p.add_argument(
        "--auto-reconcile",
        action="store_true",
        default=False,
        help="Auto-update catalog on drift (default: False).",
    )

    args = p.parse_args(argv)

    # Validate: --override requires --override-reason
    if args.override and not args.override_reason:
        p.error("--override requires --override-reason <text>")

    return args


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)

    ledger_path = Path(args.ledger)
    catalog_path = Path(args.catalog)

    # File existence check (graceful error = exit 2)
    if args.source_family == "your-harness":
        if not ledger_path.exists():
            sys.stderr.write(
                f"ERROR: ledger file not found: {ledger_path}\n"
            )
            return 2
        if not catalog_path.exists():
            sys.stderr.write(
                f"ERROR: catalog file not found: {catalog_path}\n"
            )
            return 2

    override = OverrideConfig(
        applied=args.override,
        reason=args.override_reason,
    )

    try:
        result = verify_self_stop(
            source_family=args.source_family,
            phase=args.phase,
            ledger_path=ledger_path,
            catalog_path=catalog_path,
            override=override,
            auto_reconcile=args.auto_reconcile,
            strict=args.strict,
        )
    except Exception as exc:  # noqa: BLE001
        sys.stderr.write(f"ERROR: unexpected failure: {exc}\n")
        return 2

    # Format output
    if args.output_format == "json":
        output = _fmt_json(result)
    elif args.output_format == "markdown":
        output = _fmt_markdown(result)
    else:
        output = _fmt_console(
            result,
            source_family=args.source_family,
            phase=args.phase,
            ledger_path=ledger_path,
            catalog_path=catalog_path,
        )

    # Write output
    if args.report:
        Path(args.report).write_text(output, encoding="utf-8")
    else:
        sys.stdout.write(output)
        if not output.endswith("\n"):
            sys.stdout.write("\n")

    # Determine exit code
    if result.decision == Decision.BLOCK:
        return 1
    if result.decision == Decision.WARN and args.strict:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
