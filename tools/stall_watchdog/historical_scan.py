"""ADR-06 Phase 6F: historical stall pattern scan over the JSONL pool.

Scans every workspace-encoded directory under the pool for sessions whose last
activity falls within the lookback window AND whose tail matches the stall
signature (assistant tool_use or user tool_result followed only by skipable
entries, with idle > threshold). Reports counts per family — used by the
project-doctor skill.

Read-only. Does not push to Discord (this is an offline audit helper).
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

from tools.stall_watchdog.family_paths import WORKSPACE_DIR_TO_FAMILY
from tools.stall_watchdog.scan import ScanConfig, scan_pool


def historical_scan(
    pool_root: Path,
    *,
    lookback_days: int = 14,
    threshold_seconds: int = 180,
    workspace_to_family: dict[str, str] | None = None,
    now: datetime | None = None,
) -> dict:
    """Run a single offline scan.

    Returns a JSON-serializable dict with per-family stall counts and the raw
    verdict list.
    """
    if workspace_to_family is None:
        workspace_to_family = WORKSPACE_DIR_TO_FAMILY
    if now is None:
        now = datetime.now(tz=UTC)

    config = ScanConfig(
        pool_root=pool_root,
        threshold_seconds=threshold_seconds,
        recent_k_minutes=lookback_days * 24 * 60,
    )
    verdicts = scan_pool(config, now, workspace_to_family)

    stall_counts: Counter[str] = Counter()
    for v in verdicts:
        if v.is_stall:
            stall_counts[v.family_slug] += 1

    return {
        "incident_code": "MIR-STALL-001",
        "pattern_code": "STALL-IDLE-AFTER-TOOLUSE",
        "lookback_days": lookback_days,
        "threshold_seconds": threshold_seconds,
        "now": now.isoformat(),
        "pool_root": str(pool_root),
        "stall_counts": dict(stall_counts),
        "total_stall": sum(stall_counts.values()),
        "total_sessions_scanned": len(verdicts),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="mir-stall-historical-scan")
    parser.add_argument(
        "--pool-root",
        type=Path,
        default=Path("<your-home>/.claude/projects"),
    )
    parser.add_argument("--lookback-days", type=int, default=14)
    parser.add_argument("--threshold-seconds", type=int, default=180)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    report = historical_scan(
        args.pool_root,
        lookback_days=args.lookback_days,
        threshold_seconds=args.threshold_seconds,
    )

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(
            f"scanned {report['total_sessions_scanned']} sessions "
            f"(lookback {report['lookback_days']}d, threshold {report['threshold_seconds']}s)"
        )
        print(f"total stalls: {report['total_stall']}")
        for family, count in sorted(report["stall_counts"].items()):
            print(f"  {family}: {count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
