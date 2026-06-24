"""ADR-06 Phase 6C-5 unit tests — tools/stall_watchdog/cli.py."""

from __future__ import annotations

import ast
import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path

from tools.stall_watchdog import cli as cli_mod
from tools.stall_watchdog.cli import main
from tools.stall_watchdog.scan import (
    ExecutionHealthVerdict,
    IntegrityVerdict,
    StallVerdict,
)


def _make_entry(top, *, ts, content=None):
    obj = {"type": top, "timestamp": ts}
    if content is not None:
        obj["message"] = {"content": content}
    return json.dumps(obj)


def _write_session(pool: Path, workspace: str, name: str, lines, mtime_offset: int = -30):
    ws = pool / workspace
    ws.mkdir(parents=True, exist_ok=True)
    jsonl = ws / f"{name}.jsonl"
    jsonl.write_text("\n".join(lines) + "\n", encoding="utf-8")
    now_ts = datetime.now(tz=UTC).timestamp()
    os.utime(jsonl, (now_ts + mtime_offset, now_ts + mtime_offset))


def test_doctor_runs_and_returns_zero(tmp_path: Path, capsys, monkeypatch):
    monkeypatch.setenv("MIR_STALL_WATCHDOG_POOL_ROOT", str(tmp_path / "pool"))
    monkeypatch.delenv("MIR_STALL_WATCHDOG_WEBHOOK_DEFAULT", raising=False)
    rc = main(["doctor"])
    assert rc == 0
    out = capsys.readouterr().out
    payload = json.loads(out)
    assert payload["pool_root_exists"] is False  # pool dir not created
    assert payload["family_count_in_map"] == 13
    assert payload["workspace_dir_count"] == 16
    assert "webhooks" in payload


