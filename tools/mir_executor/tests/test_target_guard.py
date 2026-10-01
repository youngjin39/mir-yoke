"""The invoking package's Git repository owns cross-repository admission."""

from __future__ import annotations

import argparse
import subprocess

import pytest

from tools.mir_executor import cli, local_hooks
from tools.mir_executor.jobs import JobRecord, JobRegistry


@pytest.fixture
def repositories(tmp_path, monkeypatch):
    home = tmp_path / "home"
    target = tmp_path / "target"
    for root in (home, target):
        subprocess.run(["git", "init", "-q", str(root)], check=True)
        (root / "tools/mir_executor").mkdir(parents=True)
    monkeypatch.setattr(local_hooks, "__file__", str(home / "tools/mir_executor/local_hooks.py"))
    # CWD is deliberately the target: home must come from the package location.
    monkeypatch.chdir(target)
    return home, target


def _write_hook(root, source):
    (root / "tools/mir_executor/local.py").write_text(source)


@pytest.mark.parametrize("command", ["execute", "resume", "sweep"])
def test_should_refuse_before_target_import_or_execution(repositories, capsys, command):
    home, target = repositories
    _write_hook(home, """
def authorize_target(home_root, target_root, args):
    assert home_root.name == 'home'
    assert target_root.name == 'target'
    assert args.subcommand in {'execute', 'resume', 'sweep'}
    raise RuntimeError('home policy refuses this target')
""")
    marker = target / "target-loaded"
    _write_hook(target, f"""
from pathlib import Path
Path({str(marker)!r}).touch()
raise AssertionError('target local.py must not load before authorization')
""")
    options = [command, "--repo-root", str(target)]
    if command == "execute":
        options += ["--dispatch", "--codex-args", "task"]
    elif command == "resume":
        options += ["--job-id", "missing"]
    with pytest.raises(SystemExit) as exc:
        cli.main(options)
    assert exc.value.code == 1
    assert "authorize_target" in capsys.readouterr().err
    assert not marker.exists()
    assert not (target / "tasks/jobs.db").exists()


@pytest.mark.parametrize("same_root", [False, True])
def test_should_allow_without_loading_target_guard(repositories, same_root):
    home, target = repositories
    if same_root:
        _write_hook(home, "raise AssertionError('same-repository behavior must stay unchanged')\n")
        target = home
    else:
        _write_hook(target, "raise AssertionError('target guard must not be consulted')\n")
    local_hooks.authorize_target(target, argparse.Namespace(repo_root=target))


def test_should_ignore_package_location_that_is_not_git_root(repositories, monkeypatch):
    home, target = repositories
    nested = home / "nested/tools/mir_executor"
    nested.mkdir(parents=True)
    _write_hook(home, "raise AssertionError('package parent is not a Git root')\n")
    monkeypatch.setattr(local_hooks, "__file__", str(nested / "local_hooks.py"))
    local_hooks.authorize_target(target, argparse.Namespace(repo_root=target))


@pytest.mark.parametrize("redirect", [False, True])
def test_should_authorize_before_pre_execute_and_after_redirect(repositories, redirect):
    home, target = repositories
    _write_hook(home, """
def authorize_target(home_root, target_root, args):
    if target_root != home_root:
        raise RuntimeError('external target refused')
""")
    if redirect:
        _write_hook(home, f"""
from pathlib import Path
def authorize_target(home_root, target_root, args):
    if target_root != home_root:
        raise RuntimeError('external target refused')
def pre_execute(args, root):
    args.repo_root = Path({str(target)!r})
""")
    else:
        _write_hook(
            target, "raise AssertionError('pre_execute must not load before authorization')\n",
        )
    args = argparse.Namespace(repo_root=home if redirect else target)
    with pytest.raises(ValueError, match="authorize_target.*external target refused"):
        cli._prepare_execute_root(args)


@pytest.mark.parametrize("help_requested", [False, True])
def test_should_pass_args_to_home_hook_before_target_options(
    repositories, monkeypatch, capsys, help_requested,
):
    home, target = repositories
    marker = home / "authorized"
    _write_hook(home, """
def authorize_target(home_root, target_root, args):
    assert args.family == 'selected'
    assert args.dispatch is True
    (home_root / 'authorized').touch()
""")
    _write_hook(target, f"""
from pathlib import Path
assert Path({str(marker)!r}).exists(), 'home hook must run before target import'
def register_execute_options(parser):
    parser.add_argument('--local-choice', required=True)
""")
    calls = []
    monkeypatch.setattr(cli, "_handle_execute", lambda args: calls.append(args.local_choice) or 0)
    options = [
        "execute", "--repo-root", str(target), "--family", "selected", "--dispatch",
        "--codex-args", "task", "--local-choice", "chosen",
    ]
    if help_requested:
        with pytest.raises(SystemExit) as exc:
            cli.main([*options, "--help"])
        assert exc.value.code == 0
        assert marker.exists()
        assert "--local-choice" in capsys.readouterr().out
        assert not calls
    else:
        assert cli.main(options) == 0
        assert calls == ["chosen"]


@pytest.mark.parametrize("redirect", [False, True])
def test_should_authorize_saved_resume_target_before_loading_its_hooks(
    repositories, capsys, redirect,
):
    home, target = repositories
    _write_hook(home, """
def authorize_target(home_root, target_root, args):
    if target_root != home_root:
        raise RuntimeError('saved external target refused')
""")
    if redirect:
        with (home / "tools/mir_executor/local.py").open("a") as file:
            file.write(f"""
from pathlib import Path
def pre_execute(args, root):
    args.repo_root = Path({str(target)!r})
""")
    _write_hook(target, "raise AssertionError('saved target hooks must not load')\n")
    brief = home / "brief.json"
    brief.write_text('{"expanded_goal": "task"}')
    registry = JobRegistry(home / "tasks/jobs.db")
    try:
        registry.insert(JobRecord(
            job_id="saved", change_id="change", category="unit", family=None,
            repo_root=str(home if redirect else target), codex_args=["task"],
            allow_harness_self_modify=False,
            timeout_seconds=600, status="failed", started_at="2026-10-01T00:00:00Z",
            dispatch_brief_path=str(brief),
        ))
    finally:
        registry.close()
    with pytest.raises(SystemExit) as exc:
        cli.main(["resume", "--repo-root", str(home), "--job-id", "saved"])
    assert exc.value.code == 1
    assert "authorize_target" in capsys.readouterr().err
    registry = JobRegistry(home / "tasks/jobs.db", read_only=True)
    try:
        assert registry.get("saved").status == "failed"
    finally:
        registry.close()


def test_should_authorize_parsed_target_before_writer_scope(repositories, monkeypatch, capsys):
    home, target = repositories
    _write_hook(home, """
from pathlib import Path
def authorize_target(home_root, target_root, args):
    if target_root != home_root:
        raise RuntimeError('parsed external target refused')
def register_execute_options(parser):
    parser.add_argument('--selected-root', dest='repo_root', type=Path)
""")
    _write_hook(target, "raise AssertionError('writer hook must not load before authorization')\n")
    monkeypatch.setattr(cli, "_handle_execute", lambda args: 0)
    with pytest.raises(SystemExit) as exc:
        cli.main([
            "execute", "--repo-root", str(home), "--selected-root", str(target),
        ])
    assert exc.value.code == 1
    assert "authorize_target" in capsys.readouterr().err
