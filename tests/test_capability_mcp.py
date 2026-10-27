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
from mir.core.capabilities.config import load_consumer_acknowledgements
from mir.core.capabilities.manager import _tree_digest, _validate_plugin
from tests.test_capability_cli import (
    ACKNOWLEDGEMENTS,
    ROOT,
    CopyGit,
    make_project,
    observed_hooks,
    observed_skills,
    runtime_runner,
    write_acknowledgements,
)
from tests.test_mir_mcp_package import FILES
from tools.template_assets import _candidate_files

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
    # The checkout's own mir-mcp approval is consumer state, never the provider default.
    payload["active_package_digest_acknowledgements"].pop("mir-mcp", None)
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


def acknowledge_locally(manager, provider, name="mir-mcp"):
    path = write_acknowledgements(
        manager.project_root, {name: _tree_digest(provider / "plugins" / name)}
    )
    manager.config = manager._with_consumer_acknowledgements(
        manager.config, load_consumer_acknowledgements(path),
    )


@pytest.mark.parametrize("local_ack", [False, True])
def test_remote_mcp_ack_cannot_replace_local_approval(tmp_path, provider, local_ack):
    manager = manager_for(tmp_path, provider)
    if local_ack:
        acknowledge_locally(manager, provider)
        manager.sync("code", mcp=True, apply=True)
    local_path = manager.project_root / ACKNOWLEDGEMENTS
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
    local_before = local_path.read_bytes()
    assert manager.update("code", mcp=True, apply=True)["registration_status"] == "restart-required"
    assert json.loads(manager.lock_path.read_text())["plugins"]["mir-mcp"]["sha256"] == (
        _tree_digest(provider / "plugins/mir-mcp")
    )
    # A provider update never writes or renews the consumer's approval.
    assert local_path.read_bytes() == local_before


HOOKS = "mir-lifecycle-hooks"


def acknowledge_hooks(config_path, digest):
    payload = json.loads(config_path.read_text())
    payload["active_package_digest_acknowledgements"][HOOKS] = digest
    config_path.write_text(json.dumps(payload))


def test_remote_hook_ack_cannot_replace_local_approval(tmp_path, provider):
    manager = manager_for(tmp_path, provider)
    manager.sync("code", apply=True)
    local_path = manager.project_root / ACKNOWLEDGEMENTS
    local_before = local_path.read_bytes()
    lock_before = manager.lock_path.read_bytes()
    hook = provider / "plugins/mir-lifecycle-hooks/.claude-plugin/plugin.json"
    hook.write_bytes(hook.read_bytes() + b"\n")
    digest = _tree_digest(provider / "plugins/mir-lifecycle-hooks")
    acknowledge_hooks(provider / "config/capability-sources.json", digest)
    manager.git.commit = "b" * 40
    calls = []
    original = manager.command_runner

    def record(args, **kwargs):
        calls.append(args)
        return original(args, **kwargs)

    manager.command_runner = record
    with pytest.raises(
        CapabilityError,
        match=r"stale: mir-lifecycle-hooks.*"
        r"active_package_digest_acknowledgements\.mir-lifecycle-hooks.*"
        r"config/capability-acknowledgements\.local\.json",
    ):
        manager.update("code", apply=True)
    assert calls == []
    assert local_path.read_bytes() == local_before
    assert manager.lock_path.read_bytes() == lock_before
    acknowledge_locally(manager, provider, HOOKS)
    local_before = local_path.read_bytes()
    assert manager.update("code", apply=True)["registration_status"] == "restart-required"
    assert json.loads(manager.lock_path.read_text())["plugins"][HOOKS]["sha256"] == digest
    assert local_path.read_bytes() == local_before


