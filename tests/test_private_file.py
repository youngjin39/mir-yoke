"""Private capability state permissions on POSIX and Windows."""

from __future__ import annotations

import json
import os
import stat
import subprocess
import sys
from pathlib import Path

import pytest
from test_capability_cli import CopyGit, make_project, runtime_runner

from mir.core.capabilities import CapabilityError, CapabilityManager
from mir.core.capabilities import manager as capability_manager


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX mode bits")
@pytest.mark.parametrize("mode", [0o000, 0o400, 0o600, 0o640, 0o644, 0o666, 0o700])
def test_posix_is_private_requires_exact_mode(tmp_path: Path, mode: int) -> None:
    from mir.core.capabilities.private_file import is_private

    path = tmp_path / "state.json"
    path.touch()
    path.chmod(mode)
    assert is_private(path, path.stat()) is (mode == 0o600)


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX mode bits")
def test_posix_is_private_rejects_special_mode_bits(tmp_path: Path) -> None:
    from mir.core.capabilities.private_file import is_private

    path = tmp_path / "state.json"
    path.touch(mode=0o600)
    metadata = path.stat()
    metadata = os.stat_result((metadata.st_mode | stat.S_ISUID, *metadata[1:]))
    assert not is_private(path, metadata)


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX mode bits")
@pytest.mark.parametrize("mode", [0o400, 0o666, 0o700])
def test_posix_make_private_sets_mode_0600(tmp_path: Path, mode: int) -> None:
    from mir.core.capabilities.private_file import is_private, make_private

    path = tmp_path / "state.json"
    path.touch()
    path.chmod(mode)
    make_private(path)
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert is_private(path, path.stat())


def test_atomic_json_stays_private_after_replacement(tmp_path: Path) -> None:
    from mir.core.capabilities.private_file import is_private

    path = tmp_path / "state.json"
    for value in (1, 2):
        capability_manager._atomic_write_json(path, {"value": value})
        assert json.loads(path.read_text(encoding="utf-8")) == {"value": value}
        assert is_private(path, path.stat())


def test_apply_rollback_reapplies_private_state_permissions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    from mir.core.capabilities.private_file import is_private, make_private

    home = tmp_path / "provider"
    codex_home = tmp_path / "codex-home"
    manager = CapabilityManager(
        make_project(tmp_path), capability_home=home, user_home=tmp_path / "user",
        codex_home=codex_home, git=CopyGit(),
        command_runner=runtime_runner(home / "active", codex_home),
        which=lambda executable: f"/fake/{executable}",
    )
    manager.sync("code_app", apply=True)
    snapshots = {
        path: path.read_bytes()
        for path in (
            manager.lock_path, manager.registry_path, manager.consumer_bindings_path,
            manager.active_receipt_path,
        )
    }
    private_writes = []

    def record_private(path: Path) -> None:
        private_writes.append((path.parent, path.name, path.read_bytes()))
        make_private(path)

    def fail_derivatives(*, raise_on_error: bool = True) -> bool:
        if raise_on_error:
            raise CapabilityError("forced derivative failure")
        return True

    monkeypatch.setattr(capability_manager, "make_private", record_private)
    monkeypatch.setattr(manager, "_regenerate_agent_derivatives", fail_derivatives)
    with pytest.raises(CapabilityError, match="local rollback was complete"):
        manager.sync("content_workspace", apply=True)

    for path, body in snapshots.items():
        assert path.read_bytes() == body
        assert is_private(path, path.stat())
        assert any(
            parent == path.parent and name.startswith(f".{path.name}.") and written == body
            for parent, name, written in private_writes
        ), f"rollback did not make {path.name} private before replacement"
    assert manager.status()["provider_ready"] is True


@pytest.mark.parametrize("private", [False, True])
def test_load_consumer_bindings_delegates_to_is_private(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, private: bool,
) -> None:
    (tmp_path / "provider").mkdir()
    manager = CapabilityManager(
        make_project(tmp_path), user_home=tmp_path / "user", capability_home=tmp_path / "provider",
    )
    path = manager.consumer_bindings_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('{"schema_version": 1, "consumers": {}}\n', encoding="utf-8")
    # Deliberately disagree with POSIX mode bits: the helper decides privacy.
    path.chmod(0o644 if private else 0o600)
    seen = []

    def is_private(candidate: Path, metadata: os.stat_result) -> bool:
        assert candidate == path
        assert metadata == path.lstat()
        seen.append(candidate)
        return private

    monkeypatch.setattr(capability_manager, "is_private", is_private, raising=False)
    if private:
        assert manager._load_consumer_bindings() == {}
    else:
        with pytest.raises(CapabilityError, match="consumer binding ledger is invalid"):
            manager._load_consumer_bindings()
    assert seen == [path]


@pytest.mark.skipif(sys.platform != "win32", reason="Windows DACLs")
@pytest.mark.parametrize("mutation", ["everyone", "inheritance", "deny"])
def test_windows_private_dacl_rejects_unsafe_changes(tmp_path: Path, mutation: str) -> None:
    from mir.core.capabilities.private_file import is_private, make_private

    path = tmp_path / "private state.json"
    path.touch()
    make_private(path)
    assert is_private(path, path.stat())
    arguments = {
        "everyone": ["/grant", "*S-1-1-0:(R)"],
        "inheritance": ["/inheritancelevel:e"],
        "deny": ["/deny", "*S-1-5-18:(R)"],
    }[mutation]
    subprocess.run(["icacls", str(path), *arguments], check=True, capture_output=True)
    assert not is_private(path, path.stat())
    make_private(path)
    assert is_private(path, path.stat())


@pytest.mark.skipif(sys.platform != "win32", reason="Windows DACLs")
@pytest.mark.parametrize("sid", ["S-1-5-18", "S-1-5-32-544"])
def test_windows_private_dacl_allows_system_and_administrators(tmp_path: Path, sid: str) -> None:
    from mir.core.capabilities.private_file import is_private, make_private

    path = tmp_path / "state.json"
    path.touch()
    make_private(path)
    subprocess.run(
        ["icacls", str(path), "/grant", f"*{sid}:(F)"], check=True, capture_output=True,
    )
    assert is_private(path, path.stat())


@pytest.mark.skipif(sys.platform != "win32", reason="Windows API errors")
def test_windows_missing_file_fails_closed(tmp_path: Path) -> None:
    from mir.core.capabilities.private_file import is_private, make_private

    path = tmp_path / "missing.json"
    assert not is_private(path, tmp_path.stat())
    with pytest.raises(OSError):
        make_private(path)
