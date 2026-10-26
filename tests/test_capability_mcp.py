"""ADR-91 admission and lifecycle contracts, using only temporary providers/homes."""

from __future__ import annotations

import copy
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from mir.cli.capability import _parser
from mir.core.capabilities import (
    CapabilityConfigError,
    CapabilityError,
    CapabilityManager,
    load_capability_config,
)
from mir.core.capabilities.manager import _tree_digest, _validate_plugin
from tests.test_capability_cli import (
    ROOT,
    CopyGit,
    make_project,
    observed_hooks,
    observed_skills,
    runtime_runner,
)
from tests.test_mir_mcp_package import FILES

TOOLS = [
    "ontology_validate",
    "ontology_lookup",
    "ontology_impact",
    "handoff_pins",
    "relations_query",
]
METADATA = {
    "path": "plugins/mir-mcp",
    "package_kind": "mcp-stdio",
    "files": sorted(FILES),
    "server": "mir-mcp",
    "tools": TOOLS,
}


def schema5() -> dict:
    payload = json.loads((ROOT / "config/capability-sources.json").read_text())
    payload["schema_version"] = 5
    payload["plugins"]["mir-mcp"] = copy.deepcopy(METADATA)
    payload["plugin_component_policy"]["admitted_package_kinds"] = [
        "skills",
        "skills-hooks",
        "mcp-stdio",
    ]
    return payload


def write_config(tmp_path: Path, payload: dict) -> Path:
    path = tmp_path / "capability-sources.json"
    path.write_text(json.dumps(payload))
    return path


def test_schema5_exact_optional_inventory_without_fictitious_skills(tmp_path):
    config = load_capability_config(write_config(tmp_path, schema5()))
    assert config.plugin_kinds["mir-mcp"] == "mcp-stdio"
    assert config.plugin_mcp["mir-mcp"] == METADATA
    assert "mir-mcp" not in config.plugin_skills
    assert "mir-mcp" not in config.active_digest_acknowledgements
    assert all("mir-mcp" not in pack.plugins for pack in config.packs.values())


@pytest.mark.parametrize(
    "mutation",
    [
        "name",
        "path",
        "kind",
        "kind-type",
        "files",
        "server",
        "tools",
        "skills",
        "hooks",
        "policy",
        "ack-skills",
        "ack-unknown",
        "ack-malformed",
    ],
)
def test_schema5_rejects_noncanonical_mcp_metadata(tmp_path, mutation):
    payload = schema5()
    mcp = payload["plugins"]["mir-mcp"]
    if mutation == "name":
        payload["plugins"]["other"] = payload["plugins"].pop("mir-mcp")
    elif mutation == "path":
        mcp["path"] = "plugins/nested/mir-mcp"
    elif mutation == "kind":
        mcp["package_kind"] = "mcp"
    elif mutation == "kind-type":
        mcp["package_kind"] = []
    elif mutation == "files":
        mcp["files"] = mcp["files"][:-1]
    elif mutation == "server":
        mcp["server"] = "other"
    elif mutation == "tools":
        mcp["tools"] = TOOLS + ["hub_dispatch"]
    elif mutation in {"skills", "hooks"}:
        mcp[mutation] = ["fake"]
    elif mutation == "policy":
        payload["plugin_component_policy"]["reserved_active_package_kinds"] = []
    else:
        name = {"ack-skills": "mir-core", "ack-unknown": "unknown", "ack-malformed": "mir-mcp"}[
            mutation
        ]
        payload["active_package_digest_acknowledgements"][name] = (
            "invalid" if mutation == "ack-malformed" else "a" * 64
        )
    with pytest.raises(CapabilityConfigError):
        load_capability_config(write_config(tmp_path, payload))


