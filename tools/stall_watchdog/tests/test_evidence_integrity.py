import json
import subprocess
from pathlib import Path

import pytest

from tools.stall_watchdog.scan import IntegrityVerdict, check_evidence_integrity


def _git(args, cwd: Path):
    subprocess.run(["git"] + args, cwd=cwd, check=True, capture_output=True)


def _init_repo(tmp_path: Path):
    _git(["init"], tmp_path)
    _git(["config", "user.email", "test@test.com"], tmp_path)
    _git(["config", "user.name", "Test"], tmp_path)


@pytest.mark.parametrize("ref", ["HEAD"])
def test_narrowed_ruff_gate_detected(tmp_path: Path, ref: str):
    _init_repo(tmp_path)
    tasks_dir = tmp_path / "tasks"
    tasks_dir.mkdir()
    tdd = {"my-change": {"commands": [{"command": "uv run ruff check --select F,I src/"}]}}
    (tasks_dir / "tdd.json").write_text(json.dumps(tdd))
    _git(["add", "."], tmp_path)
    _git(["commit", "-m", "init"], tmp_path)
    verdicts: list[IntegrityVerdict] = check_evidence_integrity(
        tmp_path, "my-change", ref
    )
    kinds = [v.kind for v in verdicts]
    assert "NARROWED_RUFF_GATE" in kinds


def test_narrowed_ruff_gate_detected_in_categories_command(tmp_path: Path):
    _init_repo(tmp_path)
    tasks_dir = tmp_path / "tasks"
    tasks_dir.mkdir()
    tdd = {
        "my-change": {
            "categories": {
                "unit": {"command": "uv run ruff check --select E tools/"}
            }
        }
    }
    (tasks_dir / "tdd.json").write_text(json.dumps(tdd))
    _git(["add", "."], tmp_path)
    _git(["commit", "-m", "init"], tmp_path)
    verdicts: list[IntegrityVerdict] = check_evidence_integrity(
        tmp_path, "my-change", "HEAD"
    )
    kinds = [v.kind for v in verdicts]
    assert "NARROWED_RUFF_GATE" in kinds


def test_plan_md_edit_detected(tmp_path: Path):
    _init_repo(tmp_path)
    tasks_dir = tmp_path / "tasks"
    tasks_dir.mkdir()
    (tasks_dir / "tdd.json").write_text(json.dumps({}))
    (tasks_dir / "plan.md").write_text("# Plan\n")
    _git(["add", "."], tmp_path)
    _git(["commit", "-m", "init with plan.md"], tmp_path)
    verdicts = check_evidence_integrity(tmp_path, "some-id", "HEAD")
    kinds = [v.kind for v in verdicts]
    assert "PLAN_MD_EDIT" in kinds


def test_prior_ledger_edit_detected(tmp_path: Path):
    _init_repo(tmp_path)
    tasks_dir = tmp_path / "tasks"
    tasks_dir.mkdir()
    (tasks_dir / "tdd.json").write_text(json.dumps({}))
    _git(["add", "."], tmp_path)
    _git(["commit", "-m", "init"], tmp_path)
    tdd = {"prior-id": {"commands": []}}
    (tasks_dir / "tdd.json").write_text(json.dumps(tdd, indent=2))
    _git(["add", "tasks/tdd.json"], tmp_path)
    _git(["commit", "-m", "add prior-id"], tmp_path)
    verdicts = check_evidence_integrity(tmp_path, "current-id", "HEAD")
    kinds = [v.kind for v in verdicts]
    assert "PRIOR_LEDGER_EDIT" in kinds


def test_clean_commit_no_verdicts(tmp_path: Path):
    _init_repo(tmp_path)
    tasks_dir = tmp_path / "tasks"
    tasks_dir.mkdir()
    (tasks_dir / "tdd.json").write_text(json.dumps({}))
    _git(["add", "."], tmp_path)
    _git(["commit", "-m", "init"], tmp_path)
    tdd = {"my-change": {"commands": [{"command": "uv run ruff check"}]}}
    (tasks_dir / "tdd.json").write_text(json.dumps(tdd, indent=2))
    _git(["add", "tasks/tdd.json"], tmp_path)
    _git(["commit", "-m", "add my-change"], tmp_path)
    verdicts = check_evidence_integrity(tmp_path, "my-change", "HEAD")
    assert verdicts == []
