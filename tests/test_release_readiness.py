from __future__ import annotations

import ast
import hashlib
import json
import os
import platform
import shutil
from pathlib import Path

import pytest

from scripts import verify_release_readiness as readiness

ROOT = Path(__file__).resolve().parents[1]
TARGET = "aarch64-apple-darwin"


@pytest.fixture
def consumer_candidate(tmp_path, monkeypatch):
    if os.name == "nt":
        pytest.skip("consumer contract probes run POSIX hooks on the Mac maintainer host")
    candidate = tmp_path / "candidate"
    assets = candidate / "assets"
    temp = tmp_path / "temp installs"
    assets.mkdir(parents=True)
    temp.mkdir()
    monkeypatch.setattr(readiness.tempfile, "tempdir", str(temp))
    monkeypatch.setattr(platform, "system", lambda: "Darwin")
    monkeypatch.setattr(platform, "machine", lambda: "arm64")
    monkeypatch.delenv("MIR_RELEASE_CONSUMER_CHECK", raising=False)
    monkeypatch.setattr(readiness, "ROOT", candidate)
    monkeypatch.setattr(readiness, "_verify_clean_tree", lambda root: None)
    monkeypatch.setattr(readiness, "CHECKS", ())

    lock_path = Path(".mir/capability-lock.json")
    cli_path = Path("config/cli-native-artifacts.json")
    lock = json.loads((ROOT / lock_path).read_text())
    cli = json.loads((ROOT / cli_path).read_text())
    for pin in lock["plugins"].values():
        shutil.copytree(ROOT / pin["path"], candidate / pin["path"])
    pins = {"mir": cli["targets"][TARGET]}
    pins.update(
        (name, artifact["targets"][TARGET])
        for name, artifact in lock["native_artifacts"].items()
    )
    for name, pin in pins.items():
        artifact = assets / pin["url"].rsplit("/", 1)[-1]
        probe = "--mir-warmup" if name in {"handoff-packet", "runtime-continuity"} else "--help"
        blob = f'#!/bin/sh\n[ "$1" = "{probe}" ]\n'.encode()
        artifact.write_bytes(blob)
        artifact.chmod(0o700)
        pin.update(sha256=hashlib.sha256(blob).hexdigest(), size=len(blob))
    for path, data in ((lock_path, lock), (cli_path, cli)):
        (candidate / path).parent.mkdir()
        (candidate / path).write_text(json.dumps(data))
    return candidate, assets, temp


@pytest.mark.parametrize(
    ("case", "diagnostic"),
    [
        ("old-hook", "consumer-hook:"),
        ("unquoted-hook", "consumer-hook:"),
        ("mode", "consumer-mode:"),
        ("digest", "consumer-digest:"),
        ("missing", "consumer-digest:"),
        ("contract", "consumer-contract:"),
        ("contract-mode", "consumer-contract:"),
        ("probe-exit", "consumer-hook:"),
    ],
)
def test_consumer_contract_blocks_bad_candidate(
    consumer_candidate, monkeypatch, capsys, case, diagnostic
) -> None:
    candidate, assets, temp = consumer_candidate
    hooks = candidate / "plugins/mir-lifecycle-hooks/hooks/hooks.json"
    binary = assets / f"mir-{TARGET}"
    if case == "old-hook":
        hooks.write_text(hooks.read_text().replace("/bin/runtime-continuity", "/hooks/old-hook"))
    elif case == "unquoted-hook":
        manifest = json.loads(hooks.read_text())
        hook = manifest["hooks"]["SessionStart"][0]["hooks"][0]
        word = '"${CLAUDE_PLUGIN_ROOT}/bin/runtime-continuity"'
        hook["command"] = hook["command"].replace(f"exec {word}", f"exec {word[1:-1]}")
        hooks.write_text(json.dumps(manifest))
    elif case == "mode":
        binary.chmod(0o644)
    elif case == "digest":
        binary.write_bytes(binary.read_bytes().replace(b"--help", b"--halt"))
    elif case == "missing":
        binary.unlink()
    elif case == "probe-exit":
        probe = assets / f"runtime-continuity-{TARGET}"
        probe.write_bytes(b"#!/bin/sh\nexit 42\n")
        lock_path = candidate / ".mir/capability-lock.json"
        lock = json.loads(lock_path.read_text())
        pin = lock["native_artifacts"]["runtime-continuity"]["targets"][TARGET]
        pin.update(sha256=hashlib.sha256(probe.read_bytes()).hexdigest(), size=probe.stat().st_size)
        lock_path.write_text(json.dumps(lock))
    else:
        runner = assets / "consumer runner"
        runner.write_text("#!/bin/sh\nexit 42\n")
        runner.chmod(0o700 if case == "contract" else 0o600)
        monkeypatch.setenv("MIR_RELEASE_CONSUMER_CHECK", str(runner))

    assert readiness.main(["--current-clean-tree"]) == 1
    output = capsys.readouterr()
    assert len(output.err.splitlines()) == 1
    assert output.err.startswith(diagnostic)
    if case in {"probe-exit", "contract"}:
        assert "exited 42" in output.err
    assert json.loads(output.out)["checks"][0]["name"] == "consumer-contract"
    assert list(temp.iterdir()) == []