@pytest.mark.parametrize("version", [1, 2, 3, 4])
def test_legacy_schemas_validate_but_never_admit_mcp(tmp_path, version):
    payload = schema5()
    payload["schema_version"] = version
    payload["plugins"].pop("mir-mcp")
    payload["plugin_component_policy"]["admitted_package_kinds"].remove("mcp-stdio")
    if version < 4:
        payload["plugins"].pop("mir-lifecycle-hooks")
        payload.pop("active_package_digest_acknowledgements")
        payload["agents"].pop("provider_local")
        payload["plugin_component_policy"]["admitted_package_kinds"] = ["skills"]
        payload["plugin_component_policy"]["reserved_active_package_kinds"] = ["hooks", "mcp"]
        for pack in payload["profiles"]["packs"].values():
            pack["plugins"].remove("mir-lifecycle-hooks")
    if version < 3:
        payload.pop("commands")
        payload.pop("project_integrations")
        for pack in payload["profiles"]["packs"].values():
            pack.pop("commands")
    if version == 1:
        payload.pop("plugin_component_policy")
        for metadata in payload["plugins"].values():
            metadata.pop("package_kind")
        payload["policy"]["activation_required_runtimes"] = ["codex-cli-desktop"]
    assert load_capability_config(write_config(tmp_path, payload)).source_schema_version == version
    payload["plugins"]["mir-mcp"] = METADATA
    with pytest.raises(CapabilityConfigError):
        load_capability_config(write_config(tmp_path, payload))


def test_production_validator_admits_isolated_mcp_package(tmp_path):
    package = tmp_path / "package with spaces"
    shutil.copytree(ROOT / "plugins/mir-mcp", package)
    assert _validate_plugin(package, "mir-mcp", package_kind="mcp-stdio") == _tree_digest(package)
    with pytest.raises(CapabilityError):
        _validate_plugin(package, "other", package_kind="mcp-stdio")


def test_cli_exposes_explicit_mcp_selection_and_receipt_input():
    assert _parser().parse_args(["sync", "--mcp"]).mcp is True
    assert _parser().parse_args(["sync", "--no-mcp"]).mcp is False
    assert _parser().parse_args(["sync"]).mcp is None
    parsed = _parser().parse_args(
        [
            "attest",
            "--runtime",
            "claude-code",
            "--mcp-evidence",
            "/tmp/receipt.json",
        ]
    )
    assert parsed.mcp_evidence == Path("/tmp/receipt.json")


@pytest.fixture
def provider(tmp_path):
    provider = tmp_path / "provider"
    CopyGit().export(
        "",
        "",
        "",
        [
            "config/capability-sources.json",
            ".claude-plugin/marketplace.json",
            ".agents/plugins/marketplace.json",
            "plugins",
            ".claude/agents",
            ".claude/commands",
        ],
        provider,
    )
    payload = schema5()
    (provider / "config/capability-sources.json").write_text(json.dumps(payload))
    # Apply the pending marketplace change only to the temporary provider.
    # The workspace's .agents directory is read-only in this sandbox.
    market = provider / ".agents/plugins/marketplace.json"
    data = json.loads(market.read_text())
    if not any(item["name"] == "mir-mcp" for item in data["plugins"]):
        data["plugins"].insert(
            0,
            {
                "name": "mir-mcp",
                "source": {"source": "local", "path": "./plugins/mir-mcp"},
                "policy": {"installation": "AVAILABLE", "authentication": "ON_INSTALL"},
                "category": "Developer Tools",
            },
        )
        market.write_text(json.dumps(data))
    return provider


def manager_for(tmp_path, provider, name="consumer", *, runner=None):
    project = make_project(tmp_path, name)
    shutil.copy2(
        provider / "config/capability-sources.json", project / "config/capability-sources.json"
    )
    home = tmp_path / "home"
    home.mkdir(exist_ok=True)
    codex = home / ".codex"
    codex.mkdir(exist_ok=True)
    capability_home = tmp_path / "capabilities"
    manager = CapabilityManager(
        project,
        capability_home=capability_home,
        user_home=home,
        codex_home=codex,
        git=CopyGit(provider),
        command_runner=runner
        or runtime_runner(
            capability_home / "active",
            codex,
        ),
        which=lambda name: name,
    )
    return manager


def acknowledge(provider):
    path = provider / "config/capability-sources.json"
    payload = json.loads(path.read_text())
    payload["active_package_digest_acknowledgements"]["mir-mcp"] = _tree_digest(
        provider / "plugins/mir-mcp",
    )
    path.write_text(json.dumps(payload))


def acknowledge_locally(manager, provider):
    path = manager.project_root / "config/capability-sources.json"
    payload = json.loads(path.read_text())
    payload["active_package_digest_acknowledgements"]["mir-mcp"] = _tree_digest(
        provider / "plugins/mir-mcp"
    )
    path.write_text(json.dumps(payload))
    manager.config = load_capability_config(path)