def test_scan_dry_run_with_no_stall(tmp_path: Path, capsys, monkeypatch):
    pool = tmp_path / "pool"
    pool.mkdir()
    monkeypatch.setenv("MIR_STALL_WATCHDOG_POOL_ROOT", str(pool))
    rc = main(["scan", "--dry-run"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "0 stall(s)" in out


def test_scan_json_emits_structured_report(tmp_path: Path, capsys, monkeypatch):
    pool = tmp_path / "pool"
    pool.mkdir()
    monkeypatch.setenv("MIR_STALL_WATCHDOG_POOL_ROOT", str(pool))
    rc = main(["scan", "--dry-run", "--json"])
    assert rc == 0
    out = capsys.readouterr().out
    parsed = json.loads(out)
    assert "verdicts" in parsed
    assert "pushed" in parsed


def test_scan_detects_stall_and_dry_run_no_push(tmp_path: Path, capsys, monkeypatch):
    pool = tmp_path / "pool"
    now = datetime.now(tz=UTC)
    _write_session(
        pool,
        "-Volumes-T7-Shield-Project-05-Write-Score",
        "abc",
        [
            _make_entry(
                "assistant",
                ts=(now - timedelta(seconds=400)).isoformat().replace("+00:00", "Z"),
                content=[{"type": "tool_use"}],
            ),
            _make_entry(
                "queue-operation",
                ts=(now - timedelta(seconds=200)).isoformat().replace("+00:00", "Z"),
            ),
        ],
        mtime_offset=-30,
    )
    monkeypatch.setenv("MIR_STALL_WATCHDOG_POOL_ROOT", str(pool))
    monkeypatch.setenv("MIR_STALL_WATCHDOG_THRESHOLD_SECONDS", "180")
    monkeypatch.setenv("MIR_STALL_WATCHDOG_RECENT_K_MINUTES", "60")
    rc = main(["scan", "--dry-run", "--json"])
    assert rc == 0
    parsed = json.loads(capsys.readouterr().out)
    stalls = [v for v in parsed["verdicts"] if v["is_stall"]]
    assert len(stalls) == 1
    assert stalls[0]["family_slug"] == "<example-family>"
    assert all(p["dry_run"] for p in parsed["pushed"])


def test_scan_with_webhook_calls_push(tmp_path: Path, monkeypatch, capsys):
    pool = tmp_path / "pool"
    now = datetime.now(tz=UTC)
    _write_session(
        pool,
        "-Volumes-T7-Shield-Project-09-Mini-Harness",
        "xyz",
        [
            _make_entry(
                "assistant",
                ts=(now - timedelta(seconds=400)).isoformat().replace("+00:00", "Z"),
                content=[{"type": "tool_use"}],
            ),
        ],
    )
    monkeypatch.setenv("MIR_STALL_WATCHDOG_POOL_ROOT", str(pool))
    monkeypatch.setenv(
        "MIR_STALL_WATCHDOG_WEBHOOK_MIR_HARNESS",
        "https://discord.com/api/webhooks/x/y",
    )
    calls = []

    def fake_push(url, alarm, **kwargs):
        calls.append((url, alarm.family))
        return True

    monkeypatch.setattr(cli_mod, "push_to_discord", fake_push)
    rc = main(["scan", "--json"])
    assert rc == 0
    assert len(calls) == 1
    assert calls[0][1] == "your-harness"


def test_daemon_max_ticks_exits_cleanly(tmp_path: Path, monkeypatch, capsys):
    pool = tmp_path / "pool"
    pool.mkdir()
    monkeypatch.setenv("MIR_STALL_WATCHDOG_POOL_ROOT", str(pool))
    rc = main(["daemon", "--max-ticks", "2", "--poll", "0"])
    assert rc == 0


def test_daemon_dry_run_no_webhook(tmp_path: Path, monkeypatch, capsys):
    pool = tmp_path / "pool"
    now = datetime.now(tz=UTC)
    _write_session(
        pool,
        "-Volumes-T7-Shield-Project-05-Write-Score",
        "stall",
        [
            _make_entry(
                "assistant",
                ts=(now - timedelta(seconds=400)).isoformat().replace("+00:00", "Z"),
                content=[{"type": "tool_use"}],
            ),
        ],
    )
    monkeypatch.setenv("MIR_STALL_WATCHDOG_POOL_ROOT", str(pool))
    monkeypatch.delenv("MIR_STALL_WATCHDOG_WEBHOOK_DEFAULT", raising=False)
    monkeypatch.delenv("MIR_STALL_WATCHDOG_WEBHOOK_WRITE_SCORE", raising=False)
    rc = main(["daemon", "--max-ticks", "1", "--poll", "0"])
    assert rc == 0


def test_daemon_tick_pushes_deep_scan_verdicts(tmp_path: Path, monkeypatch):
    pool = tmp_path / "pool"
    pool.mkdir()
    events_path = tmp_path / "events.jsonl"
    db_path = tmp_path / "jobs.db"
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    monkeypatch.setenv("MIR_STALL_WATCHDOG_POOL_ROOT", str(pool))
    monkeypatch.setenv("MIR_STALL_WATCHDOG_WEBHOOK_DEFAULT", "https://d.example/hook")
    monkeypatch.setenv("MIR_AGENT_CHECK_EVENTS_PATH", str(events_path))
    monkeypatch.setenv("MIR_AGENT_CHECK_DB_PATH", str(db_path))
    monkeypatch.setenv("MIR_AGENT_CHECK_REPO_ROOT", str(repo_root))
    monkeypatch.setenv("MIR_AGENT_CHECK_CHANGE_ID", "adr61-b5")
    seen = []
    pushed = []

    monkeypatch.setattr(cli_mod, "scan_pool", lambda *args: [])

    def fake_codex_events(path):
        seen.append(("codex", path))
        return [
            ExecutionHealthVerdict(
                verdict="HANG",
                recommendation="ESCALATE_HUMAN",
                source="codex_events",
                detail="Codex exec hung: exit_code=142",
            )
        ]

    def fake_job_registry(path, now):
        seen.append(("job", path))
        return [
            ExecutionHealthVerdict(
                verdict="HANG",
                recommendation="ESCALATE_HUMAN",
                source="job_registry",
                detail="job_id=j1 status=running elapsed=200s > timeout=120s",
            )
        ]

    def fake_integrity(root, change_id, ref):
        seen.append(("integrity", root, change_id, ref))
        return [
            IntegrityVerdict(
                kind="PLAN_MD_EDIT",
                detail="commit HEAD modified tasks/plan.md",
            )
        ]

    def fake_subagent_pool(config, now, workspace_to_family):
        seen.append(("subagent", config.pool_root))
        return [
            StallVerdict(
                is_stall=True,
                family_slug="<example-family>",
                workspace_encoded="-Volumes-T7-Shield-Project-05-Write-Score",
                session_uuid="session/agent001",
                jsonl_path=tmp_path / "agent001.output",
                idle_seconds=240,
                last_entry=None,
                skip_reason=None,
            )
        ]

    def fake_push(url, alarm, **kwargs):
        pushed.append((url, alarm))
        return True

    monkeypatch.setattr(cli_mod, "scan_codex_events", fake_codex_events)
    monkeypatch.setattr(cli_mod, "scan_job_registry", fake_job_registry)
    monkeypatch.setattr(cli_mod, "check_evidence_integrity", fake_integrity)
    monkeypatch.setattr(cli_mod, "scan_subagent_pool", fake_subagent_pool)
    monkeypatch.setattr(cli_mod, "push_to_discord", fake_push)

    assert main(["daemon", "--max-ticks", "1", "--poll", "0"]) == 0

    assert ("codex", events_path) in seen
    assert ("job", db_path) in seen
    assert ("integrity", repo_root, "adr61-b5", "HEAD") in seen
    assert ("subagent", pool) in seen
    labels = [
        (alarm.family, getattr(alarm, "source", "stall"), getattr(alarm, "kind", ""))
        for _, alarm in pushed
    ]
    assert ("your-harness", "codex_events", "HANG") in labels
    assert ("your-harness", "job_registry", "HANG") in labels
    assert ("your-harness", "integrity", "PLAN_MD_EDIT") in labels
    assert ("<example-family>", "stall", "") in labels


def test_daemon_skips_integrity_when_change_id_empty(tmp_path: Path, monkeypatch):
    pool = tmp_path / "pool"
    pool.mkdir()
    monkeypatch.setenv("MIR_STALL_WATCHDOG_POOL_ROOT", str(pool))
    monkeypatch.setenv("MIR_STALL_WATCHDOG_WEBHOOK_DEFAULT", "https://d.example/hook")
    monkeypatch.setenv("MIR_AGENT_CHECK_EVENTS_PATH", str(tmp_path / "events.jsonl"))
    monkeypatch.setenv("MIR_AGENT_CHECK_DB_PATH", str(tmp_path / "jobs.db"))
    monkeypatch.setenv("MIR_AGENT_CHECK_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("MIR_AGENT_CHECK_CHANGE_ID", "")
    called = {"integrity": 0}

    monkeypatch.setattr(cli_mod, "scan_pool", lambda *args: [])
    monkeypatch.setattr(cli_mod, "scan_codex_events", lambda path: [])
    monkeypatch.setattr(cli_mod, "scan_job_registry", lambda path, now: [])
    monkeypatch.setattr(cli_mod, "scan_subagent_pool", lambda *args: [])

    def fake_integrity(*args):
        called["integrity"] += 1
        return []

    monkeypatch.setattr(cli_mod, "check_evidence_integrity", fake_integrity)

    assert main(["daemon", "--max-ticks", "1", "--poll", "0"]) == 0
    assert called["integrity"] == 0


def test_production_path_has_no_llm_imports():
    root = Path(cli_mod.__file__).resolve().parent
    banned_fragments = (
        "anthropic",
        "api",
        "generativeai",
        "langchain",
        "litellm",
        "llm",
        "llama_index",
        "mistralai",
        "model",
        "openai",
    )
    offenders = []
    for path in sorted(root.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                imported = [node.module or ""]
            else:
                continue
            for name in imported:
                if any(fragment in name.lower() for fragment in banned_fragments):
                    offenders.append(f"{path.name}:{name}")
    assert offenders == []


def test_unknown_subcommand_exits_nonzero(capsys):
    import pytest

    with pytest.raises(SystemExit) as exc_info:
        main(["unknown-command"])
    assert exc_info.value.code != 0


def test_env_int_invalid_falls_back_default(monkeypatch):
    monkeypatch.setenv("MIR_STALL_WATCHDOG_THRESHOLD_SECONDS", "not-an-int")
    config = cli_mod._build_scan_config()
    assert config.threshold_seconds == 180


def test_resolve_webhook_per_family_then_default(monkeypatch):
    monkeypatch.delenv("MIR_STALL_WATCHDOG_WEBHOOK_DEFAULT", raising=False)
    monkeypatch.delenv("MIR_STALL_WATCHDOG_WEBHOOK_WRITE_SCORE", raising=False)
    assert cli_mod._resolve_webhook("<example-family>") == ""
    monkeypatch.setenv("MIR_STALL_WATCHDOG_WEBHOOK_DEFAULT", "https://d.example/d")
    assert cli_mod._resolve_webhook("unknown-slug") == "https://d.example/d"
    monkeypatch.setenv(
        "MIR_STALL_WATCHDOG_WEBHOOK_WRITE_SCORE", "https://d.example/ws"
    )
    assert cli_mod._resolve_webhook("<example-family>") == "https://d.example/ws"


def test_python_version_in_doctor_report(tmp_path: Path, capsys, monkeypatch):
    monkeypatch.setenv("MIR_STALL_WATCHDOG_POOL_ROOT", str(tmp_path))
    assert main(["doctor"]) == 0
    out = capsys.readouterr().out
    parsed = json.loads(out)
    assert parsed["python_version"].startswith(("3.12", "3.13"))