def test_consumer_contract_passes_candidate_manifests(consumer_candidate, monkeypatch, capsys):
    candidate, assets, temp = consumer_candidate
    runner = assets / "consumer runner"
    runner.write_text(
        '#!/bin/sh\n'
        '[ "$#" -eq 1 ] && [ "$PWD" = "$1" ] && [ -d "$HOME" ] &&\n'
        '[ -z "${MIR_CAPABILITY_HOME+x}" ] &&\n'
        '[ -x "$1/bin/mir" ] &&\n'
        '[ -x "$1/plugins/mir-lifecycle-hooks/bin/handoff-packet" ] &&\n'
        '[ -x "$1/plugins/mir-mcp/bin/mir-mcp" ] &&\n'
        'touch "$1/consumer-check-ran"\n'
    )
    runner.chmod(0o700)
    monkeypatch.setenv("MIR_CAPABILITY_HOME", str(candidate / "real home"))
    monkeypatch.setenv("MIR_RELEASE_CONSUMER_CHECK", str(runner))

    assert readiness.main(["--current-clean-tree", "--native-artifacts-dir", str(assets)]) == 0
    output = capsys.readouterr()
    assert output.err == ""
    result = json.loads(output.out)
    assert result["ready"]
    assert result["checks"][0]["name"] == "consumer-contract"
    assert list(temp.iterdir()) == []
    assert not (candidate / "bin").exists()
    assert not (candidate / "real home").exists()


# @spec FR-007 IR-001
def test_should_include_every_required_gate_when_release_script_is_inspected() -> None:
    script = ROOT / "scripts/verify_release_readiness.py"
    tree = ast.parse(script.read_text(encoding="utf-8"))
    body = script.read_text(encoding="utf-8")

    assert tree is not None
    assert '"clone"' in body
    assert '"--no-hardlinks"' in body
    assert '"--extra"' in body
    assert '"dev"' in body
    assert '["git", "init"' not in body
    for token in (
        "test_project_agent_kit.py",
        "test_project_agent_kit_release_evidence.py",
        "test_minimal_starter.py",
        "test_public_template_identity.py",
        "test_template_asset_classification.py",
        "test_decision_authority.py",
        "test_plugin_skill_packages.py",
        "test_common_skill_contracts.py",
        "test_capability_security.py",
        "test_installed_cli.py",
        "tools/mir_executor/tests/test_policy.py",
        "verify_codex_sync.py",
        "verify_project_agent_kit_evidence.py",
        "test_no_korean_in_user_facing.py",
        "pytest",
        "ruff",
    ):
        assert token in body


def test_tag_workflow_publishes_release_after_repository_validation() -> None:
    workflow = (ROOT / ".github/workflows/release.yml").read_text(encoding="utf-8")

    assert "contents: write" in workflow
    assert "group: release-${{ github.ref }}" in workflow
    assert "cancel-in-progress: false" in workflow
    assert "verify_release_readiness.py --current-clean-tree --repository-only" in workflow
    assert "--require-project-agent-kit-evidence" not in workflow
    assert "git push" not in workflow
    assert workflow.index("verify_release_readiness.py") < workflow.index("gh release create")
    for token in (
        "gh release view",
        "gh release create",
        "--verify-tag",
        "--generate-notes",
        "startsWith(github.ref, 'refs/tags/v')",
    ):
        assert token in workflow