@pytest.mark.parametrize("local_ack", [False, True])
def test_remote_mcp_ack_cannot_replace_local_approval(tmp_path, provider, local_ack):
    manager = manager_for(tmp_path, provider)
    if local_ack:
        acknowledge_locally(manager, provider)
        manager.sync("code", mcp=True, apply=True)
    local_path = manager.project_root / "config/capability-sources.json"
    local_before = local_path.read_bytes()
    path = provider / "plugins/mir-mcp/mir_mcp.py"
    path.write_bytes(path.read_bytes() + b"\n")
    acknowledge(provider)
    manager.git.commit = "b" * 40
    calls = []
    original = manager.command_runner

    def record(args, **kwargs):
        calls.append(args)
        return original(args, **kwargs)

    manager.command_runner = record
    with pytest.raises(CapabilityError, match="acknowledgement"):
        manager.update("code", mcp=True, apply=True)
    assert calls == []
    assert local_path.read_bytes() == local_before
    acknowledge_locally(manager, provider)
    assert manager.update("code", mcp=True, apply=True)["registration_status"] == "restart-required"
    assert json.loads(manager.lock_path.read_text())["plugins"]["mir-mcp"]["sha256"] == (
        _tree_digest(provider / "plugins/mir-mcp")
    )


def test_remote_hook_ack_update_behavior_is_unchanged(tmp_path, provider):
    manager = manager_for(tmp_path, provider)
    manager.sync("code", apply=True)
    local_before = manager.config.active_digest_acknowledgements["mir-lifecycle-hooks"]
    hook = provider / "plugins/mir-lifecycle-hooks/.claude-plugin/plugin.json"
    hook.write_bytes(hook.read_bytes() + b"\n")
    path = provider / "config/capability-sources.json"
    payload = json.loads(path.read_text())
    digest = _tree_digest(provider / "plugins/mir-lifecycle-hooks")
    payload["active_package_digest_acknowledgements"]["mir-lifecycle-hooks"] = digest
    path.write_text(json.dumps(payload))
    manager.git.commit = "b" * 40
    assert manager.update("code", apply=True)["registration_status"] == "restart-required"
    assert digest != local_before
    assert manager.config.active_digest_acknowledgements["mir-lifecycle-hooks"] == digest


def test_consumer_only_mcp_ack_survives_activation_rollback(tmp_path, provider):
    manager = manager_for(tmp_path, provider)
    acknowledge_locally(manager, provider)
    assert "mir-mcp" not in load_capability_config(
        provider / "config/capability-sources.json"
    ).active_digest_acknowledgements
    manager.sync("code", mcp=True, apply=True)
    lock = manager.lock_path.read_bytes()
    receipt = manager.active_receipt_path.read_bytes()
    original = manager.command_runner
    failed = False

    def fail_once(args, **kwargs):
        nonlocal failed
        if args[1:3] == ["plugin", "add"] and not failed:
            failed = True
            return subprocess.CompletedProcess(args, 1, "", "fixture failure")
        return original(args, **kwargs)

    manager.command_runner = fail_once
    with pytest.raises(CapabilityError, match="rollback was complete"):
        manager.sync("code", mcp=True, apply=True)
    assert failed
    assert manager.lock_path.read_bytes() == lock
    assert manager.active_receipt_path.read_bytes() == receipt
    assert manager._activation_evidence(json.loads(lock), require_active_receipt=False)[
        "status"
    ] == "verified"


def test_missing_ack_blocks_only_explicit_mcp_registration(tmp_path, provider):
    calls = []
    manager = manager_for(tmp_path, provider, runner=lambda *a, **kw: calls.append(a))
    assert "mir-mcp" not in manager.check("code")["plugins"]
    with pytest.raises(CapabilityError, match="acknowledgement"):
        manager.sync("code", mcp=True, apply=True)
    assert calls == []
    assert not manager.lock_path.exists()


