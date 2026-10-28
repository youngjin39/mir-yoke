"""Consumer runner selects the active distribution without contacting host services."""

from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "plugins/mir-core/skills/ontology/scripts/mir_ontology_runner.py"

# The SessionStart hook stays the exact print-only H1 source (ADR-90); the handoff hook warns.
FLOOR_ENTRYPOINTS = (
    "plugins/mir-lifecycle-hooks/skills/runtime-continuity/scripts/handoff_packet.py",
    "plugins/mir-core/skills/ontology/scripts/mir_ontology_runner.py",
    "plugins/mir-core/skills/ontology/scripts/mk_query.py",
    "plugins/mir-core/skills/ontology/scripts/ontology_check.py",
    "plugins/mir-mcp/ontology/scripts/ontology_check.py",
)


@pytest.mark.parametrize("relative", FLOOR_ENTRYPOINTS)
@pytest.mark.parametrize("version", [(3, 9, 6), (3, 10, 0), (3, 11, 0), (3, 14, 6)])
def test_entrypoint_python_floor_warns_and_preserves_stdout(relative, version):
    path = ROOT / relative

    def run(injected):
        code = (
            "import runpy, sys; "
            f"sys.version_info = {injected!r}; "
            f"sys.argv = [{str(path)!r}, '--help']; "
            f"runpy.run_path({str(path)!r}, run_name='__main__')"
        )
        return subprocess.run(
            [sys.executable, "-c", code], input='{"hook_event_name": "PreToolUse"}',
            text=True, capture_output=True, check=False,
        )

    baseline = run((3, 11, 0))
    result = run(version)
    assert baseline.returncode == result.returncode == 0, result.stderr
    assert result.stdout == baseline.stdout
    assert baseline.stderr == ""
    expected = (
        "mir: Python 3.11+ is required; running on "
        + ".".join(map(str, version)) + " (upgrade python3)\n"
    ) if version < (3, 11) else ""
    assert result.stderr == expected


@pytest.mark.parametrize("relative", FLOOR_ENTRYPOINTS)
def test_import_does_not_emit_python_floor_warning(relative):
    code = (
        "import runpy, sys; sys.version_info = (3, 9, 6); "
        f"runpy.run_path({str(ROOT / relative)!r}, run_name='floor_import_test')"
    )
    result = subprocess.run([sys.executable, "-c", code], text=True, capture_output=True)
    assert result.returncode == 0, result.stderr
    assert result.stdout == result.stderr == ""