def test_consumer_only_hook_ack_survives_activation_rollback(tmp_path, provider):
    manager = manager_for(tmp_path, provider)
    digest = _tree_digest(provider / "plugins/mir-lifecycle-hooks")
    # The provider's own grant is wrong; only the consumer-owned approval is exact.
    acknowledge_hooks(provider / "config/capability-sources.json", "0" * 64)
    manager.sync("code", apply=True)
    receipt_body = json.loads(manager.active_receipt_path.read_text())
    assert receipt_body["consumer_digest_acknowledgements"] == {HOOKS: digest}
    lock = manager.lock_path.read_bytes()
    receipt = manager.active_receipt_path.read_bytes()
    approval = (manager.project_root / ACKNOWLEDGEMENTS).read_bytes()
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
        manager.sync("code", apply=True)
    assert failed
    assert manager.lock_path.read_bytes() == lock
    assert manager.active_receipt_path.read_bytes() == receipt
    assert (manager.project_root / ACKNOWLEDGEMENTS).read_bytes() == approval
    assert manager._activation_evidence(json.loads(lock), require_active_receipt=False)[
        "status"
    ] == "verified"


@pytest.mark.parametrize("consumer_hook_ack", ["exact", "stale"])
def test_legacy_mcp_only_receipt_still_restores_without_provider_renewal(
    tmp_path, provider, consumer_hook_ack,
):
    digest = _tree_digest(provider / "plugins/mir-lifecycle-hooks")
    acknowledge_hooks(provider / "config/capability-sources.json", digest)
    manager = manager_for(tmp_path, provider)
    acknowledge_locally(manager, provider)
    manager.sync("code", mcp=True, apply=True)
    receipt = json.loads(manager.active_receipt_path.read_text())
    mcp_ack = {"mir-mcp": _tree_digest(provider / "plugins/mir-mcp")}
    assert receipt["consumer_digest_acknowledgements"] == {**mcp_ack, HOOKS: digest}
    receipt.pop("consumer_digest_acknowledgements")
    receipt["mcp_digest_acknowledgements"] = mcp_ack
    if consumer_hook_ack == "stale":
        # The provider's active config still grants the exact digest; it must not count.
        assert load_capability_config(
            manager.active_path / "config/capability-sources.json"
        ).declared_digest_acknowledgements[HOOKS] == digest
        object.__setattr__(manager.config, "active_digest_acknowledgements", {
            **manager.config.active_digest_acknowledgements, HOOKS: "0" * 64,
        })
    previous = manager._use_previous_config_for_rollback(receipt)
    assert previous is not None
    expected_hook = digest if consumer_hook_ack == "exact" else "0" * 64
    assert manager.config.active_digest_acknowledgements == {**mcp_ack, HOOKS: expected_hook}
    assert manager._rollback_runtime_registration(
        tuple(receipt["plugins"]), receipt,
    ) is (consumer_hook_ack == "exact")


def test_consumer_only_mcp_ack_survives_activation_rollback(tmp_path, provider):
    manager = manager_for(tmp_path, provider)
    acknowledge_locally(manager, provider)
    assert "mir-mcp" not in load_capability_config(
        provider / "config/capability-sources.json"
    ).declared_digest_acknowledgements
    manager.sync("code", mcp=True, apply=True)
    lock = manager.lock_path.read_bytes()
    receipt = manager.active_receipt_path.read_bytes()
    approval = (manager.project_root / ACKNOWLEDGEMENTS).read_bytes()
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
    assert (manager.project_root / ACKNOWLEDGEMENTS).read_bytes() == approval
    assert manager._activation_evidence(json.loads(lock), require_active_receipt=False)[
        "status"
    ] == "verified"


def test_missing_ack_blocks_only_explicit_mcp_registration(tmp_path, provider):
    calls = []
    manager = manager_for(tmp_path, provider, runner=lambda *a, **kw: calls.append(a))
    assert "mir-mcp" not in manager.check("code")["plugins"]
    with pytest.raises(
        CapabilityError, match=r"acknowledgement.*config/capability-acknowledgements\.local\.json"
    ):
        manager.sync("code", mcp=True, apply=True)
    assert calls == []
    assert not manager.lock_path.exists()


