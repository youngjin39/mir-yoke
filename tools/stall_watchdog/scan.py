"""ADR-06 Phase 6C-4: stall scan over the workspace-encoded JSONL pool.

Glues jsonl_tail + family_paths into a verdict list per scan tick. Read-only.
"""

from __future__ import annotations

# isort: off
import json
import os
import logging
import subprocess
# isort: on
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from tools.autonomous_loop.loop import trigger_spinning
from tools.mir_executor.jobs import JobRegistry
from tools.stall_watchdog.jsonl_tail import (
    JsonlEntry,
    find_last_significant,
    has_following_skipable_only,
    tail_line_jsonl,
)

_LOG = logging.getLogger(__name__)


@dataclass(frozen=True)
class ScanConfig:
    pool_root: Path
    threshold_seconds: int = 180
    recent_k_minutes: int = 60
    tail_n: int = 20


@dataclass(frozen=True)
class StallVerdict:
    is_stall: bool
    family_slug: str
    workspace_encoded: str
    session_uuid: str
    jsonl_path: Path
    idle_seconds: int
    last_entry: JsonlEntry | None
    skip_reason: str | None


def _file_mtime(p: Path) -> datetime:
    return datetime.fromtimestamp(p.stat().st_mtime, tz=UTC)


def _aware(ts: datetime) -> datetime:
    if ts.tzinfo is None:
        return ts.replace(tzinfo=UTC)
    return ts


def scan_pool(
    config: ScanConfig,
    now: datetime,
    workspace_to_family: dict[str, str],
) -> list[StallVerdict]:
    """Scan the JSONL pool for stall signatures.

    ``now`` should be timezone-aware (UTC recommended). ``workspace_to_family``
    maps the encoded directory name to the ASCII family slug
    (``WORKSPACE_DIR_TO_FAMILY``).
    """
    now = _aware(now)
    verdicts: list[StallVerdict] = []

    if not config.pool_root.exists() or not config.pool_root.is_dir():
        _LOG.warning("scan_pool: pool root missing or not a dir: %s", config.pool_root)
        return verdicts

    recent_cutoff = now.timestamp() - (config.recent_k_minutes * 60)

    for workspace_dir in sorted(config.pool_root.iterdir()):
        if not workspace_dir.is_dir():
            continue
        workspace_encoded = workspace_dir.name
        family_slug = workspace_to_family.get(workspace_encoded)
        if family_slug is None:
            _LOG.debug(
                "scan_pool: unmapped workspace skip: %s", workspace_encoded
            )
            continue

        for jsonl in sorted(workspace_dir.glob("*.jsonl")):
            try:
                stat = jsonl.stat()
            except (FileNotFoundError, PermissionError) as exc:
                _LOG.warning("scan_pool: stat failed %s: %s", jsonl, exc)
                continue

            if stat.st_mtime < recent_cutoff:
                continue

            session_uuid = jsonl.stem
            entries = tail_line_jsonl(jsonl, n=config.tail_n)
            if not entries:
                verdicts.append(
                    StallVerdict(
                        is_stall=False,
                        family_slug=family_slug,
                        workspace_encoded=workspace_encoded,
                        session_uuid=session_uuid,
                        jsonl_path=jsonl,
                        idle_seconds=0,
                        last_entry=None,
                        skip_reason="no_entries",
                    )
                )
                continue

            last_sig = find_last_significant(entries)
            if last_sig is None:
                verdicts.append(
                    StallVerdict(
                        is_stall=False,
                        family_slug=family_slug,
                        workspace_encoded=workspace_encoded,
                        session_uuid=session_uuid,
                        jsonl_path=jsonl,
                        idle_seconds=0,
                        last_entry=None,
                        skip_reason="no_significant_entry",
                    )
                )
                continue

            if not has_following_skipable_only(entries, last_sig):
                verdicts.append(
                    StallVerdict(
                        is_stall=False,
                        family_slug=family_slug,
                        workspace_encoded=workspace_encoded,
                        session_uuid=session_uuid,
                        jsonl_path=jsonl,
                        idle_seconds=0,
                        last_entry=last_sig,
                        skip_reason="session_continued",
                    )
                )
                continue

            if last_sig.ts is None:
                pivot_ts = _aware(_file_mtime(jsonl))
            else:
                pivot_ts = _aware(last_sig.ts)

            idle_seconds = int((now - pivot_ts).total_seconds())
            if idle_seconds < config.threshold_seconds:
                verdicts.append(
                    StallVerdict(
                        is_stall=False,
                        family_slug=family_slug,
                        workspace_encoded=workspace_encoded,
                        session_uuid=session_uuid,
                        jsonl_path=jsonl,
                        idle_seconds=idle_seconds,
                        last_entry=last_sig,
                        skip_reason="below_threshold",
                    )
                )
                continue

            verdicts.append(
                StallVerdict(
                    is_stall=True,
                    family_slug=family_slug,
                    workspace_encoded=workspace_encoded,
                    session_uuid=session_uuid,
                    jsonl_path=jsonl,
                    idle_seconds=idle_seconds,
                    last_entry=last_sig,
                    skip_reason=None,
                )
            )

    return verdicts


