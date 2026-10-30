"""Dual-runtime plugin packaging and single-provider regressions."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from mir.core.capabilities.manager import _validate_plugin
from scripts import verify_plugin_cli_activation as activation
from scripts.verify_codex_sync import PLUGIN_SKILLS, validate_plugin_skill_providers
from scripts.verify_plugin_cli_activation import _validate_installed_path

ROOT = Path(__file__).resolve().parents[1]


def _json(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def test_common_skills_have_one_namespaced_provider() -> None:
    providers: dict[str, str] = {}
    for plugin_name, expected_skills in PLUGIN_SKILLS.items():
        skills_root = ROOT / "plugins" / plugin_name / "skills"
        actual = {path.parent.name for path in skills_root.glob("*/SKILL.md")}
        assert actual == expected_skills
        for skill in actual:
            assert skill not in providers
            providers[skill] = plugin_name

    assert len(providers) == 23
    assert not (ROOT / ".claude" / "skills").exists()
    assert not (ROOT / ".agents" / "skills").exists()


def test_dual_runtime_manifests_share_one_skill_tree() -> None:
    for plugin_name in PLUGIN_SKILLS:
        plugin_root = ROOT / "plugins" / plugin_name
        claude = _json(plugin_root / ".claude-plugin" / "plugin.json")
        codex = _json(plugin_root / ".codex-plugin" / "plugin.json")
        assert claude["name"] == codex["name"] == plugin_name
        assert claude["version"] == codex["version"] == "0.13.53"
        assert codex["skills"] == "./skills/"
        assert isinstance(codex["interface"]["defaultPrompt"], list)
        assert 1 <= len(codex["interface"]["defaultPrompt"]) <= 3
        assert "interface" not in claude
        forbidden = ("mcpServers", "apps", "scripts", "agents", "commands")
        if plugin_name == "mir-lifecycle-hooks":
            assert "hooks" not in claude
            assert "hooks" not in codex
        else:
            forbidden = ("hooks", *forbidden)
        for field in forbidden:
            assert field not in claude
            assert field not in codex
        assert len(list(plugin_root.glob("skills/*/SKILL.md"))) == len(
            PLUGIN_SKILLS[plugin_name]
        )
        assert not any(path.is_symlink() for path in plugin_root.rglob("*"))


def test_lifecycle_hook_plugin_uses_one_exact_shared_hook_file() -> None:
    plugin_root = ROOT / "plugins" / "mir-lifecycle-hooks"
    claude = _json(plugin_root / ".claude-plugin" / "plugin.json")
    codex = _json(plugin_root / ".codex-plugin" / "plugin.json")
    hooks = _json(plugin_root / "hooks" / "hooks.json")

    assert claude["name"] == codex["name"] == "mir-lifecycle-hooks"
    assert "hooks" not in claude
    assert "hooks" not in codex
    assert codex["skills"] == "./skills/"
    assert hooks == {
        "hooks": {
            "SessionStart": [
                {
                    "hooks": [
                        {
                            "type": "command",
                            "command": (
                                'python3 "${CLAUDE_PLUGIN_ROOT}/hooks/'
                                "runtime_continuity.py\""
                            ),
                            "timeout": 2,
                        }
                    ]
                }
            ],
            "UserPromptSubmit": [
                {
                    "hooks": [
                        {
                            "type": "command",
                            "command": (
                                'python3 "${CLAUDE_PLUGIN_ROOT}/skills/runtime-continuity/'
                                'scripts/handoff_packet.py"'
                            ),
                            "timeout": 8,
                        }
                    ]
                }
            ],
            "PreToolUse": [
                {
                    "hooks": [
                        {
                            "type": "command",
                            "command": (
                                'python3 "${CLAUDE_PLUGIN_ROOT}/skills/runtime-continuity/'
                                'scripts/handoff_packet.py"'
                            ),
                            "timeout": 8,
                        }
                    ]
                }
            ],
            "Stop": [
                {
                    "hooks": [
                        {
                            "type": "command",
                            "command": (
                                'python3 "${CLAUDE_PLUGIN_ROOT}/skills/runtime-continuity/'
                                'scripts/handoff_packet.py"'
                            ),
                            "timeout": 8,
                        }
                    ]
                }
            ],
        }
    }
    handler = plugin_root / "hooks" / "runtime_continuity.py"
    assert handler.stat().st_mode & 0o111 == 0
    assert len(handler.read_bytes()) <= 1024
    assert _validate_plugin(plugin_root, "mir-lifecycle-hooks", package_kind="skills-hooks")
    completed = subprocess.run(
        ["python3", str(handler)], capture_output=True, text=True, check=True
    )
    assert completed.stderr == ""
    assert completed.stdout == (
        'Mir lifecycle continuity: preserve the active task intent and verify state before '
        'continuing. Default work method: 1 Method/intent -> 2 Design (+scenarios) -> 3 TDD '
        '-> 4 Eval -> 5 '
        'Develop -> 6 Repeat 3-5 until tests pass -> 7 Finish; done only when every request-'
        'matrix cell has evidence checked now, otherwise report N/M and open cells (details: '
        'runtime-continuity skill, references/default-work-method.md). Handoffs: qualified '
        'target; four status axes; full pins; evidence provenance+time; unknowns; owner may/may-'
        'not only. If commands allowed, paste `python3 scripts/mir_ontology.py mapping --handoff '
        '<source paths>` unchanged; else inventory unavailable pins. Recipients label each pin '
        'verified-in-repo or parent-supplied. Self-check each gap; scope the whole envelope. See '
        'ontology Handoff.\n'
    )
    assert len(completed.stdout.encode("utf-8")) < 800


def test_should_package_portable_default_work_method_in_order(tmp_path: Path) -> None:
    isolated = tmp_path / "mir-lifecycle-hooks"
    shutil.copytree(ROOT / "plugins" / "mir-lifecycle-hooks", isolated)
    skill = isolated / "skills" / "runtime-continuity"
    reference = skill / "references" / "default-work-method.md"

    assert reference.is_file()
    text = reference.read_text(encoding="utf-8")
    steps = re.findall(r"^\| ([1-7]) \| ([^|]+) \|", text, flags=re.MULTILINE)
    assert [(number, name.strip()) for number, name in steps] == [
        ("1", "Method and intent"),
        ("2", "Design"),
        ("3", "TDD"),
        ("4", "Eval"),
        ("5", "Develop"),
        ("6", "Repeat"),
        ("7", "Finish"),
    ]
    for prefix in ("Users", "Volumes"):
        assert f"/{prefix}/" not in text
    assert re.search(r"\bADR[- ]?\d+", text, flags=re.IGNORECASE) is None
    assert "(references/default-work-method.md)" in (skill / "SKILL.md").read_text()
    design = (ROOT / "plugins" / "mir-core" / "skills" / "design" / "SKILL.md").read_text()
    assert "mir-lifecycle-hooks:runtime-continuity" in design
    assert "references/default-work-method.md" in design


def test_marketplaces_publish_identical_plugin_names() -> None:
    claude = _json(ROOT / ".claude-plugin" / "marketplace.json")
    codex = _json(ROOT / ".agents" / "plugins" / "marketplace.json")
    expected = set(PLUGIN_SKILLS) | {"mir-mcp"}
    assert {item["name"] for item in claude["plugins"]} == expected
    assert {item["name"] for item in codex["plugins"]} == expected

    failures: list[str] = []
    validate_plugin_skill_providers(failures)
    assert failures == []


def test_repository_has_no_tracked_worktree_symlinks() -> None:
    completed = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=ROOT,
        capture_output=True,
        check=True,
    )
    tracked = [Path(raw.decode()) for raw in completed.stdout.split(b"\0") if raw]
    assert [path for path in tracked if (ROOT / path).is_symlink()] == []

    index = subprocess.run(
        ["git", "ls-files", "-s"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.splitlines()
    stale_symlink_entries = []
    for row in index:
        mode, _, _, relative = row.split(maxsplit=3)
        path = ROOT / relative
        if mode == "120000" and (path.is_symlink() or (path.exists() and not path.is_dir())):
            stale_symlink_entries.append(relative)
    assert stale_symlink_entries == []


def test_plugin_packages_are_self_contained_in_isolated_copy(tmp_path: Path) -> None:
    for plugin_name in PLUGIN_SKILLS:
        isolated = tmp_path / plugin_name
        shutil.copytree(ROOT / "plugins" / plugin_name, isolated)
        kind = "skills-hooks" if plugin_name == "mir-lifecycle-hooks" else "skills"
        assert _validate_plugin(isolated, plugin_name, package_kind=kind)
        text = "\n".join(path.read_text() for path in isolated.rglob("*.md"))
        assert "archive/skills/" not in text
        assert "memory_gc_runner.py" not in text


def test_bluebricks_relation_reference_survives_isolated_plugin_copy(tmp_path: Path) -> None:
    isolated = tmp_path / "mir-code"
    shutil.copytree(ROOT / "plugins" / "mir-code", isolated)

    reference = isolated / "skills" / "bluebricks" / "references" / "selective-relations.md"
    assert reference.is_file()
    assert _validate_plugin(isolated, "mir-code", package_kind="skills")


def test_activation_path_must_be_a_real_copy_inside_the_runtime_home(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Model the provider explicitly; repo-local pytest scratch is also supported.
    provider = tmp_path / "provider"
    monkeypatch.setattr("scripts.verify_plugin_cli_activation.ROOT", provider)
    runtime_home = tmp_path / "runtime-home"
    installed = runtime_home / "plugins" / "mir-core"
    installed.mkdir(parents=True)
    (installed / "plugin.json").write_text("{}\n", encoding="utf-8")

    assert _validate_installed_path(installed, runtime_home) == installed.resolve()

    outside = tmp_path / "provider-copy" / "mir-core"
    outside.mkdir(parents=True)
    with pytest.raises(RuntimeError, match="outside the isolated runtime home"):
        _validate_installed_path(outside, runtime_home)

    linked = runtime_home / "plugins" / "linked"
    linked.symlink_to(outside, target_is_directory=True)
    with pytest.raises(RuntimeError, match="symlinked installed path"):
        _validate_installed_path(linked, runtime_home)

    provider.mkdir()
    with pytest.raises(RuntimeError, match="resolves into the provider checkout"):
        _validate_installed_path(provider, tmp_path)


@pytest.mark.parametrize("scope", ["user", "project", "local", None])
def test_should_reject_non_user_claude_install_scope(tmp_path, monkeypatch, capsys, scope):
    provider = tmp_path / "provider"
    for relative in (".claude-plugin/marketplace.json", ".agents/plugins/marketplace.json"):
        path = provider / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{}")
    skill = provider / "plugins/mir-core/skills/ontology/SKILL.md"
    skill.parent.mkdir(parents=True)
    skill.write_text("Synthetic skill")
    monkeypatch.setattr(activation, "ROOT", provider)
    monkeypatch.setattr(activation, "PLUGIN_NAMES", ("mir-core",))
    monkeypatch.setattr(activation, "PLUGIN_SKILLS", {"mir-core": ("ontology",)})
    monkeypatch.setattr(activation.shutil, "which", lambda name: name)
    calls = []

    def synthetic_cli(argv, environment, cwd):
        calls.append((argv[0], cwd.name))
        if argv[1:4] == ["plugin", "list", "--json"]:
            runtime = argv[0]
            home = Path(environment["HOME" if runtime == "claude" else "CODEX_HOME"])
            installed = home / "plugins/mir-core"
            if not installed.exists():
                shutil.copytree(skill.parents[2], installed)
            entry = {"name": "mir-core", "enabled": True, "installPath": str(installed)}
            if runtime == "claude" and scope is not None:
                entry["scope"] = scope
            return json.dumps([entry])
        return ""

    monkeypatch.setattr(activation, "_run", synthetic_cli)
    if scope == "user":
        assert activation.main() == 0
        assert json.loads(capsys.readouterr().out)["consumer_count"] == 2
        assert [(runtime, cwd) for runtime, cwd in calls if runtime != "git"][-4:] == [
            ("claude", "consumer-a"),
            ("codex", "consumer-a"),
            ("claude", "consumer-b"),
            ("codex", "consumer-b"),
        ]
    else:
        with pytest.raises(RuntimeError, match="claude.*user scope.*mir-core"):
            activation.main()


def test_manifest_versions_match_repository_release() -> None:
    version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    assert version == "0.13.53"
    for plugin_name in PLUGIN_SKILLS:
        plugin_root = ROOT / "plugins" / plugin_name
        assert _json(plugin_root / ".claude-plugin" / "plugin.json")["version"] == version
        assert _json(plugin_root / ".codex-plugin" / "plugin.json")["version"] == version
    marketplace = _json(ROOT / ".claude-plugin" / "marketplace.json")
    assert all(entry["version"] == version for entry in marketplace["plugins"])


def test_runtime_marketplace_manifest_shapes_are_distinct() -> None:
    claude = _json(ROOT / ".claude-plugin" / "marketplace.json")
    codex = _json(ROOT / ".agents" / "plugins" / "marketplace.json")
    assert isinstance(claude["owner"], dict)
    assert all(isinstance(entry["source"], str) for entry in claude["plugins"])
    assert "interface" in codex
    assert all(entry["source"]["source"] == "local" for entry in codex["plugins"])
    assert all(
        set(entry["policy"]) == {"installation", "authentication"}
        for entry in codex["plugins"]
    )


def test_should_keep_h1_hook_print_only_and_permission_aware():
    import ast

    handler = ROOT / "plugins/mir-lifecycle-hooks/hooks/runtime_continuity.py"
    tree = ast.parse(handler.read_bytes())
    assert not any(
        isinstance(node, (ast.Import, ast.ImportFrom, ast.With)) for node in ast.walk(tree)
    )
    calls = [node for node in ast.walk(tree) if isinstance(node, ast.Call)]
    assert [node.func.id for node in calls] == ["print", "main"]
    assert "If commands allowed" in handler.read_text()
