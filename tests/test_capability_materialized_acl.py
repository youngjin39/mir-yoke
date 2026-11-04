"""Published capability trees inherit destination permissions, never staging ACLs."""
from __future__ import annotations

import ctypes
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from test_capability_cli import CopyGit, make_project, runtime_runner

from mir.core.capabilities import CapabilityError, CapabilityManager, manager, private_file


@pytest.mark.parametrize("error", [0, 5])
def test_inherit_parent_uses_empty_unprotected_dacl_and_frees_descriptor(error):
    calls = []

    def convert(sddl, revision, descriptor, size):
        assert sddl == "D:"
        descriptor._obj.value = 123
        return True

    def get_dacl(descriptor, present, dacl, defaulted):
        present._obj.value = True
        dacl._obj.value = 456
        return True

    def set_info(*args):
        calls.append(args)
        return error

    security = object.__new__(private_file._WindowsSecurity)
    security.advapi = SimpleNamespace(
        ConvertStringSecurityDescriptorToSecurityDescriptorW=convert,
        GetSecurityDescriptorDacl=get_dacl, SetNamedSecurityInfoW=set_info,
    )
    freed = []
    security.kernel = SimpleNamespace(LocalFree=lambda pointer: freed.append(pointer.value) or 0)
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(
            ctypes, "WinError", lambda code: OSError(code, "Windows error"), raising=False,
        )
        if error:
            with pytest.raises(OSError):
                security.inherit_parent(Path("published"))
        else:
            security.inherit_parent(Path("published"))
    assert calls[0][0:3] == ("published", 1, 0x20000004)
    assert calls[0][3:5] == (None, None)  # owner/group unchanged
    assert calls[0][5].value == 456  # empty ACL, never a NULL DACL
    assert freed == [123]


def test_tree_repair_visits_parents_before_children(tmp_path, monkeypatch):
    root = tmp_path / "active"
    (root / "plugin").mkdir(parents=True)
    (root / "plugin/file").touch()
    seen = []
    monkeypatch.setattr(private_file, "sys", SimpleNamespace(platform="win32"))
    monkeypatch.setattr(private_file, "_WindowsSecurity", lambda: SimpleNamespace(
        inherit_parent=lambda path: seen.append(path)))
    private_file.make_tree_inherit_parent(root)
    assert set(seen) == {root, root / "plugin", root / "plugin/file"}
    assert seen.index(root) < seen.index(root / "plugin") < seen.index(root / "plugin/file")


def test_tree_repair_is_posix_noop(tmp_path, monkeypatch):
    monkeypatch.setattr(private_file, "sys", SimpleNamespace(platform="linux"))
    monkeypatch.setattr(
        private_file, "_WindowsSecurity", lambda: pytest.fail("Windows API on POSIX"),
    )
    private_file.make_tree_inherit_parent(tmp_path)


@pytest.mark.parametrize("operation", ["sync", "update"])
def test_apply_repairs_published_tree_on_initial_and_existing_sync(
    tmp_path, monkeypatch, operation,
):
    home = tmp_path / "provider"
    codex = tmp_path / "codex"
    instance = CapabilityManager(
        make_project(tmp_path), capability_home=home, user_home=tmp_path / "user",
        codex_home=codex, git=CopyGit(), command_runner=runtime_runner(home / "active", codex),
        which=lambda executable: f"/fake/{executable}",
    )
    seen = []

    def repair(path):
        assert path == instance.active_path
        assert (path / ".agents/plugins/marketplace.json").is_file()
        seen.append(path)

    monkeypatch.setattr(manager, "make_tree_inherit_parent", repair, raising=False)
    instance.sync("code_app", apply=True)
    getattr(instance, operation)("code_app", apply=True)
    assert seen == [instance.active_path, instance.active_path]


def test_acl_repair_failure_rolls_back_publication(tmp_path, monkeypatch):
    home = tmp_path / "provider"
    codex = tmp_path / "codex"
    instance = CapabilityManager(
        make_project(tmp_path), capability_home=home, user_home=tmp_path / "user",
        codex_home=codex, git=CopyGit(), command_runner=runtime_runner(home / "active", codex),
        which=lambda executable: f"/fake/{executable}",
    )
    instance.sync("code_app", apply=True)
    receipt = instance.active_receipt_path.read_bytes()
    marker = instance.active_path / "previous-tree"
    marker.touch()

    def fail(path):
        raise OSError("ACL repair denied")

    monkeypatch.setattr(manager, "make_tree_inherit_parent", fail)
    with pytest.raises(CapabilityError, match="local rollback was complete"):
        instance.sync("code_app", apply=True)
    assert marker.is_file()
    assert instance.active_receipt_path.read_bytes() == receipt
    assert not (home / ".active.previous").exists()


@pytest.mark.skipif(sys.platform != "win32", reason="Windows DACL integration")
def test_windows_published_tree_replaces_elevated_like_staging_acl(tmp_path):
    import tempfile

    destination = tmp_path / "capabilities"
    destination.mkdir()
    security = private_file._WindowsSecurity()
    user = security.current_user()
    subprocess.run(["icacls", str(destination), "/grant", f"*{user}:(OI)(CI)(F)"],
                   check=True, capture_output=True)
    with tempfile.TemporaryDirectory(dir=tmp_path) as stage:
        root = Path(stage) / "active"
        (root / "plugin").mkdir(parents=True)
        (root / "plugin/manifest.json").write_text("{}")
        # Match the protected temp ACL even on a CI runner without an elevated token.
        subprocess.run(["icacls", str(root), "/inheritance:r", "/grant:r",
                        "*S-1-3-4:(OI)(CI)(F)", "*S-1-5-18:(OI)(CI)(F)",
                        "*S-1-5-32-544:(OI)(CI)(F)", "/T"], check=True, capture_output=True)
        active = destination / "active"
        os.replace(root, active)
        private_file.make_tree_inherit_parent(active)
        for path in [active, active / "plugin", active / "plugin/manifest.json"]:
            script = ("$a=Get-Acl -LiteralPath $env:MIR_TEST_ACL_PATH; "
                      "if($a.AreAccessRulesProtected){exit 2}; "
                      "$r=@($a.Access | Where-Object { $_.IsInherited -and "
                      "$_.IdentityReference.Translate("
                      f"[System.Security.Principal.SecurityIdentifier]).Value -eq '{user}'"
                      "}); if(!$r.Count){exit 3}")
            result = subprocess.run(["powershell", "-NoProfile", "-Command", script],
                                    env={**os.environ, "MIR_TEST_ACL_PATH": str(path)},
                                    capture_output=True, text=True)
            assert result.returncode == 0, result.stderr