def scan_subagent_pool(
    config: ScanConfig,
    now: datetime,
    workspace_to_family: dict[str, str],
    *,
    tmp_root: Path | None = None,
) -> list[StallVerdict]:
    '''Scan sub-agent transcript files in /private/tmp/claude-<uid>/<workspace>/<session>/tasks/*.output.

    Sub-agent (Agent/Task-tool) transcripts are JSONL files at
    tmp_root/<workspace-encoded>/<session-uuid>/tasks/<agent-id>.output.
    Tolerant of absence (tmp_root may not exist). Read-only.
    '''
    if tmp_root is None:
        tmp_root = Path(f'/private/tmp/claude-{os.getuid()}')
    now = _aware(now)
    verdicts: list[StallVerdict] = []

    if not tmp_root.exists() or not tmp_root.is_dir():
        _LOG.debug('scan_subagent_pool: tmp_root missing, skip: %s', tmp_root)
        return verdicts

    recent_cutoff = now.timestamp() - (config.recent_k_minutes * 60)

    for workspace_dir in sorted(tmp_root.iterdir()):
        if not workspace_dir.is_dir():
            continue
        workspace_encoded = workspace_dir.name
        family_slug = workspace_to_family.get(workspace_encoded)
        if family_slug is None:
            _LOG.debug('scan_subagent_pool: unmapped workspace skip: %s', workspace_encoded)
            continue

        for session_dir in sorted(workspace_dir.iterdir()):
            if not session_dir.is_dir():
                continue
            session_uuid = session_dir.name
            tasks_dir = session_dir / 'tasks'
            if not tasks_dir.is_dir():
                continue

            for output_file in sorted(tasks_dir.glob('*.output')):
                try:
                    stat = output_file.stat()
                except (FileNotFoundError, PermissionError) as exc:
                    _LOG.warning('scan_subagent_pool: stat failed %s: %s', output_file, exc)
                    continue

                if stat.st_mtime < recent_cutoff:
                    continue

                agent_id = output_file.stem
                entries = tail_line_jsonl(output_file, n=config.tail_n)
                if not entries:
                    verdicts.append(
                        StallVerdict(
                            is_stall=False,
                            family_slug=family_slug,
                            workspace_encoded=workspace_encoded,
                            session_uuid=f'{session_uuid}/{agent_id}',
                            jsonl_path=output_file,
                            idle_seconds=0,
                            last_entry=None,
                            skip_reason='no_entries',
                        )
                    )
                    continue

                last_sig = find_last_significant(entries)
                if last_sig is None:
                    verdicts.append(
                        StallVerdict(
                            is_stall=False,
                            family_slug=family_slug,
                            workspace_encoded=workspace_encoded,
                            session_uuid=f'{session_uuid}/{agent_id}',
                            jsonl_path=output_file,
                            idle_seconds=0,
                            last_entry=None,
                            skip_reason='no_significant_entry',
                        )
                    )
                    continue

                if not has_following_skipable_only(entries, last_sig):
                    verdicts.append(
                        StallVerdict(
                            is_stall=False,
                            family_slug=family_slug,
                            workspace_encoded=workspace_encoded,
                            session_uuid=f'{session_uuid}/{agent_id}',
                            jsonl_path=output_file,
                            idle_seconds=0,
                            last_entry=last_sig,
                            skip_reason='session_continued',
                        )
                    )
                    continue

                if last_sig.ts is None:
                    pivot_ts = _aware(_file_mtime(output_file))
                else:
                    pivot_ts = _aware(last_sig.ts)

                idle_seconds = int((now - pivot_ts).total_seconds())
                if idle_seconds < config.threshold_seconds:
                    verdicts.append(
                        StallVerdict(
                            is_stall=False,
                            family_slug=family_slug,
                            workspace_encoded=workspace_encoded,
                            session_uuid=f'{session_uuid}/{agent_id}',
                            jsonl_path=output_file,
                            idle_seconds=idle_seconds,
                            last_entry=last_sig,
                            skip_reason='below_threshold',
                        )
                    )
                    continue

                verdicts.append(
                    StallVerdict(
                        is_stall=True,
                        family_slug=family_slug,
                        workspace_encoded=workspace_encoded,
                        session_uuid=f'{session_uuid}/{agent_id}',
                        jsonl_path=output_file,
                        idle_seconds=idle_seconds,
                        last_entry=last_sig,
                        skip_reason=None,
                    )
                )

    return verdicts