def provider_only_manager(tmp_path, provider, source, monkeypatch):
    """A consumer without its own config falls back to a provider-supplied config."""
    if source == "active":
        manager_for(tmp_path, provider, "seed").sync("code", apply=True)
    else:
        bundled = tmp_path / "bundled"
        (bundled / "resources").mkdir(parents=True)
        shutil.copy2(
            provider / "config/capability-sources.json",
            bundled / "resources/capability-sources.json",
        )
        monkeypatch.setattr("mir.core.capabilities.manager.files", lambda _package: bundled)
    manager = manager_for(tmp_path, provider)
    (manager.project_root / "config/capability-sources.json").unlink()
    manager = CapabilityManager(
        manager.project_root,
        capability_home=manager.capability_home,
        user_home=manager.user_home,
        codex_home=manager.codex_home,
        git=manager.git,
        command_runner=manager.command_runner,
        which=manager.which,
    )
    assert manager.provider_only
    return manager


@pytest.mark.parametrize("source", ["active", "bundled"])
def test_provider_mcp_ack_never_admits_first_sync(tmp_path, provider, source, monkeypatch):
    acknowledge(provider)
    manager = provider_only_manager(tmp_path, provider, source, monkeypatch)
    calls = []
    original = manager.command_runner

    def record(args, **kwargs):
        calls.append(args)
        return original(args, **kwargs)

    manager.command_runner = record
    assert "mir-mcp" in load_capability_config(
        manager.config_path
    ).active_digest_acknowledgements
    # Finalization and READY read this same in-memory approval set.
    assert "mir-mcp" not in manager.config.active_digest_acknowledgements
    receipt_before = (
        manager.active_receipt_path.read_bytes() if manager.active_receipt_path.exists() else None
    )
    with pytest.raises(
        CapabilityError,
        match=r"active_package_digest_acknowledgements\.mir-mcp.*config/capability-sources\.json",
    ):
        manager.sync("code", mcp=True, apply=True)
    with pytest.raises(CapabilityError, match=r"acknowledgements\.mir-mcp"):
        manager.update("code", mcp=True, apply=True)
    assert calls == []
    assert not manager.lock_path.exists()
    assert (
        manager.active_receipt_path.read_bytes() if manager.active_receipt_path.exists() else None
    ) == receipt_before


@pytest.mark.parametrize("source", ["active", "bundled"])
def test_provider_hook_ack_still_admits_provider_only_sync(tmp_path, provider, source, monkeypatch):
    manager = provider_only_manager(tmp_path, provider, source, monkeypatch)
    assert "mir-lifecycle-hooks" in manager.config.active_digest_acknowledgements
    result = manager.sync("code", apply=True)
    assert result["registration_status"] == "restart-required"
    assert "mir-lifecycle-hooks" in json.loads(manager.lock_path.read_text())["plugins"]


@pytest.mark.parametrize("owner", ["local", "explicit"])
def test_consumer_owned_mcp_ack_admits_first_sync(tmp_path, provider, owner):
    manager = manager_for(tmp_path, provider)
    acknowledge_locally(manager, provider)
    if owner == "explicit":
        local = manager.project_root / "config/capability-sources.json"
        explicit = tmp_path / "reviewed" / "capability-sources.json"
        explicit.parent.mkdir()
        local.rename(explicit)
        manager = CapabilityManager(
            manager.project_root,
            config_path=explicit,
            capability_home=manager.capability_home,
            user_home=manager.user_home,
            codex_home=manager.codex_home,
            git=manager.git,
            command_runner=manager.command_runner,
            which=manager.which,
        )
    assert not manager.provider_only
    assert "mir-mcp" not in load_capability_config(
        provider / "config/capability-sources.json"
    ).active_digest_acknowledgements
    assert manager.sync("code", mcp=True, apply=True)["registration_status"] == "restart-required"
    assert json.loads(manager.lock_path.read_text())["plugins"]["mir-mcp"]["sha256"] == (
        _tree_digest(provider / "plugins/mir-mcp")
    )


def test_unselected_package_is_validated_before_registration(tmp_path, provider):
    (provider / "plugins/mir-mcp/undeclared").write_text("extra")
    calls = []
    manager = manager_for(tmp_path, provider, runner=lambda *a, **kw: calls.append(a))
    with pytest.raises(CapabilityError):
        manager.sync("code", apply=True)
    assert calls == []


def test_provider_cannot_claim_ready_from_installation_only(tmp_path, provider):
    acknowledge(provider)
    manager = manager_for(tmp_path, provider)
    manager.sync("code", mcp=True, apply=True)
    assert manager.status()["provider_ready"] is False