def provider_only_manager(tmp_path, provider, source, monkeypatch, *, approved=False):
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
    if not approved:
        (manager.project_root / ACKNOWLEDGEMENTS).unlink()
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
    ).declared_digest_acknowledgements
    # Finalization and READY read this same in-memory approval set.
    assert "mir-mcp" not in manager.config.active_digest_acknowledgements
    receipt_before = (
        manager.active_receipt_path.read_bytes() if manager.active_receipt_path.exists() else None
    )
    with pytest.raises(
        CapabilityError,
        match=r"active_package_digest_acknowledgements\.mir-mcp.*"
        r"config/capability-acknowledgements\.local\.json",
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
def test_provider_hook_ack_never_admits_provider_only_sync(tmp_path, provider, source, monkeypatch):
    acknowledge_hooks(
        provider / "config/capability-sources.json",
        _tree_digest(provider / "plugins/mir-lifecycle-hooks"),
    )
    manager = provider_only_manager(tmp_path, provider, source, monkeypatch)
    assert HOOKS in load_capability_config(manager.config_path).declared_digest_acknowledgements
    assert HOOKS not in manager.config.active_digest_acknowledgements
    calls = []
    original = manager.command_runner

    def record(args, **kwargs):
        calls.append(args)
        return original(args, **kwargs)

    manager.command_runner = record
    receipt_before = (
        manager.active_receipt_path.read_bytes() if manager.active_receipt_path.exists() else None
    )
    with pytest.raises(
        CapabilityError,
        match=r"acknowledgements\.mir-lifecycle-hooks.*"
        r"config/capability-acknowledgements\.local\.json",
    ):
        manager.sync("code", apply=True)
    assert calls == []
    assert not manager.lock_path.exists()
    assert (
        manager.active_receipt_path.read_bytes() if manager.active_receipt_path.exists() else None
    ) == receipt_before


@pytest.mark.parametrize("source", ["active", "bundled"])
def test_local_ack_admits_provider_only_sync(tmp_path, provider, source, monkeypatch):
    manager = provider_only_manager(tmp_path, provider, source, monkeypatch, approved=True)
    acknowledge_locally(manager, provider)
    assert manager.sync("code", mcp=True, apply=True)["registration_status"] == "restart-required"
    assert set(json.loads(manager.lock_path.read_text())["plugins"]) >= {HOOKS, "mir-mcp"}


@pytest.mark.parametrize("receipt_ack", ["recorded", "stale", "legacy"])
def test_provider_only_status_checks_recorded_consumer_ack(
    tmp_path, provider, receipt_ack, monkeypatch,
):
    acknowledge_hooks(
        provider / "config/capability-sources.json",
        _tree_digest(provider / "plugins/mir-lifecycle-hooks"),
    )
    manager = provider_only_manager(tmp_path, provider, "active", monkeypatch)
    receipt = json.loads(manager.active_receipt_path.read_text())
    if receipt_ack == "stale":
        receipt["consumer_digest_acknowledgements"][HOOKS] = "0" * 64
    elif receipt_ack == "legacy":
        receipt.pop("consumer_digest_acknowledgements")
    # The provider's configuration still grants the exact digest; it must not count.
    assert HOOKS in load_capability_config(manager.config_path).declared_digest_acknowledgements
    assert manager._provider_active_integrity(receipt) is (receipt_ack == "recorded")


def reopened(manager, config_path=None):
    """A fresh process for the same consumer rereads its host-local approval."""
    return CapabilityManager(
        manager.project_root,
        config_path=config_path,
        capability_home=manager.capability_home,
        user_home=manager.user_home,
        codex_home=manager.codex_home,
        git=manager.git,
        command_runner=manager.command_runner,
        which=manager.which,
    )


@pytest.mark.parametrize("plugin", [HOOKS, "mir-mcp"])
@pytest.mark.parametrize("owner", ["local", "explicit"])
def test_local_ack_file_admits_sync_update_and_revalidation(tmp_path, provider, owner, plugin):
    digest = _tree_digest(provider / "plugins" / plugin)
    manager = manager_for(tmp_path, provider)
    acknowledge_hooks(provider / "config/capability-sources.json", "0" * 64)
    acknowledge_locally(manager, provider, plugin)
    if owner == "explicit":
        local = manager.project_root / "config/capability-sources.json"
        explicit = tmp_path / "reviewed" / "capability-sources.json"
        explicit.parent.mkdir()
        local.rename(explicit)
        manager = reopened(manager, explicit)
    assert not manager.provider_only
    assert "mir-mcp" not in load_capability_config(
        provider / "config/capability-sources.json"
    ).declared_digest_acknowledgements
    assert manager.config.active_digest_acknowledgements[plugin] == digest
    mcp = plugin == "mir-mcp"
    assert manager.sync("code", mcp=mcp, apply=True)["registration_status"] == "restart-required"
    assert json.loads(manager.lock_path.read_text())["plugins"][plugin]["sha256"] == digest
    manager.git.commit = "b" * 40
    assert manager.update("code", mcp=mcp, apply=True)["registration_status"] == (
        "restart-required"
    )
    config_path = None if owner == "local" else manager.config_path
    assert reopened(manager, config_path).status()["active_integrity"] is True
    (manager.project_root / ACKNOWLEDGEMENTS).unlink()
    revoked = reopened(manager, config_path)
    assert revoked.status()["active_integrity"] is False
    with pytest.raises(CapabilityError):
        revoked.finalize(apply=True, after_restart=True)


@pytest.mark.parametrize("operation", ["sync", "update"])
@pytest.mark.parametrize("plugin", [HOOKS, "mir-mcp"])
def test_tracked_config_ack_never_admits_fresh_clone(tmp_path, provider, plugin, operation):
    """A clone's tracked capability-sources.json approval belongs to whoever committed it."""
    digest = _tree_digest(provider / "plugins" / plugin)
    calls = []
    manager = manager_for(tmp_path, provider, runner=lambda *a, **kw: calls.append(a))
    approval = manager.project_root / ACKNOWLEDGEMENTS
    if plugin == HOOKS:
        approval.unlink()
    tracked = manager.project_root / "config/capability-sources.json"
    payload = json.loads(tracked.read_text())
    payload["active_package_digest_acknowledgements"][plugin] = digest
    tracked.write_text(json.dumps(payload))
    clone = reopened(manager)
    assert plugin not in clone.config.active_digest_acknowledgements
    with pytest.raises(
        CapabilityError,
        match=rf"missing: {plugin}.*config/capability-acknowledgements\.local\.json.*"
        rf"move active_package_digest_acknowledgements\.{plugin} out of .*"
        r"capability-sources\.json",
    ):
        getattr(clone, operation)("code", mcp=plugin == "mir-mcp", apply=True)
    assert calls == []
    assert not clone.lock_path.exists()
    assert not approval.exists() or plugin not in json.loads(approval.read_text())[
        "active_package_digest_acknowledgements"
    ]


@pytest.mark.parametrize(
    "content",
    [
        "not json",
        "[]",
        "{}",
        '{"active_package_digest_acknowledgements": [], "extra": 1}',
        '{"active_package_digest_acknowledgements": []}',
        '{"active_package_digest_acknowledgements": {"mir-mcp": "invalid"}}',
        '{"active_package_digest_acknowledgements": {"Not A Plugin": "' + "a" * 64 + '"}}',
        "symlink",
    ],
)
def test_malformed_local_ack_file_fails_closed(tmp_path, provider, content):
    manager = manager_for(tmp_path, provider)
    path = manager.project_root / ACKNOWLEDGEMENTS
    path.unlink()
    if content == "symlink":
        target = tmp_path / "elsewhere.json"
        target.write_text(json.dumps({"active_package_digest_acknowledgements": {}}))
        path.symlink_to(target)
    else:
        path.write_text(content)
    with pytest.raises(
        CapabilityConfigError, match=r"config/capability-acknowledgements\.local\.json"
    ):
        reopened(manager)


def test_local_ack_file_is_ignored_and_never_payload_input(tmp_path):
    relative = str(ACKNOWLEDGEMENTS)
    ignored = subprocess.run(
        ["git", "check-ignore", "-q", "--no-index", relative], cwd=ROOT, check=False,
    )
    assert ignored.returncode == 0
    repo = tmp_path / "repo"
    (repo / "config").mkdir(parents=True)
    shutil.copy2(ROOT / ".gitignore", repo / ".gitignore")
    shutil.copy2(ROOT / "config/capability-sources.json", repo / "config/capability-sources.json")
    (repo / relative).write_text('{"active_package_digest_acknowledgements": {}}')
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    candidates = _candidate_files(repo)
    assert "config/capability-sources.json" in candidates
    assert relative not in candidates


def test_unselected_package_is_validated_before_registration(tmp_path, provider):
    (provider / "plugins/mir-mcp/undeclared").write_text("extra")
    calls = []
    manager = manager_for(tmp_path, provider, runner=lambda *a, **kw: calls.append(a))
    with pytest.raises(CapabilityError):
        manager.sync("code", apply=True)
    assert calls == []


def test_provider_cannot_claim_ready_from_installation_only(tmp_path, provider):
    manager = manager_for(tmp_path, provider)
    acknowledge_locally(manager, provider)
    manager.sync("code", mcp=True, apply=True)
    assert manager.status()["provider_ready"] is False


def test_changed_provider_byte_blocks_registration_before_any_command(tmp_path, provider):
    calls = []
    manager = manager_for(tmp_path, provider, runner=lambda *args, **kwargs: calls.append(args))
    acknowledge_locally(manager, provider)
    path = provider / "plugins/mir-mcp/mir_mcp.py"
    path.write_bytes(path.read_bytes() + b"\n")
    with pytest.raises(CapabilityError, match="acknowledgement is stale"):
        manager.sync("code", mcp=True, apply=True)
    assert calls == []


@pytest.mark.parametrize(
    "mutation",
    [
        "ack", "materialized", "contract", "schema", "receipt-ack", "legacy-receipt-ack",
        "receipt-missing-ack",
    ],
)
def test_rollback_refuses_stale_or_downgraded_mcp_inventory(tmp_path, provider, mutation):
    manager = manager_for(tmp_path, provider)
    acknowledge_locally(manager, provider)
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
        receipt["consumer_digest_acknowledgements"]["mir-mcp"] = "0" * 64
    elif mutation == "legacy-receipt-ack":
        receipt.pop("consumer_digest_acknowledgements", None)
        receipt["mcp_digest_acknowledgements"] = {"mir-mcp": "0" * 64}
    else:
        receipt.pop("consumer_digest_acknowledgements", None)
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
    first = manager_for(tmp_path, provider, "first")
    acknowledge_locally(first, provider)
    first.sync("code", mcp=True, apply=True)
    selection = json.loads(first.lock_path.read_text())["plugins"]["mir-mcp"]["mcp"]
    assert selection["runtimes"] == ["claude-code", "codex-cli-desktop"]
    assert selection["launchers"] == {
        "claude": {"command": "python3",
                   "args": ["-I", "-B", "-u", "${CLAUDE_PLUGIN_ROOT}/mir_mcp.py"]},
        "codex": {"command": "python3", "args": ["-I", "-B", "-u", "./mir_mcp.py"], "cwd": "."},
    }
    second = manager_for(tmp_path, provider, "second", runner=first.command_runner)
    acknowledge_locally(second, provider)
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
    manager = manager_for(tmp_path, provider)
    acknowledge_locally(manager, provider)
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
    manager = manager_for(tmp_path, provider)
    acknowledge_locally(manager, provider)
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
    manager = manager_for(tmp_path, provider)
    acknowledge_locally(manager, provider)
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
    manager = manager_for(tmp_path, provider)
    acknowledge_locally(manager, provider)
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
    manager = manager_for(tmp_path, provider)
    acknowledge_locally(manager, provider)
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
    manager = manager_for(tmp_path, provider)
    acknowledge_locally(manager, provider)
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
    manager = manager_for(tmp_path, provider)
    acknowledge_locally(manager, provider)
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


# The 0.13.33 Codex launcher, recorded in locks enrolled before 0.13.34.
OLD_CODEX_LAUNCHER = {"command": "python3", "args": ["-I", "-B", "-u", "${PLUGIN_ROOT}/mir_mcp.py"]}


def enrolled_with_old_contract(tmp_path, provider):
    manager = manager_for(tmp_path, provider)
    acknowledge_locally(manager, provider)
    manager.sync("code", mcp=True, apply=True)
    lock = json.loads(manager.lock_path.read_text())
    current = copy.deepcopy(lock["plugins"]["mir-mcp"])
    lock["plugins"]["mir-mcp"]["mcp"]["launchers"]["codex"] = copy.deepcopy(OLD_CODEX_LAUNCHER)
    manager.lock_path.write_text(json.dumps(lock))
    receipt = json.loads(manager.active_receipt_path.read_text())
    receipt["mcp_packages"]["mir-mcp"]["launchers"]["codex"] = copy.deepcopy(OLD_CODEX_LAUNCHER)
    manager.active_receipt_path.write_text(json.dumps(receipt))
    manager.git.commit = "b" * 40
    return manager, lock, current


def test_update_accepts_enrollment_with_older_wellformed_mcp_contract(tmp_path, provider):
    manager, _, current = enrolled_with_old_contract(tmp_path, provider)
    assert manager.update("code", mcp=True)["ready_to_apply"] is True
    result = manager.update("code", mcp=True, apply=True)
    assert result["registration_status"] == "restart-required"
    lock = json.loads(manager.lock_path.read_text())
    assert lock["source"]["commit"] == "b" * 40
    assert lock["plugins"]["mir-mcp"] == current


def _mutate_enrollment(lock, mutation):
    plugins = lock["plugins"]
    contract = plugins["mir-mcp"]["mcp"]
    if mutation in {"sha256", "path", "package_kind"}:
        plugins["mir-mcp"][mutation] = {
            "sha256": "0" * 64, "path": "plugins/other", "package_kind": "skills",
        }[mutation]
    elif mutation == "skill-sha256":
        plugins[next(name for name in plugins if name != "mir-mcp")]["sha256"] = "0" * 64
    elif mutation == "commit":
        lock["source"]["commit"] = "c" * 40
    elif mutation == "binding":
        lock["consumer_binding"] = "d" * 64
    elif mutation == "extra-plugin":
        plugins["extra"] = copy.deepcopy(plugins["mir-mcp"])
    elif mutation == "missing-plugin":
        plugins.pop(next(name for name in plugins if name != "mir-mcp"))
    elif mutation == "missing-mcp":
        plugins["mir-mcp"].pop("mcp")
    elif mutation == "extra-metadata-key":
        plugins["mir-mcp"]["extra"] = True
    elif mutation == "extra-mcp-key":
        contract["extra"] = True
    elif mutation == "missing-mcp-key":
        contract.pop("schema_source")
    elif mutation == "mcp-path":
        contract["path"] = "plugins/other"
    elif mutation == "mcp-files":
        contract["files"] = "mir_mcp.py"
    elif mutation == "mcp-schema-source":
        contract["schema_source"] = "missing.py"
    elif mutation == "mcp-runtimes":
        contract["runtimes"] = ["unknown-runtime"]
    elif mutation == "mcp-launcher-runtime":
        contract["launchers"].pop("claude")
    elif mutation == "mcp-launcher-args":
        contract["launchers"]["codex"]["args"] = "./mir_mcp.py"
    else:
        contract["launchers"]["codex"]["env"] = {}


@pytest.mark.parametrize(
    "mutation",
    [
        "sha256", "path", "package_kind", "skill-sha256", "commit", "binding",
        "extra-plugin", "missing-plugin", "missing-mcp", "extra-metadata-key",
        "extra-mcp-key", "missing-mcp-key", "mcp-path", "mcp-files", "mcp-schema-source",
        "mcp-runtimes", "mcp-launcher-runtime", "mcp-launcher-args", "mcp-launcher-key",
    ],
)
def test_update_still_rejects_changed_enrollment_identity(tmp_path, provider, mutation):
    manager, lock, _ = enrolled_with_old_contract(tmp_path, provider)
    _mutate_enrollment(lock, mutation)
    manager.lock_path.write_text(json.dumps(lock))
    before = manager.lock_path.read_bytes()
    assert manager.update("code", mcp=True)["ready_to_apply"] is False
    with pytest.raises(CapabilityError, match="current consumer enrollment is invalid"):
        manager.update("code", mcp=True, apply=True)
    assert manager.lock_path.read_bytes() == before
