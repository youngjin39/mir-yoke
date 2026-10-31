"""Offline native artifact placement and exact tree verification regressions."""

import hashlib
import json

import pytest

DATA = b"fake native bytes\x00\xff"


def api():
    from mir.core.capabilities import native

    return native


def manifest(url="artifact"):
    return {
        "handoff-packet": {
            "plugin": "mir-lifecycle-hooks",
            "install_path": "bin/handoff-packet",
            "targets": {
                "aarch64-apple-darwin": {
                    "url": url,
                    "sha256": hashlib.sha256(DATA).hexdigest(),
                    "size": len(DATA),
                }
            },
        }
    }


@pytest.mark.parametrize(
    ("system", "machine", "expected"),
    [
        ("Darwin", "arm64", "aarch64-apple-darwin"),
        ("Darwin", "x86_64", "x86_64-apple-darwin"),
        ("Linux", "x86_64", "x86_64-unknown-linux-gnu"),
        ("Linux", "aarch64", "aarch64-unknown-linux-gnu"),
        ("Windows", "AMD64", "x86_64-pc-windows-msvc"),
        ("Windows", "ARM64", None),
        ("Other", "unknown", None),
    ],
)
def test_host_target(system, machine, expected):
    assert api().host_target(system, machine) == expected


@pytest.mark.parametrize("uri", [False, True])
@pytest.mark.parametrize("target", ["aarch64-apple-darwin", "x86_64-pc-windows-msvc"])
def test_placement(tmp_path, monkeypatch, uri, target):
    source = tmp_path / "source"
    source.write_bytes(DATA)
    records = manifest(source.as_uri() if uri else str(source))
    records["handoff-packet"]["targets"][target] = records["handoff-packet"]["targets"].pop(
        "aarch64-apple-darwin"
    )
    root = tmp_path / "plugin"
    root.mkdir()
    (root / "reference").write_bytes(b"python")
    monkeypatch.setenv("MIR_CAPABILITY_NATIVE_ARTIFACTS", "1")
    api().place_artifacts(root, "mir-lifecycle-hooks", records, target=target)
    path = root / ("bin/handoff-packet.exe" if "windows" in target else "bin/handoff-packet")
    assert path.read_bytes() == DATA
    assert path.stat().st_mode & 0o111
    with api().source_tree(root, "mir-lifecycle-hooks", records, target=target) as view:
        assert sorted(p.name for p in view.iterdir()) == ["reference"]
    path.write_bytes(b"tampered")
    with pytest.raises(ValueError, match="native artifact"):
        with api().source_tree(root, "mir-lifecycle-hooks", records, target=target):
            pass


@pytest.mark.parametrize("setting", [None, "0"])
def test_default_placement_and_explicit_opt_out(tmp_path, monkeypatch, setting):
    if setting is None:
        monkeypatch.delenv("MIR_CAPABILITY_NATIVE_ARTIFACTS", raising=False)
    else:
        monkeypatch.setenv("MIR_CAPABILITY_NATIVE_ARTIFACTS", setting)
    source = tmp_path / "source"
    source.write_bytes(DATA)
    records = manifest(str(source))
    root = tmp_path / "plugin"
    root.mkdir()
    (root / "reference").write_bytes(b"python")
    if setting == "0":
        def unexpected_read(*args):
            pytest.fail("opt-out must skip native artifact downloads")
        monkeypatch.setattr(api(), "_read", unexpected_read)
    api().place_artifacts(root, "mir-lifecycle-hooks", records, target="aarch64-apple-darwin")
    binary = root / "bin/handoff-packet"
    assert binary.exists() == (setting is None)
    if setting is None:
        assert binary.read_bytes() == DATA
    assert (root / "reference").read_bytes() == b"python"