def test_changed_provider_byte_blocks_registration_before_any_command(tmp_path, provider):
    acknowledge(provider)
    path = provider / "plugins/mir-mcp/mir_mcp.py"
    path.write_bytes(path.read_bytes() + b"\n")
    calls = []
    manager = manager_for(tmp_path, provider, runner=lambda *args, **kwargs: calls.append(args))
    with pytest.raises(CapabilityError, match="acknowledgement is stale"):
        manager.sync("code", mcp=True, apply=True)
    assert calls == []


@pytest.mark.parametrize(
    "mutation", ["ack", "materialized", "contract", "schema", "receipt-ack", "receipt-missing-ack"],
)
def test_rollback_refuses_stale_or_downgraded_mcp_inventory(tmp_path, provider, mutation):
    acknowledge(provider)
    manager = manager_for(tmp_path, provider)
    manager.sync("code", mcp=True, apply=True)
    receipt = json.loads(manager.active_receipt_path.read_text())
    if mutation == "ack":
        object.__setattr__(manager.config, "active_digest_acknowledgements", {
            **manager.config.active_digest_acknowledgements, "mir-mcp": "0" * 64,
        })
    elif mutation == "materialized":
        receipt["materialized_plugins"].pop("mir-mcp")
    elif mutation == "contract":
        receipt.pop("mcp_packages")
    elif mutation == "schema":
        receipt["schema_version"] = 1
    elif mutation == "receipt-ack":
        receipt["mcp_digest_acknowledgements"] = {"mir-mcp": "0" * 64}
    else:
        receipt.pop("mcp_digest_acknowledgements", None)
    calls = []
    original = manager.command_runner

    def record(args, **kwargs):
        calls.append(args)
        return original(args, **kwargs)

    manager.command_runner = record
    assert manager._rollback_runtime_registration(("mir-mcp",), receipt) is False
    assert calls == []


def test_explicit_selection_is_locked_separately_from_active_union(tmp_path, provider):
    acknowledge(provider)
    first = manager_for(tmp_path, provider, "first")
    first.sync("code", mcp=True, apply=True)
    selection = json.loads(first.lock_path.read_text())["plugins"]["mir-mcp"]["mcp"]
    assert selection["runtimes"] == ["claude-code", "codex-cli-desktop"]
    assert selection["launchers"] == {
        "claude": {"command": "python3",
                   "args": ["-I", "-B", "-u", "${CLAUDE_PLUGIN_ROOT}/mir_mcp.py"]},
        "codex": {"command": "python3", "args": ["-I", "-B", "-u", "./mir_mcp.py"], "cwd": "."},
    }
    second = manager_for(tmp_path, provider, "second", runner=first.command_runner)
    second.sync("content", apply=True)
    second_lock = json.loads(second.lock_path.read_text())
    receipt = json.loads(first.active_receipt_path.read_text())
    assert "mir-mcp" not in second_lock["plugins"]
    assert "mir-mcp" in receipt["plugins"]
    first.sync("code", apply=True)  # retain the explicit choice across sync
    assert "mir-mcp" in json.loads(first.lock_path.read_text())["plugins"]
    assert first.status()["managed_surfaces"]["mcp"]["plugins"]["mir-mcp"]["tools"] == TOOLS
    second.sync("code", mcp=True, apply=True)
    first.sync("code", mcp=False, apply=True)
    assert "mir-mcp" in json.loads(first.active_receipt_path.read_text())["plugins"]
    second.sync("code", mcp=False, apply=True)
    assert "mir-mcp" not in json.loads(first.active_receipt_path.read_text())["plugins"]


@pytest.mark.parametrize("surface", ["provider", "installed", "acknowledgement"])
def test_drift_blocks_finalization_and_ready(tmp_path, provider, surface):
    acknowledge(provider)
    manager = manager_for(tmp_path, provider)
    manager.sync("code", mcp=True, apply=True)
    if surface == "installed":
        path = next((tmp_path / "home/.codex/plugins/cache/mir-yoke/mir-mcp").glob("*/mir_mcp.py"))
    elif surface == "acknowledgement":
        manager.config = copy.copy(manager.config)
        object.__setattr__(
            manager.config,
            "active_digest_acknowledgements",
            {
                **manager.config.active_digest_acknowledgements,
                "mir-mcp": "0" * 64,
            },
        )
        path = None
    else:
        path = manager.active_path / "plugins/mir-mcp/mir_mcp.py"
    if path is not None:
        path.write_bytes(path.read_bytes() + b"\n")
    status = manager.status()
    assert status["ready"] is False
    with pytest.raises(CapabilityError):
        manager.finalize(apply=True, after_restart=True)


