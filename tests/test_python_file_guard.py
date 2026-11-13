"""Rust-first additions: exact Yoke baseline, cited categories, or a churn reason."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path, PurePosixPath

import pytest

ROOT = Path(__file__).resolve().parents[1]
POLICY = "config/python-allowlist.json"


def check_python_files(root: Path, tracked: set[str]) -> None:
    policy = json.loads((root / POLICY).read_text(encoding="utf-8"))
    baseline = {
        str(PurePosixPath(prefix) / name)
        for prefix, names in policy["baseline"].items()
        for name in names
    }
    reasons = policy["allowlist"]
    errors = []
    for path, reason in reasons.items():
        if not isinstance(reason, str) or not reason.strip() or len(reason.splitlines()) != 1:
            errors.append(f"{path}: provide a nonempty one-line churn reason.")
    stale = {
        path for path in baseline | reasons.keys()
        if path not in tracked or not (root / path).is_file()
    }
    if stale:
        errors.append("Stale baseline/allowlist entries; remove them: " + ", ".join(sorted(stale)))
    for path in sorted(tracked - baseline - reasons.keys()):
        parts = PurePosixPath(path).parts
        if "tests" in parts[:-1] or parts[-1] == "conftest.py":
            continue
        if any(path.startswith(prefix) for prefix in policy["python_allowed_prefixes"]):
            continue
        errors.append(
            f"{path}: Write it in Rust, or add the exact path with a one-line churn reason "
            f"to {POLICY}."
        )
    assert not errors, "\n".join(errors)


def test_python_files_have_recorded_reasons() -> None:
    tracked = subprocess.run(
        ["git", "ls-files", "-z", "--", "*.py"], cwd=ROOT,
        check=True, capture_output=True,
    ).stdout.decode().split("\0")
    check_python_files(ROOT, set(tracked) - {""})


@pytest.mark.parametrize(
    ("tracked", "baseline", "reasons", "message"),
    [
        ({"src/pkg/old.py", "src/pkg/new.py"}, {"src/pkg": ["old.py"]}, {}, "Write it in Rust"),
        (set(), {"src/pkg": ["removed.py"]}, {}, "Stale"),
        (set(), {}, {"src/removed.py": "Frequently changing protocol."}, "Stale"),
        ({"src/new.py"}, {}, {"src/new.py": ""}, "one-line churn reason"),
        ({"src/new.py"}, {}, {"src/new.py": "First line.\nSecond line."}, "one-line churn reason"),
    ],
)
def test_python_guard_rejects_invalid_inventory(
    tmp_path: Path, tracked: set[str], baseline: dict, reasons: dict, message: str,
) -> None:
    (tmp_path / "config").mkdir()
    (tmp_path / POLICY).write_text(json.dumps({
        "baseline": baseline, "allowlist": reasons, "python_allowed_prefixes": {},
    }))
    for path in tracked:
        target = tmp_path / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.touch()
    with pytest.raises(AssertionError, match=message):
        check_python_files(tmp_path, tracked)


def test_python_guard_accepts_categories_and_churn_reasons(tmp_path: Path) -> None:
    policy = json.loads((ROOT / POLICY).read_text())
    policy.update(baseline={}, allowlist={"src/new.py": "Frequently changing protocol."})
    (tmp_path / "config").mkdir()
    (tmp_path / POLICY).write_text(json.dumps(policy))
    paths = {
        "tests/oracle.py", "pkg/tests/oracle.py", "conftest.py", "pkg/conftest.py",
        "src/new.py", *(prefix + "probe.py" for prefix in policy["python_allowed_prefixes"]),
    }
    for path in paths:
        target = tmp_path / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.touch()
    check_python_files(tmp_path, paths)


def test_python_guard_rejects_missing_worktree_file(tmp_path: Path) -> None:
    (tmp_path / "config").mkdir()
    (tmp_path / POLICY).write_text(json.dumps({
        "baseline": {"src": ["removed.py"]}, "allowlist": {}, "python_allowed_prefixes": {},
    }))
    with pytest.raises(AssertionError, match="Stale.*src/removed.py"):
        check_python_files(tmp_path, {"src/removed.py"})


@pytest.mark.parametrize(
    ("path", "accepted"),
    [
        ("tests/fixtures/generate.py", True),
        ("native/mir-hooks/tests/capture.py", True),
        ("tools/harness_consistency/probe.py", True),
        ("src/mir/new.py", False),
        ("tools/mir_executor/new.py", False),
        ("scripts/new.py", False),
        ("plugins/new.py", False),
        ("tools/harness_consistency_extra/new.py", False),
        ("src/tests_extra/new.py", False),
    ],
)
def test_python_guard_uses_git_tracked_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, path: str, accepted: bool,
) -> None:
    """Exercise the real Git listing without touching the worktree index."""
    policy = json.loads((ROOT / POLICY).read_text(encoding="utf-8"))
    policy.update(baseline={}, allowlist={})
    (tmp_path / "config").mkdir()
    (tmp_path / POLICY).write_text(json.dumps(policy), encoding="utf-8")
    target = tmp_path / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.touch()
    # An untracked file must not enter a tracked-only inventory.
    (tmp_path / "untracked.py").touch()
    subprocess.run(["git", "init", "--quiet", str(tmp_path)], check=True)
    subprocess.run(["git", "add", "--", path], cwd=tmp_path, check=True)
    monkeypatch.setitem(globals(), "ROOT", tmp_path)
    if accepted:
        test_python_files_have_recorded_reasons()
    else:
        with pytest.raises(AssertionError, match="Write it in Rust"):
            test_python_files_have_recorded_reasons()