@pytest.mark.parametrize("failure", ["digest", "size", "target", "source", "url"])
def test_failure_falls_back(tmp_path, monkeypatch, capsys, failure):
    source = tmp_path / "source"
    source.write_bytes(DATA)
    records = manifest(str(source))
    pin = records["handoff-packet"]["targets"]["aarch64-apple-darwin"]
    if failure == "digest":
        pin["sha256"] = "0" * 64
    elif failure == "size":
        pin["size"] -= 1
    elif failure == "target":
        records["handoff-packet"]["targets"] = {}
    elif failure == "url":
        # urlsplit accepts it; httpx raises InvalidURL, which is not an HTTPError.
        pin["url"] = "http://host:abc/artifact"
    else:
        source.unlink()
    root = tmp_path / "plugin"
    root.mkdir()
    (root / "reference").write_bytes(b"python")
    monkeypatch.delenv("MIR_CAPABILITY_NATIVE_ARTIFACTS", raising=False)
    api().place_artifacts(root, "mir-lifecycle-hooks", records, target="aarch64-apple-darwin")
    assert list(root.iterdir()) == [root / "reference"]
    assert capsys.readouterr().err.count("Warning: native artifact") == 1


@pytest.mark.parametrize(
    "path", ["/tmp/bin", "../bin", "bin/../x", "C:/bin", "bin\\x", "bin/x.exe"]
)
def test_unsafe_install_path(path):
    records = manifest()
    records["handoff-packet"]["install_path"] = path
    with pytest.raises(ValueError):
        api().validate_artifacts(records, {"mir-lifecycle-hooks"})


@pytest.mark.parametrize("url", ["/opt/fixture/bin", "file:///tmp/bin", "C:\\bin"])
def test_portable_lock_rejects_host_sources(url):
    with pytest.raises(ValueError):
        api().validate_artifacts(manifest(url), {"mir-lifecycle-hooks"}, portable=True)


def test_optional_section():
    assert api().validate_artifacts({}, {"mir-lifecycle-hooks"}) == {}
    assert json.dumps(api().validate_artifacts(manifest(), {"mir-lifecycle-hooks"}))


def test_tree_integrity(tmp_path, monkeypatch):
    from mir.core.capabilities.manager import _tree_digest

    root = tmp_path / "plugin"
    root.mkdir()
    (root / "reference").write_bytes(b"python")
    expected = _tree_digest(root)
    source = tmp_path / "source"
    source.write_bytes(DATA)
    records = manifest(str(source))
    monkeypatch.setenv("MIR_CAPABILITY_NATIVE_ARTIFACTS", "1")
    api().place_artifacts(root, "mir-lifecycle-hooks", records, target="aarch64-apple-darwin")
    with api().source_tree(
        root,
        "mir-lifecycle-hooks",
        records,
        target="aarch64-apple-darwin",
    ) as view:
        assert _tree_digest(view) == expected
    (root / "bin" / "extra").write_bytes(b"extra")
    with api().source_tree(
        root,
        "mir-lifecycle-hooks",
        records,
        target="aarch64-apple-darwin",
    ) as view:
        assert _tree_digest(view) != expected