@pytest.mark.parametrize("prior_mcp", [False, True])
def test_failed_install_rolls_back_prior_selection(tmp_path, provider, prior_mcp):
    acknowledge(provider)
    manager = manager_for(tmp_path, provider)
    manager.sync("code", mcp=prior_mcp, apply=True)
    lock = manager.lock_path.read_bytes()
    receipt = manager.active_receipt_path.read_bytes()
    original = manager.command_runner
    failed = False

    def fail_once(args, **kwargs):
        nonlocal failed
        if args[1:3] == ["plugin", "add"] and not failed:
            failed = True
            return subprocess.CompletedProcess(args, 1, "", "fixture failure")
        return original(args, **kwargs)

    manager.command_runner = fail_once
    with pytest.raises(CapabilityError, match="rollback was complete"):
        manager.sync("code", mcp=not prior_mcp, apply=True)
    assert manager.lock_path.read_bytes() == lock
    assert manager.active_receipt_path.read_bytes() == receipt
    assert manager._activation_evidence(json.loads(lock), require_active_receipt=False)[
        "status"
    ] == ("verified")


def mcp_evidence(manager, runtime, session):
    digest = json.loads(manager.lock_path.read_text())["plugins"]["mir-mcp"]["sha256"]
    probe = manager._activation_evidence(
        json.loads(manager.lock_path.read_text()), require_active_receipt=False
    )
    installed = probe["runtimes"][runtime]["plugins"]["mir-mcp"]["installed_path"]
    return {
        "mir-mcp": {
            "installed_sha256": digest,
            "client": runtime,
            "client_version": "fixture-1",
            "session_id": session,
            "session_cwd": str(manager.project_root),
            "platform": "macos",
            "interpreter": {"executable": "/usr/bin/python3", "version": "3.12.13"},
            "server": "mir-mcp",
            "protocol_version": "2026-07-28",
            "launcher": (
                {"command": "python3", "args": ["-I", "-B", "-u", f"{installed}/mir_mcp.py"],
                 "env": {}}
                if runtime == "claude-code"
                else {"command": "python3", "args": ["-I", "-B", "-u", "./mir_mcp.py"],
                      "cwd": installed, "env": {}}
            ),
            "tools": [{"name": name, "raw_name": f"mcp__mir-mcp__{name}"} for name in TOOLS],
            "safe_calls": {
                name: {
                    "arguments": {
                        "target_root": str(manager.project_root),
                        **{
                            "ontology_validate": {},
                            "ontology_lookup": {"query": "capability"},
                            "ontology_impact": {"paths": ["CLAUDE.md"]},
                            "handoff_pins": {"paths": ["CLAUDE.md"]},
                            "relations_query": {"anchor": "MOD-1", "purpose": "verification"},
                        }[name],
                    },
                    "result_sha256": "a" * 64,
                    "is_error": False,
                    "ok": True,
                }
                for name in TOOLS
            },
            "tools_list": {
                "sha256": "b" * 64,
                "bytes": 8000,
                "tokens": 3000,
                "tokenizer": "fixture-counter",
                "initial_tokens": 3000,
                "after_call_tokens": 3200,
                "deferred_loading": "eager",
            },
        }
    }


