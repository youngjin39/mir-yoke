"""Pure Windows spelling rules and native handle-walk security boundaries."""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
from pathlib import Path, PureWindowsPath

import pytest

SERVER = Path(__file__).resolve().parents[1] / "plugins/mir-mcp/mir_mcp.py"
WINDOWS = pytest.mark.skipif(sys.platform != "win32", reason="Windows handle APIs required")


@pytest.fixture
def server():
    spec = importlib.util.spec_from_file_location("windows_mir_mcp", SERVER)
    module = importlib.util.module_from_spec(spec)
    exec(compile(SERVER.read_bytes(), str(SERVER), "exec"), module.__dict__)
    return module


@pytest.mark.parametrize("part", [
    ".env::$DATA", "a:b", "name.", "name ", "*", "a?b", 'a"b', "a<b", "a>b", "a|b",
    "CON", "con.txt", "NUL.txt", "AUX", "PRN.ext", "CONIN$", "conout$.txt",
    *[prefix + str(number) + extension for prefix in ("COM", "LPT")
      for number in range(10) for extension in ("", ".txt")],
])
def test_windows_components_refuse_ambiguous_names(server, part):
    with pytest.raises(server.Refusal, match="E_PATH"):
        server.windows_components(("safe", part))


@pytest.mark.parametrize("part", ["source.py", "A B", "com10", "lpt10.txt", "console", "SECRET~1"])
def test_windows_components_accept_unambiguous_names(server, part):
    server.windows_components(("safe", part))


@pytest.mark.parametrize("root", [
    r"\\server\share\repo", r"\\?\C:\repo", r"\\.\C:\repo", "//server/share/repo",
    r"C:repo", "C:", r"\repo", "repo", r"C:\repo\..\outside", r"C:\NUL.txt",
    r"C:\repo.\child", r"C:\repo:stream", r"C:\repo \child",
])
def test_windows_root_refuses_unsafe_spelling(server, root):
    with pytest.raises(server.Refusal, match="E_PATH"):
        server.windows_root(root)


@pytest.mark.parametrize("root", ["C:\\", r"C:\Users\A B\repo", "d:/work tree/repo"])
def test_windows_root_accepts_absolute_drive_with_spaces(server, root):
    server.windows_root(root)


def test_relative_path_selects_windows_rules_only_on_windows(server, monkeypatch):
    with monkeypatch.context() as patch:
        patch.setattr(server.sys, "platform", "win32")
        with pytest.raises(server.Refusal, match="E_PATH"):
            server.relative_path("safe/NUL.txt")
    if sys.platform != "win32":
        assert server.relative_path("safe/NUL.txt") == "safe/NUL.txt"


def test_windows_profile_globs_still_work_but_slots_refuse_them(server, monkeypatch):
    with monkeypatch.context() as patch:
        patch.setattr(server.sys, "platform", "win32")
        assert server.relative_path("private/**", pattern=True) == "private/**"
        assert server.relative_path("*.token", pattern=True) == "*.token"
        with pytest.raises(server.Refusal, match="E_PATH"):
            server.relative_path("private/**")


@WINDOWS
def test_windows_profile_globs_protect_reads(server, tmp_path):
    (tmp_path / ".mir").mkdir()
    (tmp_path / ".mir/repo-profile.toml").write_text('protected_paths=["private/**"]\n')
    (tmp_path / "private").mkdir()
    (tmp_path / "private/source.txt").write_bytes(b"DO_NOT_DISCLOSE_SENTINEL")
    guard = server.Guard(str(tmp_path))
    try:
        with pytest.raises(server.Refusal, match="E_PROTECTED"):
            guard.read("private/source.txt")
    finally:
        guard.close()


@WINDOWS
def test_windows_drive_root_with_spaces_reads_and_releases_ancestors(server, tmp_path):
    root = tmp_path / "work tree"
    (root / "sub").mkdir(parents=True)
    (root / "sub/source.txt").write_bytes(b"in-root\r\n\x1aunchanged")
    guard = server.Guard(str(root))
    try:
        assert guard.read("sub/source.txt") == b"in-root\r\n\x1aunchanged"
        # The read released its intermediate handle; only the pinned root stays held.
        (root / "sub").rename(root / "renamed")
    finally:
        guard.close()
    root.rename(tmp_path / "released root")


@WINDOWS
@pytest.mark.parametrize("path", [".env::$DATA", "NUL.txt", "name."])
def test_windows_unsafe_slot_is_refused_before_read(server, tmp_path, monkeypatch, path):
    guard = server.Guard(str(tmp_path))
    try:
        monkeypatch.setattr(server.os, "read", lambda *args: pytest.fail("must not read"))
        with pytest.raises(server.Refusal, match="E_PATH"):
            guard.read(path)
    finally:
        guard.close()