@pytest.mark.parametrize("setting", [None, "0", "1"])
@pytest.mark.parametrize("target", ["aarch64-apple-darwin", "x86_64-pc-windows-msvc"])
def test_manager_materializes_and_verifies_artifacts(tmp_path, monkeypatch, setting, target):
    from test_capability_cli import CopyGit, make_project, runtime_runner

    from mir.core.capabilities import CapabilityManager

    monkeypatch.setattr(api(), "host_target", lambda: target)
    enabled = setting != "0"
    if setting is None:
        monkeypatch.delenv("MIR_CAPABILITY_NATIVE_ARTIFACTS", raising=False)
    else:
        monkeypatch.setenv("MIR_CAPABILITY_NATIVE_ARTIFACTS", setting)
    project = make_project(tmp_path)
    home, codex = tmp_path / "provider", tmp_path / "codex"
    manager = CapabilityManager(
        project,
        capability_home=home,
        user_home=tmp_path / "user",
        codex_home=codex,
        git=CopyGit(),
        command_runner=runtime_runner(home / "active", codex),
        which=lambda executable: f"/fake/{executable}",
    )
    manager.update(apply=True)
    before = {
        str(p.relative_to(manager.active_path)): p.read_bytes()
        for p in manager.active_path.rglob("*")
        if p.is_file()
    }
    source = tmp_path / "artifact"
    source.write_bytes(DATA)
    lock = json.loads(manager.lock_path.read_text())
    records = manifest(str(source))
    records["handoff-packet"]["targets"][target] = records["handoff-packet"]["targets"].pop(
        "aarch64-apple-darwin"
    )
    continuity_source = tmp_path / "continuity-artifact"
    continuity_data = DATA + b"-continuity"
    continuity_source.write_bytes(continuity_data)
    records["runtime-continuity"] = {
        "plugin": "mir-lifecycle-hooks", "install_path": "bin/runtime-continuity",
        "targets": {target: {
            "url": str(continuity_source),
            "sha256": hashlib.sha256(continuity_data).hexdigest(), "size": len(continuity_data),
        }},
    }
    lock["native_artifacts"] = records
    manager.lock_path.write_text(json.dumps(lock))
    manager.update(apply=True)
    lock = json.loads(manager.lock_path.read_text())
    assert lock["native_artifacts"] == records
    suffix = ".exe" if "windows" in target else ""
    binary = manager.active_path / f"plugins/mir-lifecycle-hooks/bin/handoff-packet{suffix}"
    assert binary.exists() == enabled
    continuity = binary.with_name("runtime-continuity" + suffix)
    assert continuity.exists() == enabled
    if enabled:
        assert binary.read_bytes() == DATA
        assert continuity.read_bytes() == continuity_data
    if not enabled:
        assert not binary.parent.exists()
        assert before == {
            str(p.relative_to(manager.active_path)): p.read_bytes()
            for p in manager.active_path.rglob("*")
            if p.is_file()
        }
    assert manager._active_integrity(lock, tuple(lock["plugins"]))
    receipt = json.loads(manager.active_receipt_path.read_text())
    assert manager._provider_active_integrity(receipt)
    if enabled:
        legacy_consumer = {key: value for key, value in lock.items() if key != "native_artifacts"}
        assert manager._active_integrity(legacy_consumer, tuple(lock["plugins"]))
        binary.write_bytes(b"tampered")
        assert not manager._active_integrity(lock, tuple(lock["plugins"]))
        assert not manager._provider_active_integrity(receipt)
        binary.write_bytes(DATA)
        extra = binary.parent / "extra"
        extra.write_bytes(b"extra")
        assert not manager._active_integrity(lock, tuple(lock["plugins"]))
    assert before


def test_bootstrap_rejects_invalid_native_section(tmp_path):
    from mir.cli.bootstrap import _capability_lock_evidence

    directory = tmp_path / ".mir"
    directory.mkdir()
    (directory / "capability-lock.json").write_text(
        json.dumps(
            {
                "source": {"commit": "a" * 40},
                "plugins": {"mir-lifecycle-hooks": {}},
                "native_artifacts": [],
            }
        )
    )
    assert _capability_lock_evidence(tmp_path)[0] == "failed"


def test_linked_native_root_rejected(tmp_path, monkeypatch):
    root = tmp_path / "root"
    root.mkdir()
    source = tmp_path / "artifact"
    source.write_bytes(DATA)
    records = manifest(str(source))
    monkeypatch.setenv("MIR_CAPABILITY_NATIVE_ARTIFACTS", "1")
    api().place_artifacts(root, "mir-lifecycle-hooks", records, target="aarch64-apple-darwin")
    linked = tmp_path / "linked"
    linked.symlink_to(root, target_is_directory=True)
    with pytest.raises(ValueError, match="linked"):
        with api().source_tree(
            linked, "mir-lifecycle-hooks", records, target="aarch64-apple-darwin"
        ):
            pass