@pytest.mark.parametrize(
    "mutation",
    [
        "none",
        "digest",
        "client",
        "version",
        "session",
        "cwd",
        "windows",
        "python",
        "launcher",
        "launcher-cwd",
        "launcher-missing-cwd",
        "launcher-claude-form",
        "launcher-relative-cwd",
        "era",
        "tools",
        "raw-name",
        "safe-call",
        "call-error",
        "call-root",
        "budget",
        "counter",
        "extra-package",
    ],
)
def test_mcp_attestation_rejects_incomplete_or_wrong_evidence(
    tmp_path, provider, monkeypatch, mutation
):
    acknowledge(provider)
    manager = manager_for(tmp_path, provider)
    manager.sync("code", mcp=True, apply=True)
    session = "fresh-session"
    monkeypatch.setenv("CODEX_THREAD_ID", session)
    evidence = mcp_evidence(manager, "codex-cli-desktop", session)
    item = evidence["mir-mcp"]
    if mutation == "none":
        evidence = {}
    elif mutation == "digest":
        item["installed_sha256"] = "0" * 64
    elif mutation == "client":
        item["client"] = "claude-code"
    elif mutation == "version":
        item["client_version"] = ""
    elif mutation == "session":
        item["session_id"] = "old-session"
    elif mutation == "cwd":
        item["session_cwd"] = str(manager.active_path)
    elif mutation == "windows":
        item["platform"] = "windows"
    elif mutation == "python":
        item["interpreter"]["version"] = "3.8.20"
    elif mutation == "launcher":
        item["launcher"]["args"].remove("-I")
    elif mutation == "launcher-cwd":
        item["launcher"]["cwd"] = str(manager.project_root)
    elif mutation == "launcher-missing-cwd":
        item["launcher"].pop("cwd")
    elif mutation == "launcher-claude-form":
        item["launcher"] = mcp_evidence(manager, "claude-code", session)["mir-mcp"]["launcher"]
    elif mutation == "launcher-relative-cwd":
        item["launcher"]["cwd"] = "."
    elif mutation == "era":
        item["protocol_version"] = "2024-01-01"
    elif mutation == "tools":
        item["tools"].append({"name": "hub_dispatch", "raw_name": "hub_dispatch"})
    elif mutation == "raw-name":
        item["tools"][0]["raw_name"] = ""
    elif mutation == "safe-call":
        item["safe_calls"].pop(TOOLS[-1])
    elif mutation == "call-error":
        item["safe_calls"][TOOLS[0]]["is_error"] = True
    elif mutation == "call-root":
        item["safe_calls"][TOOLS[0]]["arguments"]["target_root"] = "."
    elif mutation == "budget":
        item["tools_list"]["tokens"] = 6001
    elif mutation == "counter":
        item["tools_list"]["tokenizer"] = ""
    else:
        evidence["other"] = copy.deepcopy(item)
    with pytest.raises(CapabilityError, match="MCP"):
        manager.attest(
            "codex-cli-desktop",
            observed_skills(manager),
            observed_hooks(manager),
            observed_mcp=evidence,
            apply=True,
        )


def test_claude_attestation_rejects_codex_launcher_form(tmp_path, provider, monkeypatch):
    acknowledge(provider)
    manager = manager_for(tmp_path, provider)
    manager.sync("code", mcp=True, apply=True)
    monkeypatch.setenv("CLAUDE_SESSION_ID", "fresh-claude")
    evidence = mcp_evidence(manager, "claude-code", "fresh-claude")
    launcher = evidence["mir-mcp"]["launcher"]
    launcher["cwd"] = str(Path(launcher["args"][-1]).parent)
    launcher["args"][-1] = "./mir_mcp.py"
    with pytest.raises(CapabilityError, match="MCP"):
        manager.attest("claude-code", observed_skills(manager), observed_hooks(manager),
                       observed_mcp=evidence, apply=True)


@pytest.mark.parametrize(
    "tool,patch,remove",
    [
        ("ontology_validate", {"scope": "invalid"}, None),
        ("ontology_lookup", {}, "query"),
        ("ontology_impact", {}, "paths"),
        ("handoff_pins", {}, "paths"),
        ("relations_query", {}, "anchor"),
        ("relations_query", {}, "purpose"),
        ("ontology_validate", {"extra": True}, None),
        ("ontology_lookup", {"query": 3}, None),
        ("ontology_lookup", {"query": ""}, None),
        ("ontology_lookup", {"query": "q" * 257}, None),
        ("ontology_lookup", {"query": "\uac00" * 86}, None),
        ("ontology_lookup", {"limit": True}, None),
        ("ontology_lookup", {"limit": 3.0}, None),
        ("ontology_lookup", {"limit": 0}, None),
        ("ontology_lookup", {"limit": 17}, None),
        ("ontology_impact", {"paths": []}, None),
        ("handoff_pins", {"paths": ["CLAUDE.md"] * 17}, None),
        ("relations_query", {"depth": 5}, None),
    ],
)
def test_schema_invalid_call_receipt_cannot_reach_ready(
    tmp_path, provider, monkeypatch, tool, patch, remove,
):
    acknowledge(provider)
    manager = manager_for(tmp_path, provider)
    manager.sync("code", mcp=True, apply=True)
    for runtime, env in (
        ("codex-cli-desktop", "CODEX_THREAD_ID"), ("claude-code", "CLAUDE_SESSION_ID"),
    ):
        session = f"fresh-{runtime}"
        monkeypatch.setenv(env, session)
        evidence = mcp_evidence(manager, runtime, session)
        arguments = evidence["mir-mcp"]["safe_calls"][tool]["arguments"]
        arguments.update(patch)
        if remove:
            arguments.pop(remove)
        with pytest.raises(CapabilityError, match="MCP"):
            manager.attest(runtime, observed_skills(manager), observed_hooks(manager),
                           observed_mcp=evidence, apply=True)
    assert manager.finalize()["ready_to_finalize"] is False
    assert manager.status()["ready"] is False