@WINDOWS
@pytest.mark.parametrize("root", [r"\\?\C:\repo", r"\\server\share\repo", r"\\.\C:\repo", "C:repo"])
def test_windows_namespace_root_refused_before_open(server, monkeypatch, root):
    monkeypatch.setattr(server, "windows_open", lambda *args: pytest.fail("must not open"))
    with pytest.raises(server.Refusal, match="E_PATH"):
        server.Guard(root)


@WINDOWS
def test_windows_root_resolving_to_unc_is_refused(server, tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "resolve", lambda *args, **kwargs: Path(r"\\server\share\repo"))
    monkeypatch.setattr(server, "windows_open", lambda *args: pytest.fail("must not open"))
    with pytest.raises(server.Refusal, match="E_PATH"):
        server.Guard(str(tmp_path))


@WINDOWS
@pytest.mark.parametrize("final", [
    r"\\?\UNC\server\share\source.txt", r"\\?\C:\elsewhere\source.txt",
])
def test_windows_final_path_mismatch_refuses_and_closes(server, tmp_path, monkeypatch, final):
    path = tmp_path / "source.txt"
    path.write_bytes(b"in-root")

    def final_path(handle, buffer, size, flags):
        assert flags == 0
        buffer.value = final
        return len(final)

    monkeypatch.setattr(server.kernel32, "GetFinalPathNameByHandleW", final_path)
    with pytest.raises(server.Refusal, match="E_PATH"):
        server.windows_open(path)
    path.unlink()  # Would fail if the rejected descriptor still held a non-delete share.


@WINDOWS
def test_windows_conversion_failure_closes_native_handle(server, tmp_path, monkeypatch):
    path = tmp_path / "source.txt"
    path.write_bytes(b"in-root")
    closed = []
    original = server.kernel32.CloseHandle

    def close(handle):
        closed.append(handle)
        return original(handle)

    def failed_conversion(*args):
        raise OSError("CRT descriptor conversion failed")

    monkeypatch.setattr(server.kernel32, "CloseHandle", close)
    monkeypatch.setattr(server.msvcrt, "open_osfhandle", failed_conversion)
    with pytest.raises(OSError, match="CRT descriptor conversion failed"):
        server.windows_open(path)
    assert len(closed) == 1
    path.unlink()


@WINDOWS
def test_windows_junction_outside_never_reads_outside_bytes(server, tmp_path, monkeypatch):
    root = tmp_path / "target"
    outside = tmp_path / "outside"
    root.mkdir()
    outside.mkdir()
    (outside / "source.txt").write_bytes(b"DO_NOT_DISCLOSE_SENTINEL")
    junction = root / "escape"
    result = subprocess.run(
        ["cmd.exe", "/c", "mklink", "/J", str(junction), str(outside)], capture_output=True
    )
    assert result.returncode == 0, result.stderr
    guard = server.Guard(str(root))
    try:
        monkeypatch.setattr(server.os, "read", lambda *args: pytest.fail("must not read"))
        with pytest.raises(server.Refusal, match="E_PATH"):
            guard.read("escape/source.txt")
    finally:
        guard.close()
        junction.rmdir()


@WINDOWS
def test_windows_short_name_final_path_is_protected(server, tmp_path, monkeypatch):
    root = tmp_path / "target"
    secret = root / "secret directory"
    secret.mkdir(parents=True)
    (root / ".mir").mkdir()
    (root / ".mir/repo-profile.toml").write_text('protected_paths=["secret directory/**"]\n')
    (secret / "source.txt").write_bytes(b"DO_NOT_DISCLOSE_SENTINEL")
    result = subprocess.run(
        ["cmd.exe", "/c", f'for %I in ("{secret}") do @echo %~sI'],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    alias = PureWindowsPath(result.stdout.strip()).name
    if "~" not in alias:
        pytest.skip("Windows volume must have 8.3 short-name generation enabled")
    assert alias.upper() == "SECRET~1"
    guard = server.Guard(str(root))
    original = Path.resolve

    def lexical_resolve(path, *args, **kwargs):
        # Model a spelling resolved before a rename; only the opened final path is proof.
        if alias in path.parts:
            return path
        return original(path, *args, **kwargs)

    try:
        monkeypatch.setattr(Path, "resolve", lexical_resolve)
        monkeypatch.setattr(server.os, "read", lambda *args: pytest.fail("must not read"))
        with pytest.raises(server.Refusal, match="E_PROTECTED"):
            guard.read(alias + "/source.txt")
    finally:
        guard.close()


@WINDOWS
def test_windows_ancestor_cannot_be_renamed_during_read(server, tmp_path, monkeypatch):
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub/source.txt").write_bytes(b"in-root")
    guard = server.Guard(str(tmp_path))
    original = os.read

    def read(handle, size):
        with pytest.raises(OSError):
            (tmp_path / "sub").rename(tmp_path / "moved")
        return original(handle, size)

    try:
        monkeypatch.setattr(server.os, "read", read)
        assert guard.read("sub/source.txt") == b"in-root"
    finally:
        guard.close()
    (tmp_path / "sub").rename(tmp_path / "moved")