@dataclass(frozen=True)
class CodexEvent:
    """One row from tasks/codex-exec-events.jsonl (L1 shim output)."""

    ts: str | None
    pid: int | None
    caller: str | None
    exit_code: int | None
    signal: str | None
    duration_s: float | None
    error_sig: str | None


HANG_EXIT_CODE = 142
HANG_EXIT_CODES = (HANG_EXIT_CODE, 124)
HANG_SIGNAL = "SIG14"
DURATION_ANOMALY_MULTIPLIER = 3.0
DURATION_ANOMALY_MIN_BASELINE_S = 30.0


@dataclass(frozen=True)
class ExecutionHealthVerdict:
    """Advisory verdict over L1 codex-exec events or JobRegistry."""

    verdict: str
    recommendation: str
    source: str
    detail: str


@dataclass(frozen=True)
class IntegrityVerdict:
    kind: str
    detail: str
    recommendation: str = "ESCALATE_HUMAN"


def _parse_codex_events(events_path: Path) -> list[CodexEvent]:
    """Parse tasks/codex-exec-events.jsonl into CodexEvent list.

    Returns [] if absent, empty, or unreadable.
    """
    if not events_path.exists():
        return []
    events: list[CodexEvent] = []
    try:
        text = events_path.read_text(encoding="utf-8")
    except OSError:
        return []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        events.append(
            CodexEvent(
                ts=row.get("ts"),
                pid=row.get("pid"),
                caller=row.get("caller"),
                exit_code=row.get("exit_code"),
                signal=row.get("signal"),
                duration_s=row.get("duration_s"),
                error_sig=row.get("error_sig") or None,
            )
        )
    return events


def scan_codex_events(
    events_path: Path,
    *,
    duration_baseline_s: float = DURATION_ANOMALY_MIN_BASELINE_S,
    duration_multiplier: float = DURATION_ANOMALY_MULTIPLIER,
) -> list[ExecutionHealthVerdict]:
    """Scan L1 codex-exec event log. Read-only; verdicts advisory only.

    Detects:
    - HANG: any event with exit_code in (142, 124) OR signal==SIG14.
    - SPINNING: same non-empty error_sig appears >=3 consecutive times.
    - DURATION_ANOMALY: duration_s > baseline * multiplier when baseline > threshold.
    """
    events = _parse_codex_events(events_path)
    verdicts: list[ExecutionHealthVerdict] = []

    for ev in events:
        if ev.exit_code in HANG_EXIT_CODES or ev.signal == HANG_SIGNAL:
            verdicts.append(
                ExecutionHealthVerdict(
                    verdict="HANG",
                    recommendation="ESCALATE_HUMAN",
                    source="codex_events",
                    detail=(
                        f"Codex exec hung: exit_code={ev.exit_code} signal={ev.signal} "
                        f"ts={ev.ts} caller={ev.caller}"
                    ),
                )
            )

    error_sigs = [ev.error_sig for ev in events]
    spin_result = trigger_spinning(error_sigs)
    if spin_result is not None:
        verdicts.append(
            ExecutionHealthVerdict(
                verdict="SPINNING",
                recommendation="ESCALATE_HUMAN",
                source="codex_events",
                detail=spin_result.reason,
            )
        )

    durations = [ev.duration_s for ev in events if ev.duration_s is not None]
    if len(durations) >= 2:
        sorted_d = sorted(durations[:-1])
        mid = len(sorted_d) // 2
        baseline = sorted_d[mid]
        last_d = durations[-1]
        if baseline >= duration_baseline_s and last_d > baseline * duration_multiplier:
            verdicts.append(
                ExecutionHealthVerdict(
                    verdict="DURATION_ANOMALY",
                    recommendation="ESCALATE_HUMAN",
                    source="codex_events",
                    detail=(
                        f"duration_s={last_d:.1f}s exceeds {duration_multiplier}x "
                        f"baseline={baseline:.1f}s"
                    ),
                )
            )

    return verdicts


