"""Capture E7 merge-gate outcomes from the unchanged Python implementation."""

import dataclasses
import json
import os
import pathlib
import subprocess
import sys
import tempfile
from unittest.mock import patch

ROOT = pathlib.Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
from tools.mir_executor import dispatch  # noqa: E402
from tools.mir_executor.worktree import cleanup_worktree, create_dispatch_worktree  # noqa: E402

FAKE = pathlib.Path(__file__).with_name("executor_verifier_fake.py")
PROFILE = '[repo]\nrepository_type = "fixture"\n'
LITERAL = ["two words", "$(not-a-shell); * [literal]", "unicode-\u03bb-\ud55c"]


def git(repo, *args):
    return subprocess.run(
        ["git", "-C", str(repo), *args], check=True, capture_output=True, text=True
    ).stdout.strip()


def scenarios():
    cases = [
        {"name": "inherit-success"},
        {"name": "large-output", "runs": {"first": "output-large"}},
        {"name": "invalid-output", "runs": {"first": "output-invalid"}},
        {"name": "descendant-invalid-output", "runs": {"first": "descendant-invalid"}},
        {"name": "isolated-two", "mode": "isolated", "commands": ["first", "second"]},
        {"name": "isolated-failure", "mode": "isolated", "runs": {"first": "fail"}},
        {
            "name": "isolated-home-cleanup-error",
            "mode": "isolated",
            "runs": {"first": "home-cleanup-error"},
        },
        {
            "name": "isolated-timeout",
            "mode": "isolated",
            "runs": {"first": "timeout"},
            "timeout": 3,
        },
        {
            "name": "isolated-spawn-error",
            "mode": "isolated",
            "verifiers": {"first": ["mir-e7-nonexistent-verifier"]},
        },
        {"name": "failure-first", "runs": {"first": "fail"}, "commands": ["first", "second"]},
        {"name": "failure-second", "runs": {"second": "fail"}, "commands": ["first", "second"]},
        {"name": "timeout", "runs": {"first": "timeout"}, "timeout": 3},
        {"name": "cleanup-failure", "runs": {"first": "lock"}},
        {"name": "cleanup-overrides-failure", "runs": {"first": "lock-fail"}},
        {
            "name": "cleanup-overrides-spawn-error",
            "runs": {"first": "lock"},
            "commands": ["first", "second"],
            "verifiers": {"second": ["mir-e7-nonexistent-verifier"]},
        },
        {"name": "dirty-after", "runs": {"first": "dirty"}},
        {"name": "dirty-before", "dirty": True},
        {"name": "runtime-artifacts-ignored", "runtime_dirty": True},
        {"name": "empty-diff", "changes": {}},
        {"name": "reviewed-no-diff", "changes": {}, "expect_changes": False},
        {"name": "denied-plan", "changes": {"tasks/plan.md": "changed\n"}},
        {"name": "denied-source", "changes": {"config/source.py": "changed\n"}},
        {
            "name": "self-modify-source",
            "changes": {"config/source.py": "changed\n"},
            "self_modify": True,
        },
        {
            "name": "self-modify-still-denies-plan",
            "changes": {"tasks/plan.md": "changed\n"},
            "self_modify": True,
        },
        {
            "name": "denied-quoted-unicode",
            "changes": {"tasks/a'b\u03bb.txt": "changed\n", "tasks/z.txt": "changed\n"},
        },
        {"name": "allowed-tdd-path", "changes": {"tasks/tdd.json": "{}\n"}},
        {
            "name": "secret-basename",
            "changes": {"nested/private.key": "secret\n"},
            "secrets": ["*.key"],
        },
        {
            "name": "secret-directory",
            "changes": {"vault/code.txt": "secret\n"},
            "secrets": ["vault"],
        },
        {
            "name": "secret-slash",
            "changes": {"nested/private.key": "secret\n"},
            "secrets": ["nested/*.key"],
        },
        {
            "name": "secret-before-allowlist",
            "changes": {"private.key": "secret\n"},
            "secrets": ["*.key"],
            "allowlist": [],
        },
        {"name": "outside-allowlist", "allowlist": ["other/"]},
        {
            "name": "literal-allowlist",
            "changes": {"code [literal].txt": "changed\n"},
            "allowlist": ["code [literal].txt"],
        },
        {"name": "glob-allowlist", "allowlist": ["*.txt"]},
        {"name": "unknown-sorted", "commands": ["z", "a", "z"]},
        {"name": "invalid-empty", "verifiers": {"first": []}},
        {"name": "invalid-empty-arg", "verifiers": {"first": [""]}},
        {"name": "invalid-nonstring-arg", "verifiers": {"first": [True]}},
        {"name": "invalid-string-argv", "verifiers": {"first": "echo unsafe"}},
        {"name": "invalid-null-argv", "verifiers": {"first": None}},
        {"name": "no-verifiers", "commands": []},
        {
            "name": "path-before-unknown",
            "changes": {"tasks/plan.md": "changed\n"},
            "commands": ["unknown"],
        },
        {"name": "invalid-before-dirty", "verifiers": {"first": []}, "dirty": True},
        {"name": "pinned-source", "pinned": True},
        {"name": "invalid-env", "mode": "unknown"},
        {"name": "invalid-timeout-zero", "timeout": 0},
        {"name": "invalid-timeout-bool", "timeout": True},
        {"name": "timeout-bounds", "timeout": 1, "bounds": [2, 20]},
    ]
    for case in cases:
        case.setdefault("changes", {"code.txt": "changed\n"})
        case.setdefault("allowlist", list(case["changes"]))
        case.setdefault("commands", ["first"])
        case.setdefault("mode", "inherit")
        case.setdefault("runs", {})
        case.setdefault("expect_changes", True)
    return cases