@pytest.fixture
def runner(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location("ontology_runner_under_test", RUNNER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    home = tmp_path / "home"
    account = tmp_path / "account"
    home.mkdir()
    account.mkdir()
    monkeypatch.setattr(module.Path, "home", lambda: home)
    monkeypatch.setattr(
        module, "pwd", SimpleNamespace(getpwuid=lambda uid: SimpleNamespace(pw_dir=str(account)))
    )
    monkeypatch.setattr(module.os, "getuid", lambda: 1000, raising=False)
    monkeypatch.delenv("MIR_ONTOLOGY_CHECKER", raising=False)
    return module, home, account


def distribution(home, runtime, version):
    scripts = (
        home / runtime / "plugins/cache/mir-yoke/mir-core" / version / "skills/ontology/scripts"
    )
    scripts.mkdir(parents=True)
    for name in ("ontology_check.py", "mk_query.py"):
        (scripts / name).write_text("pass\n")
    return scripts / "ontology_check.py"


def claude(home, checker, version):
    metadata = home / ".claude/plugins/installed_plugins.json"
    metadata.parent.mkdir(parents=True, exist_ok=True)
    metadata.write_text(
        json.dumps(
            {
                "plugins": {
                    "mir-core@mir-yoke": [
                        {
                            "installPath": str(checker.parents[3]),
                            "version": version,
                            "scope": "user",
                        }
                    ]
                }
            }
        )
    )


def codex(home, version=None, enabled=True):
    config = home / ".codex/config.toml"
    config.parent.mkdir(parents=True, exist_ok=True)
    config.write_text(
        '[plugins."mir-core@mir-yoke"]\n'
        f"enabled = {str(enabled).lower()}\n" + (f'version = "{version}"\n' if version else "")
    )


def test_import_without_pwd_uses_path_home(tmp_path, monkeypatch):
    monkeypatch.setitem(sys.modules, "pwd", None)
    spec = importlib.util.spec_from_file_location("ontology_runner_without_pwd", RUNNER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setattr(module.Path, "home", lambda: home)
    expected = distribution(home, ".codex", "0.13.0")

    assert module.pwd is None
    assert module.find_checker() == expected


def test_mk_query_imports_without_pwd(tmp_path, monkeypatch):
    monkeypatch.setitem(sys.modules, "pwd", None)
    spec = importlib.util.spec_from_file_location(
        "mk_query_without_pwd", RUNNER.with_name("mk_query.py")
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    home = tmp_path / "home"
    (home / ".mir").mkdir(parents=True)
    (home / ".mir/knowledge-supply.json").write_text("{}", encoding="utf-8")
    monkeypatch.delenv("MIR_KNOWLEDGE_SUPPLY_CONFIG", raising=False)
    monkeypatch.setattr(module.Path, "home", lambda: home)

    assert module.pwd is None
    assert module.config_path() == (home / ".mir/knowledge-supply.json").resolve()


def test_active_rollback_beats_newer_cache(runner):
    module, home, _ = runner
    active = distribution(home, ".claude", "0.11.0")
    distribution(home, ".codex", "0.12.0")
    claude(home, active, "0.11.0")
    assert module.find_checker() == active


def test_active_versions_disagree(runner, capsys):
    module, home, _ = runner
    checker = distribution(home, ".claude", "0.11.0")
    claude(home, checker, "0.11.0")
    distribution(home, ".codex", "0.12.0")
    codex(home, "0.12.0")
    with pytest.raises(OSError, match="runtime distributions disagree"):
        module.find_checker()


def test_active_missing_path_never_falls_back(runner, capsys):
    module, home, _ = runner
    missing = home / "removed/skills/ontology/scripts/ontology_check.py"
    claude(home, missing, "0.11.0")
    distribution(home, ".codex", "0.12.0")
    assert module.main(["--which"]) == 2
    assert "active" in capsys.readouterr().err.lower()


def test_active_codex_version(runner):
    module, home, _ = runner
    expected = distribution(home, ".codex", "0.11.0")
    distribution(home, ".codex", "0.12.0")
    codex(home, "0.11.0")
    assert module.find_checker() == expected


def test_real_codex_shape_enabled_without_version(runner, capsys):
    module, home, _ = runner
    expected = distribution(home, ".codex", "0.12.0")
    codex(home)
    assert module.main(["--which"]) == 0
    report = capsys.readouterr().out
    assert str(expected) in report and "active Codex" in report


def test_unversioned_codex_multiple_versions_is_ambiguous(runner, capsys):
    module, home, _ = runner
    distribution(home, ".codex", "0.11.0")
    distribution(home, ".codex", "0.12.0")
    codex(home)
    assert module.main(["--which"]) == 2
    assert "ambiguous" in capsys.readouterr().err.lower()


def test_disabled_codex_is_not_active(runner, capsys):
    module, home, _ = runner
    expected = distribution(home, ".codex", "0.12.0")
    codex(home, "0.11.0", enabled=False)
    assert module.find_checker() == expected
    assert "fallback" in capsys.readouterr().err.lower()


def test_fallback_newest_semver_across_homes_and_runtimes(runner, capsys):
    module, home, account = runner
    distribution(home, ".codex", "0.9.0")
    distribution(home, ".claude", "0.12.0-rc.1")
    expected = distribution(account, ".claude", "0.12.0")
    distribution(account, ".codex", "not-a-version")
    assert module.find_checker() == expected
    warning = capsys.readouterr().err
    assert "fallback" in warning.lower() and "0.12.0" in warning


def test_account_home_active_record_wins_over_home_cache(runner):
    module, home, account = runner
    distribution(home, ".codex", "0.13.0")
    expected = distribution(account, ".claude", "0.11.0")
    claude(account, expected, "0.11.0")
    assert module.find_checker() == expected


def test_matching_active_versions_prefer_path_home(runner, capsys):
    module, home, account = runner
    expected = distribution(home, ".codex", "0.12.0")
    codex(home, "0.12.0")
    other = distribution(account, ".claude", "0.12.0")
    claude(account, other, "0.12.0")
    assert module.main(["--which"]) == 0
    assert str(expected) in capsys.readouterr().out


def test_override_bypasses_active_records_and_requires_file(runner, monkeypatch, capsys):
    module, home, _ = runner
    checker = home / "explicit.py"
    checker.write_text("pass\n")
    monkeypatch.setenv("MIR_ONTOLOGY_CHECKER", str(checker))
    codex(home, "0.1.0")
    assert module.find_checker() == checker
    monkeypatch.setenv("MIR_ONTOLOGY_CHECKER", str(home))
    assert module.main(["--which"]) == 2
    assert "not a file" in capsys.readouterr().err


def test_no_distribution(runner, capsys):
    module, _, _ = runner
    assert module.main(["--which"]) == 2
    assert "missing" in capsys.readouterr().err.lower()


def test_which_reports_version_path_and_reason(runner, capsys):
    module, home, _ = runner
    checker = distribution(home, ".claude", "0.12.0")
    claude(home, checker, "0.12.0")
    assert module.main(["--which"]) == 0
    report = capsys.readouterr().out
    assert all(
        value in report for value in ("0.12.0", str(checker), "active", "version", "path", "reason")
    )


@pytest.mark.parametrize("command", ["mapping", "impact", "lookup"])
def test_checker_forwarding(runner, monkeypatch, command):
    module, home, _ = runner
    checker = distribution(home, ".claude", "0.12.0")
    claude(home, checker, "0.12.0")
    distribution(home, ".codex", "0.13.0")
    calls = []
    monkeypatch.setattr(
        module.subprocess,
        "run",
        lambda argv, **kw: calls.append(argv) or SimpleNamespace(returncode=7),
    )
    assert module.main([command, "some query", "--json"]) == 7
    assert calls == [
        [
            sys.executable,
            str(checker),
            command,
            "--repo",
            str(module.REPO_ROOT),
            "some query",
            "--json",
        ]
    ]


@pytest.mark.parametrize(
    "arguments, expected",
    [
        (
            ["query", "bounded question", "--soft", "--k", "3"],
            ["--soft", "query", "bounded question", "--k", "3"],
        ),
        (["query", "--soft"], ["query", "--soft"]),
        (["--soft", "query", "bounded question"], ["--soft", "query", "bounded question"]),
        (["feedback", "example:node", "used", "--soft"],
         ["--soft", "feedback", "example:node", "used"]),
    ],
)
def test_mk_forwarding(runner, monkeypatch, arguments, expected):
    module, home, _ = runner
    checker = distribution(home, ".claude", "0.12.0")
    claude(home, checker, "0.12.0")
    distribution(home, ".codex", "0.13.0")
    calls = []
    monkeypatch.setattr(
        module.subprocess,
        "run",
        lambda argv, **kw: calls.append(argv) or SimpleNamespace(returncode=0),
    )
    assert module.main(["mk", *arguments]) == 0
    assert calls == [
        [
            sys.executable,
            str(checker.with_name("mk_query.py")),
            "--repo",
            str(module.REPO_ROOT),
            *expected,
        ]
    ]


def test_consumer_copy_uses_own_repo_root(tmp_path, monkeypatch):
    repo = tmp_path / "consumer"
    scripts = repo / "scripts"
    scripts.mkdir(parents=True)
    copied = scripts / "mir_ontology.py"
    shutil.copyfile(RUNNER, copied)
    checker = tmp_path / "checker.py"
    checker.write_text("import json, sys\nprint(json.dumps(sys.argv[1:]))\n")
    monkeypatch.setenv("MIR_ONTOLOGY_CHECKER", str(checker))
    which = subprocess.run([sys.executable, str(copied), "--which"], capture_output=True, text=True)
    assert which.returncode == 0, which.stderr
    assert str(checker) in which.stdout and "override" in which.stdout
    result = subprocess.run(
        [sys.executable, str(copied), "mapping"], capture_output=True, text=True
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == ["mapping", "--repo", str(repo)]


def test_codex_active_missing_does_not_use_other_runtime_cache(runner):
    module, home, _ = runner
    codex(home, "0.11.0")
    distribution(home, ".claude", "0.12.0")
    with pytest.raises(OSError, match="active.*missing"):
        module.find_checker()


@pytest.mark.parametrize("metadata", ["{", '{"plugins":{"mir-core@mir-yoke":[{}]}}'])
def test_invalid_active_metadata_does_not_use_cache(runner, metadata):
    module, home, _ = runner
    checker = distribution(home, ".claude", "0.12.0")
    claude(home, checker, "0.12.0")
    (home / ".claude/plugins/installed_plugins.json").write_text(metadata)
    with pytest.raises(OSError, match="invalid active Claude"):
        module.find_checker()


def test_missing_mk_sibling_does_not_use_newer_distribution(runner, capsys):
    module, home, _ = runner
    checker = distribution(home, ".claude", "0.11.0")
    checker.with_name("mk_query.py").unlink()
    claude(home, checker, "0.11.0")
    distribution(home, ".codex", "0.12.0")
    assert module.main(["mk", "query", "question"]) == 2
    assert str(checker.with_name("mk_query.py")) in capsys.readouterr().err


@pytest.mark.parametrize("version", ["9.0.0-..", "9.0.0-01", "9.0.0+.."])
def test_invalid_semver_cache_is_ignored(runner, capsys, version):
    if sys.platform == "win32" and version.endswith("."):
        pytest.skip("Windows cannot create directory names ending in '.'")
    module, home, _ = runner
    expected = distribution(home, ".codex", "0.12.0")
    distribution(home, ".claude", version)
    assert module.find_checker() == expected
    assert "0.12.0" in capsys.readouterr().err


@pytest.mark.parametrize("runtime", [".claude", ".codex"])
@pytest.mark.parametrize("version", ["9.0.0-..", "9.0.0-01", "9.0.0+.."])
def test_invalid_active_semver_is_rejected(runner, runtime, version):
    if sys.platform == "win32" and version.endswith("."):
        pytest.skip("Windows cannot create directory names ending in '.'")
    module, home, _ = runner
    checker = distribution(home, runtime, version)
    if runtime == ".claude":
        claude(home, checker, version)
    else:
        codex(home, version)
    with pytest.raises(OSError, match="invalid active"):
        module.find_checker()


def test_should_forward_h1_handoff_json_argv_without_mk_lookup(tmp_path, monkeypatch):
    repo = tmp_path / "consumer with spaces"
    scripts = repo / "scripts"
    scripts.mkdir(parents=True)
    copied = scripts / "mir_ontology.py"
    copied.write_bytes(RUNNER.read_bytes())
    checker = tmp_path / "checker.py"
    checker.write_text("import json, sys\nprint(json.dumps(sys.argv[1:]))\n")
    monkeypatch.setenv("MIR_ONTOLOGY_CHECKER", str(checker))
    args = ["mapping", "--json", "--handoff", "source with spaces.md", "missing.md"]
    result = subprocess.run([sys.executable, str(copied), *args], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == ["mapping", "--repo", str(repo), *args[1:]]
    assert result.stderr == ""
    monkeypatch.setenv("MIR_ONTOLOGY_CHECKER", str(RUNNER.with_name("ontology_check.py")))
    result = subprocess.run([sys.executable, str(copied), *args], capture_output=True, text=True)
    assert result.returncode == 2  # Missing mapping remains an IO error through the runner.
    block = json.loads(result.stdout)["handoff"]
    assert all(item["availability"] == "unknown" for item in block["pin_inventory"]
               if item["pointer"].startswith("/sources/"))
    assert len(block["pin_inventory"]) == 12