def scan_job_registry(
    db_path: Path,
    now: datetime,
) -> list[ExecutionHealthVerdict]:
    """Scan JobRegistry for HANG: jobs with status=running past timeout_seconds."""
    if not db_path.exists():
        return []
    verdicts: list[ExecutionHealthVerdict] = []
    try:
        registry = JobRegistry(db_path)
        running_jobs = registry.list_jobs(status_filter="running")
        registry.close()
    except Exception as exc:  # noqa: BLE001
        _LOG.warning("scan_job_registry: failed to open %s: %s", db_path, exc)
        return []
    now_ts = _aware(now)
    for job in running_jobs:
        if not job.started_at:
            continue
        try:
            started = datetime.fromisoformat(job.started_at.replace("Z", "+00:00"))
            started = _aware(started)
        except ValueError:
            continue
        elapsed_s = (now_ts - started).total_seconds()
        if elapsed_s > job.timeout_seconds:
            verdicts.append(
                ExecutionHealthVerdict(
                    verdict="HANG",
                    recommendation="ESCALATE_HUMAN",
                    source="job_registry",
                    detail=(
                        f"job_id={job.job_id} change_id={job.change_id} status=running "
                        f"elapsed={elapsed_s:.0f}s > timeout={job.timeout_seconds}s"
                    ),
                )
            )
    return verdicts


def check_evidence_integrity(repo_root, change_id: str, ref: str = "HEAD") -> list:
    verdicts = []
    tdd_path = Path(repo_root) / "tasks" / "tdd.json"

    def _iter_tdd_commands(tdd_data):
        def _commands_from_entry(entry_key, entry_val):
            if not isinstance(entry_val, dict):
                return
            for cmd_obj in entry_val.get("commands", []):
                if not isinstance(cmd_obj, dict):
                    continue
                cmd_str = cmd_obj.get("command", "")
                if isinstance(cmd_str, str):
                    yield entry_key, cmd_str
            categories = entry_val.get("categories", {})
            if isinstance(categories, dict):
                for category_key, category_val in categories.items():
                    if not isinstance(category_val, dict):
                        continue
                    cmd_str = category_val.get("command", "")
                    if isinstance(cmd_str, str):
                        yield f"{entry_key}.categories.{category_key}", cmd_str

        for entry_key, entry_val in tdd_data.items():
            if entry_key == "changes" and isinstance(entry_val, list):
                for idx, change_entry in enumerate(entry_val):
                    yield from _commands_from_entry(f"changes[{idx}]", change_entry)
                continue
            yield from _commands_from_entry(entry_key, entry_val)

    try:
        with open(tdd_path) as f:
            tdd_data = json.load(f)
        for entry_key, cmd_str in _iter_tdd_commands(tdd_data):
            if "ruff" in cmd_str and "--select" in cmd_str:
                verdicts.append(
                    IntegrityVerdict(
                        kind="NARROWED_RUFF_GATE",
                        detail=(
                            f"tdd.json entry '{entry_key}' command uses narrowed "
                            f"ruff gate: {cmd_str!r}"
                        ),
                    )
                )
    except Exception:
        pass
    result = subprocess.run(
        ["git", "show", "--name-only", "--pretty=format:", ref],
        cwd=str(repo_root),
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode == 0:
        changed_files = [line.strip() for line in result.stdout.splitlines() if line.strip()]
        if "tasks/plan.md" in changed_files:
            verdicts.append(
                IntegrityVerdict(
                    kind="PLAN_MD_EDIT",
                    detail=(
                        f"commit {ref} modified tasks/plan.md "
                        "(control-plane cursor; executor must not touch it)"
                    ),
                )
            )
        if "tasks/tdd.json" in changed_files:
            diff_result = subprocess.run(
                ["git", "show", ref, "--", "tasks/tdd.json"],
                cwd=str(repo_root),
                capture_output=True,
                text=True,
                check=False,
            )
            if diff_result.returncode == 0:
                import re

                touched_keys = set()
                for line in diff_result.stdout.splitlines():
                    m = re.match(r'^[+-]\s{2}"([^"]+)":', line)
                    if m:
                        touched_keys.add(m.group(1))
                for touched_key in touched_keys:
                    if touched_key != change_id:
                        verdicts.append(
                            IntegrityVerdict(
                                kind="PRIOR_LEDGER_EDIT",
                                detail=(
                                    f"commit {ref} modified ledger entry '{touched_key}' "
                                    f"(not the declared change_id '{change_id}')"
                                ),
                            )
                        )
    return verdicts