def test_call_receipt_requires_explicit_success_on_revalidation(tmp_path, provider, monkeypatch):
    acknowledge(provider)
    manager = manager_for(tmp_path, provider)
    manager.sync("code", mcp=True, apply=True)
    for runtime, env in (
        ("codex-cli-desktop", "CODEX_THREAD_ID"), ("claude-code", "CLAUDE_SESSION_ID"),
    ):
        session = f"fresh-{runtime}"
        monkeypatch.setenv(env, session)
        manager.attest(runtime, observed_skills(manager), observed_hooks(manager),
                       observed_mcp=mcp_evidence(manager, runtime, session), apply=True)
    manager.finalize(apply=True, after_restart=True)
    assert manager.status()["ready"] is True
    original = json.loads(manager.active_receipt_path.read_text())
    for mutation in ("missing-ok", "false-ok", "is-error", "isError", "invalid-arguments"):
        receipt = copy.deepcopy(original)
        call = receipt["discovery"][str(manager.project_root)]["claude-code"]["observed_mcp"][
            "mir-mcp"
        ]["safe_calls"]["ontology_lookup"]
        if mutation == "missing-ok":
            call.pop("ok", None)
        elif mutation == "false-ok":
            call["ok"] = False
        elif mutation == "is-error":
            call["is_error"] = True
        elif mutation == "isError":
            call["isError"] = True
        else:
            call["arguments"].pop("query")
        manager.active_receipt_path.write_text(json.dumps(receipt))
        assert manager.status()["ready"] is False, mutation
        assert manager.finalize()["ready_to_finalize"] is False, mutation
        with pytest.raises(CapabilityError):
            manager.finalize(apply=True, after_restart=True)


@pytest.mark.parametrize("mutation", ["downgrade", "parity"])
def test_mcp_finalization_requires_both_receipts_and_rechecks_them(
    tmp_path, provider, monkeypatch, mutation,
):
    acknowledge(provider)
    manager = manager_for(tmp_path, provider)
    manager.sync("code", mcp=True, apply=True)
    for runtime, env in (
        ("codex-cli-desktop", "CODEX_THREAD_ID"),
        ("claude-code", "CLAUDE_SESSION_ID"),
    ):
        monkeypatch.setenv(env, f"fresh-{runtime}")
        manager.attest(
            runtime,
            observed_skills(manager),
            observed_hooks(manager),
            observed_mcp=mcp_evidence(manager, runtime, f"fresh-{runtime}"),
            apply=True,
        )
        if runtime == "codex-cli-desktop":
            assert manager.finalize()["ready_to_finalize"] is False
    assert manager.finalize()["ready_to_finalize"] is True
    manager.finalize(apply=True, after_restart=True)
    assert manager.status()["ready"] is True
    receipt = json.loads(manager.active_receipt_path.read_text())
    claude = receipt["discovery"][str(manager.project_root)]["claude-code"]
    if mutation == "downgrade":
        claude.pop("observed_mcp")
    else:
        claude["observed_mcp"]["mir-mcp"]["tools_list"]["sha256"] = "c" * 64
    manager.active_receipt_path.write_text(json.dumps(receipt))
    assert manager.status()["ready"] is False
    with pytest.raises(CapabilityError):
        manager.finalize(apply=True, after_restart=True)
