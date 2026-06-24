"""ADR-06 Phase 6C-5: CLI entry point for the stall watchdog daemon.

Three sub-commands:
  - ``scan``   : one-shot scan + Discord push (or dry-run).
  - ``daemon`` : 60s-tick loop with SIGTERM/SIGINT graceful shutdown.
  - ``doctor`` : environment diagnosis (pool root + webhooks + family map).
  - ``agent-check`` : aggregated agent-execution health surface (L3). Observe-only.

Configuration is environment-only (no config file):
  - ``MIR_STALL_WATCHDOG_THRESHOLD_SECONDS`` (default 180)
  - ``MIR_STALL_WATCHDOG_RECENT_K_MINUTES`` (default 60)
  - ``MIR_STALL_WATCHDOG_POLL_SECONDS``     (default 60, daemon tick)
  - ``MIR_STALL_WATCHDOG_POOL_ROOT``        (default ``<your-home>/.claude/projects``)
  - ``MIR_STALL_WATCHDOG_WEBHOOK_<SLUG_UPPER>`` (per-family secret)
  - ``MIR_STALL_WATCHDOG_WEBHOOK_DEFAULT``  (fallback)

Webhooks are never written to disk by this CLI. Missing webhook = dry-run skip.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import re
import signal
import sys
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from tools.stall_watchdog.dedup import DedupLedger
from tools.stall_watchdog.discord_push import (
    StallAlarm,
    VerdictAlarm,
    push_to_discord,
)
from tools.stall_watchdog.family_paths import (
    FAMILY_SLUG_TO_DISPLAY,
    WORKSPACE_DIR_TO_FAMILY,
    family_display_name,
    family_slug_to_env_key,
)
from tools.stall_watchdog.scan import (
    ScanConfig,
    StallVerdict,
    check_evidence_integrity,
    scan_codex_events,
    scan_job_registry,
    scan_pool,
    scan_subagent_pool,
)

_LOG = logging.getLogger("stall_watchdog")

_DEFAULT_POOL_ROOT = Path("<your-home>/.claude/projects")
_DEFAULT_THRESHOLD = 180
_DEFAULT_RECENT_K_MIN = 60
_DEFAULT_POLL = 60
_DEEP_HEALTH_FAMILY = "your-harness"


@dataclass(frozen=True)
class AgentCheckPaths:
    events_path: Path
    db_path: Path
    repo_root: Path
    change_id: str


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        _LOG.warning("env %s=%r is not int — using default %d", name, raw, default)
        return default


def _build_scan_config() -> ScanConfig:
    pool_root = Path(
        os.environ.get("MIR_STALL_WATCHDOG_POOL_ROOT", str(_DEFAULT_POOL_ROOT))
    )
    return ScanConfig(
        pool_root=pool_root,
        threshold_seconds=_env_int(
            "MIR_STALL_WATCHDOG_THRESHOLD_SECONDS", _DEFAULT_THRESHOLD
        ),
        recent_k_minutes=_env_int(
            "MIR_STALL_WATCHDOG_RECENT_K_MINUTES", _DEFAULT_RECENT_K_MIN
        ),
    )


def _build_agent_check_paths() -> AgentCheckPaths:
    return AgentCheckPaths(
        events_path=Path(
            os.environ.get(
                "MIR_AGENT_CHECK_EVENTS_PATH", "tasks/codex-exec-events.jsonl"
            )
        ),
        db_path=Path(os.environ.get("MIR_AGENT_CHECK_DB_PATH", "tasks/jobs.db")),
        repo_root=Path(os.environ.get("MIR_AGENT_CHECK_REPO_ROOT", ".")),
        change_id=os.environ.get("MIR_AGENT_CHECK_CHANGE_ID", ""),
    )


def _resolve_webhook(family_slug: str) -> str:
    key = family_slug_to_env_key(family_slug)
    return (
        os.environ.get(f"MIR_STALL_WATCHDOG_WEBHOOK_{key}")
        or os.environ.get("MIR_STALL_WATCHDOG_WEBHOOK_DEFAULT")
        or ""
    )


def _verdict_to_alarm(v: StallVerdict) -> StallAlarm:
    nested = ""
    if v.last_entry is not None and v.last_entry.nested_content_types:
        nested = v.last_entry.nested_content_types[-1]
    return StallAlarm(
        family=v.family_slug,
        family_display=family_display_name(v.family_slug),
        workspace_encoded=v.workspace_encoded,
        session_uuid=v.session_uuid,
        idle_seconds=v.idle_seconds,
        last_entry_top_type=v.last_entry.top_type if v.last_entry else "_unknown",
        last_entry_nested_type=nested,
        last_entry_ts=v.last_entry.ts if v.last_entry else None,
        jsonl_path=v.jsonl_path,
    )


def _verdict_to_dict(v: StallVerdict) -> dict:
    return {
        "is_stall": v.is_stall,
        "family_slug": v.family_slug,
        "workspace_encoded": v.workspace_encoded,
        "session_uuid": v.session_uuid,
        "idle_seconds": v.idle_seconds,
        "skip_reason": v.skip_reason,
        "jsonl_path": str(v.jsonl_path),
    }


def _stable_digest(*parts: str) -> str:
    raw = "\n".join(parts)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def _dedup_detail(detail: str) -> str:
    detail = re.sub(r"\belapsed=\d+(?:\.\d+)?s\b", "elapsed=<seconds>", detail)
    return re.sub(r"\bduration_s=\d+(?:\.\d+)?s\b", "duration_s=<seconds>", detail)


def _health_verdict_to_alarm(
    *,
    source: str,
    kind: str,
    recommendation: str,
    detail: str,
    reference: Path | str,
    now: datetime,
) -> tuple[str, str, str, VerdictAlarm]:
    detail_key = _dedup_detail(detail)
    family = _DEEP_HEALTH_FAMILY
    workspace = source
    session_uuid = f"{kind}:{_stable_digest(source, kind, detail_key)}"
    return (
        family,
        workspace,
        session_uuid,
        VerdictAlarm(
            family=family,
            family_display=family_display_name(family),
            source=source,
            kind=kind,
            recommendation=recommendation,
            detail=detail,
            observed_at=now,
            reference=str(reference),
        ),
    )


def _collect_deep_health_alarms(
    config: ScanConfig,
    now: datetime,
) -> list[tuple[str, str, str, StallAlarm | VerdictAlarm]]:
    paths = _build_agent_check_paths()
    alarms: list[tuple[str, str, str, StallAlarm | VerdictAlarm]] = []

    for verdict in scan_codex_events(paths.events_path):
        alarms.append(
            _health_verdict_to_alarm(
                source=verdict.source,
                kind=verdict.verdict,
                recommendation=verdict.recommendation,
                detail=verdict.detail,
                reference=paths.events_path,
                now=now,
            )
        )

    for verdict in scan_job_registry(paths.db_path, now):
        alarms.append(
            _health_verdict_to_alarm(
                source=verdict.source,
                kind=verdict.verdict,
                recommendation=verdict.recommendation,
                detail=verdict.detail,
                reference=paths.db_path,
                now=now,
            )
        )

    if paths.change_id:
        for verdict in check_evidence_integrity(
            paths.repo_root, paths.change_id, "HEAD"
        ):
            alarms.append(
                _health_verdict_to_alarm(
                    source="integrity",
                    kind=verdict.kind,
                    recommendation=verdict.recommendation,
                    detail=verdict.detail,
                    reference=paths.repo_root,
                    now=now,
                )
            )

    for verdict in scan_subagent_pool(config, now, WORKSPACE_DIR_TO_FAMILY):
        if not verdict.is_stall:
            continue
        alarms.append(
            (
                verdict.family_slug,
                verdict.workspace_encoded,
                verdict.session_uuid,
                _verdict_to_alarm(verdict),
            )
        )

    return alarms


def _push_alarm_once(
    ledger: DedupLedger,
    *,
    family_slug: str,
    workspace_encoded: str,
    session_uuid: str,
    alarm: StallAlarm | VerdictAlarm,
    now: datetime,
) -> bool:
    if ledger.already_alarmed(family_slug, workspace_encoded, session_uuid, now):
        return False
    webhook = _resolve_webhook(family_slug)
    if not webhook:
        _LOG.info(
            "daemon: verdict detected (dry-run, no webhook) family=%s session=%s",
            family_slug,
            session_uuid,
        )
        return False
    ok = push_to_discord(webhook, alarm)
    if ok:
        ledger.mark_alarmed(family_slug, workspace_encoded, session_uuid, now)
    return ok


def cmd_scan(args: argparse.Namespace) -> int:
    config = _build_scan_config()
    now = datetime.now(tz=UTC)
    verdicts = scan_pool(config, now, WORKSPACE_DIR_TO_FAMILY)
    ledger = DedupLedger()
    pushed: list[dict] = []
    for v in verdicts:
        if not v.is_stall:
            continue
        if ledger.already_alarmed(
            v.family_slug, v.workspace_encoded, v.session_uuid, now
        ):
            continue
        webhook = _resolve_webhook(v.family_slug)
        if args.dry_run or not webhook:
            pushed.append({**_verdict_to_dict(v), "pushed": False, "dry_run": True})
            continue
        alarm = _verdict_to_alarm(v)
        ok = push_to_discord(webhook, alarm)
        if ok:
            ledger.mark_alarmed(
                v.family_slug, v.workspace_encoded, v.session_uuid, now
            )
        pushed.append({**_verdict_to_dict(v), "pushed": ok, "dry_run": False})

    if args.json:
        print(
            json.dumps(
                {
                    "verdicts": [_verdict_to_dict(v) for v in verdicts],
                    "pushed": pushed,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    else:
        stalls = [v for v in verdicts if v.is_stall]
        print(f"scanned {len(verdicts)} sessions, {len(stalls)} stall(s)")
        for v in stalls:
            print(
                f"  STALL {v.family_slug} {v.workspace_encoded} {v.session_uuid} "
                f"idle={v.idle_seconds}s"
            )
    return 0


class _DaemonStop:
    def __init__(self):
        self.requested = False

    def request(self, *args):
        self.requested = True


def cmd_daemon(args: argparse.Namespace) -> int:
    poll = _env_int("MIR_STALL_WATCHDOG_POLL_SECONDS", _DEFAULT_POLL)
    if args.max_ticks is not None:
        max_ticks = args.max_ticks
    else:
        max_ticks = None

    stop = _DaemonStop()
    try:
        signal.signal(signal.SIGTERM, stop.request)
        signal.signal(signal.SIGINT, stop.request)
    except ValueError:
        # signal handlers can fail in non-main threads; tolerate for tests.
        pass

    ledger = DedupLedger()
    tick = 0
    config = _build_scan_config()
    while not stop.requested:
        now = datetime.now(tz=UTC)
        verdicts = scan_pool(config, now, WORKSPACE_DIR_TO_FAMILY)
        for v in verdicts:
            if not v.is_stall:
                continue
            _push_alarm_once(
                ledger,
                family_slug=v.family_slug,
                workspace_encoded=v.workspace_encoded,
                session_uuid=v.session_uuid,
                alarm=_verdict_to_alarm(v),
                now=now,
            )
        for family_slug, workspace_encoded, session_uuid, alarm in (
            _collect_deep_health_alarms(config, now)
        ):
            _push_alarm_once(
                ledger,
                family_slug=family_slug,
                workspace_encoded=workspace_encoded,
                session_uuid=session_uuid,
                alarm=alarm,
                now=now,
            )
        ledger.gc(now)
        tick += 1
        if max_ticks is not None and tick >= max_ticks:
            break
        if stop.requested:
            break
        time.sleep(poll if args.poll is None else args.poll)
    return 0


def cmd_doctor(args: argparse.Namespace) -> int:
    config = _build_scan_config()
    report = {
        "pool_root": str(config.pool_root),
        "pool_root_exists": config.pool_root.exists(),
        "threshold_seconds": config.threshold_seconds,
        "recent_k_minutes": config.recent_k_minutes,
        "family_count_in_map": len(FAMILY_SLUG_TO_DISPLAY),
        "workspace_dir_count": len(WORKSPACE_DIR_TO_FAMILY),
        "webhooks": {},
        "python_version": sys.version.split()[0],
    }
    for slug in sorted(FAMILY_SLUG_TO_DISPLAY):
        key = family_slug_to_env_key(slug)
        configured = bool(os.environ.get(f"MIR_STALL_WATCHDOG_WEBHOOK_{key}"))
        report["webhooks"][slug] = {"env_key": key, "configured": configured}
    report["webhooks"]["__default__"] = {
        "env_key": "MIR_STALL_WATCHDOG_WEBHOOK_DEFAULT",
        "configured": bool(os.environ.get("MIR_STALL_WATCHDOG_WEBHOOK_DEFAULT")),
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


def cmd_agent_check(args: argparse.Namespace) -> int:
    config = _build_scan_config()
    now = datetime.now(tz=UTC)
    paths = _build_agent_check_paths()

    event_verdicts = scan_codex_events(paths.events_path)
    job_verdicts = scan_job_registry(paths.db_path, now)
    integrity_verdicts = []
    if paths.change_id:
        integrity_verdicts = check_evidence_integrity(
            paths.repo_root, paths.change_id, "HEAD"
        )
    subagent_verdicts = scan_subagent_pool(config, now, WORKSPACE_DIR_TO_FAMILY)
    main_verdicts = scan_pool(config, now, WORKSPACE_DIR_TO_FAMILY)

    rows = []
    for verdict in [*event_verdicts, *job_verdicts]:
        rows.append(
            (
                verdict.source,
                verdict.verdict,
                verdict.recommendation,
                verdict.detail[:80],
            )
        )
    for verdict in integrity_verdicts:
        rows.append(
            (
                "integrity",
                verdict.kind,
                verdict.recommendation,
                verdict.detail[:80],
            )
        )
    for verdict in subagent_verdicts:
        if verdict.is_stall:
            rows.append(
                (
                    "subagent_pool",
                    "STALL",
                    "ESCALATE_HUMAN",
                    f"family={verdict.family_slug} session={verdict.session_uuid} "
                    f"idle={verdict.idle_seconds}s",
                )
            )
    main_pool_stalls = [verdict for verdict in main_verdicts if verdict.is_stall]
    for verdict in main_pool_stalls:
        rows.append(
            (
                "main_pool",
                "STALL",
                "ESCALATE_HUMAN",
                f"family={verdict.family_slug} session={verdict.session_uuid} "
                f"idle={verdict.idle_seconds}s",
            )
        )

    print("=== Agent Execution Health Check ===")
    print("SOURCE\tKIND\tRECOMMENDATION\tDETAIL")
    for row in rows:
        print("\t".join(row))
    if rows:
        print(f"=== {len(rows)} issue(s) found ===")
    else:
        print("=== No issues found ===")

    if args.push:
        ledger = DedupLedger()
        for stall in main_pool_stalls:
            if ledger.already_alarmed(
                stall.family_slug, stall.workspace_encoded, stall.session_uuid, now
            ):
                continue
            webhook = _resolve_webhook(stall.family_slug)
            if not webhook:
                continue
            alarm = _verdict_to_alarm(stall)
            ok = push_to_discord(webhook, alarm)
            if ok:
                ledger.mark_alarmed(
                    stall.family_slug, stall.workspace_encoded, stall.session_uuid, now
                )
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="mir-stall-watchdog")
    sub = parser.add_subparsers(dest="cmd", required=True)

    scan = sub.add_parser("scan", help="one-shot scan + Discord push")
    scan.add_argument("--dry-run", action="store_true", help="never POST to Discord")
    scan.add_argument("--json", action="store_true", help="emit JSON report")
    scan.set_defaults(func=cmd_scan)

    daemon = sub.add_parser("daemon", help="continuous polling loop")
    daemon.add_argument(
        "--max-ticks", type=int, default=None, help="exit after N ticks (test mode)"
    )
    daemon.add_argument(
        "--poll", type=int, default=None, help="override poll seconds"
    )
    daemon.set_defaults(func=cmd_daemon)

    doctor = sub.add_parser("doctor", help="environment diagnosis")
    doctor.set_defaults(func=cmd_doctor)

    agent_check = sub.add_parser(
        "agent-check", help="aggregated agent-execution health surface (L3)"
    )
    agent_check.add_argument(
        "--push",
        action="store_true",
        help="push main-pool stalls to Discord (dedup-guarded)",
    )
    agent_check.set_defaults(func=cmd_agent_check)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    logging.basicConfig(
        level=os.environ.get("MIR_STALL_WATCHDOG_LOG_LEVEL", "INFO"),
        format="%(levelname)s %(name)s: %(message)s",
        stream=sys.stderr,
    )
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