def receipt_projection(receipt, repo, wt, source_env, mode):
    env = receipt["env"]
    if mode == "isolated":
        env["HOME"] = "<ISOLATED_HOME>"
        env["UV_CACHE_DIR"] = "<ISOLATED_CACHE>"
    else:
        env["HOME"] = "<PARENT_HOME>"
        env["UV_CACHE_DIR"] = "<PARENT_CACHE>"
        env["CODEX_EVENTS_FILE"] = "<REPO>/tasks/codex-exec-events.jsonl"
        env["CODEX_HOME"] = "<CODEX_HOME>"
    return {
        key: receipt[key]
        for key in [
            "literal",
            "stdin_eof",
            "code",
            "profile",
            "home_exists",
            "cache_exists",
            "home_preexisting",
        ]
    } | {"env": env, "cwd_is_dispatch": pathlib.Path(receipt["cwd"]) == wt.path}


def capture(root, case):
    base = root / case["name"]
    repo = base / "repo"
    repo.mkdir(parents=True)
    git(repo, "init", "-q")
    git(repo, "config", "core.autocrlf", "false")
    git(repo, "config", "user.name", "Fixture")
    git(repo, "config", "user.email", "fixture@example.invalid")
    (repo / ".gitignore").write_text(".mir/\n.mir-dispatch/\nconfig/mir-executor.local.json\n")
    (repo / "code.txt").write_text("initial\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "fixture")
    (repo / ".mir").mkdir()
    profile = PROFILE
    if "secrets" in case:
        profile += "\n[boundaries]\nsecrets = " + json.dumps(case["secrets"]) + "\n"
    (repo / ".mir/repo-profile.toml").write_text(profile)
    wt = create_dispatch_worktree(repo, "fixture", worktrees_root=base / "trees")
    for path, text in case["changes"].items():
        target = wt.path / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
    if case["changes"]:
        git(wt.path, "add", "-A")
        git(wt.path, "commit", "-qm", "changes")
    source = git(wt.path, "rev-parse", "HEAD")
    if case.get("pinned"):
        (wt.path / "later.txt").write_text("not selected\n")
        (wt.path / "code.txt").write_text("later\n")
        git(wt.path, "add", "-A")
        git(wt.path, "commit", "-qm", "later")
    if case.get("dirty"):
        (wt.path / "dirty.txt").write_text("dirty\n")
    if case.get("runtime_dirty"):
        (wt.path / ".mir-dispatch/runtime.log").write_text("runtime\n")
    receipts = {name: base / (name + ".json") for name in ["first", "second"]}
    verifiers = {
        name: [
            sys.executable,
            str(FAKE),
            str(path),
            case["runs"].get(name, "pass"),
            str(wt.path),
            *LITERAL,
        ]
        for name, path in receipts.items()
    }
    verifiers.update(case.get("verifiers", {}))
    config = {
        "verifiers": verifiers,
        "verifier_env": case["mode"],
        "child_env_extra_keys": ["EXPLICIT_TOKEN", "UV_CACHE_DIR", "SystemRoot"],
    }
    if "bounds" in case:
        config["timeout_seconds_range"] = case["bounds"]
    (repo / "config").mkdir()
    (repo / "config/mir-executor.local.json").write_text(json.dumps(config))
    for name in ["parent-home", "parent-cache", "tmp"]:
        (base / name).mkdir()
    env = {key: os.environ[key] for key in ["PATH", "SystemRoot"] if key in os.environ}
    env.update(
        {
            "HOME": str(base / "parent-home"),
            "UV_CACHE_DIR": str(base / "parent-cache"),
            "TMPDIR": str(base / "tmp"),
            "LANG": "C.UTF-8",
            "LC_MESSAGES": "C",
            "OPENAI_API_KEY": "must-not-inherit",
            "EXPLICIT_TOKEN": "explicit",
            "UNLISTED": "must-not-inherit",
            "CODEX_HOME": str(base / "codex-home"),
        }
    )
    try:
        with patch.dict(os.environ, env, clear=True):
            # Keep both verification worktrees and isolated homes in caller-owned scratch.
            with patch.object(tempfile, "tempdir", str(base / "tmp")):
                gate = dispatch.evaluate_merge_gate(
                    wt,
                    allowlist=case["allowlist"],
                    verification_commands=case["commands"],
                    verify_timeout=case.get("timeout"),
                    expect_changes=case["expect_changes"],
                    allow_harness_self_modify=case.get("self_modify", False),
                    source_commit=source if case.get("pinned") else None,
                )
        expected = {"gate": dataclasses.asdict(gate)}
    except (ValueError, OSError) as exc:
        expected = {"error": type(exc).__name__, "message": str(exc).replace(str(base), "<CASE>")}
    observed = []
    for name, path in receipts.items():
        if path.exists():
            receipt = json.loads(path.read_text())
            if "message" in expected:
                for key in ["cache", "home", "cwd"]:
                    expected["message"] = expected["message"].replace(
                        receipt[key].replace(str(base), "<CASE>"), "<" + key.upper() + ">"
                    )
            observed.append(
                {"name": name, "receipt": receipt_projection(receipt, repo, wt, env, case["mode"])}
            )
            isolated_root = pathlib.Path(receipt["cwd"])
            if isolated_root.exists():
                git(repo, "worktree", "unlock", str(isolated_root))
                git(repo, "worktree", "remove", "--force", str(isolated_root))
    expected["receipts"] = observed
    cleanup_worktree(wt)
    return case | {"expected": expected}


def main():
    with tempfile.TemporaryDirectory(
        prefix="python-e7-", dir=os.environ.get("MIR_NATIVE_TEST_SCRATCH")
    ) as tmp:
        cases = [capture(pathlib.Path(tmp), case) for case in scenarios()]
        profiles = []
        for index, text in enumerate(
            [
                None,
                "",
                "not toml [",
                '[repo]\nrepository_type="meta_harness"\n',
                '[repo]\nrepository_type="consumer"\n',
                'repo="meta_harness"\n',
            ]
        ):
            repo = pathlib.Path(tmp) / ("profile-" + str(index))
            (repo / ".mir").mkdir(parents=True)
            if text is not None:
                (repo / ".mir/repo-profile.toml").write_text(text, encoding="utf-8")
            profiles.append({"text": text, "expected": dispatch._resolve_harness_self_modify(repo)})
    pathlib.Path(__file__).with_name("executor_verifier.json").write_text(
        json.dumps(
            {"literal": LITERAL, "cases": cases, "profiles": profiles}, indent=2, ensure_ascii=True
        )
        + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
